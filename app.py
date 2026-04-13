import re
import time
from dataclasses import dataclass
from typing import Dict, List

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
# BRANDING
# Replace these with your exact previous logo/tagline if needed
# =========================================================
APP_LOGO = "🔮"
APP_HEADING = "Crypto Guru"
APP_TAGLINE = "Precision crypto intelligence."


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
    coin: str
    answer: str
    bias: str
    confidence: str
    risk: str
    action: str
    reasons: List[str]


# =========================================================
# STYLES
# =========================================================
def inject_styles() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg: #07101d;
                --panel: #0f1726;
                --panel-2: #101a2c;
                --border: rgba(255,255,255,0.08);
                --text: #ffffff;
                --muted: #a6b3c8;
                --accent: #6f8cff;
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(111,140,255,0.10), transparent 28%),
                    radial-gradient(circle at top right, rgba(111,140,255,0.08), transparent 22%),
                    linear-gradient(180deg, #07101d 0%, #0a1220 100%);
            }

            .block-container {
                max-width: 920px;
                padding-top: 4rem;
                padding-bottom: 3rem;
            }

            .hero-wrap {
                text-align: center;
                margin-bottom: 2rem;
            }

            .hero-logo {
                font-size: 3rem;
                line-height: 1;
                margin-bottom: 0.8rem;
            }

            .hero-title {
                color: white;
                font-size: 2.8rem;
                font-weight: 800;
                letter-spacing: -0.03em;
                margin-bottom: 0.4rem;
            }

            .hero-tagline {
                color: var(--muted);
                font-size: 1rem;
                margin-bottom: 1.8rem;
            }

            .search-shell {
                background: linear-gradient(180deg, rgba(15,23,38,0.96) 0%, rgba(10,18,32,0.98) 100%);
                border: 1px solid var(--border);
                border-radius: 24px;
                padding: 1rem;
                box-shadow: 0 20px 60px rgba(0,0,0,0.30);
                margin-bottom: 1.4rem;
            }

            .result-card {
                background: linear-gradient(180deg, rgba(15,23,38,0.96) 0%, rgba(10,18,32,0.98) 100%);
                border: 1px solid var(--border);
                border-radius: 20px;
                padding: 1.15rem 1.2rem;
                margin-top: 1rem;
                box-shadow: 0 12px 36px rgba(0,0,0,0.18);
            }

            .result-title {
                color: white;
                font-size: 1.1rem;
                font-weight: 750;
                margin-bottom: 0.7rem;
            }

            .answer-text {
                color: #eef3ff;
                font-size: 1.02rem;
                line-height: 1.7;
                margin-bottom: 0.95rem;
            }

            .signal-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 0.8rem;
            }

            .signal-box {
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.07);
                border-radius: 16px;
                padding: 0.85rem 0.9rem;
            }

            .signal-label {
                color: var(--muted);
                font-size: 0.8rem;
                margin-bottom: 0.3rem;
            }

            .signal-value {
                color: white;
                font-size: 0.95rem;
                font-weight: 700;
                line-height: 1.4;
            }

            .why-line {
                color: #e9efff;
                line-height: 1.6;
                margin-bottom: 0.45rem;
            }

            .stTextInput > div > div > input {
                background: rgba(255,255,255,0.04);
                color: white;
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,0.08);
                padding: 1rem 1rem;
                font-size: 1.02rem;
                text-align: center;
            }

            .stTextInput > div > div > input::placeholder {
                color: #95a3bc;
            }

            .stButton button {
                width: 100%;
                border-radius: 14px;
                font-weight: 700;
                border: 1px solid rgba(255,255,255,0.08);
                background: linear-gradient(180deg, #7c9cff 0%, #6486ff 100%);
                color: white;
                padding: 0.72rem 1rem;
            }

            .stButton button:hover {
                color: white;
                border: 1px solid rgba(255,255,255,0.10);
            }

            div[data-testid="stExpander"] {
                border: 1px solid rgba(255,255,255,0.08) !important;
                border-radius: 16px !important;
                background: rgba(255,255,255,0.02) !important;
            }

            @media (max-width: 820px) {
                .hero-title {
                    font-size: 2.2rem;
                }

                .signal-grid {
                    grid-template-columns: 1fr 1fr;
                }
            }

            @media (max-width: 580px) {
                .signal-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# SESSION STATE
# =========================================================
def init_state() -> None:
    defaults = {
        "coin_input": "",
        "last_coin": "",
        "last_response": None,
        "last_signals": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# =========================================================
# HELPERS
# =========================================================
def normalize_coin(raw: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw.strip().upper())
    return cleaned


def pseudo_score(seed_text: str, modifier: int) -> float:
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


# =========================================================
# ENGINES
# Swap these with your real engine logic
# =========================================================
def run_ai_lab(coin: str) -> EngineSignal:
    score = pseudo_score(coin + "ai_lab", 11)
    return EngineSignal(
        label="AI Lab",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=f"AI Lab reads {coin} as {score_to_bias(score)} from a structure and reasoning perspective.",
    )


def run_miro(coin: str) -> EngineSignal:
    score = pseudo_score(coin + "miro", 19)
    return EngineSignal(
        label="Miro",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=f"Miro sees the momentum profile on {coin} as {score_to_bias(score)}.",
    )


def run_kronos(coin: str) -> EngineSignal:
    score = pseudo_score(coin + "kronos", 7)
    return EngineSignal(
        label="Kronos",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=f"Kronos rates the timing quality on {coin} as {score_to_bias(score)}.",
    )


def run_engines(coin: str) -> Dict[str, EngineSignal]:
    return {
        "ai_lab": run_ai_lab(coin),
        "miro": run_miro(coin),
        "kronos": run_kronos(coin),
    }


# =========================================================
# RESPONSE COMPOSITION
# =========================================================
def compose_response(coin: str, signals: Dict[str, EngineSignal]) -> FinalResponse:
    avg_score = sum(s.score for s in signals.values()) / len(signals)
    bias = score_to_bias(avg_score)
    confidence = score_to_confidence(avg_score)

    if bias == "strong bullish":
        action = "Strong watch"
        risk = "Overextension risk if momentum gets crowded."
    elif bias == "bullish":
        action = "Watch closely"
        risk = "Pullback risk if confirmation weakens."
    elif bias == "constructive":
        action = "Early watch"
        risk = "Still not a clean high-conviction confirmation."
    elif bias == "neutral":
        action = "Stay selective"
        risk = "Direction is not strong enough yet."
    else:
        action = "Avoid forcing"
        risk = "Weak structure and false signal risk remain high."

    answer = (
        f"{coin} currently reads as {bias} with {confidence} confidence across "
        f"AI Lab, Miro, and Kronos."
    )

    reasons = [
        f"AI Lab: {signals['ai_lab'].summary}",
        f"Miro: {signals['miro'].summary}",
        f"Kronos: {signals['kronos'].summary}",
    ]

    return FinalResponse(
        coin=coin,
        answer=answer,
        bias=bias,
        confidence=confidence,
        risk=risk,
        action=action,
        reasons=reasons,
    )


# =========================================================
# RENDER
# =========================================================
def render_header() -> None:
    st.markdown(
        f"""
        <div class="hero-wrap">
            <div class="hero-logo">{APP_LOGO}</div>
            <div class="hero-title">{APP_HEADING}</div>
            <div class="hero-tagline">{APP_TAGLINE}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_search() -> None:
    st.markdown('<div class="search-shell">', unsafe_allow_html=True)

    coin = st.text_input(
        "",
        value=st.session_state.coin_input,
        placeholder="Enter coin",
        label_visibility="collapsed",
        key="coin_input_widget",
    )

    col1, col2 = st.columns([5, 1])
    with col1:
        analyze_clicked = st.button("Run Signal", use_container_width=True)
    with col2:
        clear_clicked = st.button("Clear", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if clear_clicked:
        st.session_state.coin_input = ""
        st.session_state.last_coin = ""
        st.session_state.last_response = None
        st.session_state.last_signals = None
        st.rerun()

    if analyze_clicked:
        clean_coin = normalize_coin(coin)
        if not clean_coin:
            st.warning("Enter a valid coin.")
            return

        st.session_state.coin_input = clean_coin
        st.session_state.last_coin = clean_coin

        with st.spinner("Running engines..."):
            time.sleep(0.35)
            signals = run_engines(clean_coin)
            response = compose_response(clean_coin, signals)

        st.session_state.last_signals = signals
        st.session_state.last_response = response
        st.rerun()


def render_output(response: FinalResponse, signals: Dict[str, EngineSignal]) -> None:
    st.markdown(
        f"""
        <div class="result-card">
            <div class="result-title">{response.coin} Signal Output</div>
            <div class="answer-text">{response.answer}</div>
            <div class="signal-grid">
                <div class="signal-box">
                    <div class="signal-label">Bias</div>
                    <div class="signal-value">{response.bias.title()}</div>
                </div>
                <div class="signal-box">
                    <div class="signal-label">Confidence</div>
                    <div class="signal-value">{response.confidence.title()}</div>
                </div>
                <div class="signal-box">
                    <div class="signal-label">Risk</div>
                    <div class="signal-value">{response.risk}</div>
                </div>
                <div class="signal-box">
                    <div class="signal-label">Action</div>
                    <div class="signal-value">{response.action}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Why"):
        for reason in response.reasons:
            st.markdown(f'<div class="why-line">• {reason}</div>', unsafe_allow_html=True)

    with st.expander("Engine Scores"):
        for key in ["ai_lab", "miro", "kronos"]:
            signal = signals[key]
            st.write(f"{signal.label}: {signal.score:.1f} / 10 · {signal.confidence.title()}")


# =========================================================
# MAIN
# =========================================================
def main() -> None:
    init_state()
    inject_styles()
    render_header()
    render_search()

    if st.session_state.last_response and st.session_state.last_signals:
        render_output(st.session_state.last_response, st.session_state.last_signals)


if __name__ == "__main__":
    main()
