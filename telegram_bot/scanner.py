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
STABLECOINS = {
    "USDT","USDC","BUSD","DAI","TUSD","USDP","USDD","GUSD","FRAX","LUSD",
    "FDUSD","PYUSD","STETH","WBTC","WETH","WBETH","EZETH","WEETH","SUSDE","USDE"
}
MIN_VOLUME_USD = 500_000


# ─────────────────────────────────────────────
#  Universe fetch — Binance USDT pairs
# ─────────────────────────────────────────────

async def _get_top_symbols(n: int = 200) -> list[str]:
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(
                BINANCE_TICKER,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status != 200:
                    logger.error(f"Binance ticker returned {r.status}")
                    return []
                tickers = await r.json()
        except Exception as e:
            logger.error(f"Binance universe fetch failed: {e}")
            return []

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

    coins.sort(key=lambda x: x[1], reverse=True)
    symbols = [sym for sym, _ in coins[:n]]
    logger.info(f"[Scanner] Binance universe: {len(symbols)} symbols")
    return symbols


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
            timeout=aiohttp.ClientTimeout(total=25)
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

    block  = f"\n#{rank}  {symbol}/USDT"
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

    # 1. Wake API
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{API_BASE}/health", timeout=aiohttp.ClientTimeout(total=15)) as r:
                logger.info(f"[Scanner] API health: {r.status}")
    except Exception as e:
        logger.warning(f"[Scanner] API wake failed: {e}")

    # 2. Fetch universe
    symbols = await _get_top_symbols(200)
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
                atr_val = float(timing.get("atr") or trade.get("atr") or 0)
                record_signal(
                    source       = "cex",
                    symbol       = coin.get("symbol", "?"),
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
                )
            except Exception as e:
                logger.warning(f"[Scanner] Tracker record failed for {coin.get('symbol','?')}: {e}")
