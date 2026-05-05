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
MIN_SCORE  = int(os.environ.get("SCANNER_MIN_SCORE", "9"))
TOP_N      = int(os.environ.get("SCANNER_TOP_N", "10"))

STABLECOINS = {
    "USDT","USDC","BUSD","DAI","TUSD","USDP","USDD","GUSD","FRAX","LUSD",
    "FDUSD","PYUSD","STETH","WBTC","WETH","WBETH","EZETH","WEETH","SUSDE","USDE"
}

# ─────────────────────────────────────────────
#  Step 1: fetch top 200 symbols from CoinGecko
# ─────────────────────────────────────────────

async def _get_top_symbols(n: int = 200) -> list[str]:
    symbols = []
    async with aiohttp.ClientSession() as session:
        for page in range(1, 3):
            try:
                url = (
                    f"https://api.coingecko.com/api/v3/coins/markets"
                    f"?vs_currency=usd&order=market_cap_desc&per_page=100&page={page}&sparkline=false"
                )
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status != 200:
                        logger.warning(f"CoinGecko page {page} returned {r.status}")
                        continue
                    coins = await r.json()
                    for coin in coins:
                        sym = coin.get("symbol", "").upper().strip()
                        if sym and sym not in STABLECOINS and sym not in symbols:
                            symbols.append(sym)
            except Exception as e:
                logger.error(f"CoinGecko fetch error page {page}: {e}")
            await asyncio.sleep(0.6)
    return symbols[:n]


# ─────────────────────────────────────────────
#  Step 2: score a single symbol
# ─────────────────────────────────────────────

async def _analyse_symbol(session: aiohttp.ClientSession, symbol: str) -> dict | None:
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
            if score >= MIN_SCORE:
                return data
    except Exception as e:
        logger.debug(f"Analyse error {symbol}: {e}")
    return None


# ─────────────────────────────────────────────
#  Step 3: format a Telegram alert block
# ─────────────────────────────────────────────

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

    # Sort by score descending, take top N
    hits.sort(key=lambda x: x.get("signal", {}).get("total", 0), reverse=True)
    top = hits[:TOP_N]

    logger.info(f"[Scanner] {len(top)} signals found, {errors} errors")

    # 4. Send to Telegram (or stay silent if nothing found)
    if not top:
        logger.info("[Scanner] No STRONG BUY signals this hour — staying silent")
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
