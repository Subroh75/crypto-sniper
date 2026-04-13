import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import streamlit as st


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Crypto Guru",
    page_icon="🔮",
    layout="wide",
)


# =========================================================
# DATA MODELS
# =========================================================
@dataclass
class EngineSignal:
    label: str
    bias: str
    confidence: str
    score: float
    summary: str


@dataclass
class FinalResponse:
    title: str
    answer: str
    signal_bias: str
    signal_confidence: str
    risk_note: str
    next_action: str
    reasons: List[str]
    detailed_analysis: str
    related_prompts: List[str]


# =========================================================
# APP STYLES
# =========================================================
def inject_styles() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg: #0b1020;
                --panel: #11172a;
                --panel-2: #0f1525;
                --border: rgba(255,255,255,0.08);
                --text: #f5f7fb;
                --muted: #aeb8d0;
                --accent: #7c9cff;
                --accent-2: #9f7cff;
                --good: #43d787;
                --warn: #ffb84d;
                --bad: #ff6b6b;
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(124,156,255,0.12), transparent 28%),
                    radial-gradient(circle at top right, rgba(159,124,255,0.10), transparent 24%),
                    linear-gradient(180deg, #08101f 0%, #0b1020 100%);
            }

            .block-container {
                max-width: 1050px;
                padding-top: 2.2rem;
                padding-bottom: 3rem;
            }

            .hero-wrap {
                text-align: center;
                padding: 1.8rem 0 1.2rem 0;
            }

            .hero-badge {
                display: inline-block;
                padding: 0.35rem 0.8rem;
                border-radius: 999px;
                background: rgba(124,156,255,0.10);
                border: 1px solid rgba(124,156,255,0.22);
                color: #dbe4ff;
                font-size: 0.85rem;
                font-weight: 600;
                margin-bottom: 1rem;
            }

            .hero-title {
                color: white;
                font-size: 3rem;
                font-weight: 800;
                line-height: 1.08;
                margin-bottom: 0.55rem;
                letter-spacing: -0.02em;
            }

            .hero-subtitle {
                color: var(--muted);
                font-size: 1.08rem;
                max-width: 760px;
                margin: 0 auto 1.4rem auto;
                line-height: 1.55;
            }

            .query-card {
                background: linear-gradient(180deg, rgba(17,23,42,0.92) 0%, rgba(12,18,34,0.98) 100%);
                border: 1px solid var(--border);
                border-radius: 22px;
                padding: 1rem 1rem 0.75rem 1rem;
                box-shadow: 0 18px 50px rgba(0,0,0,0.28);
                margin-bottom: 1.3rem;
            }

            .section-card {
                background: linear-gradient(180deg, rgba(17,23,42,0.94) 0%, rgba(12,18,34,0.98) 100%);
                border: 1px solid var(--border);
                border-radius: 20px;
                padding: 1.1rem 1.2rem;
                margin-bottom: 1rem;
                box-shadow: 0 12px 36px rgba(0,0,0,0.18);
            }

            .card-title {
                color: #ffffff;
                font-weight: 700;
                font-size: 1.05rem;
                margin-bottom: 0.65rem;
            }

            .answer-text {
                color: #eef2ff;
                font-size: 1.06rem;
                line-height: 1.7;
                margin: 0;
            }

            .mini-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 0.8rem;
                margin-top: 0.2rem;
            }

            .mini-box {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.07);
                border-radius: 16px;
                padding: 0.85rem 0.9rem;
            }

            .mini-label {
                color: var(--muted);
                font-size: 0.82rem;
                margin-bottom: 0.35rem;
            }

            .mini-value {
                color: white;
                font-size: 0.98rem;
                font-weight: 700;
                line-height: 1.35;
            }

            .reason-item {
                color: #e7ecfb;
                line-height: 1.65;
                margin-bottom: 0.55rem;
            }

            .engine-pill-row {
                display: flex;
                gap: 0.55rem;
                flex-wrap: wrap;
                margin-top: 0.2rem;
            }

            .engine-pill {
                display: inline-block;
                padding: 0.45rem 0.75rem;
                border-radius: 999px;
                background: rgba(255,255,255,0.04);
                border: 1px solid rgba(255,255,255,0.08);
                color: #dfe7ff;
                font-size: 0.84rem;
                font-weight: 600;
            }

            .examples-title {
                color: #dfe7ff;
                font-size: 0.95rem;
                font-weight: 700;
                margin-bottom: 0.7rem;
                margin-top: 0.15rem;
            }

            .footer-note {
                color: var(--muted);
                text-align: center;
                font-size: 0.88rem;
                margin-top: 1rem;
            }

            .stTextInput > div > div > input {
                background: rgba(255,255,255,0.04);
                color: white;
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,0.08);
                padding: 0.95rem 1rem;
                font-size: 1rem;
            }

            .stTextInput > div > div > input::placeholder {
                color: #95a1bf;
            }

            .stButton button {
                border-radius: 12px;
                font-weight: 700;
                border: 1px solid rgba(255,255,255,0.08);
                background: linear-gradient(180deg, #7c9cff 0%, #6588ff 100%);
                color: white;
                padding: 0.6rem 1rem;
            }

            .stButton button:hover {
                border: 1px solid rgba(255,255,255,0.10);
                color: white;
            }

            div[data-testid="stExpander"] {
                border: 1px solid rgba(255,255,255,0.08) !important;
                border-radius: 16px !important;
                background: rgba(255,255,255,0.02) !important;
            }

            @media (max-width: 900px) {
                .hero-title {
                    font-size: 2.25rem;
                }

                .mini-grid {
                    grid-template-columns: 1fr 1fr;
                }
            }

            @media (max-width: 640px) {
                .mini-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# STATE
# =========================================================
def init_state() -> None:
    defaults = {
        "selected_prompt": "",
        "query_text": "",
        "last_response": None,
        "last_query": "",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# =========================================================
# QUERY / INTENT HELPERS
# =========================================================
COIN_PATTERN = re.compile(r"\b(BTC|ETH|SOL|XRP|DOGE|ADA|AVAX|LINK|ARB|OP|FET|PEPE|SUI|SEI|WIF|BONK)\b", re.I)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.strip())


def extract_assets(query: str) -> List[str]:
    matches = COIN_PATTERN.findall(query.upper())
    seen = []
    for m in matches:
        if m not in seen:
            seen.append(m)
    return seen


def classify_intent(query: str) -> str:
    q = query.lower()

    comparison_terms = ["compare", "vs", "versus", "stronger than", "better than"]
    momentum_terms = ["momentum", "bullish", "bearish", "trend", "strength", "breakout"]
    watch_terms = ["watch", "worth watching", "watchlist"]
    timing_terms = ["entry", "enter", "buy now", "good time", "timing"]
    narrative_terms = ["narrative", "theme", "sector", "ai tokens", "memes", "rwa", "defi"]
    risk_terms = ["risk", "safe", "danger", "avoid", "risky"]
    wallet_terms = ["wallet", "whale", "on-chain", "smart money"]

    if any(term in q for term in comparison_terms):
        return "comparison"
    if any(term in q for term in wallet_terms):
        return "wallet_activity"
    if any(term in q for term in narrative_terms):
        return "narrative"
    if any(term in q for term in timing_terms):
        return "entry_timing"
    if any(term in q for term in risk_terms):
        return "risk_check"
    if any(term in q for term in watch_terms):
        return "watchlist"
    if any(term in q for term in momentum_terms):
        return "momentum"
    return "coin_analysis"


# =========================================================
# ENGINE STUBS
# Replace these with your real AI Lab / Miro / Kronos logic
# =========================================================
def pseudo_score_from_text(seed_text: str, modifier: int) -> float:
    base = sum(ord(c) for c in seed_text) % 100
    value = (base + modifier) / 10
    return max(4.8, min(9.4, round(value, 1)))


def score_to_bias(score: float) -> str:
    if score >= 8.1:
        return "strong bullish"
    if score >= 7.2:
        return "bullish"
    if score >= 6.4:
        return "constructive"
    if score >= 5.7:
        return "neutral"
    return "cautious"


def score_to_confidence(score: float) -> str:
    if score >= 8.0:
        return "high"
    if score >= 6.7:
        return "medium"
    return "low"


def run_ai_lab(query: str, intent: str, assets: List[str]) -> EngineSignal:
    score = pseudo_score_from_text(query + intent + "ai_lab", 11)
    asset_text = ", ".join(assets) if assets else "the requested setup"
    summary = (
        f"AI Lab interprets {asset_text} as {score_to_bias(score)}, "
        f"with the current structure favoring a focused response instead of a broad market dump."
    )
    return EngineSignal(
        label="AI Lab",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=summary,
    )


def run_miro(query: str, intent: str, assets: List[str]) -> EngineSignal:
    score = pseudo_score_from_text(query + intent + "miro", 19)
    asset_text = ", ".join(assets) if assets else "the asset"
    summary = (
        f"Miro reads the momentum profile for {asset_text} as {score_to_bias(score)}, "
        f"with trend quality and structure shaping the current signal."
    )
    return EngineSignal(
        label="Miro",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=summary,
    )


def run_kronos(query: str, intent: str, assets: List[str]) -> EngineSignal:
    score = pseudo_score_from_text(query + intent + "kronos", 7)
    asset_text = ", ".join(assets) if assets else "the setup"
    summary = (
        f"Kronos views the timing on {asset_text} as {score_to_bias(score)}, "
        f"which helps determine whether this is early, confirmed, or still unstable."
    )
    return EngineSignal(
        label="Kronos",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=summary,
    )


def run_signal_orchestrator(query: str, intent: str, assets: List[str]) -> Dict[str, EngineSignal]:
    # You can customize which engines run for which intent
    signals = {
        "ai_lab": run_ai_lab(query, intent, assets),
        "miro": run_miro(query, intent, assets),
        "kronos": run_kronos(query, intent, assets),
    }
    return signals


# =========================================================
# RESPONSE COMPOSITION
# =========================================================
def summarize_bias(signals: Dict[str, EngineSignal]) -> Tuple[str, str]:
    avg_score = sum(s.score for s in signals.values()) / len(signals)
    return score_to_bias(avg_score), score_to_confidence(avg_score)


def make_risk_note(intent: str, overall_bias: str) -> str:
    if intent == "entry_timing":
        return "Timing can fail quickly if price pushes without confirmation and then reverses."
    if intent == "comparison":
        return "Relative strength can rotate fast, especially when market beta shifts."
    if intent == "wallet_activity":
        return "Wallet flow alone is not enough; copied moves can arrive late and unwind hard."
    if overall_bias in ["strong bullish", "bullish"]:
        return "Momentum can still break down if volume fades or the move gets crowded."
    if overall_bias == "constructive":
        return "This looks promising, but it is not yet a high-conviction confirmation."
    return "Current structure is not clean enough to remove false signal risk."


def make_next_action(intent: str, overall_bias: str) -> str:
    if intent == "comparison":
        return "Use this as a relative-strength decision rather than a blind trade trigger."
    if intent == "watchlist":
        return "Keep it on watch and wait for cleaner confirmation before acting aggressively."
    if intent == "entry_timing":
        return "Treat this as a timing read; wait for confirmation instead of forcing an entry."
    if overall_bias in ["strong bullish", "bullish"]:
        return "Good candidate to monitor closely for confirmation or continuation."
    if overall_bias == "constructive":
        return "Watchlist candidate rather than a high-conviction immediate setup."
    return "Stay selective and avoid overcommitting until the structure improves."


def build_direct_answer(
    query: str,
    intent: str,
    assets: List[str],
    overall_bias: str,
    overall_confidence: str,
) -> str:
    asset_text = ", ".join(assets) if assets else "the requested asset"

    if intent == "comparison" and len(assets) >= 2:
        return (
            f"For this query, {assets[0]} currently looks {overall_bias} relative to {assets[1]}, "
            f"with {overall_confidence} conviction across the signal stack. "
            f"This is more useful as a relative-strength read than a blind entry call."
        )

    if intent == "entry_timing":
        return (
            f"{asset_text} currently reads as {overall_bias} with {overall_confidence} confidence, "
            f"but this should be treated as a timing setup rather than an automatic buy signal."
        )

    if intent == "watchlist":
        return (
            f"{asset_text} looks like a {overall_bias} watchlist candidate with {overall_confidence} confidence. "
            f"It is worth monitoring, but not necessarily forcing right now."
        )

    if intent == "wallet_activity":
        return (
            f"The wallet-driven read on {asset_text} is {overall_bias} with {overall_confidence} confidence, "
            f"but it should be confirmed with structure and timing before acting."
        )

    if intent == "narrative":
        return (
            f"The narrative setup around {asset_text} appears {overall_bias} with {overall_confidence} confidence, "
            f"which suggests interest is present but still needs confirmation through price behavior."
        )

    return (
        f"{asset_text} currently reads as {overall_bias} with {overall_confidence} confidence across AI Lab, "
        f"Miro, and Kronos. The setup is best understood as a focused signal read rather than a full market dump."
    )


def build_reasons(signals: Dict[str, EngineSignal]) -> List[str]:
    return [
        f"AI Lab: {signals['ai_lab'].summary}",
        f"Miro: {signals['miro'].summary}",
        f"Kronos: {signals['kronos'].summary}",
    ]


def build_detailed_analysis(
    query: str,
    intent: str,
    assets: List[str],
    signals: Dict[str, EngineSignal],
    overall_bias: str,
) -> str:
    asset_text = ", ".join(assets) if assets else "the asset"
    return (
        f"This response was generated from a query-first workflow for '{query}'. "
        f"The system classified the request as '{intent}' and used AI Lab, Miro, and Kronos as internal signal engines. "
        f"For {asset_text}, the blended read is {overall_bias}. "
        f"AI Lab contributed contextual reasoning, Miro contributed structure and momentum framing, "
        f"and Kronos contributed timing quality. "
        f"The final output is intentionally concise so the client only sees what was requested, "
        f"with deeper analysis available on demand."
    )


def build_related_prompts(intent: str, assets: List[str]) -> List[str]:
    primary = assets[0] if assets else "this token"

    suggestions = {
        "coin_analysis": [
            f"Is {primary} bullish right now?",
            f"Should I watch {primary} this week?",
            f"What is the risk on {primary} here?",
        ],
        "comparison": [
            "Which one has cleaner momentum right now?",
            "Which is better for short-term strength?",
            "Give me the safer setup between the two.",
        ],
        "entry_timing": [
            f"Is now too early for {primary}?",
            f"What would confirm an entry on {primary}?",
            f"Should I wait for better timing on {primary}?",
        ],
        "watchlist": [
            f"Compare {primary} with a stronger alternative.",
            f"What would upgrade {primary} into a high-conviction setup?",
            f"Show me the risk case for {primary}.",
        ],
        "wallet_activity": [
            "Is smart money actually accumulating this?",
            "Does on-chain activity confirm the move?",
            "Is this whale flow worth following?",
        ],
        "narrative": [
            "Which tokens in this theme look strongest?",
            "Is this narrative early or crowded?",
            "Show me the best watchlist names in this sector.",
        ],
        "risk_check": [
            f"What is the invalidation for {primary}?",
            f"Is {primary} getting too crowded?",
            f"What makes this setup risky?",
        ],
        "momentum": [
            f"Does {primary} have breakout strength?",
            f"Is the trend on {primary} confirmed?",
            f"Is {primary} leading or lagging right now?",
        ],
    }

    return suggestions.get(intent, suggestions["coin_analysis"])


def compose_final_response(query: str, intent: str, assets: List[str], signals: Dict[str, EngineSignal]) -> FinalResponse:
    overall_bias, overall_confidence = summarize_bias(signals)
    answer = build_direct_answer(query, intent, assets, overall_bias, overall_confidence)
    risk_note = make_risk_note(intent, overall_bias)
    next_action = make_next_action(intent, overall_bias)
    reasons = build_reasons(signals)
    detailed_analysis = build_detailed_analysis(query, intent, assets, signals, overall_bias)
    related_prompts = build_related_prompts(intent, assets)

    title_asset = ", ".join(assets) if assets else "Crypto Signal"
    title = f"{title_asset} — Focused Signal Output"

    return FinalResponse(
        title=title,
        answer=answer,
        signal_bias=overall_bias,
        signal_confidence=overall_confidence,
        risk_note=risk_note,
        next_action=next_action,
        reasons=reasons,
        detailed_analysis=detailed_analysis,
        related_prompts=related_prompts,
    )


# =========================================================
# QUERY EXECUTION
# =========================================================
def process_query(query: str) -> FinalResponse:
    clean_query = normalize_query(query)
    assets = extract_assets(clean_query)
    intent = classify_intent(clean_query)
    signals = run_signal_orchestrator(clean_query, intent, assets)
    return compose_final_response(clean_query, intent, assets, signals)


# =========================================================
# RENDER HELPERS
# =========================================================
def render_hero() -> None:
    st.markdown(
        """
        <div class="hero-wrap">
            <div class="hero-badge">Query-First Crypto Intelligence</div>
            <div class="hero-title">Ask Crypto Guru</div>
            <div class="hero-subtitle">
                Focused crypto signals without the noise.
                Ask about a coin, setup, comparison, wallet, or narrative —
                and get only the answer you asked for.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_example_prompts() -> None:
    st.markdown('<div class="examples-title">Try one of these</div>', unsafe_allow_html=True)

    prompt_rows = [
        [
            "Is SOL bullish right now?",
            "Compare ETH vs SOL",
            "Should I watch FET this week?",
        ],
        [
            "Is PEPE showing momentum?",
            "What is the risk on ARB here?",
            "Are AI tokens heating up again?",
        ],
    ]

    for row in prompt_rows:
        cols = st.columns(len(row))
        for i, prompt in enumerate(row):
            with cols[i]:
                if st.button(prompt, use_container_width=True):
                    st.session_state.selected_prompt = prompt
                    st.session_state.query_text = prompt


def render_query_box() -> None:
    st.markdown('<div class="query-card">', unsafe_allow_html=True)

    current_value = st.session_state.query_text or st.session_state.selected_prompt
    query = st.text_input(
        "Ask a question",
        value=current_value,
        placeholder="Is SOL bullish right now?",
        label_visibility="collapsed",
        key="query_input_widget",
    )

    col1, col2 = st.columns([4, 1])
    with col1:
        submitted = st.button("Generate signal output", use_container_width=True)
    with col2:
        clear_clicked = st.button("Clear", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if clear_clicked:
        st.session_state.selected_prompt = ""
        st.session_state.query_text = ""
        st.session_state.last_response = None
        st.session_state.last_query = ""
        st.rerun()

    if submitted and query.strip():
        st.session_state.query_text = query.strip()
        st.session_state.last_query = query.strip()

        with st.spinner("Running AI Lab, Miro, and Kronos..."):
            time.sleep(0.4)
            response = process_query(query.strip())

        st.session_state.last_response = response
        st.rerun()


def render_answer_card(response: FinalResponse) -> None:
    st.markdown(
        f"""
        <div class="section-card">
            <div class="card-title">{response.title}</div>
            <p class="answer-text">{response.answer}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_signal_summary(response: FinalResponse) -> None:
    st.markdown(
        f"""
        <div class="section-card">
            <div class="card-title">Signal Read</div>
            <div class="mini-grid">
                <div class="mini-box">
                    <div class="mini-label">Bias</div>
                    <div class="mini-value">{response.signal_bias.title()}</div>
                </div>
                <div class="mini-box">
                    <div class="mini-label">Confidence</div>
                    <div class="mini-value">{response.signal_confidence.title()}</div>
                </div>
                <div class="mini-box">
                    <div class="mini-label">Risk</div>
                    <div class="mini-value">{response.risk_note}</div>
                </div>
                <div class="mini-box">
                    <div class="mini-label">Next Best Action</div>
                    <div class="mini-value">{response.next_action}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_why_section(response: FinalResponse, signals: Dict[str, EngineSignal]) -> None:
    reason_html = "".join([f'<div class="reason-item">• {reason}</div>' for reason in response.reasons])
    engine_html = "".join(
        [
            f'<span class="engine-pill">{signal.label}: {signal.score:.1f} / 10 · {signal.confidence.title()}</span>'
            for signal in signals.values()
        ]
    )

    st.markdown(
        f"""
        <div class="section-card">
            <div class="card-title">Why</div>
            {reason_html}
            <div class="engine-pill-row">{engine_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_expandable_details(response: FinalResponse) -> None:
    with st.expander("Show detailed analysis"):
        st.write(response.detailed_analysis)

    with st.expander("Show follow-up prompts"):
        for prompt in response.related_prompts:
            st.write(f"- {prompt}")


def render_footer() -> None:
    st.markdown(
        """
        <div class="footer-note">
            Crypto Guru is designed to answer the client’s query directly,
            not overwhelm them with dashboards, filters, or signal clutter.
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# MAIN APP
# =========================================================
def main() -> None:
    init_state()
    inject_styles()
    render_hero()
    render_query_box()
    render_example_prompts()

    if st.session_state.last_response:
        query = st.session_state.last_query
        assets = extract_assets(query)
        intent = classify_intent(query)
        signals = run_signal_orchestrator(query, intent, assets)

        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        render_answer_card(st.session_state.last_response)
        render_signal_summary(st.session_state.last_response)
        render_why_section(st.session_state.last_response, signals)
        render_expandable_details(st.session_state.last_response)

    render_footer()


if __name__ == "__main__":
    main()
