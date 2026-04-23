"""
agents.py — 4-Agent Council for Crypto Sniper
Agents: Bull Case, Bear Case, Risk Manager, CIO Verdict
Powered by Claude claude-haiku-4-5-20251001 via Anthropic API
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
        "instruction": "You are a bullish crypto analyst. Find the strongest reasons why this setup could be a buy. Reference the EMA structure, macro context, and any positive signals. Be direct and concise — 2-3 sentences max. End with your verdict: BUY or HOLD.",
    },
    "bear": {
        "name": "BEAR CASE",
        "icon": "🐻",
        "role": "bearish crypto analyst",
        "instruction": "You are a bearish crypto analyst. Find the strongest reasons why this setup is risky or a sell. Reference overbought conditions, weak momentum, news risks. Be direct and concise — 2-3 sentences max. End with your verdict: SELL or HOLD.",
    },
    "risk": {
        "name": "RISK MANAGER",
        "icon": "🛡",
        "role": "risk manager",
        "instruction": "You are a risk manager. Focus only on position sizing, stop placement, and risk management rules. Reference ATR, ADX, and market structure. Give specific numbers. Be direct — 2-3 sentences max. End with your verdict: HOLD (if not a strong setup) or GO (if risk is manageable).",
    },
    "cio": {
        "name": "CIO VERDICT",
        "icon": "👁",
        "role": "chief investment officer",
        "instruction": "You are the CIO. Synthesise all signals into a final verdict. If score < 5, say so clearly and tell the trader to preserve capital. If score >= 9, give high conviction. Reference the total score. Be authoritative — 2-3 sentences max. End with your final verdict: BUY / HOLD / SELL / AVOID.",
    },
}


def _build_context(symbol: str, ctx: dict) -> str:
    """Build the shared market context string fed to all agents."""
    return f"""
SYMBOL: {symbol}/USDT
INTERVAL: {ctx.get('interval', '1H')}
SIGNAL SCORE: {ctx.get('total', 0)}/16 — {ctx.get('signal', 'NO SIGNAL')}
DIRECTION: {ctx.get('direction', 'NEUTRAL')}

PRICE DATA:
  Close: ${ctx.get('close', 0):,.2f}
  24H Change: {ctx.get('change_24h', 0):+.2f}%

TECHNICAL:
  RSI: {ctx.get('rsi', 50):.1f}
  ADX: {ctx.get('adx', 0):.1f}
  ATR: {ctx.get('atr', 0):.2f}
  EMA Stack: {'✓ Bullish (price > EMA20 > EMA50)' if ctx.get('ema_stack') else '✗ Not confirmed'}
  BB Upper: ${ctx.get('bb_upper', 0):,.2f}
  
TRADE SETUP:
  Entry: ${ctx.get('entry', 0) or 'N/A'}
  Stop:  ${ctx.get('stop', 0) or 'N/A'}
  Target: ${ctx.get('target', 0) or 'N/A'}
  R/R: {ctx.get('rr_ratio', 0) or 'N/A'}

LIVE CONTEXT:
{ctx.get('news_context', 'No live news available.')}
""".strip()


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
                max_tokens=150,
                system=agent["instruction"],
                messages=[{
                    "role": "user",
                    "content": f"Analyse this setup and give your verdict:\n\n{context}"
                }]
            )
            text = msg.content[0].text.strip()

            # Extract verdict from last word/sentence
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
    """Extract the final verdict word from agent response."""
    upper = text.upper()
    if "STRONG BUY" in upper: return "STRONG BUY"
    if "AVOID"  in upper: return "AVOID"
    if "SELL"   in upper: return "SELL"
    if "BUY"    in upper: return "BUY"
    if "HOLD"   in upper: return "HOLD"
    if "GO"     in upper: return "GO"
    # Default by agent
    defaults = {"bull": "HOLD", "bear": "HOLD", "risk": "HOLD", "cio": "HOLD"}
    return defaults.get(agent_key, "HOLD")


def _fallback_agent(agent_key: str, symbol: str, ctx: dict) -> dict:
    agent = AGENTS[agent_key]
    score = ctx.get("total", 0)
    rsi   = ctx.get("rsi", 50)
    adx   = ctx.get("adx", 0)
    ema   = ctx.get("ema_stack", False)
    chg   = ctx.get("change_24h", 0)
    atr   = ctx.get("atr", 0)
    stop  = ctx.get("stop")
    close = ctx.get("close", 0)

    texts = {
        "bull": (
            f"EMA20 > EMA50 confirms bullish structure. " if ema else f"EMA structure not confirmed — wait for stack. "
        ) + (f"Price above EMA200 — macro trend intact." if ctx.get("ema200") and close > ctx.get("ema200",0) else "Macro trend unclear."),

        "bear": (
            f"RSI {rsi:.0f} is {'overbought — fade the rally.' if rsi >= 70 else 'neutral.'} "
        ) + (f"Weak ATR move — no real momentum behind this move." if ctx.get("rel_volume", 1) < 1.5 else "Volume backing the move."),

        "risk": (
            f"ATR at {atr:.2f} — size positions accordingly. "
        ) + (f"Suggested stop: {stop:,.2f} (1.5× ATR below close). " if stop else "No clear stop level. "
        ) + (f"ADX {adx:.0f} — {'trending' if adx >= 25 else 'ranging'} market conditions apply."),

        "cio": (
            f"Score {score}/16 — {'setup does not meet minimum thresholds.' if score < 5 else 'building momentum.' if score < 9 else 'strong setup — high conviction.'} "
        ) + f"RSI {rsi:.0f}, ADX {adx:.0f}. {'Preserve capital and wait for a proper signal.' if score < 5 else 'Proceed with discipline.'}"
    }

    verdicts = {
        "bull": "HOLD" if score < 5 else "BUY",
        "bear": "SELL" if rsi >= 75 else "HOLD",
        "risk": "HOLD" if score < 5 else "GO",
        "cio":  "AVOID" if score < 5 else "HOLD" if score < 9 else "BUY",
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
