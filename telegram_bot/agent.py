"""
Claude-powered CS + crypto Q&A agent.
Uses Anthropic claude-3-5-haiku for fast, cost-effective responses.
Falls back to rule-based if ANTHROPIC_API_KEY is not set.
"""
import os
import re
import anthropic

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SYSTEM_PROMPT = """You are the Crypto Sniper support agent — sharp, direct, and on-brand.
Crypto Sniper is a real-time crypto signal engine at https://crypto-sniper.app that scores coins using VPRT (Volume, Momentum, Range, Trend) methodology out of 16 points. STRONG BUY signals require 9+/16.

Your role:
1. CUSTOMER SUPPORT — handle complaints, subscription queries, bug reports, payment issues, and feature requests about Crypto Sniper professionally and efficiently.
2. CRYPTO Q&A — answer general crypto trading questions, explain technical analysis concepts, discuss market conditions.
3. SIGNAL EXPLAINER — explain what VPRT scores mean, how to read signals, what STRONG BUY vs MODERATE means.

Tone: Confident, sharp, no fluff. You're not a cheerful chatbot — you're a trading desk assistant.
Keep responses concise. Use short paragraphs. Use plain text (no markdown — Telegram renders it differently).

Key info:
- App: https://crypto-sniper.app
- Scoring: V (Volume, max 5) + P (Momentum, max 3) + R (Range, max 2) + T (Trend, max 3) = 13 base, max 16 total
- STRONG BUY: 9+/16 | MODERATE: 5-8 | WEAK/NO SIGNAL: <5
- Daily scanner runs at 8:00 AM AEST scanning top 200 coins by market cap
- Kronos AI: provides expected move, target price, agent debate (Bull/Bear/Risk/CIO verdicts)
- Payment: Solana wallet or 340+ crypto options
- Support contact: support@crypto-sniper.app (handled by Kai)

ESCALATION TRIGGER — if the user:
- Mentions a payment issue you cannot resolve
- Reports a persistent technical bug you cannot diagnose
- Is angry/frustrated after 2+ exchanges
- Asks to speak to a human / the founder

...respond with exactly: [ESCALATE: <one-line summary of the issue>]
This will trigger the escalation system and Kai will follow up directly.

ANALYSE TRIGGER — if the user asks to analyse a coin (e.g. "analyse BTC", "what's the signal for ETH", "check SOL 4H"):
Respond with exactly: [ANALYSE: SYMBOL INTERVAL]
Example: [ANALYSE: BTC 1H] or [ANALYSE: ETH 4H]
Default interval is 1H if not specified.

Do not make up data. If you don't know something, say so and offer to escalate."""


async def get_agent_response(
    user_message: str,
    history: list[dict],
    user: dict | None
) -> str:
    if not ANTHROPIC_API_KEY:
        return _rule_based(user_message)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build context about this user — email intentionally omitted to prevent exposure
    user_context = ""
    if user:
        name = user.get("first_name", "")
        tier = user.get("tier", "free")
        has_email = bool(user.get("email"))
        user_context = f"\nCurrent user: {name} | Tier: {tier.upper()} | Account linked: {'yes' if has_email else 'no'}"

    system = SYSTEM_PROMPT + user_context

    # Build message history for Claude
    messages = []
    for m in history[-12:]:  # last 12 messages for context
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=600,
            system=system,
            messages=messages
        )
        return response.content[0].text.strip()
    except anthropic.NotFoundError:
        # Fallback to older model if haiku not available on this key
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=600,
                system=system,
                messages=messages
            )
            return response.content[0].text.strip()
        except Exception as e2:
            import logging
            logging.getLogger(__name__).error(f"Claude fallback failed: {e2}")
            return _rule_based(messages[-1]["content"])
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Claude error: {type(e).__name__}: {e}")
        return _rule_based(messages[-1]["content"])


def _rule_based(text: str) -> str:
    """Minimal fallback when no API key is configured."""
    t = text.lower()
    if any(w in t for w in ["analyse", "analyze", "signal", "score", "check"]):
        # Extract symbol
        words = text.upper().split()
        for w in words:
            if w.isalpha() and 2 <= len(w) <= 8 and w not in {"ANALYSE","ANALYZE","SIGNAL","CHECK","THE","FOR","WHAT","IS","GET"}:
                return f"[ANALYSE: {w} 1H]"
        return "Which coin? Send me the symbol — e.g. /analyse BTC"
    if any(w in t for w in ["payment", "paid", "subscription", "pro", "upgrade"]):
        return "For subscription or payment issues, email subroh.iyer@gmail.com directly and we'll sort it within 24H."
    if any(w in t for w in ["bug", "broken", "error", "not working", "crash"]):
        return "Sorry to hear that. Can you describe exactly what happened and which device/browser you were using? I'll log it."
    if any(w in t for w in ["human", "person", "founder", "real person"]):
        return "[ESCALATE: User requested human support]"
    return (
        "I'm the Crypto Sniper support agent. Try:\n"
        "/analyse BTC — get a live signal\n"
        "/status — check your account\n"
        "/help — full command list\n\n"
        "Or just describe your issue and I'll help."
    )


def extract_analyse_command(text: str) -> tuple[str, str] | None:
    """Parse [ANALYSE: SYMBOL INTERVAL] from agent response."""
    m = re.search(r'\[ANALYSE:\s*([A-Z0-9]+)\s*([0-9]+[mMhHdD])?\]', text)
    if m:
        symbol = m.group(1)
        interval = m.group(2) or "1H"
        return symbol.upper(), interval.upper()
    return None


def extract_escalation(text: str) -> str | None:
    """Parse [ESCALATE: summary] from agent response."""
    m = re.search(r'\[ESCALATE:\s*(.+?)\]', text)
    return m.group(1).strip() if m else None
