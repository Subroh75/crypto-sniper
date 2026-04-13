from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

import streamlit as st
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
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

COLOR_BG = "#0A0E14"
COLOR_CARD = "#111722"
COLOR_CARD_2 = "#0F141D"
COLOR_BORDER = "#242E3F"
COLOR_TEXT = "#D9E1EC"
COLOR_TEXT_STRONG = "#F3F6FB"
COLOR_TEXT_DARKER = "#C2CCD9"
COLOR_SUBTEXT = "#8692A3"
COLOR_GREEN = "#7CFF5B"
COLOR_GREEN_SOFT = "#67D84A"
COLOR_AMBER = "#D7A63A"
COLOR_RED = "#D96A6A"
COLOR_ORANGE = "#D48A2F"
COLOR_PDF_HEADER = "#0B1018"
COLOR_PDF_RULE = "#222C3A"

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
    volume_expansion: int
    volatility_expansion: int
    range_control: int
    trend_quality: int
    onchain_confirmation: int
    risk_penalty: int


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
            padding-top: 1.15rem;
            padding-bottom: 1.8rem;
            max-width: 1180px;
        }}

        section[data-testid="stSidebar"] {{
            background-color: {COLOR_CARD_2};
        }}

        .brand-box {{
            background: linear-gradient(180deg, {COLOR_CARD}, #0E141E);
            border: 1px solid {COLOR_BORDER};
            border-radius: 16px;
            padding: 16px 18px;
            margin-bottom: 16px;
        }}

        .brand-title {{
            font-size: 2rem;
            font-weight: 900;
            margin: 0;
            line-height: 1.05;
            letter-spacing: -0.02em;
        }}

        .brand-subtitle {{
            color: {COLOR_SUBTEXT};
            font-size: 0.92rem;
            margin-top: 0.22rem;
            font-weight: 500;
            letter-spacing: 0.01em;
        }}

        .section-box {{
            background: linear-gradient(180deg, {COLOR_CARD}, #0F151F);
            border: 1px solid {COLOR_BORDER};
            border-radius: 15px;
            padding: 15px 17px;
            margin-bottom: 13px;
        }}

        .section-label {{
            color: {COLOR_ORANGE};
            font-size: 0.78rem;
            font-weight: 900;
            letter-spacing: 0.12rem;
            text-transform: uppercase;
            margin-bottom: 0.75rem;
        }}

        .score-text {{
            font-size: 2.15rem;
            font-weight: 900;
            margin-bottom: 0.14rem;
            letter-spacing: -0.03em;
        }}

        .status-pill {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid {COLOR_BORDER};
            background: #171F2C;
            font-size: 0.78rem;
            font-weight: 800;
            color: {COLOR_TEXT_STRONG};
        }}

        .small-note {{
            color: {COLOR_SUBTEXT};
            font-size: 0.88rem;
            line-height: 1.5;
            font-weight: 500;
        }}

        .agent-box {{
            background: #0F151F;
            border: 1px solid {COLOR_BORDER};
            border-radius: 12px;
            padding: 11px 13px;
            margin-bottom: 9px;
        }}

        .agent-title {{
            font-size: 0.82rem;
            font-weight: 900;
            letter-spacing: 0.07rem;
            margin-bottom: 0.26rem;
            text-transform: uppercase;
            color: {COLOR_TEXT_DARKER};
        }}

        .verdict-box {{
            background: linear-gradient(180deg, #101912, #0D1510);
            border: 1px solid #29472D;
            border-radius: 14px;
            padding: 15px;
        }}

        .footer-note {{
            text-align: center;
            color: {COLOR_SUBTEXT};
            font-size: 0.83rem;
            margin-top: 18px;
        }}

        .compact-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            padding: 5px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.93rem;
        }}

        .compact-row:last-child {{
            border-bottom: none;
        }}

        .compact-label {{
            flex: 1;
            color: {COLOR_TEXT_DARKER};
            font-weight: 600;
        }}

        .compact-bar {{
            width: 70px;
            text-align: center;
            color: {COLOR_GREEN_SOFT};
            font-family: monospace;
            font-weight: 700;
        }}

        .compact-value {{
            width: 52px;
            text-align: right;
            color: {COLOR_TEXT};
            font-size: 0.90rem;
            font-weight: 700;
        }}

        .stDownloadButton > button {{
            background: linear-gradient(180deg, #16211A, #121A15);
            color: {COLOR_TEXT_STRONG};
            border: 1px solid #29472D;
            border-radius: 12px;
            font-weight: 800;
        }}

        .stTextInput input, .stNumberInput input {{
            background-color: #0E141D !important;
            color: {COLOR_TEXT_STRONG} !important;
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
        return "#C89C42"
    return COLOR_RED


def clamp_score(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def make_bar(value: int, max_value: int) -> str:
    value = max(0, min(value, max_value))
    return ("█" * value) + ("░" * (max_value - value))


def get_safe_logo_for_pdf(path: str, width_mm: float = 14, height_mm: float = 14):
    if not Path(path).exists():
        return None

    try:
        with Image.open(path) as img:
            img = img.convert("RGBA")
            pixels = img.getdata()
            cleaned = []
            for pixel in pixels:
                r, g, b, a = pixel
                if r > 245 and g > 245 and b > 245:
                    cleaned.append((255, 255, 255, 0))
                else:
                    cleaned.append((r, g, b, a))
            img.putdata(cleaned)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return RLImage(buf, width=width_mm * mm, height=height_mm * mm)
    except Exception:
        return None


def pdf_header_band(canvas, doc):
    canvas.saveState()
    page_width, page_height = A4

    canvas.setFillColor(colors.HexColor(COLOR_PDF_HEADER))
    canvas.rect(0, page_height - 28 * mm, page_width, 28 * mm, fill=1, stroke=0)

    canvas.setStrokeColor(colors.HexColor(COLOR_PDF_RULE))
    canvas.setLineWidth(0.6)
    canvas.line(16 * mm, page_height - 29 * mm, page_width - 16 * mm, page_height - 29 * mm)

    canvas.restoreState()


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
    if relative_volume >= 8:
        volume_expansion = 5
    elif relative_volume >= 4:
        volume_expansion = 3
    elif relative_volume >= 2:
        volume_expansion = 2
    else:
        volume_expansion = 0

    if atr_multiple >= 4:
        volatility_expansion = 3
    elif atr_multiple >= 2.5:
        volatility_expansion = 2
    elif atr_multiple >= 1.5:
        volatility_expansion = 1
    else:
        volatility_expansion = 0

    if range_position >= 0.85:
        range_control = 2
    elif range_position >= 0.70:
        range_control = 1
    else:
        range_control = 0

    trend_quality = 0
    if price_above_ema20:
        trend_quality += 1
    if ema20_above_ema50:
        trend_quality += 1
    if adx_strength >= 20:
        trend_quality += 1

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
    net_flow = "Positive" if net_flow_positive else "Mixed"

    parts = []
    if smart_wallets_active >= 2:
        parts.append("accumulation visible")
    if repeat_buyers:
        parts.append("repeat buys")
    if holder_growth_24h >= 5:
        parts.append("holder growth supportive")

    summary = "Early positioning suggests " + ", ".join(parts) + "." if parts else "No strong smart money pattern yet."

    return SmartMoneySnapshot(
        smart_wallets_active=smart_wallets_active,
        repeat_buyers=repeat_buyers,
        net_flow=net_flow,
        holder_growth_24h=holder_growth_24h,
        summary=summary,
    )


def build_kronos(atr_multiple: float, adx_strength: float, range_position: float) -> KronosSnapshot:
    if atr_multiple < 1.5 and adx_strength < 20:
        regime = "Compression"
        bias = "Mild Bullish" if range_position >= 0.70 else "Neutral"
        confidence = 64 if range_position >= 0.70 else 56
        summary = "Expansion probability is rising."
    elif atr_multiple >= 2.5 and adx_strength >= 20:
        regime = "Expansion"
        bias = "Bullish"
        confidence = 72
        summary = "Momentum and volatility support continuation."
    else:
        regime = "Mixed"
        bias = "Neutral"
        confidence = 58
        summary = "Structure is tradable but not clean."

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
    concentration = "Elevated" if concentration_penalty else "Moderate"
    suspicious_activity = "Detected" if suspicious_volume_penalty else "None"
    execution_risk = "Use tighter execution." if any(
        [low_liquidity_penalty, concentration_penalty, suspicious_volume_penalty]
    ) else "No critical issue."

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
                f"{smart_money.smart_wallets_active} active wallets. "
                f"{'Repeat buys seen. ' if smart_money.repeat_buyers else ''}"
                "Accumulation is building."
            ),
        ),
        CouncilAgent(
            name="Bear Risk",
            emoji="🐻",
            text=(
                f"Liquidity {risk.liquidity.lower()}, concentration {risk.concentration.lower()}. "
                "Stay selective."
            ),
        ),
        CouncilAgent(
            name="Quant Brain",
            emoji="🤖",
            text=(
                f"{kronos.regime} regime, {kronos.bias.lower()} bias. "
                f"Confidence {kronos.confidence}%."
            ),
        ),
        CouncilAgent(
            name="Risk Manager",
            emoji="🛡",
            text=(
                f"Risk {breakdown.risk_penalty}/5. "
                f"{'Wait for confirmation.' if breakdown.risk_penalty >= 2 else 'Tradable with discipline.'}"
            ),
        ),
    ]


def build_verdict(score: float) -> Tuple[str, List[str], str]:
    if score >= 11:
        return (
            "⚡ VERDICT: HIGH-CONVICTION MOMENTUM",
            [
                "Participation is strong.",
                "On-chain confirmation is supportive.",
                "Structure can continue with follow-through.",
            ],
            "Act only on confirmed strength and disciplined sizing.",
        )
    if score >= 8:
        return (
            "🟡 VERDICT: WATCH FOR BREAKOUT",
            [
                "Momentum is forming.",
                "Structure is improving.",
                "Smart money adds credibility.",
            ],
            "Wait for a clean trigger before acting.",
        )
    if score >= 5:
        return (
            "👁 VERDICT: WATCHLIST ONLY",
            [
                "Interesting setup, but incomplete.",
                "Conviction is not strong enough.",
                "Structure remains mixed.",
            ],
            "Monitor and avoid forcing an entry.",
        )
    return (
        "• VERDICT: NOISE",
        [
            "Signal quality is low.",
            "Structure is not aligned.",
            "No meaningful edge is visible.",
        ],
        "Ignore until the setup improves.",
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
        topMargin=34 * mm,
        bottomMargin=12 * mm,
    )

    styles = getSampleStyleSheet()

    brand_style = ParagraphStyle(
        name="BrandStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=16,
        textColor=colors.HexColor(COLOR_TEXT_STRONG),
    )
    report_title_style = ParagraphStyle(
        name="ReportTitleStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=13.2,
        leading=14,
        textColor=colors.HexColor(COLOR_TEXT_STRONG),
        alignment=TA_RIGHT,
    )
    small_style = ParagraphStyle(
        name="SmallStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.3,
        leading=10.5,
        textColor=colors.HexColor(COLOR_SUBTEXT),
    )
    body_style = ParagraphStyle(
        name="BodyStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.4,
        leading=12.3,
        textColor=colors.HexColor(COLOR_TEXT_DARKER),
    )
    section_style = ParagraphStyle(
        name="SectionStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.2,
        leading=12.5,
        textColor=colors.HexColor(COLOR_ORANGE),
        spaceAfter=2,
    )
    verdict_style = ParagraphStyle(
        name="VerdictStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12.5,
        leading=14.8,
        textColor=colors.HexColor(COLOR_GREEN_SOFT),
    )

    story = []

    safe_logo = get_safe_logo_for_pdf(LOGO_PATH, width_mm=12.5, height_mm=12.5)

    brand_copy = Paragraph(
        f'<font color="{COLOR_TEXT_DARKER}">crypto</font><font color="{COLOR_GREEN_SOFT}">.guru</font><br/><font size="7.6" color="{COLOR_SUBTEXT}">{TAGLINE}</font>',
        brand_style,
    )
    report_title = Paragraph("CRYPTO INTELLIGENCE REPORT", report_title_style)

    if safe_logo is not None:
        brand_table = Table(
            [[safe_logo, brand_copy]],
            colWidths=[14 * mm, 56 * mm],
        )
    else:
        brand_table = Table(
            [[brand_copy]],
            colWidths=[70 * mm],
        )

    brand_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    header_table = Table(
        [[brand_table, report_title]],
        colWidths=[92 * mm, 78 * mm],
    )
    header_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    story.append(header_table)
    story.append(Spacer(1, 3 * mm))

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
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("01 · MIRO v2 SCORE", section_style))
    score_table = Table(
        [[
            Paragraph(
                f'<font size="21" color="{COLOR_GREEN_SOFT}"><b>{report.miro_total:.1f} / 15</b></font>',
                body_style,
            ),
            Paragraph(
                f'<font size="11.2" color="{COLOR_TEXT_STRONG}"><b>{report.status}</b></font>',
                body_style,
            ),
        ]],
        colWidths=[36 * mm, 96 * mm],
    )
    score_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(score_table)
    story.append(Spacer(1, 1.8 * mm))

    compact_score_table = Table(
        [
            ["Volume", f"{report.breakdown.volume_expansion}/5"],
            ["Volatility", f"{report.breakdown.volatility_expansion}/3"],
            ["Range", f"{report.breakdown.range_control}/2"],
            ["Trend", f"{report.breakdown.trend_quality}/3"],
            ["On-Chain", f"{report.breakdown.onchain_confirmation}/4"],
            ["Risk", f"-{report.breakdown.risk_penalty}"],
        ],
        colWidths=[42 * mm, 15 * mm],
    )
    compact_score_table.setStyle(
        TableStyle(
            [
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(COLOR_TEXT_DARKER)),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ]
        )
    )
    story.append(compact_score_table)
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("02 · SMART MONEY SNAPSHOT", section_style))
    story.append(
        Paragraph(
            (
                f"<b>Active Smart Wallets:</b> {report.smart_money.smart_wallets_active}<br/>"
                f"<b>Repeat Buyers:</b> {'Detected' if report.smart_money.repeat_buyers else 'No'}<br/>"
                f"<b>Net Flow:</b> {report.smart_money.net_flow}<br/>"
                f"<b>Holder Growth (24H):</b> {report.smart_money.holder_growth_24h:.1f}%<br/><br/>"
                f"{report.smart_money.summary}"
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 3.6 * mm))

    story.append(Paragraph("03 · MARKET STRUCTURE", section_style))
    story.append(
        Paragraph(
            (
                f"<b>Regime:</b> {report.kronos.regime}<br/>"
                f"<b>Bias:</b> {report.kronos.bias}<br/>"
                f"<b>Confidence:</b> {report.kronos.confidence}%<br/><br/>"
                f"{report.kronos.summary}"
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 3.6 * mm))

    story.append(Paragraph("04 · AI COUNCIL", section_style))
    for agent in report.council:
        story.append(Paragraph(f"<b>{agent.emoji} {agent.name}:</b> {agent.text}", body_style))
        story.append(Spacer(1, 1.2 * mm))

    story.append(Spacer(1, 2.5 * mm))

    story.append(Paragraph("05 · RISK SUMMARY", section_style))
    story.append(
        Paragraph(
            (
                f"<b>Liquidity:</b> {report.risk.liquidity}<br/>"
                f"<b>Concentration:</b> {report.risk.concentration}<br/>"
                f"<b>Suspicious Activity:</b> {report.risk.suspicious_activity}<br/>"
                f"<b>Execution Risk:</b> {report.risk.execution_risk}"
            ),
            body_style,
        )
    )
    story.append(Spacer(1, 3.6 * mm))

    story.append(Paragraph("06 · FINAL VERDICT", section_style))
    story.append(Paragraph(report.verdict_title, verdict_style))
    clean_points = "<br/>".join([f"<b>—</b> {point}" for point in report.verdict_points])
    story.append(Paragraph(clean_points, body_style))
    story.append(Spacer(1, 1.8 * mm))
    story.append(Paragraph(f"<b>Recommended Action:</b> {report.action_note}", body_style))
    story.append(Spacer(1, 6 * mm))

    story.append(
        Paragraph(
            "Generated by crypto.guru · Detect Early. Act Smart. · For informational and research purposes only. Not financial advice.",
            small_style,
        )
    )

    doc.build(story, onFirstPage=pdf_header_band, onLaterPages=pdf_header_band)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# =========================
# UI COMPONENTS
# =========================
def render_brand_header() -> None:
    st.markdown('<div class="brand-box">', unsafe_allow_html=True)

    if Path(LOGO_PATH).exists():
        col1, col2 = st.columns([1, 7], gap="small")
        with col1:
            st.image(LOGO_PATH, width=72)
        with col2:
            st.markdown(
                f"""
                <div class="brand-title">
                    <span style="color:{COLOR_TEXT_DARKER};">crypto</span><span style="color:{COLOR_GREEN_SOFT};">.guru</span>
                </div>
                <div class="brand-subtitle">{TAGLINE}</div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f"""
            <div class="brand-title">
                <span style="color:{COLOR_TEXT_DARKER};">crypto</span><span style="color:{COLOR_GREEN_SOFT};">.guru</span>
            </div>
            <div class="brand-subtitle">{TAGLINE}</div>
            <div style="margin-top:8px; color:{COLOR_RED}; font-size:0.9rem;">
                Logo not found at: {LOGO_PATH}
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


def render_token_header(report: ReportData) -> None:
    st.markdown(
        f"""
        <div class="section-box">
            <div class="section-label">Live Signal</div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap;">
                <div>
                    <div style="font-size:1.9rem; font-weight:900; color:{COLOR_TEXT_STRONG}; letter-spacing:-0.02em;">{report.token.token_name} <span style="color:{COLOR_SUBTEXT}; font-size:1rem; font-weight:700;">· {report.token.chain}</span></div>
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
        ("Volume", make_bar(b.volume_expansion, 5), f"{b.volume_expansion}/5"),
        ("Volatility", make_bar(b.volatility_expansion, 3), f"{b.volatility_expansion}/3"),
        ("Range", make_bar(b.range_control, 2), f"{b.range_control}/2"),
        ("Trend", make_bar(b.trend_quality, 3), f"{b.trend_quality}/3"),
        ("On-Chain", make_bar(b.onchain_confirmation, 4), f"{b.onchain_confirmation}/4"),
        ("Risk", make_bar(b.risk_penalty, 5), f"-{b.risk_penalty}"),
    ]

    st.markdown(
        '<div class="section-box"><div class="section-label">01 · Miro v2 Breakdown</div>',
        unsafe_allow_html=True,
    )

    for name, bar, value in rows:
        st.markdown(
            f"""
            <div class="compact-row">
                <div class="compact-label">{name}</div>
                <div class="compact-bar">{bar}</div>
                <div class="compact-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
                <div style="color:{COLOR_TEXT_DARKER}; font-weight:600;">{agent.text}</div>
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
            <div class="section-label" style="margin-bottom:0.45rem;">06 · Final Verdict</div>
            <div style="font-size:1.2rem; font-weight:900; color:{COLOR_GREEN_SOFT}; margin-bottom:0.55rem; letter-spacing:-0.01em;">{report.verdict_title}</div>
            <ul style="margin-top:0.15rem; margin-bottom:0.7rem; color:{COLOR_TEXT_DARKER}; font-weight:600;">{bullets}</ul>
            <div style="color:{COLOR_TEXT_STRONG};"><b>Recommended Action:</b> {report.action_note}</div>
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
