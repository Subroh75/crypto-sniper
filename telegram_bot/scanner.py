"""
Hourly background scanner.
Scans top 200 coins by market cap, pushes STRONG BUY signals (>=9/16) to Telegram.
Wired into python-telegram-bot's JobQueue — no APScheduler needed.
"""
import os
import asyncio
import logging
import aiohttp
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

API_BASE   = os.environ.get("RENDER_API_URL", "https://crypto-sniper.onrender.com")
ADMIN_CHAT = int(os.environ.get("ADMIN_CHAT_ID", "5861457546"))
MIN_SCORE       = int(os.environ.get("SCANNER_MIN_SCORE", "9"))
WATCH_MIN_SCORE  = 5   # coins scored 5–8 shown in "no trade" report
BACKUP_INTERVAL  = "1h"  # re-score on this interval when 1D has no 9+ hits
BACKUP_TOP_N     = 5     # max coins in backup signal
TOP_N      = int(os.environ.get("SCANNER_TOP_N", "10"))

BINANCE_TICKER = "https://data-api.binance.vision/api/v3/ticker/24hr"
STABLECOINS = {
    "USDT","USDC","BUSD","DAI","TUSD","USDP","USDD","GUSD","FRAX","LUSD",
    "FDUSD","PYUSD","STETH","WBTC","WETH","WBETH","EZETH","WEETH","SUSDE","USDE"
}
MIN_VOLUME_USD = 500_000   # filter out ultra-thin pairs

# ─────────────────────────────────────────────
#  Step 1: fetch top N symbols from Binance (volume-sorted)
# ─────────────────────────────────────────────

async def _get_top_symbols(n: int = 200) -> list[str]:
    """
    Fetches all Binance USDT spot pairs in one call, filters stables and
    low-volume pairs, sorts by 24h quote volume, returns top N symbols.
    Single request, real-time data, no rate limit concerns.
    """
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
        sym = pair[:-4]  # strip USDT suffix
        if sym in STABLECOINS:
            continue
        vol = float(t.get("quoteVolume", 0))
        if vol < MIN_VOLUME_USD:
            continue
        coins.append((sym, vol))

    # Sort by 24h USD volume descending — most liquid first
    coins.sort(key=lambda x: x[1], reverse=True)
    symbols = [sym for sym, _ in coins[:n]]
    logger.info(f"[Scanner] Binance universe: {len(symbols)} symbols (from {len(coins)} USDT pairs)")
    return symbols


# ─────────────────────────────────────────────
#  Step 2: score a single symbol
# ─────────────────────────────────────────────

async def _analyse_symbol(
    session: aiohttp.ClientSession,
    symbol: str,
    interval: str = "1d",
    min_score: int = WATCH_MIN_SCORE,
) -> dict | None:
    """
    Score a single symbol. Returns result if score >= min_score, else None.
    Interval defaults to 1d; pass interval='1h' for the backup scan.
    """
    try:
        async with session.post(
            f"{API_BASE}/analyse",
            json={"symbol": symbol, "interval": interval},
            timeout=aiohttp.ClientTimeout(total=25)
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()
            sig = data.get("signal", {})
            score = sig.get("total", 0)
            if score >= min_score:
                return data
    except Exception as e:
        logger.debug(f"Analyse error {symbol} ({interval}): {e}")
    return None


async def _run_scan(
    symbols: list[str],
    interval: str = "1d",
    min_score: int = WATCH_MIN_SCORE,
    concurrency: int = 5,
) -> tuple[list[dict], int]:
    """
    Score all symbols in parallel. Returns (hits, error_count).
    hits includes every result with score >= min_score, sorted desc.
    """
    hits   = []
    errors = 0
    sem    = asyncio.Semaphore(concurrency)

    async def bounded(session, sym):
        async with sem:
            result = await _analyse_symbol(session, sym, interval=interval, min_score=min_score)
            await asyncio.sleep(0.15)
            return result

    async with aiohttp.ClientSession() as session:
        tasks   = [bounded(session, sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception):
            errors += 1
        elif res is not None:
            hits.append(res)

    hits.sort(key=lambda x: x.get("signal", {}).get("total", 0), reverse=True)
    return hits, errors


# ─────────────────────────────────────────────
#  Step 2b: fetch Kronos AI forecast for a hit
# ─────────────────────────────────────────────

async def _fetch_kronos(session: aiohttp.ClientSession, symbol: str, analyse_data: dict) -> dict:
    """
    Calls /kronos with the signal context from the /analyse result.
    Returns the forecast dict, or {} on failure.
    """
    try:
        sig    = analyse_data.get("signal", {})
        struct = analyse_data.get("structure", {})
        timing = analyse_data.get("timing", {})
        quote  = analyse_data.get("quote", {})
        # Build the signal_ctx that Kronos expects
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
            if r.status != 200:
                return {}
            resp = await r.json()
            return resp.get("forecast", {})
    except Exception as e:
        logger.debug(f"Kronos fetch error {symbol}: {e}")
    return {}


# ─────────────────────────────────────────────
#  Step 3: format a Telegram alert block
# ─────────────────────────────────────────────

async def _send(bot, chat_id: int, msg: str) -> None:
    """Send a Telegram message, splitting at 4096 chars if needed."""
    if len(msg) <= 4096:
        await bot.send_message(chat_id=chat_id, text=msg)
    else:
        for chunk in [msg[i:i+4096] for i in range(0, len(msg), 4096)]:
            await bot.send_message(chat_id=chat_id, text=chunk)


def _format_backup_message(hits: list[dict], scan_time: str) -> str:
    """
    Sent when 1D has no 9+ signals but 1H re-scan finds some.
    Clearly labelled as a shorter-timeframe backup — lower conviction.
    """
    header = (
        f"CRYPTO SNIPER  —  BACKUP SIGNAL (1H)\n"
        f"{scan_time}  |  1H  |  Score 9+/13\n"
        f"{'─' * 34}\n"
        f"No 1D signals today — 1H scan found {len(hits)}\n"
        f"Lower conviction: use tight stops\n"
    )

    blocks = []
    for i, data in enumerate(hits, 1):
        sig    = data.get("signal", {})
        score  = sig.get("total", 0)
        label  = sig.get("label", "")
        symbol = data.get("symbol", "?")
        struct = data.get("structure", {})
        timing = data.get("timing", {})
        quote  = data.get("quote", {})
        comp   = data.get("components", {})
        trade  = data.get("trade_setup") or {}

        close  = struct.get("close") or quote.get("price") or 0
        chg    = quote.get("change_24h") or 0
        rsi    = timing.get("rsi") or 0
        rv     = timing.get("rel_volume") or 0
        adx    = timing.get("adx") or 0

        v_sc = comp.get("V", {}).get("score", 0)
        p_sc = comp.get("P", {}).get("score", 0)
        r_sc = comp.get("R", {}).get("score", 0)
        t_sc = comp.get("T", {}).get("score", 0)

        filled = round(score / 13 * 10)
        bar    = "[" + "#" * filled + "-" * (10 - filled) + "]"

        block  = f"\n#{i}  {symbol}/USDT  —  {score}/13  {bar}\n"
        block += f"Signal:  {label} (1H)\n"
        block += f"Price:   ${close:.6g}  ({chg:+.2f}% 24h)\n"
        block += f"VPRT:    V{v_sc} P{p_sc} R{r_sc} T{t_sc}  |  RSI {rsi:.0f}  ADX {adx:.0f}  Vol {rv:.1f}x\n"

        if trade and trade.get("entry") and trade.get("stop") and trade.get("target"):
            rr = trade.get("rr_ratio")
            block += f"Setup:   E {trade['entry']:.6g}  SL {trade['stop']:.6g}  TP {trade['target']:.6g}"
            if rr:
                block += f"  R:R {rr:.2f}"
            block += "\n"

        blocks.append(block)

    footer = (
        f"\n{'─' * 34}\n"
        "1H signals — confirm on higher TF before entry.\n"
        "https://crypto-sniper.app\n"
        "Not financial advice."
    )

    return header + "".join(blocks) + footer


def _format_quiet_message(watch: list[dict], scan_time: str) -> str:
    """
    Sent when no coin reaches 9/13 STRONG BUY.
    Shows top near-miss coins (5–8/13) as a watch list with market context.
    """
    header = (
        f"CRYPTO SNIPER  —  DAILY SCAN\n"
        f"{scan_time}  |  1D  |  Score 9+/13\n"
        f"{'─' * 34}\n"
        f"NO TRADES TODAY\n"
        f"Market ranging — no coin reached 9/13\n"
    )

    if not watch:
        return (
            header +
            f"{'─' * 34}\n"
            "Nothing above 5/13 this scan. Deep range or low volume market.\n"
            "https://crypto-sniper.app"
        )

    header += f"Top {len(watch)} coins on watch ({watch[0].get('signal',{}).get('total',0)}–8/13):\n"

    blocks = []
    for i, data in enumerate(watch, 1):
        sig    = data.get("signal", {})
        score  = sig.get("total", 0)
        symbol = data.get("symbol", "?")
        struct = data.get("structure", {})
        timing = data.get("timing", {})
        quote  = data.get("quote", {})
        comp   = data.get("components", {})

        close  = struct.get("close") or quote.get("price") or 0
        chg    = quote.get("change_24h") or 0
        rsi    = timing.get("rsi") or 0
        rv     = timing.get("rel_volume") or 0
        adx    = timing.get("adx") or 0

        v_sc = comp.get("V", {}).get("score", 0)
        p_sc = comp.get("P", {}).get("score", 0)
        r_sc = comp.get("R", {}).get("score", 0)
        t_sc = comp.get("T", {}).get("score", 0)

        filled = round(score / 13 * 10)
        bar    = "[" + "#" * filled + "-" * (10 - filled) + "]"

        # What's missing to reach 9?
        gap   = 9 - score
        needs = f"+{gap} to signal"

        block  = f"\n#{i}  {symbol}  —  {score}/13  {bar}"
        block += f"  ({needs})\n"
        block += f"Price: ${close:.6g}  ({chg:+.2f}%)\n"
        block += f"VPRT:  V{v_sc} P{p_sc} R{r_sc} T{t_sc}  |  RSI {rsi:.0f}  ADX {adx:.0f}  Vol {rv:.1f}x\n"
        blocks.append(block)

    footer = (
        f"\n{'─' * 34}\n"
        "Watch these — a volume or momentum shift could push them over.\n"
        "https://crypto-sniper.app"
    )

    return header + "".join(blocks) + footer


def _format_scan_message(hits: list[dict], scan_time: str) -> str:
    header = (
        f"CRYPTO SNIPER  —  HOURLY SCAN\n"
        f"{scan_time}  |  1D  |  Score 9+/13\n"
        f"{'─' * 34}\n"
        f"STRONG BUY signals found: {len(hits)}\n"
    )

    blocks = []
    for i, data in enumerate(hits, 1):
        sig    = data.get("signal", {})
        score  = sig.get("total", 0)
        label  = sig.get("label", "")
        symbol = data.get("symbol", "?")
        struct = data.get("structure", {})
        timing = data.get("timing", {})
        quote  = data.get("quote", {})
        trade  = data.get("trade_setup") or {}
        comp   = data.get("components", {})
        kronos = data.get("kronos") or {}  # injected by hourly_scan_job after _fetch_kronos

        close  = struct.get("close") or quote.get("price") or 0
        chg    = quote.get("change_24h") or 0
        rsi    = timing.get("rsi") or 0
        rv     = timing.get("rel_volume") or 0
        adx    = timing.get("adx") or 0

        v_sc   = comp.get("V", {}).get("score", 0)
        p_sc   = comp.get("P", {}).get("score", 0)
        r_sc   = comp.get("R", {}).get("score", 0)
        t_sc   = comp.get("T", {}).get("score", 0)

        # Score bar
        filled = round(score / 13 * 10)
        bar    = "[" + "#" * filled + "-" * (10 - filled) + "]"

        block  = f"\n#{i}  {symbol}/USDT  —  {score}/13  {bar}\n"
        block += f"Signal:  {label}\n"
        block += f"Price:   ${close:.6g}  ({chg:+.2f}%)\n"
        block += f"VPRT:    V{v_sc} P{p_sc} R{r_sc} T{t_sc}  |  RSI {rsi:.0f}  ADX {adx:.0f}  Vol {rv:.1f}x\n"

        if trade and trade.get("entry") and trade.get("stop") and trade.get("target"):
            rr = trade.get("rr_ratio")
            block += f"Setup:   E {trade['entry']:.6g}  SL {trade['stop']:.6g}  TP {trade['target']:.6g}"
            if rr:
                block += f"  R:R {rr:.2f}"
            block += "\n"

        # Kronos AI forecast line
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

        blocks.append(block)

    footer = (
        f"\n{'─' * 34}\n"
        "https://crypto-sniper.app\n"
        "Not financial advice."
    )

    return header + "".join(blocks) + footer


# ─────────────────────────────────────────────
#  Main job — called by JobQueue every hour
# ─────────────────────────────────────────────

async def hourly_scan_job(context) -> None:
    """JobQueue callback — runs every hour."""
    bot       = context.bot
    scan_time = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    logger.info(f"[Scanner] Starting hourly scan — {scan_time}")

    # 1. Wake the API (fire and forget, just in case Render slept)
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{API_BASE}/health", timeout=aiohttp.ClientTimeout(total=15)) as r:
                logger.info(f"[Scanner] API health: {r.status}")
    except Exception as e:
        logger.warning(f"[Scanner] API wake failed: {e}")

    # 2. Fetch top 200 symbols
    try:
        symbols = await _get_top_symbols(200)
        logger.info(f"[Scanner] Got {len(symbols)} symbols")
    except Exception as e:
        logger.error(f"[Scanner] Symbol fetch failed: {e}")
        return

    if not symbols:
        logger.warning("[Scanner] No symbols returned — aborting")
        return

    # 3. Score all symbols on 1D — primary scan
    hits_1d, errors = await _run_scan(symbols, interval="1d", min_score=WATCH_MIN_SCORE)

    strong_1d = [h for h in hits_1d if h.get("signal", {}).get("total", 0) >= MIN_SCORE]
    watch_1d  = [h for h in hits_1d if WATCH_MIN_SCORE <= h.get("signal", {}).get("total", 0) < MIN_SCORE]

    top       = strong_1d[:TOP_N]
    watch_top = watch_1d[:10]

    logger.info(f"[Scanner] 1D scan: {len(top)} STRONG BUY, {len(watch_top)} watch-tier, {errors} errors")

    # 4. No 1D signals — try 1H backup scan on the same universe
    backup_hits: list[dict] = []
    if not top:
        logger.info("[Scanner] No 1D signals — running 1H backup scan")
        hits_1h, _ = await _run_scan(symbols, interval=BACKUP_INTERVAL, min_score=MIN_SCORE)
        backup_hits = hits_1h[:BACKUP_TOP_N]
        logger.info(f"[Scanner] 1H backup: {len(backup_hits)} STRONG BUY found")

    # 5. Nothing anywhere — send watch report or stay silent
    if not top and not backup_hits:
        if watch_top:
            msg = _format_quiet_message(watch_top, scan_time)
            try:
                await _send(bot, ADMIN_CHAT, msg)
                logger.info(f"[Scanner] Quiet watch report sent — {len(watch_top)} coins")
            except Exception as e:
                logger.error(f"[Scanner] Quiet report send failed: {e}")
        else:
            logger.info("[Scanner] Nothing above 5/13 anywhere — staying silent")
        return

    # 6a. Enrich 1D hits with Kronos (only when we have real 1D signals)
    if top:
        async with aiohttp.ClientSession() as kron_session:
            kronos_results = await asyncio.gather(
                *[_fetch_kronos(kron_session, d.get("symbol", ""), d) for d in top],
                return_exceptions=True
            )
        for coin_data, kron in zip(top, kronos_results):
            coin_data["kronos"] = kron if isinstance(kron, dict) and kron else {}

    # 6b. Send backup signal if 1D had nothing but 1H found hits
    if not top and backup_hits:
        msg = _format_backup_message(backup_hits, scan_time)
        try:
            await _send(bot, ADMIN_CHAT, msg)
            logger.info(f"[Scanner] 1H backup signal sent — {len(backup_hits)} coins")
        except Exception as e:
            logger.error(f"[Scanner] Backup signal send failed: {e}")
        return

    msg = _format_scan_message(top, scan_time)

    try:
        await _send(bot, ADMIN_CHAT, msg)
        logger.info(f"[Scanner] 1D alert sent — {len(top)} signals")
    except Exception as e:
        logger.error(f"[Scanner] Telegram send failed: {e}")
