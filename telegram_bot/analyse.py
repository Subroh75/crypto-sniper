"""
Live analysis via the Crypto Sniper Render API.
Returns a formatted Telegram message for a given symbol + interval.
Gate-based display: V / T / ADX gates, plain English labels, no score bars.
"""
import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

API_BASE = os.environ.get("RENDER_API_URL", "https://crypto-sniper.onrender.com")


async def fetch_analysis(symbol: str, interval: str = "1D") -> str:
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
    sig    = data.get("signal", {})
    label  = sig.get("label", "NO SIGNAL")
    gates  = sig.get("gates", {})
    comp   = data.get("components", {})
    struct = data.get("structure", {})
    timing = data.get("timing", {})
    trade  = data.get("trade_setup") or {}
    conv   = data.get("conviction") or {}
    quote  = data.get("quote") or {}

    close = struct.get("close") or quote.get("price") or 0
    chg   = quote.get("change_24h") or 0
    rsi   = timing.get("rsi") or 0
    adx   = timing.get("adx") or 0
    rv    = timing.get("rel_volume") or 0

    bull_pct = conv.get("bull_pct", 0)
    bear_pct = conv.get("bear_pct", 0)

    # ── Gate status icons ──────────────────────────────────────────────
    def _gate(ok: bool) -> str:
        return "✅" if ok else "❌"

    v_ok   = gates.get("v",   comp.get("V", {}).get("confirmed", False))
    t_ok   = gates.get("t",   comp.get("T", {}).get("confirmed", False))
    adx_ok = gates.get("adx", adx >= 25)
    p_ok   = comp.get("P", {}).get("confirmed", False)
    r_ok   = comp.get("R", {}).get("confirmed", False)

    v_detail = comp.get("V", {}).get("detail", f"Vol: {rv:.1f}x")
    p_detail = comp.get("P", {}).get("detail", f"Momentum: {chg:+.2f}%")
    r_detail = comp.get("R", {}).get("detail", "Range: —")
    t_detail = comp.get("T", {}).get("detail", "Trend: —")

    lines = [
        f"CRYPTO SNIPER  |  {symbol}/USDT  |  {interval.upper()}",
        "─" * 36,
        f"SIGNAL:  {label}",
        f"DIR:     {sig.get('direction', 'NEUTRAL')}",
        "",
        "── GATES ────────────────────────",
        f"{_gate(v_ok)}  V  (Volume)   — {v_detail}",
        f"{_gate(t_ok)}  T  (Trend)    — {t_detail}",
        f"{_gate(adx_ok)}  ADX (Strength) — ADX {adx:.0f}",
        "",
        "── CONFIRMATION ─────────────────",
        f"{_gate(p_ok)}  P  (Momentum) — {p_detail}",
        f"{_gate(r_ok)}  R  (Range)    — {r_detail}",
        "",
        "── MARKET ───────────────────────",
        f"Price:   \${close:.6g}",
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

    # ── Trade setup (only shown when a real signal fires) ─────────────
    entry  = trade.get("entry")
    stop   = trade.get("stop")
    target = trade.get("target")
    rr     = trade.get("rr_ratio")
    if entry and stop and target:
        lines += [
            "",
            "── TRADE SETUP ──────────────────",
            f"Entry:  \${entry:.6g}",
            f"Stop:   \${stop:.6g}",
            f"Target: \${target:.6g}",
        ]
        if rr:
            lines.append(f"R:R     {rr:.2f}")

    # ── Z-score entry quality (Phase 1 — display only) ────────────────
    z_quality = timing.get("z_quality", "")
    if z_quality and z_quality != "UNKNOWN":
        q_icon   = {"IDEAL": "✅", "GOOD": "🟡", "CAUTION": "🟠", "AVOID": "🔴"}.get(z_quality, "⚪")
        z_price  = timing.get("z_price",  0)
        z_vol    = timing.get("z_vol",    0)
        z_return = timing.get("z_return", 0)
        lines += [
            "",
            "── ENTRY QUALITY ────────────────",
            f"{q_icon} {z_quality}",
            f"Price Z:  {z_price:+.2f}σ  {'↑ extended' if z_price > 1.5 else '↓ depressed' if z_price < -1.5 else 'in range'}",
            f"Vol Z:    {z_vol:+.2f}σ  {'✓ genuine spike' if z_vol >= 1.5 else '~ noise'}",
            f"Return Z: {z_return:+.2f}σ  {'⚠ chasing' if z_return > 2.0 else '✓ not exhausted'}",
            "(Phase 1: observing — not blocking signals)",
        ]

    lines += [
        "",
        "─" * 36,
        "https://crypto-sniper.app",
        "Not financial advice.",
    ]

    return "\n".join(l for l in lines)
