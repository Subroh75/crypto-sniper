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
WATCH_MIN_SCORE = 5   # coins scored 5–8 shown in "no trade" report
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

async def _analyse_symbol(session: aiohttp.ClientSession, symbol: str) -> dict | None:
    """
    Returns the analyse result if score >= WATCH_MIN_SCORE (5+).
    Callers filter by MIN_SCORE (9) for STRONG BUY and WATCH_MIN_SCORE (5–8) for watch.
    """
    try:
        async with session.post(
            f"{API_BASE}/analyse",
            json={"symbol": symbol, "interval": "1d"},
            timeout=aiohttp.ClientTimeout(total=25)
        ) as r:
            if r.status != 200:
                return None
            data = await r.json()
            sig = data.get("signal", {})
            score = sig.get("total", 0)
            if score >= WATCH_MIN_SCORE:
                return data
    except Exception as e:
        logger.debug(f"Analyse error {symbol}: {e}")
    return None


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

    # 3. Score each symbol (with concurrency limit to avoid hammering the API)
    hits    = []
    errors  = 0
    sem     = asyncio.Semaphore(5)  # max 5 concurrent requests

    async def bounded_analyse(session, sym):
        async with sem:
            result = await _analyse_symbol(session, sym)
            await asyncio.sleep(0.15)
            return result

    async with aiohttp.ClientSession() as session:
        tasks   = [bounded_analyse(session, sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception):
            errors += 1
        elif res is not None:
            hits.append(res)

    # Sort by score descending
    hits.sort(key=lambda x: x.get("signal", {}).get("total", 0), reverse=True)

    # Split into STRONG BUY (9+) and watch tier (5–8)
    strong = [h for h in hits if h.get("signal", {}).get("total", 0) >= MIN_SCORE]
    watch  = [h for h in hits if WATCH_MIN_SCORE <= h.get("signal", {}).get("total", 0) < MIN_SCORE]

    top        = strong[:TOP_N]
    watch_top  = watch[:10]   # top 10 near-miss coins

    logger.info(f"[Scanner] {len(top)} STRONG BUY, {len(watch_top)} watch-tier, {errors} errors")

    # 4. Send to Telegram
    if not top and not watch_top:
        logger.info("[Scanner] Nothing above 5/13 this scan — staying silent")
        return

    # 4a. Enrich top hits with Kronos AI forecast (parallel, best-effort)
    async with aiohttp.ClientSession() as kron_session:
        kronos_tasks = [
            _fetch_kronos(kron_session, d.get("symbol", ""), d)
            for d in top
        ]
        kronos_results = await asyncio.gather(*kronos_tasks, return_exceptions=True)

    for coin_data, kron in zip(top, kronos_results):
        if isinstance(kron, dict) and kron:
            coin_data["kronos"] = kron
        else:
            coin_data["kronos"] = {}

    # If no STRONG BUY signals, send a quiet market / watch report instead
    if not top:
        msg = _format_quiet_message(watch_top, scan_time)
        try:
            if len(msg) <= 4096:
                await bot.send_message(chat_id=ADMIN_CHAT, text=msg)
            else:
                for chunk in [msg[i:i+4096] for i in range(0, len(msg), 4096)]:
                    await bot.send_message(chat_id=ADMIN_CHAT, text=chunk)
            logger.info(f"[Scanner] Quiet market report sent — {len(watch_top)} coins on watch")
        except Exception as e:
            logger.error(f"[Scanner] Quiet report send failed: {e}")
        return

    msg = _format_scan_message(top, scan_time)

    try:
        # Split if over Telegram's 4096 char limit
        if len(msg) <= 4096:
            await bot.send_message(chat_id=ADMIN_CHAT, text=msg)
        else:
            # Send header + one block per coin
            await bot.send_message(chat_id=ADMIN_CHAT, text=msg[:4096])
            remaining = msg[4096:]
            while remaining:
                await bot.send_message(chat_id=ADMIN_CHAT, text=remaining[:4096])
                remaining = remaining[4096:]

        logger.info(f"[Scanner] Alert sent — {len(top)} signals")
    except Exception as e:
        logger.error(f"[Scanner] Telegram send failed: {e}")
