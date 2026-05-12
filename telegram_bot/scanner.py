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

def _coin_block(data: dict, rank: int, interval: str) -> str:
    """Shared single-coin block used by all formatters."""
    sig    = data.get("signal", {})
    score  = sig.get("total", 0)
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
    rsi   = timing.get("rsi") or 0
    rv    = timing.get("rel_volume") or 0
    adx   = timing.get("adx") or 0

    v_sc = comp.get("V", {}).get("score", 0)
    p_sc = comp.get("P", {}).get("score", 0)
    r_sc = comp.get("R", {}).get("score", 0)
    t_sc = comp.get("T", {}).get("score", 0)

    filled = round(score / 13 * 10)
    bar    = "[" + "#" * filled + "-" * (10 - filled) + "]"

    tf_label = interval.upper()

    block  = f"\n#{rank}  {symbol}/USDT  —  {score}/13  {bar}\n"
    block += f"Signal:  {label} ({tf_label})\n"
    block += f"Price:   ${close:.6g}  ({chg:+.2f}% 24h)\n"
    block += f"VPRT:    V{v_sc} P{p_sc} R{r_sc} T{t_sc}  |  RSI {rsi:.0f}  ADX {adx:.0f}  Vol {rv:.1f}x\n"

    if trade and trade.get("entry") and trade.get("stop") and trade.get("target"):
        rr = trade.get("rr_ratio")
        block += f"Setup:   E {trade['entry']:.6g}  SL {trade['stop']:.6g}  TP {trade['target']:.6g}"
        if rr:
            block += f"  R:R {rr:.2f}"
        block += "\n"

    # Z-Score entry quality (Phase 1 — display only)
    z_quality = timing.get("z_quality", "")
    z_detail  = timing.get("z_detail", "")
    if z_quality and z_detail:
        q_icon = {"IDEAL": "✅", "GOOD": "🟡", "CAUTION": "🟠", "AVOID": "🔴"}.get(z_quality, "⚪")
        block += f"Entry Q: {q_icon} {z_quality}  {z_detail}\n"

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


def _format_signal_message(hits: list[dict], interval: str, scan_time: str) -> str:
    """Standard STRONG BUY alert — used for both 1D and 1H scans."""
    tf     = interval.upper()
    prefix = "DAILY" if interval == "1d" else "HOURLY"
    header = (
        f"CRYPTO SNIPER  —  {prefix} SCAN\n"
        f"{scan_time}  |  {tf}  |  Score 9+/13\n"
        f"{'─' * 34}\n"
        f"STRONG BUY signals: {len(hits)}\n"
    )
    blocks = [_coin_block(d, i, interval) for i, d in enumerate(hits, 1)]
    footer = (
        f"\n{'─' * 34}\n"
        "https://crypto-sniper.app\n"
        "Not financial advice."
    )
    return header + "".join(blocks) + footer


def _format_watch_message(watch: list[dict], interval: str, scan_time: str) -> str:
    """Near-miss watch report when nothing hit 9/13."""
    tf     = interval.upper()
    header = (
        f"CRYPTO SNIPER  —  NO TRADES ({tf})\n"
        f"{scan_time}  |  {tf}  |  Score 9+/13\n"
        f"{'─' * 34}\n"
        f"No coin reached 9/13 — market ranging\n"
        f"Top {len(watch)} coins on watch:\n"
    )
    blocks = []
    for i, data in enumerate(watch, 1):
        sig    = data.get("signal", {})
        score  = sig.get("total", 0)
        symbol = data.get("symbol", "?")
        struct = data.get("structure", {})
        timing = data.get("timing", {})
        quote  = data.get("quote", {})
        comp   = data.get("components", {})

        close = struct.get("close") or quote.get("price") or 0
        chg   = quote.get("change_24h") or 0
        rsi   = timing.get("rsi") or 0
        rv    = timing.get("rel_volume") or 0
        adx   = timing.get("adx") or 0

        v_sc = comp.get("V", {}).get("score", 0)
        p_sc = comp.get("P", {}).get("score", 0)
        r_sc = comp.get("R", {}).get("score", 0)
        t_sc = comp.get("T", {}).get("score", 0)

        filled = round(score / 13 * 10)
        bar    = "[" + "#" * filled + "-" * (10 - filled) + "]"
        gap    = 9 - score

        block  = f"\n#{i}  {symbol}  —  {score}/13  {bar}  (+{gap} to signal)\n"
        block += f"Price: ${close:.6g}  ({chg:+.2f}%)\n"
        block += f"VPRT:  V{v_sc} P{p_sc} R{r_sc} T{t_sc}  |  RSI {rsi:.0f}  ADX {adx:.0f}  Vol {rv:.1f}x\n"
        blocks.append(block)

    footer = (
        f"\n{'─' * 34}\n"
        "Volume or momentum shift could push these over.\n"
        "https://crypto-sniper.app"
    )
    return header + "".join(blocks) + footer


# ─────────────────────────────────────────────
#  Main job — called by JobQueue every hour
# ─────────────────────────────────────────────

async def hourly_scan_job(context) -> None:
    """
    JobQueue callback — fires every hour.

    At 22:00 UTC (8 AM AEST): scores on 1D candles — daily overview.
    All other hours:           scores on 1H candles — intraday signals.
    """
    bot       = context.bot
    now_utc   = datetime.now(timezone.utc)
    scan_time = now_utc.strftime("%d %b %Y %H:%M UTC")

    # Determine scan mode
    is_daily = (now_utc.hour == DAILY_HOUR_UTC)
    interval = "1d" if is_daily else "1h"
    mode     = "DAILY (1D)" if is_daily else "HOURLY (1H)"

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
    watch  = [h for h in hits if WATCH_MIN_SCORE <= h.get("signal", {}).get("total", 0) < MIN_SCORE]

    top       = strong[:TOP_N]
    watch_top = watch[:10]

    logger.info(f"[Scanner] {mode}: {len(top)} STRONG BUY, {len(watch_top)} watch, {errors} errors")

    # 4. Nothing at all — stay silent
    if not top and not watch_top:
        logger.info(f"[Scanner] Nothing above {WATCH_MIN_SCORE}/13 — staying silent")
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
        msg = _format_watch_message(watch_top, interval, scan_time)

    try:
        await _send(bot, ADMIN_CHAT, msg)
        if top:
            logger.info(f"[Scanner] {mode} alert sent — {len(top)} signals")
        else:
            logger.info(f"[Scanner] Watch report sent — {len(watch_top)} coins")
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
