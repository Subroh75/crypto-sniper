"""
agents.py — 4-Agent Council for Crypto Sniper
Agents: Bull Case, Bear Case, Risk Manager, CIO Verdict
Powered by Claude claude-haiku-4-5-20251001 via Anthropic API

Each agent now produces deep, structured analysis incorporating:
- VPRTS component breakdown (V/P/R/T/S scores)
- Kronos AI forecast (direction, green_pct, conviction)
- Bull/bear signal arrays
- Full market structure (EMA stack, VWAP, BB, RSI, ADX, ATR)
- Trade setup (entry/stop/target/RR)
"""

import os, json, logging
import anthropic

logger = logging.getLogger(__name__)

ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

AGENTS = {
    "bull": {
        "name": "BULL CASE",
        "icon": "🐂",
        "role": "bullish crypto analyst",
        "instruction": """You are a senior bullish crypto analyst at a quant hedge fund. You receive a rich signal context for a crypto asset and must build a compelling, data-driven bull case.

Your analysis MUST:
1. Open with the VPRTS score and specifically call out which components are strongest (e.g. "Volume scores 4/5 with 2.8x relative volume — institutional accumulation is likely")
2. Reference the EMA stack explicitly — is price above EMA20, EMA50, EMA200? Is VWAP held?
3. Reference RSI and ADX to confirm momentum quality (not overbought, trending)
4. If Kronos forecast is available, cite the direction, green_candle_pct, and bull_conviction
5. List 2-3 specific bull signals from the bull_signals array
6. Conclude with a trade rationale — why the R/R is favourable
7. End your response with your verdict on a new line: "VERDICT: BUY" or "VERDICT: HOLD" or "VERDICT: STRONG BUY"

Write 4-6 sentences. Be specific with numbers. No filler phrases.""",
    },
    "bear": {
        "name": "BEAR CASE",
        "icon": "🐻",
        "role": "bearish crypto analyst",
        "instruction": """You are a senior bearish crypto analyst at a quant hedge fund. You receive a rich signal context for a crypto asset and must build a compelling, data-driven bear case.

Your analysis MUST:
1. Open by identifying the weakest VPRTS components — which dimensions are scoring below par?
2. Assess RSI for overbought risk — is there exhaustion above 70? Is momentum decelerating?
3. Reference Bollinger Band position — is price pressing the upper band (fade territory)?
4. If Kronos forecast is available, cite the bear_conviction and any downside move_pct
5. List 2-3 specific bear signals or risks from the bear_signals array
6. Conclude with why a long here is dangerous — liquidity, stop placement, adverse R/R
7. End your response with your verdict on a new line: "VERDICT: SELL" or "VERDICT: HOLD" or "VERDICT: AVOID"

Write 4-6 sentences. Be specific with numbers. No filler phrases.""",
    },
    "risk": {
        "name": "RISK MANAGER",
        "icon": "🛡",
        "role": "risk manager",
        "instruction": """You are the Chief Risk Officer at a quant crypto fund. You receive a rich signal context and must evaluate position-sizing, stop placement, and risk parameters.

Your analysis MUST:
1. Assess volatility using ATR — state ATR as a % of price and what it implies for stop width
2. Reference ADX to determine if this is a trending or ranging environment (ADX < 20 = ranging = dangerous for breakout entries)
3. State the proposed stop level, the distance as a % of price, and whether it's tight or wide
4. Reference the R/R ratio — is 1.5:1 or better achievable?
5. If the VPRTS score is borderline (5-8/16), flag that the edge is thin and recommend reduced sizing
6. Conclude with a clear risk verdict — is the risk manageable or does it exceed acceptable thresholds?
7. End your response with your verdict on a new line: "VERDICT: GO" or "VERDICT: HOLD" or "VERDICT: AVOID"

Write 4-6 sentences. Be specific with numbers. No filler phrases.""",
    },
    "cio": {
        "name": "CIO VERDICT",
        "icon": "👁",
        "role": "chief investment officer",
        "instruction": """You are the Chief Investment Officer synthesising the full bull/bear/risk debate for a crypto trade decision.

Your analysis MUST:
1. Open with a scorecard summary — "VPRTS: V{v}/5, P{p}/3, R{r}/2, T{t}/3, S{s}/3 = {total}/16" style statement
2. Weigh the bull case vs bear case — which argument is stronger and why?
3. Reference Kronos AI's forecast direction and conviction — does the AI model align with the signal?
4. State whether the Fear & Greed Index supports or contradicts the trade
5. Deliver a clear, authoritative final verdict with specific reasoning — not a hedge, a decision
6. End your response with your verdict on a new line: "VERDICT: STRONG BUY" or "VERDICT: BUY" or "VERDICT: HOLD" or "VERDICT: SELL" or "VERDICT: AVOID"

Write 5-7 sentences. Be authoritative and specific. No filler phrases.""",
    },
}


def _build_context(symbol: str, ctx: dict) -> str:
    """Build the rich shared market context string fed to all agents."""
    # VPRTS components
    v_score = ctx.get("v_score", ctx.get("V", 0))
    p_score = ctx.get("p_score", ctx.get("P", 0))
    r_score = ctx.get("r_score", ctx.get("R", 0))
    t_score = ctx.get("t_score", ctx.get("T", 0))
    s_score = ctx.get("s_score", ctx.get("S", 0))
    total   = ctx.get("total", 0)

    # Market structure
    close   = ctx.get("close", 0)
    ema20   = ctx.get("ema20", 0)
    ema50   = ctx.get("ema50", 0)
    ema200  = ctx.get("ema200", 0)
    vwap    = ctx.get("vwap", 0)
    bb_upper = ctx.get("bb_upper", 0)
    bb_lower = ctx.get("bb_lower", 0)

    # Timing
    rsi     = ctx.get("rsi", 50)
    adx     = ctx.get("adx", 0)
    atr     = ctx.get("atr", 0)
    rel_vol = ctx.get("rel_volume", ctx.get("rv", 1.0))
    atr_pct = (atr / close * 100) if close else 0

    # Trade setup
    entry   = ctx.get("entry")
    stop    = ctx.get("stop")
    target  = ctx.get("target")
    rr      = ctx.get("rr_ratio")
    stop_pct = ctx.get("stop_dist_pct")

    # Signals arrays
    bull_signals = ctx.get("bull_signals", [])
    bear_signals = ctx.get("bear_signals", [])
    bull_pct     = ctx.get("bull_pct", ctx.get("bull_conviction", 0))
    bear_pct     = ctx.get("bear_pct", ctx.get("bear_conviction", 0))

    # Kronos forecast
    kron_dir      = ctx.get("kron_direction", "N/A")
    kron_move     = ctx.get("kron_move_pct", None)
    kron_green    = ctx.get("kron_green_pct", None)
    kron_quality  = ctx.get("kron_trade_quality", "N/A")
    kron_bull_conv = ctx.get("kron_bull_conviction", "N/A")
    kron_bear_conv = ctx.get("kron_bear_conviction", "N/A")
    kron_momentum  = ctx.get("kron_momentum", "N/A")

    # Fear & Greed
    fg_val   = ctx.get("fg_value", None)
    fg_label = ctx.get("fg_label", "N/A")

    # EMA stack analysis
    ema_above_20  = close > ema20  if close and ema20  else None
    ema_above_50  = close > ema50  if close and ema50  else None
    ema_above_200 = close > ema200 if close and ema200 else None
    above_vwap    = close > vwap   if close and vwap   else None

    # BB position
    bb_range = bb_upper - bb_lower if bb_upper and bb_lower else 0
    bb_pos_pct = ((close - bb_lower) / bb_range * 100) if bb_range else None

    lines = [
        f"SYMBOL: {symbol}/USDT",
        f"INTERVAL: {ctx.get('interval', '1H')}",
        "",
        f"═══ VPRTS SCORE: {total}/16 — {ctx.get('signal', 'NO SIGNAL')} ═══",
        f"  V (Volume,  max 5): {v_score}/5  |  Relative Volume = {rel_vol:.2f}x",
        f"  P (Momentum, max 3): {p_score}/3  |  24H Change = {ctx.get('change_24h', 0):+.2f}%",
        f"  R (Range Pos, max 2): {r_score}/2  |  BB position = {f'{bb_pos_pct:.0f}%' if bb_pos_pct is not None else 'N/A'}",
        f"  T (Trend,   max 3): {t_score}/3  |  ADX = {adx:.1f}",
        f"  S (Social,  max 3): {s_score}/3",
        f"  Direction: {ctx.get('direction', 'NEUTRAL')}",
        "",
        "═══ MARKET STRUCTURE ═══",
        f"  Close: ${close:,.4f}",
        f"  EMA20:  ${ema20:,.4f}  → price {'ABOVE' if ema_above_20 else 'BELOW' if ema_above_20 is not None else 'N/A'}",
        f"  EMA50:  ${ema50:,.4f}  → price {'ABOVE' if ema_above_50 else 'BELOW' if ema_above_50 is not None else 'N/A'}",
        f"  EMA200: ${ema200:,.4f}  → price {'ABOVE' if ema_above_200 else 'BELOW' if ema_above_200 is not None else 'N/A'}",
        f"  VWAP:   ${vwap:,.4f}  → price {'ABOVE' if above_vwap else 'BELOW' if above_vwap is not None else 'N/A'}",
        f"  BB Upper: ${bb_upper:,.4f}  |  BB Lower: ${bb_lower:,.4f}",
        f"  BB position: {f'{bb_pos_pct:.0f}% of band width' if bb_pos_pct is not None else 'N/A'}",
        "",
        "═══ TIMING INDICATORS ═══",
        f"  RSI 14: {rsi:.1f}  ({'Overbought' if rsi >= 70 else 'Oversold' if rsi <= 30 else 'Neutral'})",
        f"  ADX 14: {adx:.1f}  ({'Trending strongly' if adx >= 25 else 'Weak trend / ranging'})",
        f"  ATR 14: ${atr:.4f}  ({atr_pct:.2f}% of price)",
        f"  Relative Volume: {rel_vol:.2f}x",
    ]

    if entry or stop or target:
        lines += [
            "",
            "═══ TRADE SETUP ═══",
            f"  Entry:  ${entry:,.4f}" if entry else "  Entry: N/A",
            f"  Stop:   ${stop:,.4f}  ({f'{stop_pct:.2f}% below entry' if stop_pct else 'N/A'})" if stop else "  Stop: N/A",
            f"  Target: ${target:,.4f}" if target else "  Target: N/A",
            f"  R/R Ratio: {rr:.2f}:1" if rr else "  R/R: N/A",
        ]

    if bull_signals or bear_signals:
        lines += ["", "═══ CONVICTION SIGNALS ═══"]
        lines += [f"  Bull conviction: {bull_pct:.0f}%  |  Bear conviction: {bear_pct:.0f}%"]
        if bull_signals:
            lines.append("  BULL signals: " + " · ".join(bull_signals[:5]))
        if bear_signals:
            lines.append("  BEAR signals: " + " · ".join(bear_signals[:5]))

    if kron_dir != "N/A":
        lines += [
            "",
            "═══ KRONOS AI FORECAST ═══",
            f"  Direction: {kron_dir}  |  Expected move: {f'{kron_move:+.2f}%' if kron_move is not None else 'N/A'}",
            f"  Green candle probability: {f'{kron_green:.0f}%' if kron_green is not None else 'N/A'}",
            f"  Momentum: {kron_momentum}  |  Trade quality: {kron_quality}",
            f"  Bull conviction: {kron_bull_conv}  |  Bear conviction: {kron_bear_conv}",
        ]

    if fg_val is not None:
        lines += [
            "",
            "═══ SENTIMENT ═══",
            f"  Fear & Greed Index: {fg_val} ({fg_label})",
        ]

    news = ctx.get("news_context", "")
    if news and news != "No live news available.":
        lines += ["", "═══ LIVE NEWS ═══", news[:400]]

    return "\n".join(lines)


async def run_agent_council(symbol: str, signal_ctx: dict) -> list[dict]:
    """
    Run all 4 agents and return their verdicts.
    Falls back to template responses if API key not set.
    """
    if not ANTHROPIC_KEY:
        return _fallback_agents(symbol, signal_ctx)

    context = _build_context(symbol, signal_ctx)
    client  = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    results = []

    for agent_key, agent in AGENTS.items():
        try:
            msg = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system=agent["instruction"],
                messages=[{
                    "role": "user",
                    "content": f"Analyse this setup and give your detailed verdict:\n\n{context}"
                }]
            )
            text = msg.content[0].text.strip()

            # Extract verdict from the dedicated VERDICT: line first, then fallback scan
            verdict = _extract_verdict(text, agent_key)

            results.append({
                "key":     agent_key,
                "name":    agent["name"],
                "icon":    agent["icon"],
                "text":    text,
                "verdict": verdict,
            })
        except Exception as e:
            logger.warning(f"Agent {agent_key} error: {e}")
            results.append(_fallback_agent(agent_key, symbol, signal_ctx))

    return results


def _extract_verdict(text: str, agent_key: str) -> str:
    """Extract the final verdict — checks for 'VERDICT: X' line first, then scans full text."""
    # Check for explicit VERDICT: line
    for line in reversed(text.splitlines()):
        line = line.strip().upper()
        if line.startswith("VERDICT:"):
            v = line.replace("VERDICT:", "").strip()
            if "STRONG BUY" in v: return "STRONG BUY"
            if "AVOID"  in v: return "AVOID"
            if "SELL"   in v: return "SELL"
            if "BUY"    in v: return "BUY"
            if "HOLD"   in v: return "HOLD"
            if "GO"     in v: return "GO"
    # Fallback: scan full text
    upper = text.upper()
    if "STRONG BUY" in upper: return "STRONG BUY"
    if "AVOID"  in upper: return "AVOID"
    if "SELL"   in upper: return "SELL"
    if "BUY"    in upper: return "BUY"
    if "HOLD"   in upper: return "HOLD"
    if "GO"     in upper: return "GO"
    defaults = {"bull": "HOLD", "bear": "HOLD", "risk": "HOLD", "cio": "HOLD"}
    return defaults.get(agent_key, "HOLD")


def _fallback_agent(agent_key: str, symbol: str, ctx: dict) -> dict:
    agent   = AGENTS[agent_key]
    score   = ctx.get("total", 0)
    rsi     = ctx.get("rsi", 50)
    adx     = ctx.get("adx", 0)
    ema     = ctx.get("ema_stack", False)
    chg     = ctx.get("change_24h", 0)
    atr     = ctx.get("atr", 0)
    stop    = ctx.get("stop")
    close   = ctx.get("close", 0)
    rel_vol = ctx.get("rel_volume", ctx.get("rv", 1.0))
    v_score = ctx.get("v_score", ctx.get("V", 0))
    p_score = ctx.get("p_score", ctx.get("P", 0))
    r_score = ctx.get("r_score", ctx.get("R", 0))
    t_score = ctx.get("t_score", ctx.get("T", 0))
    s_score = ctx.get("s_score", ctx.get("S", 0))
    rr      = ctx.get("rr_ratio")
    bull_signals = ctx.get("bull_signals", [])
    bear_signals = ctx.get("bear_signals", [])
    ema200  = ctx.get("ema200", 0)
    vwap    = ctx.get("vwap", 0)
    bb_upper = ctx.get("bb_upper", 0)
    atr_pct  = (atr / close * 100) if close else 0

    texts = {
        "bull": (
            f"VPRTS score is {score}/16 with Volume at {v_score}/5 ({rel_vol:.1f}x relative volume) and Momentum at {p_score}/3 on a {chg:+.2f}% 24H move. "
            + (f"EMA stack is confirmed bullish — price above EMA20, EMA50{', and EMA200 macro trend intact' if ema200 and close > ema200 else ''} — a classic accumulation structure. "
               if ema else
               f"EMA stack is not yet confirmed: price needs to reclaim EMA20 before a clean entry. ")
            + (f"RSI at {rsi:.0f} leaves room to run without hitting overbought territory. "
               if rsi < 65 else
               f"RSI at {rsi:.0f} is elevated but ADX at {adx:.0f} suggests trend strength, not exhaustion. ")
            + (f"Bull signals include: {', '.join(bull_signals[:3])}. " if bull_signals else "")
            + (f"With a {rr:.1f}:1 R/R and VWAP held at ${vwap:,.4f}, the risk-adjusted case for a long is credible."
               if rr and vwap else "The setup warrants monitoring for a cleaner entry signal.")
            + f"\nVERDICT: {'BUY' if score >= 9 and ema else 'HOLD'}"
        ),

        "bear": (
            f"VPRTS score of {score}/16 means {16 - score} points of potential upside are missing — "
            + (f"Trend component scores only {t_score}/3 with ADX at {adx:.0f}, indicating a weak or ranging market. "
               if adx < 20 else
               f"however ADX at {adx:.0f} shows trend strength — bears need a catalyst to reverse this momentum. ")
            + (f"RSI at {rsi:.0f} is in overbought territory — a pullback to the mean is statistically probable. "
               if rsi >= 68 else
               f"RSI at {rsi:.0f} is not overbought, limiting the immediate reversal case. ")
            + (f"Price pressing the BB upper at ${bb_upper:,.4f} suggests mean-reversion risk if volume dries up. "
               if bb_upper and close >= bb_upper * 0.98 else "")
            + (f"Bear signals include: {', '.join(bear_signals[:3])}. " if bear_signals else "")
            + f"R-score of {r_score}/2 suggests price is {'extended — fade candidates outperform here' if r_score <= 1 else 'within a normal range'}, and any volume drop should be treated as a red flag."
            + f"\nVERDICT: {'SELL' if rsi >= 75 or score < 5 else 'HOLD'}"
        ),

        "risk": (
            f"ATR at ${atr:.4f} ({atr_pct:.2f}% of price) sets the volatility baseline for position sizing — "
            + (f"a 1.5× ATR stop would be ${atr * 1.5:.4f} wide. "
               if atr else "ATR data unavailable, use caution. ")
            + (f"ADX at {adx:.0f} confirms a {'trending' if adx >= 25 else 'ranging'} regime — "
               + ("breakout entries carry higher follow-through probability. " if adx >= 25 else
                  "breakout trades in ranging markets have poor edge; prefer mean-reversion. "))
            + (f"Proposed stop at ${stop:,.4f} is {ctx.get('stop_dist_pct', 0):.2f}% below entry — "
               + ("tight relative to ATR, risk of premature stop-out. " if ctx.get("stop_dist_pct", 0) < atr_pct else
                  "reasonable given current volatility. ")
               if stop else "No stop level available — this is a risk flag. ")
            + (f"R/R of {rr:.1f}:1 {'meets minimum thresholds for execution.' if rr and rr >= 1.5 else 'is below the 1.5:1 minimum — reduce size or pass.' if rr else 'is unknown — cannot size position.'}")
            + (f" Score of {score}/16 is borderline — reduce position size to 50% of normal allocation." if 5 <= score <= 8 else "")
            + f"\nVERDICT: {'GO' if score >= 9 and rr and rr >= 1.5 else 'HOLD' if score >= 5 else 'AVOID'}"
        ),

        "cio": (
            f"Scorecard: V={v_score}/5, P={p_score}/3, R={r_score}/2, T={t_score}/3, S={s_score}/3 — total {score}/16 ({ctx.get('signal', 'NO SIGNAL')}). "
            + (f"The bull case is stronger: EMA stack confirmed, {rel_vol:.1f}x volume, and RSI at {rsi:.0f} with room to run. "
               if score >= 9 and ema else
               f"Neither bull nor bear has a decisive edge at {score}/16 — the signal is insufficient for high-conviction execution. ")
            + (f"Kronos AI forecasts a {ctx.get('kron_direction', 'neutral')} move with {'green candle bias' if (ctx.get('kron_green_pct', 50) or 50) > 55 else 'bearish candle bias'}, aligning {'with' if (ctx.get('kron_direction','NEUTRAL') == ctx.get('direction','NEUTRAL')) else 'against'} the VPRTS direction. "
               if ctx.get("kron_direction") else "")
            + (f"Fear & Greed at {ctx.get('fg_value', 'N/A')} ({ctx.get('fg_label', '')}) {'supports contrarian longs' if (ctx.get('fg_value') or 50) < 30 else 'signals caution at elevated sentiment' if (ctx.get('fg_value') or 50) > 70 else 'is neutral — no additional edge from sentiment'}. ")
            + (f"Final decision: execute at ${ctx.get('entry', 0):,.4f} with stop ${ctx.get('stop', 0):,.4f} targeting ${ctx.get('target', 0):,.4f} for a {rr:.1f}:1 return."
               if score >= 9 and ctx.get("entry") and rr else
               f"Final decision: stand aside and wait for score ≥ 9/16 before committing capital.")
            + f"\nVERDICT: {'STRONG BUY' if score >= 12 else 'BUY' if score >= 9 and ema else 'HOLD' if score >= 5 else 'AVOID'}"
        ),
    }

    verdicts = {
        "bull": "STRONG BUY" if score >= 12 else "BUY" if score >= 9 else "HOLD" if score >= 5 else "HOLD",
        "bear": "SELL" if rsi >= 75 else "HOLD",
        "risk": "GO"  if score >= 9 and rr and rr >= 1.5 else "HOLD" if score >= 5 else "AVOID",
        "cio":  "STRONG BUY" if score >= 12 else "BUY" if score >= 9 and ema else "HOLD" if score >= 5 else "AVOID",
    }

    return {
        "key":     agent_key,
        "name":    agent["name"],
        "icon":    agent["icon"],
        "text":    texts[agent_key],
        "verdict": verdicts[agent_key],
    }


def _fallback_agents(symbol: str, ctx: dict) -> list[dict]:
    return [_fallback_agent(k, symbol, ctx) for k in AGENTS.keys()]
