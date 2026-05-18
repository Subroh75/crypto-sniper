"""
CEX Hourly/Daily Scanner
─────────────────────────
Fires every hour via JobQueue.

  22:00 UTC (8 AM AEST)  →  1D candle scan   — daily overview, strong trend filter
  Every other hour       →  1H candle scan   — intraday signals, fresher momentum

Both use the same VPRT scoring engine (score ≥ 9/13 = STRONG BUY).
When nothing hits 9+, falls through to a watch report (5–8/13 near-misses).
"""
import os
import asyncio
import logging
import aiohttp
from datetime import datetime, timezone

from signal_tracker import record_signal

logger = logging.getLogger(__name__)

API_BASE   = os.environ.get("RENDER_API_URL", "https://crypto-sniper.onrender.com")
ADMIN_CHAT = int(os.environ.get("ADMIN_CHAT_ID", "5861457546"))
MIN_SCORE       = int(os.environ.get("SCANNER_MIN_SCORE", "9"))
WATCH_MIN_SCORE = 5        # near-miss threshold for watch report
TOP_N           = int(os.environ.get("SCANNER_TOP_N", "10"))
DAILY_HOUR_UTC  = 22       # 8 AM AEST — fires 1D scan at this UTC hour

BINANCE_TICKER = "https://data-api.binance.vision/api/v3/ticker/24hr"
MEXC_TICKER    = "https://api.mexc.com/api/v3/ticker/24hr"
GATE_TICKER    = "https://api.gateio.ws/api/v4/spot/tickers"
STABLECOINS = {
    "USDT","USDC","BUSD","DAI","TUSD","USDP","USDD","GUSD","FRAX","LUSD",
    "FDUSD","PYUSD","STETH","WBTC","WETH","WBETH","EZETH","WEETH","SUSDE","USDE"
}
LEVERAGED_SUFFIXES = {"3L","3S","5L","5S","2L","2S","UP","DOWN","BULL","BEAR"}
MIN_VOLUME_USD     = 500_000
MIN_VOLUME_USD_ALT = 500_000   # MEXC + Gate threshold
# Exchange -> label color prefix for Telegram (text only, no HTML)
_EXCH_PREFIX = {"mexc": "[MEXC] ", "gate": "[GATE] ", "multi": "[MULTI] "}


# ─────────────────────────────────────────────
#  Universe fetch — Binance + MEXC + Gate.io
# ─────────────────────────────────────────────

# Per-symbol exchange lookup cache (populated by _get_top_symbols)
_symbol_exchange_map: dict[str, str] = {}

# Vol baseline cache — stores last ticker snapshot {symbol: vol_24h}
# Updated every cycle; used to detect intra-hour vol spikes
_ticker_vol_baseline: dict[str, float] = {}


async def _wake_api(timeout: int = 60) -> bool:
    """
    Ping /health and wait up to `timeout` seconds for Render to wake.
    Render Standard plan sleeps after ~15min inactivity and takes 30-60s to cold-start.
    Returns True if API is up, False if it timed out.
    """
    deadline = time.time() + timeout
    async with aiohttp.ClientSession() as session:
        while time.time() < deadline:
            try:
                async with session.get(
                    f"{API_BASE}/health",
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
            await asyncio.sleep(5)
    logger.warning("[Scanner] API wake timed out after %ds", timeout)
    return False


async def _fetch_binance_coins(session: aiohttp.ClientSession) -> list[tuple[str, float]]:
    """Returns [(symbol, vol_usd), ...] from Binance 24hr ticker."""
    try:
        async with session.get(BINANCE_TICKER, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            tickers = await r.json()
        coins = []
        for t in tickers:
            pair = t.get("symbol", "")
            if not pair.endswith("USDT"):
                continue
            sym = pair[:-4]
            if sym in STABLECOINS:
                continue
            vol = float(t.get("quoteVolume", 0))
            if vol < MIN_VOLUME_USD:
                continue
            coins.append((sym, vol))
        return coins
    except Exception as e:
        logger.warning(f"[Scanner] Binance ticker failed: {e}")
        return []


async def _fetch_mexc_coins(session: aiohttp.ClientSession) -> list[tuple[str, float]]:
    """Returns [(symbol, vol_usd), ...] from MEXC 24hr ticker."""
    try:
        async with session.get(MEXC_TICKER, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            tickers = await r.json()
        coins = []
        for t in tickers:
            pair = t.get("symbol", "")
            if not pair.endswith("USDT"):
                continue
            sym = pair[:-4]
            if sym in STABLECOINS:
                continue
            # Skip leveraged tokens
            if any(sym.endswith(s) for s in LEVERAGED_SUFFIXES):
                continue
            vol = float(t.get("quoteVolume", 0) or 0)
            if vol < MIN_VOLUME_USD_ALT:
                continue
            coins.append((sym, vol))
        return coins
    except Exception as e:
        logger.warning(f"[Scanner] MEXC ticker failed: {e}")
        return []


async def _fetch_gate_coins(session: aiohttp.ClientSession) -> list[tuple[str, float]]:
    """Returns [(symbol, vol_usd), ...] from Gate.io spot tickers."""
    try:
        async with session.get(GATE_TICKER, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            tickers = await r.json()
        coins = []
        for t in tickers:
            pair = t.get("currency_pair", "")
            if not pair.endswith("_USDT"):
                continue
            sym = pair[:-5]  # strip _USDT
            if sym in STABLECOINS:
                continue
            if any(sym.endswith(s) for s in LEVERAGED_SUFFIXES):
                continue
            vol = float(t.get("quote_volume", 0) or 0)
            if vol < MIN_VOLUME_USD_ALT:
                continue
            coins.append((sym, vol))
        return coins
    except Exception as e:
        logger.warning(f"[Scanner] Gate ticker failed: {e}")
        return []


async def _get_top_symbols(n: int = 200) -> tuple[list[str], dict[str, float]]:
    """Fetch multi-exchange universe.
    Returns (symbol_list, vol_map) where vol_map = {symbol: vol_24h_usd}.
    """
    async with aiohttp.ClientSession() as session:
        bnc, mexc, gate = await asyncio.gather(
            _fetch_binance_coins(session),
            _fetch_mexc_coins(session),
            _fetch_gate_coins(session),
            return_exceptions=True,
        )

    bnc  = bnc  if isinstance(bnc,  list) else []
    mexc = mexc if isinstance(mexc, list) else []
    gate = gate if isinstance(gate, list) else []

    # Build dedup map: highest vol wins; track exchange source
    seen: dict[str, tuple[float, str]] = {}
    for sym, vol in bnc:
        seen[sym] = (vol, "binance")
    for sym, vol in mexc:
        if sym not in seen:
            seen[sym] = (vol, "mexc")
        elif vol > seen[sym][0]:
            seen[sym] = (vol, "mexc")
    for sym, vol in gate:
        if sym not in seen:
            seen[sym] = (vol, "gate")
        elif vol > seen[sym][0]:
            seen[sym] = (vol, "gate")

    # Persist exchange map for use in _coin_block
    global _symbol_exchange_map
    _symbol_exchange_map = {sym: exch for sym, (_, exch) in seen.items()}

    merged = sorted(seen.items(), key=lambda x: x[1][0], reverse=True)
    symbols = [sym for sym, _ in merged[:n]]
    vol_map  = {sym: seen[sym][0] for sym in symbols}

    bnc_n    = sum(1 for sym in symbols if _symbol_exchange_map.get(sym) == "binance")
    mexc_n   = sum(1 for sym in symbols if _symbol_exchange_map.get(sym) == "mexc")
    gate_n   = sum(1 for sym in symbols if _symbol_exchange_map.get(sym) == "gate")
    logger.info(f"[Scanner] Multi-exchange universe: {len(symbols)} symbols "
                f"(Binance={bnc_n}, MEXC={mexc_n}, Gate={gate_n})")
    return symbols, vol_map


# ─────────────────────────────────────────────
#  Single symbol scorer
# ─────────────────────────────────────────────

async def _analyse_symbol(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str,
    min_score: int = WATCH_MIN_SCORE,
) -> dict | None:
    try:
        async with session.post(
            f"{API_BASE}/analyse",
            json={"symbol": symbol, "interval": interval},
            timeout=aiohttp.ClientTimeout(total=35)
        ) as r:
            if r.status != 200:
                return None
            data  = await r.json()
            score = data.get("signal", {}).get("total", 0)
            if score >= min_score:
                return data
    except Exception as e:
        logger.debug(f"Analyse error {symbol} ({interval}): {e}")
    return None


# ─────────────────────────────────────────────
#  Parallel scan runner
# ─────────────────────────────────────────────

async def _run_scan(
    symbols: list[str],
    interval: str,
    min_score: int = WATCH_MIN_SCORE,
    concurrency: int = 5,
) -> tuple[list[dict], int]:
    """Score all symbols in parallel. Returns (hits_sorted_desc, error_count)."""
    hits   = []
    errors = 0
    sem    = asyncio.Semaphore(concurrency)

    async def bounded(session, sym):
        async with sem:
            result = await _analyse_symbol(session, sym, interval=interval, min_score=min_score)
            await asyncio.sleep(0.15)
            return result

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[bounded(session, sym) for sym in symbols],
            return_exceptions=True
        )

    for res in results:
        if isinstance(res, Exception):
            errors += 1
        elif res is not None:
            hits.append(res)

    hits.sort(key=lambda x: x.get("signal", {}).get("total", 0), reverse=True)
    return hits, errors


# ─────────────────────────────────────────────
#  Kronos enrichment
# ─────────────────────────────────────────────

async def _fetch_kronos(
    session: aiohttp.ClientSession,
    symbol: str,
    analyse_data: dict,
) -> dict:
    try:
        sig    = analyse_data.get("signal", {})
        struct = analyse_data.get("structure", {})
        timing = analyse_data.get("timing", {})
        quote  = analyse_data.get("quote", {})
        ctx = {
            "total":      sig.get("total", 0),
            "direction":  sig.get("direction", "NEUTRAL"),
            "close":      struct.get("close") or quote.get("price") or 0,
            "rsi":        timing.get("rsi") or 0,
            "adx":        timing.get("adx") or 0,
            "change_24h": quote.get("change_24h") or 0,
            "rel_volume": timing.get("rel_volume") or 0,
        }
        async with session.post(
            f"{API_BASE}/kronos",
            json={"symbol": symbol, "signal_ctx": ctx},
            timeout=aiohttp.ClientTimeout(total=30)
        ) as r:
            if r.status == 200:
                return (await r.json()).get("forecast", {})
    except Exception as e:
        logger.debug(f"Kronos error {symbol}: {e}")
    return {}


# ─────────────────────────────────────────────
#  Telegram helpers
# ─────────────────────────────────────────────

async def _send(bot, chat_id: int, msg: str) -> None:
    if len(msg) <= 4096:
        await bot.send_message(chat_id=chat_id, text=msg)
    else:
        for chunk in [msg[i:i+4096] for i in range(0, len(msg), 4096)]:
            await bot.send_message(chat_id=chat_id, text=chunk)


# ─────────────────────────────────────────────
#  Message formatters
# ─────────────────────────────────────────────

def _vol_label(rv: float) -> str:
    """Convert rel_volume float to qualitative label — never expose the multiplier."""
    if rv >= 3.5:  return "Extreme"
    if rv >= 2.5:  return "High"
    if rv >= 1.8:  return "Elevated"
    return "Normal"


def _gate_line(comp: dict, timing: dict) -> str:
    """Traffic-light gate status — VOL / TREND / ADX. No numbers exposed."""
    v_ok   = comp.get("V", {}).get("confirmed", False)
    t_ok   = comp.get("T", {}).get("confirmed", False)
    adx    = timing.get("adx") or 0
    adx_ok = adx >= 25
    vol_lbl = _vol_label(timing.get("rel_volume") or 0)
    adx_lbl = "Trending" if adx_ok else "Ranging"
    def dot(ok): return "[OK]" if ok else "[ ]"
    return f"VOL {dot(v_ok)} {vol_lbl}   TREND {dot(t_ok)}   ADX {dot(adx_ok)} {adx_lbl}"


def _coin_block(data: dict, rank: int, interval: str) -> str:
    """Single-coin block — signal tier + gates only. No raw scores exposed."""
    sig    = data.get("signal", {})
    label  = sig.get("label", "")
    symbol = data.get("symbol", "?")
    struct = data.get("structure", {})
    timing = data.get("timing", {})
    quote  = data.get("quote", {})
    comp   = data.get("components", {})
    trade  = data.get("trade_setup") or {}
    kronos = data.get("kronos") or {}

    close = struct.get("close") or quote.get("price") or 0
    chg   = quote.get("change_24h") or 0

    tf_label = interval.upper()

    # Exchange source prefix (only for non-Binance coins)
    exch       = _symbol_exchange_map.get(symbol, "binance")
    exch_tag   = "" if exch == "binance" else f" [{exch.upper()}]"

    block  = f"\n#{rank}  {symbol}/USDT{exch_tag}"
    block += f"\nSignal:  {label} ({tf_label})"
    block += f"\nPrice:   ${close:.6g}  ({chg:+.2f}% 24h)"
    block += f"\n{_gate_line(comp, timing)}\n"

    if trade and trade.get("entry") and trade.get("stop") and trade.get("target"):
        rr = trade.get("rr_ratio")
        block += f"Setup:   E {trade['entry']:.6g}  SL {trade['stop']:.6g}  TP {trade['target']:.6g}"
        if rr:
            block += f"  R:R {rr:.2f}"
        block += "\n"

    # Entry quality — label only, no sigma numbers
    z_quality = timing.get("z_quality") or ""
    z_return  = timing.get("z_return")
    if z_quality and z_quality not in ("UNKNOWN", ""):
        q_icon = {"IDEAL": "[OK]", "GOOD": "[OK]", "CAUTION": "[!!]", "AVOID": "[X]"}.get(z_quality, "[ ]")
        block += f"Entry:   {q_icon} {z_quality}"
        if z_return is not None and z_return > 2.5:
            block += "  — price extended, consider sizing down"
        elif z_return is not None and z_return < -2.0:
            block += "  — oversold zone, watch for reversal"
        block += "\n"

    if kronos:
        kdir  = kronos.get("direction", "")
        kmove = kronos.get("expected_move_pct", 0)
        kq    = kronos.get("trade_quality", "")
        kbull = kronos.get("bull_conviction", 0)
        kbear = kronos.get("bear_conviction", 0)
        block += (
            f"Kronos:  {kdir}  {kmove:+.2f}%  |  "
            f"Bull {kbull:.0f}% / Bear {kbear:.0f}%  |  {kq}\n"
        )

    return block


# ─────────────────────────────────────────────
#  Vol-first scan helper + formatter
# ─────────────────────────────────────────────

VOL_GATE = 1.8  # minimum rel_volume to appear in vol scan

async def _vol_scan(
    symbols: list[str],
    interval: str = "1d",
    concurrency: int = 5,
) -> tuple[list[dict], int]:
    """
    Score all symbols, return every coin with rel_vol >= VOL_GATE.
    Unlike _run_scan, no min_score filter — we want even low-scoring
    high-volume coins so traders can see what's building.
    """
    hits   = []
    errors = 0
    sem    = asyncio.Semaphore(concurrency)

    async def bounded(session, sym):
        async with sem:
            try:
                async with session.post(
                    f"{API_BASE}/analyse",
                    json={"symbol": sym, "interval": interval},
                    timeout=aiohttp.ClientTimeout(total=25)
                ) as r:
                    if r.status != 200:
                        return None
                    return await r.json()
            except Exception as e:
                logger.debug(f"[VolScan] {sym}: {e}")
                return None
            finally:
                await asyncio.sleep(0.15)

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[bounded(session, sym) for sym in symbols],
            return_exceptions=True
        )

    for res in results:
        if isinstance(res, Exception):
            errors += 1
        elif res is not None:
            timing = res.get("timing", {})
            rv = timing.get("rel_volume") or 0
            if rv >= VOL_GATE:
                hits.append(res)

    # Sort by rel_volume descending — highest spike first
    hits.sort(key=lambda x: x.get("timing", {}).get("rel_volume") or 0, reverse=True)
    return hits, errors


def _format_vol_report(hits: list[dict], interval: str, scan_time: str, source: str = "CEX") -> str:
    """
    Vol-first report — shows every coin clearing the 1.8x gate
    with traffic-light gate status and what's missing before a signal fires.
    Used for: daily watch report (when no STRONG BUY) + /volscan command.
    """
    tf     = interval.upper()
    strong = [h for h in hits if h.get("signal", {}).get("total", 0) >= MIN_SCORE]

    header = (
        f"CRYPTO SNIPER  —  VOL SCAN ({source})\n"
        f"{scan_time}  |  {tf}  |  Vol >= 1.8x\n"
        "──────────────────────────────────\n"
        f"Unusual volume: {len(hits)} coins\n"
        f"STRONG BUY signals: {len(strong)}\n"
    )

    if not hits:
        return (
            header +
            "\nNo coins with vol >= 1.8x right now.\n"
            "Market is quiet — volume not confirming any move.\n" +
            "─" * 34 + "\n"
            "https://crypto-sniper.app"
        )

    blocks = []
    for i, data in enumerate(hits, 1):
        sig    = data.get("signal", {})
        timing = data.get("timing", {})
        quote  = data.get("quote", {})
        struct = data.get("structure", {})
        comp   = data.get("components", {})
        trade  = data.get("trade_setup") or {}

        label  = sig.get("label", "")
        score  = sig.get("total", 0)
        rv     = timing.get("rel_volume") or 0
        adx    = timing.get("adx") or 0
        close  = quote.get("price") or struct.get("close") or 0
        chg    = quote.get("change_24h") or 0
        symbol = data.get("symbol", "?")

        v_conf   = comp.get("V", {}).get("confirmed", False)
        t_conf   = comp.get("T", {}).get("confirmed", False)
        adx_conf = adx >= 25

        vol_lbl = _vol_label(rv)
        adx_lbl = "Trending" if adx_conf else "Ranging"

        def dot(ok): return "[OK]" if ok else "[ ]"

        block  = f"\n#{i}  {symbol}/USDT"
        if label in ("STRONG BUY", "BUY"):
            block += f"  —  {label}"
        block += f"\nPrice:  ${close:.6g}  ({chg:+.1f}% 24h)"
        block += f"\nVOL {dot(v_conf)} {vol_lbl} {rv:.1f}x   TREND {dot(t_conf)}   ADX {dot(adx_conf)} {adx:.0f} {adx_lbl}"

        missing = []
        if not t_conf:    missing.append("EMA stack not aligned")
        if not adx_conf:  missing.append(f"ADX {adx:.0f} — needs 25+")
        if missing:
            block += "\nNeeds: " + " / ".join(missing)
        elif v_conf and t_conf and adx_conf:
            block += f"\nAll gates met"
            if trade and trade.get("entry") and trade.get("stop") and trade.get("target"):
                rr = trade.get("rr_ratio")
                entry  = trade.get("entry")
                stop   = trade.get("stop")
                target = trade.get("target")
                block += f"\nSetup:  E {entry:.6g}  SL {stop:.6g}  TP {target:.6g}" 
                if rr:
                    block += f"  R:R {rr:.2f}"

        block += "\n"
        blocks.append(block)

    footer = (
        "\n──────────────────────────────────\n"
        "Volume is present — waiting for Trend + ADX.\n"
        "https://crypto-sniper.app"
    ) if not strong else (
        "\n──────────────────────────────────\n"
        f"{len(strong)} signal(s) fired — full report above.\n"
        "https://crypto-sniper.app"
    )

    return header + "".join(blocks) + footer


def _format_signal_message(hits: list[dict], interval: str, scan_time: str) -> str:
    """Standard STRONG BUY alert — used for both 1D and 1H scans."""
    tf     = interval.upper()
    prefix = "DAILY" if interval == "1d" else "HOURLY"
    header = (
        f"CRYPTO SNIPER  —  {prefix} SCAN\n"
        f"{scan_time}  |  {tf}\n"
        "──────────────────────────────────\n"
        f"STRONG BUY signals: {len(hits)}\n"
    )
    blocks = [_coin_block(d, i, interval) for i, d in enumerate(hits, 1)]
    footer = (
        "\n──────────────────────────────────\n"
        "https://crypto-sniper.app\n"
        "Not financial advice."
    )
    return header + "".join(blocks) + footer


def _format_watch_message(watch: list[dict], interval: str, scan_time: str) -> str:
    """Near-miss watch report — no scores exposed, gate status only."""
    tf     = interval.upper()
    header = (
        f"CRYPTO SNIPER  —  NO TRADES ({tf})\n"
        f"{scan_time}  |  {tf}\n"
        "──────────────────────────────────\n"
        f"No signal yet — market conditions not confirmed\n"
        f"Coins building momentum:\n"
    )
    blocks = []
    for i, data in enumerate(watch, 1):
        symbol = data.get("symbol", "?")
        struct = data.get("structure", {})
        timing = data.get("timing", {})
        quote  = data.get("quote", {})
        comp   = data.get("components", {})

        close = struct.get("close") or quote.get("price") or 0
        chg   = quote.get("change_24h") or 0

        block  = f"\n#{i}  {symbol}/USDT\n"
        block += f"Price: ${close:.6g}  ({chg:+.2f}%)\n"
        block += f"{_gate_line(comp, timing)}\n"
        blocks.append(block)

    footer = (
        "\n──────────────────────────────────\n"
        "Watching for volume + trend confirmation.\n"
        "https://crypto-sniper.app"
    )
    return header + "".join(blocks) + footer


# ─────────────────────────────────────────────
#  Main job — called by JobQueue every hour
# ─────────────────────────────────────────────

async def hourly_scan_job(context) -> None:
    """
    JobQueue callback — fires every hour but only acts at 22:00 UTC (8 AM AEST).

    All other hours: silent no-op.
    1H intraday scans removed — too many false positives and noisy loss outcomes.
    """
    now_utc = datetime.now(timezone.utc)

    # Only run at 22:00 UTC — all other hours are silent
    if now_utc.hour != DAILY_HOUR_UTC:
        logger.debug(f"[Scanner] Skipping non-daily hour {now_utc.hour}:00 UTC — daily-only mode")
        return

    bot       = context.bot
    scan_time = now_utc.strftime("%d %b %Y %H:%M UTC")

    # Always daily mode
    is_daily = True
    interval = "1d"
    mode     = "DAILY (1D)"

    logger.info(f"[Scanner] Starting {mode} scan — {scan_time}")

    # 1. Wake API — wait up to 65s for Render cold start
    api_up = await _wake_api(timeout=65)
    if not api_up:
        logger.warning("[Scanner] API did not wake — aborting daily scan")
        await _send(bot, ADMIN_CHAT, "⚠️ Crypto Sniper: API did not respond — daily scan skipped. Check Render dashboard.")
        return
    logger.info("[Scanner] API awake — proceeding with scan")

    # 2. Fetch universe
    symbols, _ = await _get_top_symbols(200)
    if not symbols:
        logger.warning("[Scanner] No symbols returned — aborting")
        return

    # 3. Score on the correct interval
    hits, errors = await _run_scan(symbols, interval=interval, min_score=WATCH_MIN_SCORE)

    strong = [h for h in hits if h.get("signal", {}).get("total", 0) >= MIN_SCORE]
    top    = strong[:TOP_N]

    logger.info(f"[Scanner] {mode}: {len(top)} STRONG BUY, {errors} errors")

    # 4. Vol scan — runs regardless so watch report always has content
    vol_hits, vol_errors = await _vol_scan(symbols, interval=interval)
    logger.info(f"[Scanner] Vol screen: {len(vol_hits)} coins >= 1.8x")

    # Stay silent only if no STRONG BUY and no vol hits at all
    if not top and not vol_hits:
        logger.info("[Scanner] No STRONG BUY and no vol hits — staying silent")
        return

    # 5. Enrich STRONG BUY hits with Kronos (best-effort, 1D only — saves API calls on 1H)
    if top and is_daily:
        async with aiohttp.ClientSession() as kron_session:
            kronos_results = await asyncio.gather(
                *[_fetch_kronos(kron_session, d.get("symbol", ""), d) for d in top],
                return_exceptions=True
            )
        for coin_data, kron in zip(top, kronos_results):
            coin_data["kronos"] = kron if isinstance(kron, dict) and kron else {}

    # 6. Send
    if top:
        msg = _format_signal_message(top, interval, scan_time)
    else:
        msg = _format_vol_report(vol_hits, interval, scan_time, source="CEX")

    try:
        await _send(bot, ADMIN_CHAT, msg)
        if top:
            logger.info(f"[Scanner] {mode} alert sent — {len(top)} signals")
        else:
            logger.info(f"[Scanner] Vol report sent — {len(vol_hits)} coins with vol >= 1.8x")
    except Exception as e:
        logger.error(f"[Scanner] Telegram send failed: {e}")

    # 7. Record STRONG BUY signals for quality tracking
    if top:
        for coin in top:
            try:
                sig   = coin.get("signal", {})
                quote = coin.get("quote", {})
                struct = coin.get("structure", {})
                timing = coin.get("timing", {})
                comp  = coin.get("components", {})
                trade = coin.get("trade_setup") or {}
                price = struct.get("close") or quote.get("price") or 0
                if price <= 0:
                    continue
                gates = sig.get("gates", {})
                # ATR from timing dict — used for dynamic stop/target in tracker
                atr_val  = float(timing.get("atr") or trade.get("atr") or 0)
                sym_name = coin.get("symbol", "?")
                exch_src = _symbol_exchange_map.get(sym_name, "binance")
                record_signal(
                    source       = "cex",
                    symbol       = sym_name,
                    entry_price  = price,
                    signal_label = sig.get("label", "BUY"),
                    score        = sig.get("total", 0),
                    interval     = interval,
                    chain        = "CEX",
                    v_confirmed  = bool(gates.get("v", comp.get("V", {}).get("confirmed", False))),
                    t_confirmed  = bool(gates.get("t", comp.get("T", {}).get("confirmed", False))),
                    adx_confirmed= bool(gates.get("adx", False)),
                    p_confirmed  = bool(comp.get("P", {}).get("confirmed", False)),
                    r_confirmed  = bool(comp.get("R", {}).get("confirmed", False)),
                    rel_vol      = float(timing.get("rel_volume") or 0),
                    atr          = atr_val,
                    z_price      = float(timing.get("z_price") or 0),
                    exchange     = exch_src,
                )
            except Exception as e:
                logger.warning(f"[Scanner] Tracker record failed for {coin.get('symbol','?')}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
#  VOL SPIKE POLLER — fires every hour, instant alert on new CEX or DEX spikes
# ─────────────────────────────────────────────────────────────────────────────

# Dedup registry: symbol -> last alert timestamp
# Prevents re-alerting the same spike for 4 hours
_spike_alerted: dict[str, float] = {}
_SPIKE_COOLDOWN = 4 * 3600   # 4-hour cooldown per symbol


def _vol_spike_label(rv: float) -> str:
    if rv >= 3.5: return "Extreme"
    if rv >= 2.5: return "High"
    return "Elevated"


async def vol_spike_job(context) -> None:
    """
    JobQueue callback — runs every hour.
    Checks CEX (top 200) and DEX (all chain agents) for vol spikes >= 1.8x.
    Fires a Telegram alert immediately for any NEW spike not alerted in last 4h.

    At 22:00 UTC (daily scan hour) — skip CEX check to avoid double-alerting
    since hourly_scan_job also runs at that hour.
    """
    global _spike_alerted
    bot      = context.bot
    now      = time.time()
    now_utc  = datetime.now(timezone.utc)
    scan_time = now_utc.strftime("%d %b %Y %H:%M UTC")

    # Wake Render API before doing anything — it sleeps after ~15min inactivity
    api_up = await _wake_api(timeout=65)
    if not api_up:
        logger.warning("[VolSpike] API did not wake in time — skipping this cycle")
        return

    # Prune old cooldown entries
    _spike_alerted = {k: v for k, v in _spike_alerted.items() if now - v < _SPIKE_COOLDOWN}

    new_cex: list[dict] = []    # thin dicts for non-STRONG-BUY vol spikes
    new_cex_sb: list[dict] = []  # full /analyse payloads for STRONG BUY CEX coins
    new_dex: list[dict] = []

    # ── CEX check — ticker pre-filter then VPRT only on spikes ───────────
    # Skip at 22 UTC — hourly_scan_job handles that hour with full scoring
    if now_utc.hour != DAILY_HOUR_UTC:
        try:
            symbols, vol_map = await _get_top_symbols(200)

            # ── Raw vol pre-filter ─────────────────────────────────────────
            # Compare current 24h vol against last snapshot.
            # A coin that gained >1.8x its per-hour average since last check
            # is flagged for full VPRT scoring.
            # On cold start (_ticker_vol_baseline empty) — score all symbols.
            spiked: list[str] = []
            if not _ticker_vol_baseline:
                # First run — seed baseline, score full universe this cycle
                logger.info("[VolSpike] Cold start — seeding vol baseline, scoring all symbols")
                spiked = symbols
            else:
                for sym in symbols:
                    cur  = vol_map.get(sym, 0)
                    prev = _ticker_vol_baseline.get(sym, 0)
                    if prev <= 0:
                        continue
                    # Hourly increment = cur - prev (24h rolling window grows ~1/24 per hour normally)
                    # A spike = this hour's increment is >= 1.8x the expected per-hour rate (prev/24)
                    hourly_increment  = max(cur - prev, 0)
                    expected_per_hour = prev / 24
                    if expected_per_hour > 0 and hourly_increment >= VOL_GATE * expected_per_hour:
                        spiked.append(sym)

            # Update baseline for next cycle
            global _ticker_vol_baseline
            _ticker_vol_baseline = dict(vol_map)

            logger.info(f"[VolSpike] Pre-filter: {len(spiked)}/{len(symbols)} symbols flagged for VPRT")

            if spiked:
                cex_hits, _ = await _vol_scan(spiked, interval="1d")
                for h in cex_hits:
                    sym   = h.get("symbol", "")
                    rv    = h.get("timing", {}).get("rel_volume") or 0
                    label = h.get("signal", {}).get("label", "")
                    key   = f"CEX:{sym}"
                    if key not in _spike_alerted:
                        _spike_alerted[key] = now
                        if label == "STRONG BUY":
                            new_cex_sb.append(h)
                        else:
                            chg = h.get("quote", {}).get("change_24h") or 0
                            new_cex.append({"symbol": sym, "rv": rv,
                                            "change": chg, "signal": label})
        except Exception as e:
            logger.warning(f"[VolSpike] CEX check failed: {e}")

    # ── DEX check ─────────────────────────────────────────────────────────
    try:
        import aiohttp as _aiohttp
        from dex_scanner.chains.agent_bsc  import BSCAgent
        from dex_scanner.chains.agent_base import BASEAgent
        from dex_scanner.chains.agent_eth  import ETHAgent
        from dex_scanner.chains.agent_sol  import SOLAgent
        from dex_scanner.chains.agent_arb  import ARBAgent

        dex_agents = [BSCAgent(), BASEAgent(), ETHAgent(), SOLAgent(), ARBAgent()]

        async with _aiohttp.ClientSession() as session:
            tasks = [agent.scan_vol_hits(session) for agent in dex_agents]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        for agent, res in zip(dex_agents, results):
            if isinstance(res, Exception) or not res:
                continue
            for h in res:
                sym   = h.get("symbol", "?")
                rv    = h.get("rel_vol", 0)
                chain = h.get("chain", agent.chain_id).upper()
                key   = f"DEX:{chain}:{sym}"
                if key not in _spike_alerted:
                    _spike_alerted[key] = now
                    new_dex.append({
                        "symbol": sym, "rv": rv, "source": f"DEX/{chain}",
                        "change_1h":  h.get("change_1h", 0),
                        "change_24h": h.get("change_24h", 0),
                        "signal": h.get("signal", ""),
                        "liq": h.get("liquidity", 0),
                        "chain": chain,
                    })
    except Exception as e:
        logger.warning(f"[VolSpike] DEX check failed: {e}")

    if not new_cex and not new_cex_sb and not new_dex:
        logger.debug(f"[VolSpike] No new spikes this hour — {len(_spike_alerted)} in cooldown")
        return

    # ── STRONG BUY coins — dedicated full signal message ───────────────────
    # Same format as the daily scan. Sent first, before the vol-only summary.
    if new_cex_sb:
        sb_blocks = [_coin_block(d, i, "1D") for i, d in enumerate(new_cex_sb, 1)]
        sb_msg = (
            f"CRYPTO SNIPER  --  STRONG BUY\n"
            f"(vol spike triggered)\n"
            f"{scan_time}\n"
            f"{'─' * 32}"
            + "".join(sb_blocks)
            + f"\n{'─' * 32}\n"
            f"https://crypto-sniper.app"
        )
        try:
            await _send(bot, ADMIN_CHAT, sb_msg)
            logger.info(f"[VolSpike] {len(new_cex_sb)} STRONG BUY alert(s) sent")
        except Exception as e:
            logger.error(f"[VolSpike] STRONG BUY send failed: {e}")

    # ── Non-confirmed spikes — thin vol-only summary ────────────────────────
    if new_cex or new_dex:
        total = len(new_cex) + len(new_dex)
        lines = [
            f"CRYPTO SNIPER  --  VOL SPIKE ALERT",
            f"{scan_time}",
            f"New spikes: {total}  (CEX: {len(new_cex)}  DEX: {len(new_dex)})",
            "─" * 32,
        ]

        if new_cex:
            lines.append("\nCEX SPIKES")
            for h in sorted(new_cex, key=lambda x: x["rv"], reverse=True)[:8]:
                lbl = _vol_spike_label(h["rv"])
                sig = h["signal"]
                sig_txt = f"  [{sig}]" if sig == "BUY" else ""
                lines.append(
                    f"  {h['symbol']}  {lbl} {h['rv']:.1f}x  "
                    f"({h['change']:+.1f}%){sig_txt}"
                )

        if new_dex:
            lines.append("\nDEX SPIKES")
            for h in sorted(new_dex, key=lambda x: x["rv"], reverse=True)[:8]:
                lbl = _vol_spike_label(h["rv"])
                sig = h["signal"]
                sig_txt = f"  [{sig}]" if sig in ("STRONG BUY", "BUY") else ""
                liq_txt = f"  Liq ${h['liq']/1000:.0f}K" if h.get("liq", 0) > 0 else ""
                lines.append(
                    f"  {h['symbol']}  {h['chain']}  {lbl} {h['rv']:.1f}x  "
                    f"({h['change_1h']:+.1f}% 1h / {h['change_24h']:+.1f}% 24h)"
                    f"{liq_txt}{sig_txt}"
                )

        lines += [
            "\n" + "─" * 32,
            "Vol spike — gates not yet confirmed. Open app to analyse.",
            "https://crypto-sniper.app",
        ]

        msg = "\n".join(lines)
        logger.info(f"[VolSpike] Vol-only alert: {total} spikes (CEX:{len(new_cex)} DEX:{len(new_dex)})")
        try:
            await _send(bot, ADMIN_CHAT, msg)
        except Exception as e:
            logger.error(f"[VolSpike] Vol-only send failed: {e}")
