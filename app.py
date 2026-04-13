from __future__ import annotations

import io
import math
import textwrap
from dataclasses import dataclass
from typing import Any, Dict

import streamlit as st


# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Crypto AI Lab",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# =========================================================
# STYLES
# =========================================================
st.markdown(
    """
    <style>
    [data-testid="stSidebar"] {
        display: none;
    }

    .block-container {
        max-width: 1120px;
        padding-top: 1.2rem;
        padding-bottom: 2.2rem;
    }

    .app-title {
        font-size: 2rem;
        font-weight: 800;
        color: #111111;
        margin-bottom: 0.2rem;
    }

    .app-subtitle {
        font-size: 1rem;
        color: #555555;
        margin-bottom: 1.2rem;
    }

    .section-title {
        font-size: 1.18rem;
        font-weight: 800;
        color: #111111;
        margin-top: 1.1rem;
        margin-bottom: 0.8rem;
    }

    .signal-output-box {
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 18px;
        padding: 18px 18px;
        background: #ffffff;
        box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        margin-bottom: 12px;
    }

    .signal-main {
        font-size: 1.45rem;
        font-weight: 800;
        color: #111111;
        margin-bottom: 0.35rem;
    }

    .signal-sub {
        font-size: 0.96rem;
        color: #444444;
        line-height: 1.5;
    }

    .grid-card {
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 16px;
        padding: 14px 14px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        min-height: 106px;
        margin-bottom: 12px;
    }

    .grid-label {
        font-size: 0.82rem;
        color: #555555;
        font-weight: 700;
        margin-bottom: 6px;
    }

    .grid-value {
        font-size: 1.08rem;
        color: #111111;
        font-weight: 800;
        margin-bottom: 6px;
    }

    .grid-note {
        font-size: 0.86rem;
        color: #666666;
        line-height: 1.45;
    }

    .narrative-box {
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 16px;
        padding: 16px 16px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        margin-bottom: 12px;
    }

    .narrative-heading {
        font-size: 1rem;
        font-weight: 800;
        color: #111111;
        margin-bottom: 0.45rem;
    }

    .narrative-text {
        font-size: 0.95rem;
        color: #222222;
        line-height: 1.55;
    }

    .agent-card {
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 16px;
        padding: 14px 16px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        margin-bottom: 12px;
    }

    .agent-title {
        font-size: 0.97rem;
        font-weight: 800;
        color: #111111;
        margin-bottom: 8px;
    }

    .agent-body {
        font-size: 0.95rem;
        color: #222222;
        line-height: 1.58;
    }

    .download-wrap {
        border: 1px solid rgba(0,0,0,0.10);
        border-radius: 16px;
        padding: 16px 16px;
        background: #ffffff;
        box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        margin-top: 8px;
    }

    .tiny {
        font-size: 0.84rem;
        color: #666666;
    }

    .stButton > button {
        width: 100%;
        border-radius: 12px;
        height: 2.9rem;
        font-weight: 700;
    }

    .stDownloadButton > button {
        width: 100%;
        border-radius: 12px;
        height: 2.9rem;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# HELPERS
# =========================================================
def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def signal_strength_label(score_out_of_15: float) -> str:
    if score_out_of_15 >= 11.5:
        return "High Momentum"
    if score_out_of_15 >= 8.0:
        return "Constructive"
    if score_out_of_15 >= 5.0:
        return "Mixed"
    return "Weak"


def component_label_5(value: float) -> str:
    if value >= 4.5:
        return "Exceptional"
    if value >= 3.8:
        return "Strong"
    if value >= 3.0:
        return "Healthy"
    if value >= 2.0:
        return "Mixed"
    return "Weak"


def range_label(value: float) -> str:
    if value >= 1.6:
        return "High in range"
    if value >= 0.9:
        return "Mid-range"
    return "Low in range"


def trend_label(value: float) -> str:
    if value >= 2.5:
        return "Aligned"
    if value >= 1.8:
        return "Improving"
    if value >= 1.1:
        return "Mixed"
    return "Misaligned"


def volatility_label(value: float) -> str:
    if value >= 0.80:
        return "Very high"
    if value >= 0.60:
        return "High"
    if value >= 0.40:
        return "Moderate"
    if value >= 0.20:
        return "Low"
    return "Very low"


def timing_label(breakout_value: float, volatility_value: float, trend_score: float) -> str:
    if breakout_value >= 0.70 and volatility_value <= 0.45 and trend_score >= 1.8:
        return "High-quality setup"
    if breakout_value >= 0.55 and volatility_value <= 0.60:
        return "Good setup"
    if breakout_value >= 0.35:
        return "Average setup"
    return "Low-quality setup"


def short_direction_label(slope_value: float) -> str:
    if slope_value >= 0.60:
        return "Strong upside pressure"
    if slope_value >= 0.20:
        return "Moderate upside pressure"
    if slope_value > -0.20:
        return "Flat to mixed"
    if slope_value > -0.60:
        return "Moderate downside pressure"
    return "Strong downside pressure"


def market_structure_label(trend_score: float, range_score: float, slope_value: float, breakout_value: float) -> str:
    if trend_score >= 2.2 and range_score >= 1.2 and slope_value > 0.15:
        return "Bullish"
    if trend_score <= 1.0 and range_score <= 0.8 and slope_value < -0.15:
        return "Bearish"
    if abs(slope_value) < 0.20 and breakout_value < 0.50:
        return "Sideways"
    if slope_value > 0:
        return "Bullish"
    if slope_value < 0:
        return "Bearish"
    return "Sideways"


def market_structure_narrative(structure: str, volume: float, price: float, trend: float, range_score: float, volatility: float) -> str:
    if structure == "Bullish":
        return (
            f"Price structure is bullish. Participation is {component_label_5(volume).lower()}, "
            f"price expansion is {component_label_5(price).lower()}, trend is {trend_label(trend).lower()}, "
            f"and the asset is trading {range_label(range_score).lower()}. Volatility is {volatility_label(volatility).lower()}, "
            f"so the market currently favors upside continuation over hesitation."
        )
    if structure == "Bearish":
        return (
            f"Price structure is bearish. Participation is {component_label_5(volume).lower()}, "
            f"price expansion is {component_label_5(price).lower()}, trend is {trend_label(trend).lower()}, "
            f"and the asset is trading {range_label(range_score).lower()}. Volatility is {volatility_label(volatility).lower()}, "
            f"so the market currently favors weakness or failed rallies over clean upside continuation."
        )
    return (
        f"Price structure is sideways. Participation is {component_label_5(volume).lower()}, "
        f"price expansion is {component_label_5(price).lower()}, trend is {trend_label(trend).lower()}, "
        f"and the asset is trading {range_label(range_score).lower()}. Volatility is {volatility_label(volatility).lower()}, "
        f"so the market is better described as a range or transition than a decisive directional trend."
    )


def timing_narrative(timing_quality: str, slope_value: float, breakout_value: float, volatility_value: float) -> str:
    direction = short_direction_label(slope_value)
    if timing_quality == "High-quality setup":
        return (
            f"Timing quality is high. Direction is {direction.lower()}, breakout conditions are strong, "
            f"and noise is reasonably contained. This is the type of setup where acting on confirmation makes sense."
        )
    if timing_quality == "Good setup":
        return (
            f"Timing quality is good. Direction is {direction.lower()}, breakout conditions are improving, "
            f"and the setup has enough clarity to justify attention, but entries still need confirmation."
        )
    if timing_quality == "Average setup":
        return (
            f"Timing quality is average. Direction is {direction.lower()}, but the breakout profile is only moderate. "
            f"This is watchlist territory rather than aggressive execution territory."
        )
    return (
        f"Timing quality is low. Direction is {direction.lower()}, but the setup lacks decisive breakout quality. "
        f"Patience is more valuable than forcing activity here."
    )


def conviction_score(volume: float, price: float, trend: float, range_score: float) -> float:
    total = volume + price + trend + range_score
    return round((total / 15.0) * 10.0, 1)


# =========================================================
# DATA MODEL
# =========================================================
@dataclass
class SignalPack:
    symbol: str
    timeframe: str
    volume: float
    price: float
    trend: float
    range_score: float
    volatility: float
    slope: float
    breakout: float
    market_structure: str
    timing_quality: str
    conviction: float
    signal_output: str


def build_signal_pack(
    symbol: str,
    timeframe: str,
    volume: float,
    price: float,
    trend: float,
    range_score: float,
    volatility: float,
    slope: float,
    breakout: float,
) -> SignalPack:
    volume = clamp(safe_float(volume), 0.0, 5.0)
    price = clamp(safe_float(price), 0.0, 5.0)
    trend = clamp(safe_float(trend), 0.0, 3.0)
    range_score = clamp(safe_float(range_score), 0.0, 2.0)
    volatility = clamp(safe_float(volatility), 0.0, 1.0)
    slope = clamp(safe_float(slope), -1.0, 1.0)
    breakout = clamp(safe_float(breakout), 0.0, 1.0)

    structure = market_structure_label(trend, range_score, slope, breakout)
    timing = timing_label(breakout, volatility, trend)

    raw_total = volume + price + trend + range_score
    signal_output = signal_strength_label(raw_total)

    return SignalPack(
        symbol=symbol,
        timeframe=timeframe,
        volume=volume,
        price=price,
        trend=trend,
        range_score=range_score,
        volatility=volatility,
        slope=slope,
        breakout=breakout,
        market_structure=structure,
        timing_quality=timing,
        conviction=conviction_score(volume, price, trend, range_score),
        signal_output=signal_output,
    )


# =========================================================
# AGENT LAYER
# =========================================================
def ai_lab_outputs(pack: SignalPack) -> Dict[str, str]:
    structure_text = pack.market_structure.lower()
    timing_text = pack.timing_quality.lower()
    direction_text = short_direction_label(pack.slope).lower()
    vol_text = volatility_label(pack.volatility).lower()

    return {
        "Market Analyst": (
            f"{pack.symbol} on {pack.timeframe} currently presents a {structure_text} market structure. "
            f"Volume is {component_label_5(pack.volume).lower()}, price expansion is {component_label_5(pack.price).lower()}, "
            f"and trend alignment is {trend_label(pack.trend).lower()}, which keeps the broader read focused on directional follow-through."
        ),
        "Timing Analyst": (
            f"The setup quality is {timing_text}. Short-term direction is {direction_text}, and the breakout profile suggests "
            f"that execution should happen only when price confirms rather than on anticipation alone."
        ),
        "Risk Analyst": (
            f"Volatility is {vol_text}, so risk should be sized according to current market noise. "
            f"With a conviction score of {pack.conviction:.1f} out of 10, this is a setup for measured decision-making rather than emotional execution."
        ),
        "Execution Coach": (
            f"The clearest action bias is to align with the current {structure_text} structure while respecting the {timing_text} timing profile. "
            f"Stay selective, wait for confirmation, and avoid forcing trades when the signal is not fully aligned."
        ),
    }


# =========================================================
# RENDER HELPERS
# =========================================================
def card(title: str, value: str, note: str) -> None:
    st.markdown(
        f"""
        <div class="grid-card">
            <div class="grid-label">{title}</div>
            <div class="grid-value">{value}</div>
            <div class="grid-note">{note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def agent_card(title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="agent-card">
            <div class="agent-title">{title}</div>
            <div class="agent-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# PDF GENERATOR
# =========================================================
def create_pdf_bytes(pack: SignalPack, agents: Dict[str, str]) -> bytes:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    except Exception:
        fallback_text = build_plaintext_report(pack, agents)
        return fallback_text.encode("utf-8")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    body_style = styles["BodyText"]
    body_style.fontName = "Helvetica"
    body_style.fontSize = 10
    body_style.leading = 14

    heading_style = ParagraphStyle(
        "HeadingStyle",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=13,
        leading=16,
        spaceAfter=8,
        textColor="#111111",
    )

    story = []

    story.append(Paragraph("Crypto AI Lab Report", title_style))
    story.append(Spacer(1, 0.15 * inch))
    story.append(Paragraph(f"<b>Asset:</b> {pack.symbol}", body_style))
    story.append(Paragraph(f"<b>Timeframe:</b> {pack.timeframe}", body_style))
    story.append(Spacer(1, 0.12 * inch))

    story.append(Paragraph("Signal Output", heading_style))
    story.append(Paragraph(pack.signal_output, body_style))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Signal Components", heading_style))
    story.append(Paragraph(f"<b>Volume:</b> {pack.volume:.1f} / 5", body_style))
    story.append(Paragraph(f"<b>Price:</b> {pack.price:.1f} / 5", body_style))
    story.append(Paragraph(f"<b>Trend:</b> {pack.trend:.1f} / 3", body_style))
    story.append(Paragraph(f"<b>Range:</b> {pack.range_score:.1f} / 2", body_style))
    story.append(Paragraph(f"<b>Volatility:</b> {pack.volatility:.2f} / 1.0", body_style))
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Market Structure", heading_style))
    story.append(Paragraph(f"<b>{pack.market_structure}</b>", body_style))
    story.append(
        Paragraph(
            market_structure_narrative(
                pack.market_structure,
                pack.volume,
                pack.price,
                pack.trend,
                pack.range_score,
                pack.volatility,
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("Timing Quality", heading_style))
    story.append(Paragraph(f"<b>{pack.timing_quality}</b>", body_style))
    story.append(
        Paragraph(
            timing_narrative(
                pack.timing_quality,
                pack.slope,
                pack.breakout,
                pack.volatility,
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 0.1 * inch))

    story.append(Paragraph("AI Lab", heading_style))
    for role, text in agents.items():
        story.append(Paragraph(f"<b>{role}</b>", body_style))
        story.append(Paragraph(text, body_style))
        story.append(Spacer(1, 0.08 * inch))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def build_plaintext_report(pack: SignalPack, agents: Dict[str, str]) -> str:
    parts = [
        "Crypto AI Lab Report",
        "",
        f"Asset: {pack.symbol}",
        f"Timeframe: {pack.timeframe}",
        "",
        "Signal Output",
        pack.signal_output,
        "",
        "Signal Components",
        f"Volume: {pack.volume:.1f} / 5",
        f"Price: {pack.price:.1f} / 5",
        f"Trend: {pack.trend:.1f} / 3",
        f"Range: {pack.range_score:.1f} / 2",
        f"Volatility: {pack.volatility:.2f} / 1.0",
        "",
        "Market Structure",
        pack.market_structure,
        market_structure_narrative(
            pack.market_structure,
            pack.volume,
            pack.price,
            pack.trend,
            pack.range_score,
            pack.volatility,
        ),
        "",
        "Timing Quality",
        pack.timing_quality,
        timing_narrative(
            pack.timing_quality,
            pack.slope,
            pack.breakout,
            pack.volatility,
        ),
        "",
        "AI Lab",
    ]

    for role, text in agents.items():
        parts.append(role)
        parts.append(text)
        parts.append("")

    return "\n".join(parts)


# =========================================================
# TOP CONTROLS - NOT SIDEBAR
# =========================================================
st.markdown('<div class="app-title">Crypto AI Lab</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="app-subtitle">Clear signal translation, market structure, timing quality, deep reasoning, and PDF export.</div>',
    unsafe_allow_html=True,
)

with st.container():
    top1, top2, top3 = st.columns(3)
    with top1:
        symbol = st.text_input("Asset", value="BTC")
    with top2:
        timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=1)
    with top3:
        run_analysis = st.button("Run Analysis")

with st.container():
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        volume = st.slider("Volume", 0.0, 5.0, 3.7, 0.1)
    with c2:
        price = st.slider("Price", 0.0, 5.0, 3.4, 0.1)
    with c3:
        trend = st.slider("Trend", 0.0, 3.0, 2.2, 0.1)
    with c4:
        range_score = st.slider("Range", 0.0, 2.0, 1.4, 0.1)
    with c5:
        volatility = st.slider("Volatility", 0.0, 1.0, 0.34, 0.01)

with st.container():
    c6, c7 = st.columns(2)
    with c6:
        slope = st.slider("Short-Term Direction", -1.0, 1.0, 0.35, 0.05)
    with c7:
        breakout = st.slider("Breakout Potential", 0.0, 1.0, 0.66, 0.05)


# =========================================================
# BUILD OUTPUT
# =========================================================
pack = build_signal_pack(
    symbol=symbol,
    timeframe=timeframe,
    volume=volume,
    price=price,
    trend=trend,
    range_score=range_score,
    volatility=volatility,
    slope=slope,
    breakout=breakout,
)

agents = ai_lab_outputs(pack)


# =========================================================
# 1. SIGNAL OUTPUT
# =========================================================
st.markdown('<div class="section-title">Signal Output</div>', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="signal-output-box">
        <div class="signal-main">{pack.signal_output}</div>
        <div class="signal-sub">
            {pack.symbol} on {pack.timeframe} currently shows a <b>{pack.market_structure.lower()}</b> structure
            with <b>{pack.timing_quality.lower()}</b> timing conditions and a conviction score of
            <b>{pack.conviction:.1f} / 10</b>.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 2. SIGNAL COMPONENTS
# =========================================================
st.markdown('<div class="section-title">Signal Components</div>', unsafe_allow_html=True)

r1 = st.columns(5)
with r1[0]:
    card("Volume", f"{pack.volume:.1f} / 5", f"{component_label_5(pack.volume)} participation")
with r1[1]:
    card("Price", f"{pack.price:.1f} / 5", f"{component_label_5(pack.price)} expansion")
with r1[2]:
    card("Trend", f"{pack.trend:.1f} / 3", f"Trend is {trend_label(pack.trend).lower()}")
with r1[3]:
    card("Range", f"{pack.range_score:.1f} / 2", range_label(pack.range_score))
with r1[4]:
    card("Volatility", f"{pack.volatility:.2f} / 1.0", f"{volatility_label(pack.volatility)} volatility")


# =========================================================
# 3. MARKET STRUCTURE
# =========================================================
st.markdown('<div class="section-title">Market Structure</div>', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="narrative-box">
        <div class="narrative-heading">{pack.market_structure}</div>
        <div class="narrative-text">
            {market_structure_narrative(
                pack.market_structure,
                pack.volume,
                pack.price,
                pack.trend,
                pack.range_score,
                pack.volatility
            )}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 4. TIMING QUALITY
# =========================================================
st.markdown('<div class="section-title">Timing Quality</div>', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="narrative-box">
        <div class="narrative-heading">{pack.timing_quality}</div>
        <div class="narrative-text">
            {timing_narrative(
                pack.timing_quality,
                pack.slope,
                pack.breakout,
                pack.volatility
            )}
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# =========================================================
# 5. AI LAB
# =========================================================
st.markdown('<div class="section-title">AI Lab</div>', unsafe_allow_html=True)

for role, text in agents.items():
    agent_card(role, text)


# =========================================================
# 6. DOWNLOAD PDF
# =========================================================
st.markdown('<div class="section-title">Download PDF</div>', unsafe_allow_html=True)
st.markdown(
    """
    <div class="download-wrap">
        <div class="tiny">Export the current signal, structure, timing read, and AI Lab reasoning as a PDF report.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

pdf_bytes = create_pdf_bytes(pack, agents)

st.download_button(
    label="Download PDF Report",
    data=pdf_bytes,
    file_name=f"{pack.symbol.lower()}_{pack.timeframe}_ai_lab_report.pdf",
    mime="application/pdf",
    use_container_width=True,
)
