from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image as RLImage,
)

# =========================
# PAGE CONFIG
# =========================
st.set_page_config(
    page_title="crypto.guru",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =========================
# BRAND CONFIG
# =========================
BRAND_NAME = "crypto.guru"
TAGLINE = "Detect Early. Act Smart."

COLOR_BG = "#0B0F16"
COLOR_CARD = "#141A24"
COLOR_BORDER = "#273142"
COLOR_TEXT = "#E8EDF5"
COLOR_SUBTEXT = "#A7B1C2"
COLOR_GREEN = "#7CFF5B"
COLOR_AMBER = "#FFB800"
COLOR_RED = "#FF5C5C"
COLOR_ORANGE = "#FF7A1A"

LOGO_PATH = "assets/crypto_guru_logo.png"

# =========================
# DATA MODELS
# =========================
@dataclass
class TokenInfo:
    token_name: str
    symbol: str
    chain: str
    timeframe: str
    price: float
    generated_at: str


@dataclass
class MiroBreakdown:
    volume_expansion: int        # 0-5
    volatility_expansion: int    # 0-3
    range_control: int           # 0-2
    trend_quality: int           # 0-3
    onchain_confirmation: int    # 0-4
    risk_penalty: int            # 0-5


@dataclass
class SmartMoneySnapshot:
    smart_wallets_active: int
    repeat_buyers: bool
    net_flow: str
    holder_growth_24h: float
    summary: str


@dataclass
class KronosSnapshot:
    regime: str
    bias: str
    confidence: int
    summary: str


@dataclass
class CouncilAgent:
    name: str
    emoji: str
    text: str


@dataclass
class RiskSummary:
    liquidity: str
    concentration: str
    suspicious_activity: str
    execution_risk: str


@dataclass
class ReportData:
    token: TokenInfo
    miro_total: float
    status: str
    breakdown: MiroBreakdown
    smart_money: SmartMoneySnapshot
    kronos: KronosSnapshot
    council: List[CouncilAgent]
    risk: RiskSummary
    verdict_title: str
    verdict_points: List[str]
    action_note: str
    client_name: str


# =========================
# STYLING
# =========================
def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {COLOR_BG};
            color: {COLOR_TEXT};
        }}

        .block-container {{
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }}

        div[data-testid="stMetric"] {{
            background: {COLOR_CARD};
            border: 1px solid {COLOR_BORDER};
            padding: 14px;
            border-radius: 14px;
        }}

        .brand-box {{
            background: {COLOR_CARD};
            border: 1px solid {COLOR_BORDER};
            border-radius: 16px;
            padding: 18px 20px;
            margin-bottom: 16px;
        }}

        .brand-title {{
            font-size: 2rem;
            font-weight: 800;
            margin: 0;
            line-height: 1.1;
        }}

        .brand-subtitle {{
            color: {COLOR_SUBTEXT};
            font-size: 0.95rem;
            margin-top: 0.25rem;
        }}

        .section-box {{
            background: {COLOR_CARD};
            border: 1px solid {COLOR_BORDER};
            border-radius: 16px;
            padding: 16px 18px;
            margin-bottom: 14px;
        }}

        .section-label {{
            color: {COLOR_ORANGE};
            font-size: 0.8rem;
            font-weight: 800;
            letter-spacing: 0.12rem;
            text-transform: uppercase;
            margin-bottom: 0.8rem;
        }}

        .score-text {{
            font-size: 2.1rem;
            font-weight: 900;
            margin-bottom: 0.2rem;
        }}

        .status-pill {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid {COLOR_BORDER};
            background: #1A2230;
            font-size: 0.82rem;
            font-weight: 700;
        }}

        .small-note {{
            color: {COLOR_SUBTEXT};
            font-size: 0.9rem;
            line-height: 1.55;
        }}

        .agent-box {{
            background: #101722;
            border: 1px solid {COLOR_BORDER};
            border-radius: 12px;
            padding: 12px 14px;
            margin-bottom: 10px;
        }}

        .agent-title {{
            font-size: 0.85rem;
            font-weight: 800;
            letter-spacing: 0.08rem;
            margin-bottom: 0.35rem;
            text-transform: uppercase;
            color: {COLOR_SUBTEXT};
        }}

        .verdict-box {{
            background: #101C12;
            border: 1px solid #29472D;
            border-radius: 14px;
            padding: 16px;
        }}

        .footer-note {{
            text-align: center;
            color: {COLOR_SUBTEXT};
            font-size: 0.85rem;
            margin-top: 22px;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================
# HELPERS
# =========================
def score_status(score: float) -> str:
    if score >= 11:
        return "⚡ HIGH MOMENTUM"
    if score >= 8:
        return "🟡 BUILDING STRENGTH"
    if score >= 5:
        return "👁 WATCHLIST"
    return "• NOISE"


def score_color(score: float) -> str:
    if score >= 11:
        return COLOR_GREEN
    if score >= 8:
        return COLOR_AMBER
    if score >= 5:
        return "#D4A64A"
    return COLOR_RED


def clamp_score(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def make_bar(value: int, max_value: int) -> str:
    filled = "█" * value
    empty = "░" * (max_value - value)
    return filled + empty


# =========================
# CORE LOGIC
# =========================
def calculate_miro_v2(
    relative_volume: float,
    atr_multiple: float,
    range_position: float,
    price_above_ema20: bool,
    ema20_above_ema50: bool,
    adx_strength: float,
    smart_wallets_active: int,
    repeat_buyers: bool,
    net_flow_positive: bool,
    holder_growth_24h: float,
    low_liquidity_penalty: bool,
    concentration_penalty: bool,
    suspicious_volume_penalty: bool,
) -> MiroBreakdown:
    # Volume expansion
    if relative_volume >= 8:
        volume_expansion = 5
    elif relative_volume >= 4:
        volume_expansion = 3
    elif relative_volume >= 2:
        volume_expansion = 2
    else:
        volume_expansion = 0

    # Volatility expansion
    if atr_multiple >= 4:
        volatility_expansion = 3
    elif atr_multiple >= 2.5:
        volatility_expansion = 2
    elif atr_multiple >= 1.5:
        volatility_expansion = 1
    else:
        volatility_expansion = 0

    # Range control
    if range_position >= 0.85:
        range_control = 2
    elif range_position >= 0.70:
        range_control = 1
    else:
        range_control = 0

    # Trend quality
    trend_quality = 0
    if price_above_ema20:
        trend_quality += 1
    if ema20_above_ema50:
        trend_quality += 1
    if adx_strength >= 20:
        trend_quality += 1

    # On-chain confirmation
    onchain_confirmation = 0
    if smart_wallets_active >= 2:
        onchain_confirmation += 2
    if repeat_buyers:
        onchain_confirmation += 2
    if net_flow_positive:
        onchain_confirmation += 1
    if holder_growth_24h >= 5:
        onchain_confirmation += 1
    onchain_confirmation = clamp_score(onchain_confirmation, 0, 4)

    # Penalty
    risk_penalty = 0
    if low_liquidity_penalty:
        risk_penalty += 3
    if concentration_penalty:
        risk_penalty += 2
    if suspicious_volume_penalty:
        risk_penalty += 3
    risk_penalty = clamp_score(risk_penalty, 0, 5)

    return MiroBreakdown(
        volume_expansion=volume_expansion,
        volatility_expansion=volatility_expansion,
        range_control=range_control,
        trend_quality=trend_quality,
        onchain_confirmation=onchain_confirmation,
        risk_penalty=risk_penalty,
    )


def total_miro_score(b: MiroBreakdown) -> float:
    score = (
        b.volume_expansion
        + b.volatility_expansion
        + b.range_control
        + b.trend_quality
        + b.onchain_confirmation
        - b.risk_penalty
    )
    return round(max(score, 0.0), 1)


def build_smart_money(
    smart_wallets_active: int,
    repeat_buyers: bool,
    net_flow_positive: bool,
    holder_growth_24h: float,
) -> SmartMoneySnapshot:
    net_flow = "Positive (Buy > Sell)" if net_flow_positive else "Mixed / Flat"

    parts = []
    if smart_wallets_active >= 2:
        parts.append("smart accumulation visible")
    if repeat_buyers:
        parts.append("repeat entries detected")
    if holder_growth_24h >= 5:
        parts.append("holder growth supportive")

    if parts:
        summary = "Early positioning suggests " + ", ".join(parts) + "."
    else:
        summary = "No strong smart money pattern detected yet."

    return SmartMoneySnapshot(
        smart_wallets_active=smart_wallets_active,
        repeat_buyers=repeat_buyers,
        net_flow=net_flow,
        holder_growth_24h=holder_growth_24h,
        summary=summary,
    )


def build_kronos(atr_multiple: float, adx_strength: float, range_position: float) -> KronosSnapshot:
    if atr_multiple < 1.5 and adx_strength < 20:
        regime = "Low Volatility → Expansion Likely"
        bias = "Mild Bullish" if range_position >= 0.70 else "Neutral"
        confidence = 64 if range_position >= 0.70 else 56
        summary = "Compression conditions suggest rising probability of expansion."
    elif atr_multiple >= 2.5 and adx_strength >= 20:
        regime = "Active Expansion"
        bias = "Bullish"
        confidence = 72
        summary = "Momentum and volatility align for possible continuation."
    else:
        regime = "Mixed Structure"
        bias = "Neutral"
        confidence = 58
        summary = "The market structure is tradable but not clean."
    return KronosSnapshot(
        regime=regime,
        bias=bias,
        confidence=confidence,
        summary=summary,
    )


def build_risk(
    low_liquidity_penalty: bool,
    concentration_penalty: bool,
    suspicious_volume_penalty: bool,
) -> RiskSummary:
    liquidity = "Weak" if low_liquidity_penalty else "Strong"
    concentration = "Elevated" if concentration_penalty else "Moderate / Acceptable"
    suspicious_activity = "Detected" if suspicious_volume_penalty else "None detected"
    execution_risk = "Use tighter execution discipline." if any(
        [low_liquidity_penalty, concentration_penalty, suspicious_volume_penalty]
    ) else "No critical execution issue."
    return RiskSummary(
        liquidity=liquidity,
        concentration=concentration,
        suspicious_activity=suspicious_activity,
        execution_risk=execution_risk,
    )


def build_council(
    smart_money: SmartMoneySnapshot,
    kronos: KronosSnapshot,
    risk: RiskSummary,
    breakdown: MiroBreakdown,
) -> List[CouncilAgent]:
    return [
        CouncilAgent(
            name="Bull Whale",
            emoji="🐋",
            text=(
                f"{smart_money.smart_wallets_active} smart wallets active. "
                f"{'Repeat buying detected. ' if smart_money.repeat_buyers else ''}"
                "Early positioning is likely."
            ),
        ),
        CouncilAgent(
            name="Bear Risk",
            emoji="🐻",
            text=(
                f"Liquidity is {risk.liquidity.lower()} and concentration is {risk.concentration.lower()}. "
                "Structural caution remains."
            ),
        ),
        CouncilAgent(
            name="Quant Brain",
            emoji="🤖",
            text=(
                f"{kronos.regime}. Bias: {kronos.bias}. "
                f"Model confidence: {kronos.confidence}%."
            ),
        ),
        CouncilAgent(
            name="Risk Manager",
            emoji="🛡",
            text=(
                f"Risk penalty sits at {breakdown.risk_penalty}/5. "
                f"{'Wait for cleaner confirmation.' if breakdown.risk_penalty >= 2 else 'Conditions are tradable with discipline.'}"
            ),
        ),
    ]


def build_verdict(score: float) -> Tuple[str, List[str], str]:
    if score >= 11:
        return (
            "⚡ VERDICT: HIGH-CONVICTION MOMENTUM",
            [
                "Abnormal participation is present.",
                "On-chain confirmation supports the move.",
                "Structure favors continuation if follow-through appears.",
            ],
            "Act only on confirmed strength and disciplined risk sizing.",
        )
    if score >= 8:
        return (
            "🟡 VERDICT: WATCH FOR BREAKOUT",
            [
                "Momentum conditions are forming.",
                "Structure is improving but not fully resolved.",
                "Smart money behavior adds credibility.",
            ],
            "Wait for a confirmation candle or a clean expansion trigger.",
        )
    if score >= 5:
        return (
            "👁 VERDICT: WATCHLIST ONLY",
            [
                "Interesting candidate, but alignment is incomplete.",
                "Conviction is not yet strong enough.",
                "Structure remains mixed.",
            ],
            "Monitor and avoid forcing an entry.",
        )
    return (
        "• VERDICT: NOISE",
        [
            "Signal quality is low.",
            "Participation and structure are not strong enough.",
            "No meaningful edge is visible.",
        ],
        "Ignore until the setup materially improves.",
    )


def generate_report(
    token_name: str,
    symbol: str,
    chain: str,
    timeframe: str,
    price: float,
    relative_volume: float,
    atr_multiple: float,
    range_position: float,
    adx_strength: float,
    smart_wallets_active: int,
    repeat_buyers: bool,
    net_flow_positive: bool,
    holder_growth_24h: float,
    price_above_ema20: bool,
    ema20_above_ema50: bool,
    low_liquidity_penalty: bool,
    concentration_penalty: bool,
    suspicious_volume_penalty: bool,
    client_name: str,
) -> ReportData:
    token = TokenInfo(
        token_name=token_name,
        symbol=symbol,
        chain=chain,
        timeframe=timeframe,
        price=price,
        generated_at=datetime.now().strftime("%d %b %Y | %I:%M %p"),
    )

    breakdown = calculate_miro_v2(
        relative_volume=relative_volume,
        atr_multiple=atr_multiple,
        range_position=range_position,
        price_above_ema20=price_above_ema20,
        ema20_above_ema50=ema20_above_ema50,
        adx_strength=adx_strength,
        smart_wallets_active=smart_wallets_active,
        repeat_buyers=repeat_buyers,
        net_flow_positive=net_flow_positive,
        holder_growth_24h=holder_growth_24h,
        low_liquidity_penalty=low_liquidity_penalty,
        concentration_penalty=concentration_penalty,
        suspicious_volume_penalty=suspicious_volume_penalty,
    )

    miro_total = total_miro_score(breakdown)
    status = score_status(miro_total)
    smart_money = build_smart_money(
        smart_wallets_active=smart_wallets_active,
        repeat_buyers=repeat_buyers,
        net_flow_positive=net_flow_positive,
        holder_growth_24h=holder_growth_24h,
    )
    kronos = build_kronos(
        atr_multiple=atr_multiple,
        adx_strength=adx_strength,
        range_position=range_position,
    )
    risk = build_risk(
        low_liquidity_penalty=low_liquidity_penalty,
        concentration_penalty=concentration_penalty,
        suspicious_volume_penalty=suspicious_volume_penalty,
    )
    council = build_council(
        smart_money=smart_money,
        kronos=kronos,
        risk=risk,
        breakdown=breakdown,
    )
    verdict_title, verdict_points, action_note = build_verdict(miro_total)

    return ReportData(
        token=token,
        miro_total=miro_total,
        status=status,
        breakdown=breakdown,
        smart_money=smart_money,
        kronos=kronos,
        council=council,
        risk=risk,
        verdict_title=verdict_title,
        verdict_points=verdict_points,
        action_note=action_note,
        client_name=client_name or "Premium Client",
    )


# =========================
# PDF GENERATION
# =========================
def build_pdf(report: ReportData) -> bytes:
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    styles = getSampleStyleSheet()

    brand_style = ParagraphStyle(
        name="BrandStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor(COLOR_TEXT),
    )
    small_style = ParagraphStyle(
        name="SmallStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor(COLOR_SUBTEXT),
    )
    body_style = ParagraphStyle(
        name="BodyStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#DCE3EE"),
    )
    section_style = ParagraphStyle(
        name="SectionStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor(COLOR_ORANGE),
        spaceAfter=4,
    )
    verdict_style = ParagraphStyle(
        name="VerdictStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor(COLOR_GREEN),
    )

    story = []

    # Header
    logo_exists = Path(LOGO_PATH).exists()

    if logo_exists:
        logo = RLImage(LOGO_PATH, width=18 * mm, height=18 * mm)
        header_table = Table(
            [[
                logo,
                Paragraph(
                    f'<font color="{COLOR_SUBTEXT}">crypto</font><font color="{COLOR_GREEN}">.guru</font><br/><font size="9">{TAGLINE}</font>',
                    brand_style,
                ),
                Paragraph("CRYPTO INTELLIGENCE REPORT", brand_style),
            ]],
            colWidths=[22 * mm, 80 * mm, 70 * mm],
        )
    else:
        header_table = Table(
            [[
                Paragraph(
                    f'<font color="{COLOR_SUBTEXT}">crypto</font><font color="{COLOR_GREEN}">.guru</font><br/><font size="9">{TAGLINE}</font>',
                    brand_style,
                ),
                Paragraph("CRYPTO INTELLIGENCE REPORT", brand_style),
            ]],
            colWidths=[100 * mm, 72 * mm],
        )

    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )

    story.append(header_table)
    story.append(
        Paragraph(
            (
                f"Token: {report.token.token_name} ({report.token.symbol}) | "
                f"Chain: {report.token.chain} | "
                f"Timeframe: {report.token.timeframe} | "
                f"Generated: {report.token.generated_at} | "
                f"Prepared for: {report.client_name}"
            ),
            small_style,
        )
    )
    story.append(Spacer(1, 5 * mm))

    # Score
    story.append(Paragraph("01 · MIRO v2 SCORE", section_style))
    story.append(
        Paragraph(
            f'<font size="24" color="{COLOR_GREEN}"><b>{report.miro_total:.1f} / 15 — {report.status}</b></font>',
            body_style,
        )
    )
    story.append(Spacer(1, 2 * mm))

    score_table = Table(
        [
            ["Volume Expansion", f"{report.breakdown.volume_expansion} / 5"],
            ["Volatility Expansion", f"{report.breakdown.volatility_expansion} / 3"],
            ["Range Control", f"{report.breakdown.range_control} / 2"],
            ["Trend Quality", f"{report.breakdown.trend_quality} / 3"],
            ["On-Chain Confirmation", f"{report.breakdown.onchain_confirmation} / 4"],
            ["Risk Penalty", f"-{report.breakdown.risk_penalty}"],
        ],
        colWidths=[95 * mm, 30 * mm],
    )
    score_table.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#111722")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(COLOR_TEXT)),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(COLOR_BORDER)),
            ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor(COLOR_BORDER)),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(score_table)
    story.append(Spacer(1, 5 * mm))

    # Smart Money
    story.append(Paragraph("02 · SMART MONEY SNAPSHOT", section_style))
    story.append(
        Paragraph(
            (
                f"Active Smart Wallets: {report.smart_money.smart_wallets_active}<br/>"
                f"Repeat Buyers: {'Detected' if report.smart_money.repeat_buyers else 'No'}<br/>"
                f"Net Flow: {report.smart_money.net_flow}<br/>"
                f"Holder Growth (24H): {report.smart_money.holder_growth_24h:.1f}%<br/><br/>"
                f"{report.smart_money.summary}"
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 4 * mm))

    # Kronos
    story.append(Paragraph("03 · MARKET STRUCTURE", section_style))
    story.append(
        Paragraph(
            (
                f"Regime: {report.kronos.regime}<br/>"
                f"Bias: {report.kronos.bias}<br/>"
                f"Confidence: {report.kronos.confidence}%<br/><br/>"
                f"{report.kronos.summary}"
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 4 * mm))

    # Council
    story.append(Paragraph("04 · AI COUNCIL", section_style))
    for agent in report.council:
        story.append(Paragraph(f"<b>{agent.emoji} {agent.name}</b><br/>{agent.text}", body_style))
        story.append(Spacer(1, 2 * mm))

    story.append(Spacer(1, 3 * mm))

    # Risk
    story.append(Paragraph("05 · RISK SUMMARY", section_style))
    story.append(
        Paragraph(
            (
                f"Liquidity: {report.risk.liquidity}<br/>"
                f"Concentration: {report.risk.concentration}<br/>"
                f"Suspicious Activity: {report.risk.suspicious_activity}<br/>"
                f"Execution Risk: {report.risk.execution_risk}"
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 4 * mm))

    # Verdict
    story.append(Paragraph("06 · FINAL VERDICT", section_style))
    story.append(Paragraph(report.verdict_title, verdict_style))
    bullet_html = "<br/>".join([f"• {point}" for point in report.verdict_points])
    story.append(Paragraph(bullet_html, body_style))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"<b>Recommended Action:</b> {report.action_note}", body_style))
    story.append(Spacer(1, 8 * mm))

    # Footer
    story.append(
        Paragraph(
            "Generated by crypto.guru · Detect Early. Act Smart. · For informational and research purposes only. Not financial advice.",
            small_style,
        )
    )

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# =========================
# UI COMPONENTS
# =========================
def render_brand_header() -> None:
    st.markdown(
        f"""
        <div class="brand-box">
            <div class="brand-title">
                <span style="color:{COLOR_SUBTEXT};">crypto</span><span style="color:{COLOR_GREEN};">.guru</span>
            </div>
            <div class="brand-subtitle">{TAGLINE}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_token_header(report: ReportData) -> None:
    st.markdown(
        f"""
        <div class="section-box">
            <div class="section-label">Live Signal</div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap;">
                <div>
                    <div style="font-size:1.9rem; font-weight:800;">{report.token.token_name} <span style="color:{COLOR_SUBTEXT}; font-size:1rem;">· {report.token.chain}</span></div>
                    <div class="small-note">{report.token.generated_at} · Timeframe: {report.token.timeframe} · Price: ${report.token.price:,.4f}</div>
                </div>
                <div style="text-align:right;">
                    <div class="score-text" style="color:{score_color(report.miro_total)};">{report.miro_total:.1f} / 15</div>
                    <div class="status-pill">{report.status}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_breakdown(report: ReportData) -> None:
    b = report.breakdown
    rows = [
        ("Volume Expansion", make_bar(b.volume_expansion, 5), f"{b.volume_expansion} / 5"),
        ("Volatility Expansion", make_bar(b.volatility_expansion, 3), f"{b.volatility_expansion} / 3"),
        ("Range Control", make_bar(b.range_control, 2), f"{b.range_control} / 2"),
        ("Trend Quality", make_bar(b.trend_quality, 3), f"{b.trend_quality} / 3"),
        ("On-Chain Confirmation", make_bar(b.onchain_confirmation, 4), f"{b.onchain_confirmation} / 4"),
        ("Risk Penalty", make_bar(b.risk_penalty, 5), f"-{b.risk_penalty}"),
    ]

    st.markdown(
        '<div class="section-box"><div class="section-label">01 · Miro v2 Breakdown</div>',
        unsafe_allow_html=True,
    )
    for name, bar, value in rows:
        c1, c2, c3 = st.columns([2.2, 1.2, 1.0])
        c1.write(name)
        c2.code(bar, language=None)
        c3.write(value)
    st.markdown("</div>", unsafe_allow_html=True)


def render_smart_money(report: ReportData) -> None:
    s = report.smart_money
    st.markdown(
        '<div class="section-box"><div class="section-label">02 · Smart Money Snapshot</div>',
        unsafe_allow_html=True,
    )
    st.write(f"**Active Smart Wallets:** {s.smart_wallets_active}")
    st.write(f"**Repeat Buyers:** {'Detected' if s.repeat_buyers else 'No'}")
    st.write(f"**Net Flow:** {s.net_flow}")
    st.write(f"**Holder Growth (24H):** {s.holder_growth_24h:.1f}%")
    st.caption(s.summary)
    st.markdown("</div>", unsafe_allow_html=True)


def render_kronos(report: ReportData) -> None:
    k = report.kronos
    st.markdown(
        '<div class="section-box"><div class="section-label">03 · Market Structure</div>',
        unsafe_allow_html=True,
    )
    st.write(f"**Regime:** {k.regime}")
    st.write(f"**Bias:** {k.bias}")
    st.write(f"**Confidence:** {k.confidence}%")
    st.caption(k.summary)
    st.markdown("</div>", unsafe_allow_html=True)


def render_council(report: ReportData) -> None:
    st.markdown(
        '<div class="section-box"><div class="section-label">04 · AI Council</div>',
        unsafe_allow_html=True,
    )
    for agent in report.council:
        st.markdown(
            f"""
            <div class="agent-box">
                <div class="agent-title">{agent.emoji} {agent.name}</div>
                <div>{agent.text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_risk(report: ReportData) -> None:
    r = report.risk
    st.markdown(
        '<div class="section-box"><div class="section-label">05 · Risk Summary</div>',
        unsafe_allow_html=True,
    )
    st.write(f"**Liquidity:** {r.liquidity}")
    st.write(f"**Concentration:** {r.concentration}")
    st.write(f"**Suspicious Activity:** {r.suspicious_activity}")
    st.write(f"**Execution Risk:** {r.execution_risk}")
    st.markdown("</div>", unsafe_allow_html=True)


def render_verdict(report: ReportData) -> None:
    bullets = "".join([f"<li>{item}</li>" for item in report.verdict_points])
    st.markdown(
        f"""
        <div class="verdict-box">
            <div class="section-label" style="margin-bottom:0.5rem;">06 · Final Verdict</div>
            <div style="font-size:1.25rem; font-weight:900; color:{COLOR_GREEN}; margin-bottom:0.6rem;">{report.verdict_title}</div>
            <ul style="margin-top:0.2rem; margin-bottom:0.8rem;">{bullets}</ul>
            <div><b>Recommended Action:</b> {report.action_note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# MAIN APP
# =========================
def main() -> None:
    inject_css()
    render_brand_header()

    with st.sidebar:
        st.header("Signal Inputs")

        token_name = st.text_input("Token Name", value="AAVE")
        symbol = st.text_input("Symbol", value="AAVE")
        chain = st.selectbox("Chain", ["Ethereum", "Base", "Solana", "Arbitrum", "BNB Chain"], index=0)
        timeframe = st.selectbox("Timeframe", ["1H", "4H", "1D"], index=1)
        price = st.number_input("Price", min_value=0.0, value=171.25, step=0.01)

        st.subheader("Miro v2")
        relative_volume = st.number_input("Relative Volume", min_value=0.0, value=6.2, step=0.1)
        atr_multiple = st.number_input("ATR Multiple", min_value=0.0, value=2.4, step=0.1)
        range_position = st.slider("Range Position", min_value=0.0, max_value=1.0, value=0.82, step=0.01)
        adx_strength = st.number_input("ADX Strength", min_value=0.0, value=18.0, step=0.5)

        st.subheader("On-Chain")
        smart_wallets_active = st.number_input("Smart Wallets Active", min_value=0, value=3, step=1)
        repeat_buyers = st.checkbox("Repeat Buyers Detected", value=True)
        net_flow_positive = st.checkbox("Net Flow Positive", value=True)
        holder_growth_24h = st.number_input("Holder Growth 24H (%)", min_value=-100.0, value=6.2, step=0.1)

        st.subheader("Trend")
        price_above_ema20 = st.checkbox("Price Above EMA20", value=True)
        ema20_above_ema50 = st.checkbox("EMA20 Above EMA50", value=True)

        st.subheader("Penalties")
        low_liquidity_penalty = st.checkbox("Low Liquidity Penalty", value=False)
        concentration_penalty = st.checkbox("Concentration Penalty", value=False)
        suspicious_volume_penalty = st.checkbox("Suspicious Volume Penalty", value=False)

        st.subheader("Premium Report")
        client_name = st.text_input("Client Name", value="Premium Client")

    report = generate_report(
        token_name=token_name,
        symbol=symbol,
        chain=chain,
        timeframe=timeframe,
        price=price,
        relative_volume=relative_volume,
        atr_multiple=atr_multiple,
        range_position=range_position,
        adx_strength=adx_strength,
        smart_wallets_active=smart_wallets_active,
        repeat_buyers=repeat_buyers,
        net_flow_positive=net_flow_positive,
        holder_growth_24h=holder_growth_24h,
        price_above_ema20=price_above_ema20,
        ema20_above_ema50=ema20_above_ema50,
        low_liquidity_penalty=low_liquidity_penalty,
        concentration_penalty=concentration_penalty,
        suspicious_volume_penalty=suspicious_volume_penalty,
        client_name=client_name,
    )

    render_token_header(report)

    left_col, right_col = st.columns([1.1, 0.9])

    with left_col:
        render_breakdown(report)
        render_smart_money(report)
        render_kronos(report)

    with right_col:
        render_council(report)
        render_risk(report)
        render_verdict(report)

        pdf_bytes = build_pdf(report)
        filename = f"{report.token.symbol}_intelligence_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"

        st.download_button(
            label="Download Intelligence Report (PDF)",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=True,
        )

    st.markdown(
        f'<div class="footer-note">{BRAND_NAME} · {TAGLINE}</div>',
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
