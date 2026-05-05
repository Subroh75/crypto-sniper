"""
Live analysis via the Crypto Sniper Render API.
Returns a formatted Telegram message for a given symbol + interval.
"""
import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("RENDER_API_URL", "https://crypto-sniper.onrender.com")

SIGNAL_EMOJI = {
    "STRONG BUY":  "STRONG BUY",
    "BUY":         "BUY",
    "MODERATE":    "MODERATE",
    "WEAK":        "WEAK",
    "NO SIGNAL":   "NO SIGNAL",
    "SELL":        "SELL",
    "STRONG SELL": "STRONG SELL",
}


async def fetch_analysis(symbol: str, interval: str = "1H") -> str:
    """Hit /analyse and return a formatted Telegram-ready string."""
    url = f"{API_BASE}/analyse"
    payload = {"symbol": symbol.upper(), "interval": interval.lower()}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status != 200:
                    return f"Could not fetch signal for {symbol}. API returned {resp.status} — try again shortly."
                data = await resp.json()
    except aiohttp.ClientTimeout:
        return f"Signal engine timed out for {symbol}. It may be waking up — try again in 30 seconds."
    except Exception as e:
        logger.error(f"Analysis fetch error: {e}")
        return f"Could not reach the signal engine. Try again shortly."

    return _format_result(data, symbol, interval)


def _format_result(data: dict, symbol: str, interval: str) -> str:
    sig       = data.get("signal", {})
    score     = sig.get("total", 0)
    label     = sig.get("label", "NO SIGNAL")
    direction = sig.get("direction", "")
    comp      = data.get("components", {})
    struct    = data.get("structure", {})
    timing    = data.get("timing", {})
    trade     = data.get("trade_setup") or {}
    conv      = data.get("conviction") or {}
    quote     = data.get("quote") or {}

    close     = struct.get("close") or quote.get("price") or 0
    chg       = quote.get("change_24h") or 0
    rsi       = timing.get("rsi") or 0
    adx       = timing.get("adx") or 0
    rv        = timing.get("rel_volume") or 0

    v_score   = comp.get("V", {}).get("score", 0)
    p_score   = comp.get("P", {}).get("score", 0)
    r_score   = comp.get("R", {}).get("score", 0)
    t_score   = comp.get("T", {}).get("score", 0)

    bull_pct  = conv.get("bull_pct", 0)
    bear_pct  = conv.get("bear_pct", 0)

    # Score bar (16 chars wide)
    filled = round(score / 16 * 12)
    bar = "[" + "#" * filled + "-" * (12 - filled) + "]"

    signal_display = SIGNAL_EMOJI.get(label, label)

    lines = [
        f"CRYPTO SNIPER  |  {symbol}/USDT  |  {interval}",
        "─" * 34,
        f"SIGNAL:  {signal_display}",
        f"SCORE:   {score}/16  {bar}",
        f"DIR:     {direction}",
        "",
        "── VPRT BREAKDOWN ──────────────",
        f"V (Volume):   {v_score}/5",
        f"P (Momentum): {p_score}/3",
        f"R (Range):    {r_score}/2",
        f"T (Trend):    {t_score}/3",
        "",
        "── MARKET ──────────────────────",
        f"Price:   ${close:.6g}",
        f"24H chg: {chg:+.2f}%",
        f"RSI 14:  {rsi:.1f}",
        f"ADX 14:  {adx:.1f}",
        f"Rel Vol: {rv:.1f}x",
    ]

    if bull_pct or bear_pct:
        lines += [
            "",
            "── CONVICTION ───────────────────",
            f"Bull: {bull_pct:.0f}%  |  Bear: {bear_pct:.0f}%",
        ]

    if trade:
        entry  = trade.get("entry")
        stop   = trade.get("stop")
        target = trade.get("target")
        rr     = trade.get("rr_ratio")
        if entry and stop and target:
            lines += [
                "",
                "── TRADE SETUP ──────────────────",
                f"Entry:  {entry:.6g}",
                f"Stop:   {stop:.6g}",
                f"Target: {target:.6g}",
                f"R:R     {rr:.2f}" if rr else "",
            ]

    lines += [
        "",
        "─" * 34,
        "https://crypto-sniper.app",
        "Not financial advice.",
    ]

    return "\n".join(l for l in lines)
