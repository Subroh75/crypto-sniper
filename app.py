import io
import os
import re
import time
from dataclasses import dataclass
from typing import Dict, List

import streamlit as st
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Crypto Guru",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# BRANDING
# =========================================================
LOGO_PATH = "assets/crypto_guru_logo.png"
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
    miro_score: float
    kronos_score: float
    debate_score: float


# =========================================================
# STYLES
# =========================================================
def inject_styles() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg: #000000;
                --panel: #0a0a0a;
                --panel-2: #111111;
                --border: rgba(255,153,51,0.22);
                --text: #ffffff;
                --muted: #d7b37a;
                --accent: #ff9933;
                --accent-2: #cc6f00;
                --soft: rgba(255,153,51,0.08);
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(255,153,51,0.11), transparent 24%),
                    radial-gradient(circle at top right, rgba(255,153,51,0.08), transparent 20%),
                    linear-gradient(180deg, #000000 0%, #050505 100%);
            }

            .block-container {
                max-width: 900px;
                padding-top: 3rem;
                padding-bottom: 3rem;
            }

            header[data-testid="stHeader"] {
                background: transparent;
            }

            [data-testid="collapsedControl"] {
                display: none;
            }

            section[data-testid="stSidebar"] {
                display: none !important;
            }

            .hero-wrap {
                text-align: center;
                margin-bottom: 1.75rem;
            }

            .hero-logo-wrap {
                display: flex;
                justify-content: center;
                align-items: center;
                margin-bottom: 0.65rem;
                animation: floaty 4.5s ease-in-out infinite;
            }

            .hero-logo-glow {
                display: inline-flex;
                justify-content: center;
                align-items: center;
                padding: 14px;
                border-radius: 24px;
                background:
                    radial-gradient(circle, rgba(255,153,51,0.16) 0%, rgba(255,153,51,0.05) 45%, rgba(255,153,51,0.00) 72%);
                box-shadow:
                    0 0 0 1px rgba(255,153,51,0.05),
                    0 0 28px rgba(255,153,51,0.14),
                    0 0 56px rgba(255,153,51,0.08);
                transition: transform 0.25s ease, box-shadow 0.25s ease;
            }

            .hero-logo-glow:hover {
                transform: translateY(-1px) scale(1.01);
                box-shadow:
                    0 0 0 1px rgba(255,153,51,0.08),
                    0 0 36px rgba(255,153,51,0.18),
                    0 0 68px rgba(255,153,51,0.11);
            }

            @keyframes floaty {
                0% { transform: translateY(0px); }
                50% { transform: translateY(-3px); }
                100% { transform: translateY(0px); }
            }

            .hero-title {
                color: #ffffff;
                font-size: 2.7rem;
                font-weight: 800;
                letter-spacing: -0.03em;
                margin-top: 0.3rem;
                margin-bottom: 0.35rem;
            }

            .hero-tagline {
                color: var(--muted);
                font-size: 1rem;
                margin-bottom: 0;
            }

            .search-shell {
                background: linear-gradient(180deg, rgba(10,10,10,0.98) 0%, rgba(18,18,18,0.98) 100%);
                border: 1px solid rgba(255,153,51,0.20);
                border-radius: 22px;
                padding: 1rem;
                box-shadow:
                    0 0 0 1px rgba(255,153,51,0.03),
                    0 20px 60px rgba(0,0,0,0.45);
                margin-bottom: 1.15rem;
            }

            .result-card {
                background: linear-gradient(180deg, rgba(10,10,10,0.98) 0%, rgba(18,18,18,0.98) 100%);
                border: 1px solid rgba(255,153,51,0.20);
                border-radius: 20px;
                padding: 1.15rem 1.2rem;
                margin-top: 1rem;
                box-shadow: 0 12px 36px rgba(0,0,0,0.28);
            }

            .result-title {
                color: #ffffff;
                font-size: 1.1rem;
                font-weight: 750;
                margin-bottom: 0.7rem;
            }

            .answer-text {
                color: #fff7ed;
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
                background: rgba(255,153,51,0.04);
                border: 1px solid rgba(255,153,51,0.12);
                border-radius: 16px;
                padding: 0.85rem 0.9rem;
            }

            .signal-label {
                color: #d7b37a;
                font-size: 0.8rem;
                margin-bottom: 0.3rem;
            }

            .signal-value {
                color: #ffffff;
                font-size: 0.95rem;
                font-weight: 700;
                line-height: 1.4;
            }

            .why-line {
                color: #fff7ed;
                line-height: 1.6;
                margin-bottom: 0.45rem;
            }

            /* QUERY FIELD */
            .stTextInput > div > div > input {
                background: linear-gradient(180deg, rgba(18,18,18,0.94) 0%, rgba(8,8,8,0.98) 100%) !important;
                color: #ffffff !important;
                border-radius: 16px !important;
                border: 1px solid rgba(255,153,51,0.24) !important;
                padding: 1rem 1rem !important;
                font-size: 1.05rem !important;
                text-align: center !important;
                caret-color: #ff9933 !important;
                box-shadow:
                    inset 0 1px 0 rgba(255,255,255,0.03),
                    0 0 0 1px rgba(255,153,51,0.02);
                transition: all 0.22s ease !important;
            }

            .stTextInput > div > div > input::placeholder {
                color: #c49352 !important;
                opacity: 1 !important;
            }

            .stTextInput > div > div > input:hover {
                border: 1px solid rgba(255,153,51,0.34) !important;
                box-shadow:
                    inset 0 1px 0 rgba(255,255,255,0.03),
                    0 0 10px rgba(255,153,51,0.06) !important;
            }

            .stTextInput > div > div > input:focus {
                background: linear-gradient(180deg, rgba(18,18,18,0.98) 0%, rgba(8,8,8,1) 100%) !important;
                color: #ffffff !important;
                border: 1px solid #ff9933 !important;
                outline: none !important;
                box-shadow:
                    0 0 0 1px rgba(255,153,51,0.08),
                    0 0 18px rgba(255,153,51,0.13) !important;
                transform: translateY(-1px);
            }

            [data-testid="stTextInput"] input {
                color: #ffffff !important;
                background-color: #0d0d0d !important;
            }

            .stButton > button,
            .stDownloadButton > button {
                width: 100%;
                min-height: 2.45rem;
                border-radius: 12px;
                font-weight: 700;
                font-size: 0.92rem;
                border: 1px solid rgba(255,153,51,0.20);
                background: linear-gradient(180deg, #ff9933 0%, #d97706 100%);
                color: #000000;
                padding: 0.35rem 0.7rem;
                transition: all 0.2s ease;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover {
                color: #000000;
                border: 1px solid rgba(255,153,51,0.32);
                background: linear-gradient(180deg, #ffad5c 0%, #e68613 100%);
                box-shadow: 0 8px 22px rgba(255,153,51,0.14);
                transform: translateY(-1px);
            }

            .stButton > button:focus,
            .stDownloadButton > button:focus {
                outline: none !important;
                box-shadow: 0 0 0 2px rgba(255,153,51,0.18) !important;
            }

            div[data-testid="stExpander"] {
                border: 1px solid rgba(255,153,51,0.16) !important;
                border-radius: 16px !important;
                background: rgba(255,153,51,0.03) !important;
            }

            @media (max-width: 820px) {
                .hero-title {
                    font-size: 2.15rem;
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
        "last_pdf": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# =========================================================
# HELPERS
# =========================================================
def normalize_coin(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", raw.strip().upper())


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
# ENGINE ORDER
# =========================================================
def run_miro_logic(coin: str) -> EngineSignal:
    score = pseudo_score(coin + "miro_logic", 19)
    return EngineSignal(
        label="Miro",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=f"Miro logic reads {coin} through momentum and structure as {score_to_bias(score)}.",
    )


def run_kronos_logic(coin: str) -> EngineSignal:
    score = pseudo_score(coin + "kronos_logic", 7)
    return EngineSignal(
        label="Kronos",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=f"Kronos logic reads the timing quality on {coin} as {score_to_bias(score)}.",
    )


def run_ai_debate(coin: str, miro: EngineSignal, kronos: EngineSignal) -> EngineSignal:
    blended_seed = f"{coin}|{miro.score:.1f}|{miro.bias}|{kronos.score:.1f}|{kronos.bias}|ai_debate"
    score = pseudo_score(blended_seed, 13)

    if miro.score >= 7.2 and kronos.score >= 7.2:
        score = min(9.4, round(score + 0.4, 1))
    elif miro.score < 6.0 and kronos.score < 6.0:
        score = max(4.8, round(score - 0.4, 1))

    return EngineSignal(
        label="AI Debate",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=(
            f"AI Debate weighs Miro ({miro.bias}) against Kronos ({kronos.bias}) "
            f"and concludes {coin} is {score_to_bias(score)}."
        ),
    )


def run_engines(coin: str) -> Dict[str, EngineSignal]:
    miro = run_miro_logic(coin)
    kronos = run_kronos_logic(coin)
    ai_debate = run_ai_debate(coin, miro, kronos)
    return {
        "miro": miro,
        "kronos": kronos,
        "ai_debate": ai_debate,
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
        risk = "Overextension risk if the move gets crowded."
    elif bias == "bullish":
        action = "Watch closely"
        risk = "Pullback risk if timing weakens."
    elif bias == "constructive":
        action = "Early watch"
        risk = "Still not a full confirmation."
    elif bias == "neutral":
        action = "Stay selective"
        risk = "Direction is not yet strong enough."
    else:
        action = "Avoid forcing"
        risk = "Weak setup and false signal risk remain elevated."

    answer = (
        f"{coin} currently reads as {bias} with {confidence} confidence after "
        f"Miro logic, Kronos logic, and the final AI debate."
    )

    reasons = [
        f"Miro: {signals['miro'].summary}",
        f"Kronos: {signals['kronos'].summary}",
        f"AI Debate: {signals['ai_debate'].summary}",
    ]

    return FinalResponse(
        coin=coin,
        answer=answer,
        bias=bias,
        confidence=confidence,
        risk=risk,
        action=action,
        reasons=reasons,
        miro_score=signals["miro"].score,
        kronos_score=signals["kronos"].score,
        debate_score=signals["ai_debate"].score,
    )


# =========================================================
# PDF
# =========================================================
def wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        test = word if not current else f"{current} {word}"
        if stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped_text(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_name: str = "Helvetica",
    font_size: int = 11,
    line_gap: int = 15,
    color: HexColor = HexColor("#FFF7ED"),
) -> float:
    pdf.setFillColor(color)
    pdf.setFont(font_name, font_size)
    for line in wrap_text(text, font_name, font_size, max_width):
        pdf.drawString(x, y, line)
        y -= line_gap
    return y


def generate_pdf(response: FinalResponse) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin_x = 18 * mm
    y = height - 22 * mm
    content_width = width - (2 * margin_x)

    pdf.setFillColor(HexColor("#000000"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)

    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(margin_x, y, APP_HEADING)
    y -= 8 * mm

    pdf.setFillColor(HexColor("#D7B37A"))
    pdf.setFont("Helvetica", 11)
    pdf.drawString(margin_x, y, APP_TAGLINE)
    y -= 12 * mm

    pdf.setFillColor(HexColor("#FF9933"))
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin_x, y, f"{response.coin} Signal Output")
    y -= 8 * mm

    y = draw_wrapped_text(pdf, response.answer, margin_x, y, content_width)
    y -= 5 * mm

    pdf.setFillColor(HexColor("#111111"))
    pdf.roundRect(margin_x, y - 32 * mm, content_width, 30 * mm, 8, fill=1, stroke=0)

    stat_y = y - 7 * mm
    stats = [
        ("Bias", response.bias.title()),
        ("Confidence", response.confidence.title()),
        ("Risk", response.risk),
        ("Action", response.action),
    ]

    col_width = content_width / 2
    row_gap = 15 * mm

    for i, (label, value) in enumerate(stats):
        col = i % 2
        row = i // 2
        x = margin_x + (col * col_width) + 5 * mm
        sy = stat_y - (row * row_gap)

        pdf.setFillColor(HexColor("#D7B37A"))
        pdf.setFont("Helvetica", 9)
        pdf.drawString(x, sy, label)

        pdf.setFillColor(HexColor("#FFFFFF"))
        pdf.setFont("Helvetica-Bold", 10)
        value_lines = wrap_text(value, "Helvetica-Bold", 10, col_width - 12 * mm)
        for idx, line in enumerate(value_lines[:2]):
            pdf.drawString(x, sy - 5 - (idx * 11), line)

    y -= 40 * mm

    pdf.setFillColor(HexColor("#FF9933"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(margin_x, y, "Engine Scores")
    y -= 8 * mm

    for line in [
        f"Miro: {response.miro_score:.1f} / 10",
        f"Kronos: {response.kronos_score:.1f} / 10",
        f"AI Debate: {response.debate_score:.1f} / 10",
    ]:
        y = draw_wrapped_text(pdf, line, margin_x, y, content_width)

    y -= 4 * mm

    pdf.setFillColor(HexColor("#FF9933"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(margin_x, y, "Why")
    y -= 8 * mm

    for reason in response.reasons:
        y = draw_wrapped_text(pdf, f"• {reason}", margin_x, y, content_width)
        y -= 1 * mm
        if y < 25 * mm:
            pdf.showPage()
            pdf.setFillColor(HexColor("#000000"))
            pdf.rect(0, 0, width, height, fill=1, stroke=0)
            y = height - 22 * mm

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


# =========================================================
# UI
# =========================================================
def render_header() -> None:
    st.markdown('<div class="hero-wrap">', unsafe_allow_html=True)

    if os.path.exists(LOGO_PATH):
        st.markdown('<div class="hero-logo-wrap"><div class="hero-logo-glow">', unsafe_allow_html=True)
        st.image(LOGO_PATH, width=120)
        st.markdown('</div></div>', unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="hero-title">{APP_HEADING}</div>
        <div class="hero-tagline">{APP_TAGLINE}</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)


def render_search() -> None:
    st.markdown('<div class="search-shell">', unsafe_allow_html=True)

    coin = st.text_input(
        "",
        value=st.session_state.coin_input,
        placeholder="Enter coin",
        label_visibility="collapsed",
        key="coin_input_widget",
    )

    col1, col2, col3 = st.columns([3.4, 1.1, 1.1])
    with col2:
        analyze_clicked = st.button("Run Signal", use_container_width=True)
    with col3:
        clear_clicked = st.button("Clear", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if clear_clicked:
        st.session_state.coin_input = ""
        st.session_state.last_coin = ""
        st.session_state.last_response = None
        st.session_state.last_signals = None
        st.session_state.last_pdf = None
        st.rerun()

    if analyze_clicked:
        clean_coin = normalize_coin(coin)
        if not clean_coin:
            st.warning("Enter a valid coin.")
            return

        st.session_state.coin_input = clean_coin
        st.session_state.last_coin = clean_coin

        with st.spinner("Running engines..."):
            time.sleep(0.3)
            signals = run_engines(clean_coin)
            response = compose_response(clean_coin, signals)
            pdf_bytes = generate_pdf(response)

        st.session_state.last_signals = signals
        st.session_state.last_response = response
        st.session_state.last_pdf = pdf_bytes
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
        st.write(f"Miro: {signals['miro'].score:.1f} / 10 · {signals['miro'].confidence.title()}")
        st.write(f"Kronos: {signals['kronos'].score:.1f} / 10 · {signals['kronos'].confidence.title()}")
        st.write(f"AI Debate: {signals['ai_debate'].score:.1f} / 10 · {signals['ai_debate'].confidence.title()}")

    if st.session_state.last_pdf:
        st.download_button(
            label="Download PDF",
            data=st.session_state.last_pdf,
            file_name=f"{response.coin.lower()}_signal_output.pdf",
            mime="application/pdf",
            use_container_width=False,
        )


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
