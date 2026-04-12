# app.py
from __future__ import annotations

import base64
import io
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
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
    initial_sidebar_state="collapsed",
)


# =========================
# DATA MODELS
# =========================
@dataclass
class TokenContext:
    token_name: str
    symbol: str
    chain: str
    timeframe: str
    price: float
    timestamp: str


@dataclass
class MiroScoreBreakdown:
    volume_expansion: int         # 0-5
    volatility_expansion: int     # 0-3
    range_control: int            # 0-2
    trend_quality: int            # 0-3
    onchain_confirmation: int     # 0-4
    risk_penalty: int             # 0-5


@dataclass
class SmartMoneySnapshot:
    smart_wallets_active: int
    repeat_buyers_detected: bool
    net_flow: str
    holder_growth_24h: float
    note: str


@dataclass
class KronosSnapshot:
    regime: str
    bias: str
    confidence: int
    note: str


@dataclass
class CouncilAgent:
    title: str
    emoji: str
    text: str


@dataclass
class RiskSummary:
    liquidity: str
    concentration: str
    distribution_signals: str
    warnings: str


@dataclass
class ReportPayload:
    token: TokenContext
    miro_total: float
    status_label: str
    breakdown: MiroScoreBreakdown
    smart_money: SmartMoneySnapshot
    kronos: KronosSnapshot
    council: List[CouncilAgent]
    risk: RiskSummary
    verdict_title: str
    verdict_bullets: List[str]
    verdict_action: str
    client_name: str


# =========================
# BRAND CONFIG
# =========================
BRAND_NAME = "crypto.guru"
TAGLINE = "Detect Early. Act Smart."
APP_BG = "#05070B"
CARD_BG = "#0C1220"
CARD_BG_2 = "#0F172A"
TEXT_PRIMARY = "#E5E7EB"
TEXT_MUTED = "#8B98A7"
TEXT_SOFT = "#B8BDC7"
GREEN = "#7CFF5B"
GREEN_2 = "#00FF9C"
AMBER = "#FFB800"
RED = "#FF5C5C"
ORANGE = "#FF7A1A"
BORDER = "#1C2436"


# =========================
# UTILITIES
# =========================
def safe_float(value: float, digits: int = 2) -> str:
    return f"{value:.{digits}f}"


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
        return GREEN
    if score >= 8:
        return AMBER
    if score >= 5:
        return "#D6A24A"
    return RED


def load_logo_base64(logo_path: str = "assets/crypto_guru_logo.png") -> str:
    """
    Loads a local logo if available. If not, the app falls back to a text-only header.
    Put your logo at assets/crypto_guru_logo.png in your GitHub repo.
    """
    path = Path(logo_path)
    if not path.exists():
        return ""
    encoded = base64.b64encode(path.read_bytes()).decode("utf-8")
    return encoded


def create_brand_header_html(logo_b64: str) -> str:
    logo_html = ""
    if logo_b64:
        logo_html = f"""
        <img src="data:image/png;base64,{logo_b64}" class="brand-logo" />
        """
    else:
        logo_html = """
        <div class="brand-fallback-icon">◉</div>
        """

    return f"""
    <div class="brand-shell">
        <div class="brand-left">
            {logo_html}
            <div class="brand-copy">
                <div class="brand-title">
                    <span class="brand-crypto">crypto</span><span class="brand-dot">.</span><span class="brand-guru">guru</span>
                </div>
                <div class="brand-tagline">{TAGLINE}</div>
            </div>
        </div>
    </div>
    """


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
            .stApp {{
                background: {APP_BG};
                color: {TEXT_PRIMARY};
            }}

            .block-container {{
                padding-top: 1.4rem;
                padding-bottom: 2rem;
                max-width: 1200px;
            }}

            .brand-shell {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: linear-gradient(180deg, rgba(12,18,32,0.95), rgba(12,18,32,0.78));
                border: 1px solid {BORDER};
                border-radius: 18px;
                padding: 16px 20px;
                margin-bottom: 18px;
            }}

            .brand-left {{
                display: flex;
                align-items: center;
                gap: 14px;
            }}

            .brand-logo {{
                width: 58px;
                height: 58px;
                object-fit: contain;
                border-radius: 12px;
            }}

            .brand-fallback-icon {{
                width: 58px;
                height: 58px;
                border-radius: 16px;
                background: radial-gradient(circle at center, rgba(124,255,91,0.18), rgba(124,255,91,0.02));
                border: 1px solid rgba(124,255,91,0.25);
                display: flex;
                align-items: center;
                justify-content: center;
                color: {GREEN};
                font-size: 24px;
                font-weight: 700;
            }}

            .brand-copy {{
                display: flex;
                flex-direction: column;
                line-height: 1.1;
            }}

            .brand-title {{
                font-size: 32px;
                font-weight: 800;
                letter-spacing: -0.5px;
            }}

            .brand-crypto {{
                color: {TEXT_SOFT};
            }}

            .brand-dot {{
                color: {GREEN};
            }}

            .brand-guru {{
                color: {GREEN};
            }}

            .brand-tagline {{
                margin-top: 6px;
                color: {TEXT_MUTED};
                font-size: 13px;
                font-weight: 500;
                letter-spacing: 0.2px;
            }}

            .token-meta-card {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 18px;
                padding: 18px 20px;
                margin-bottom: 18px;
            }}

            .section-card {{
                background: {CARD_BG};
                border: 1px solid {BORDER};
                border-radius: 18px;
                padding: 18px 20px;
                margin-bottom: 16px;
            }}

            .section-title {{
                color: {ORANGE};
                font-size: 13px;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 3px;
                margin-bottom: 12px;
            }}

            .token-line {{
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                gap: 16px;
                flex-wrap: wrap;
            }}

            .token-name {{
                font-size: 30px;
                font-weight: 800;
                color: {TEXT_PRIMARY};
            }}

            .token-sub {{
                color: {TEXT_MUTED};
                font-size: 14px;
                margin-top: 4px;
            }}

            .miro-score {{
                font-size: 34px;
                font-weight: 900;
                letter-spacing: -0.7px;
            }}

            .status-pill {{
                display: inline-block;
                margin-top: 8px;
                padding: 7px 12px;
                border-radius: 999px;
                background: rgba(124,255,91,0.08);
                border: 1px solid rgba(124,255,91,0.20);
                color: {TEXT_PRIMARY};
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.4px;
            }}

            .metric-row {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px 0;
                border-bottom: 1px solid rgba(255,255,255,0.05);
                gap: 12px;
            }}

            .metric-row:last-child {{
                border-bottom: none;
            }}

            .metric-label {{
                color: {TEXT_SOFT};
                font-size: 14px;
                font-weight: 500;
            }}

            .metric-value {{
                color: {TEXT_PRIMARY};
                font-size: 15px;
                font-weight: 700;
            }}

            .bar-wrap {{
                display: inline-flex;
                gap: 4px;
                vertical-align: middle;
                margin-right: 10px;
            }}

            .bar-cell {{
                width: 14px;
                height: 8px;
                border-radius: 999px;
                background: rgba(255,255,255,0.08);
            }}

            .bar-on-green {{
                background: {GREEN};
            }}

            .bar-on-amber {{
                background: {AMBER};
            }}

            .bar-on-red {{
                background: {RED};
            }}

            .agent-card {{
                background: {CARD_BG_2};
                border: 1px solid {BORDER};
                border-left: 4px solid {ORANGE};
                border-radius: 16px;
                padding: 14px 16px;
                margin-bottom: 12px;
            }}

            .agent-title {{
                font-size: 14px;
                font-weight: 800;
                letter-spacing: 2px;
                text-transform: uppercase;
                color: {TEXT_SOFT};
                margin-bottom: 8px;
            }}

            .agent-body {{
                color: {TEXT_PRIMARY};
                font-size: 15px;
                line-height: 1.55;
            }}

            .verdict-box {{
                background: linear-gradient(180deg, rgba(124,255,91,0.07), rgba(124,255,91,0.03));
                border: 1px solid rgba(124,255,91,0.18);
                border-radius: 18px;
                padding: 18px 20px;
            }}

            .verdict-title {{
                color: {GREEN};
                font-size: 22px;
                font-weight: 900;
                margin-bottom: 10px;
            }}

            .verdict-bullet {{
                color: {TEXT_PRIMARY};
                font-size: 15px;
                line-height: 1.65;
            }}

            .footer-note {{
                color: {TEXT_MUTED};
                font-size: 12px;
                text-align: center;
                margin-top: 20px;
                margin-bottom: 14px;
            }}

            .stDownloadButton button {{
                width: 100%;
                background: linear-gradient(180deg, rgba(124,255,91,0.20), rgba(124,255,91,0.10));
                border: 1px solid rgba(124,255,91,0.28);
                color: {TEXT_PRIMARY};
                border-radius: 14px;
                padding: 0.8rem 1rem;
                font-weight: 800;
                letter-spacing: 0.2px;
            }}

            .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {{
                background: {CARD_BG} !important;
                color: {TEXT_PRIMARY} !important;
                border-radius: 12px !important;
            }}

            .stCheckbox label, .stMarkdown, .stCaption, .stRadio label {{
                color: {TEXT_PRIMARY};
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_bar(value: int, maximum: int, kind: str = "green") -> str:
    css_class = {
        "green": "bar-on-green",
        "amber": "bar-on-amber",
        "red": "bar-on-red",
    }.get(kind, "bar-on-green")
    cells = []
    for i in range(maximum):
        active = css_class if i < value else ""
        cells.append(f'<span class="bar-cell {active}"></span>')
    return f'<span class="bar-wrap">{"".join(cells)}</span>'


# =========================
# MOCK / PLACEHOLDER LOGIC
# Replace these with your real pipeline
# =========================
def calculate_miro_v2(
    relative_volume: float,
    atr_multiple: float,
    range_position: float,
    price_above_ema20: bool,
    ema20_above_ema50: bool,
    adx_strength: float,
    smart_wallets_active: int,
    repeat_buyers_detected: bool,
    net_flow_positive: bool,
    holder_growth_24h: float,
    low_liquidity_penalty: bool,
    concentration_penalty: bool,
    suspicious_volume_penalty: bool,
) -> MiroScoreBreakdown:
    # Volume Expansion V: 0-5
    if relative_volume >= 8:
        volume_expansion = 5
    elif relative_volume >= 4:
        volume_expansion = 3
    elif relative_volume >= 2:
        volume_expansion = 2
    else:
        volume_expansion = 0

    # Volatility Expansion P: 0-3
    if atr_multiple >= 4:
        volatility_expansion = 3
    elif atr_multiple >= 2.5:
        volatility_expansion = 2
    elif atr_multiple >= 1.5:
        volatility_expansion = 1
    else:
        volatility_expansion = 0

    # Range Control R: 0-2
    if range_position >= 0.85:
        range_control = 2
    elif range_position >= 0.70:
        range_control = 1
    else:
        range_control = 0

    # Trend Quality T: 0-3
    trend_quality = 0
    if price_above_ema20:
        trend_quality += 1
    if ema20_above_ema50:
        trend_quality += 1
    if adx_strength >= 20:
        trend_quality += 1

    # On-chain Confirmation O: 0-4
    onchain_confirmation = 0
    if smart_wallets_active >= 2:
        onchain_confirmation += 2
    if repeat_buyers_detected:
        onchain_confirmation += 2
    if net_flow_positive:
        onchain_confirmation += 1
    if holder_growth_24h >= 5:
        onchain_confirmation += 1
    onchain_confirmation = min(onchain_confirmation, 4)

    # Risk Penalty X: 0-5
    risk_penalty = 0
    if low_liquidity_penalty:
        risk_penalty += 3
    if concentration_penalty:
        risk_penalty += 2
    if suspicious_volume_penalty:
        risk_penalty += 3
    risk_penalty = min(risk_penalty, 5)

    return MiroScoreBreakdown(
        volume_expansion=volume_expansion,
        volatility_expansion=volatility_expansion,
        range_control=range_control,
        trend_quality=trend_quality,
        onchain_confirmation=onchain_confirmation,
        risk_penalty=risk_penalty,
    )


def total_miro_score(b: MiroScoreBreakdown) -> float:
    score = (
        b.volume_expansion
        + b.volatility_expansion
        + b.range_control
        + b.trend_quality
        + b.onchain_confirmation
        - b.risk_penalty
    )
    return round(max(score, 0), 1)


def build_kronos_snapshot(
    atr_multiple: float,
    adx_strength: float,
    range_position: float,
) -> KronosSnapshot:
    if atr_multiple < 1.5 and adx_strength < 20:
        regime = "Low Volatility → Expansion Likely"
        bias = "Mild Bullish" if range_position >= 0.70 else "Neutral"
        confidence = 64 if range_position >= 0.70 else 56
        note = "Compression conditions detected with rising probability of directional expansion."
    elif atr_multiple >= 2.5 and adx_strength >= 20:
        regime = "Active Expansion"
        bias = "Bullish"
        confidence = 72
        note = "Momentum and volatility conditions support continuation, though follow-through still matters."
    else:
        regime = "Mixed Structure"
        bias = "Neutral"
        confidence = 58
        note = "Signals are not fully aligned. Structure remains tradable but not clean."
    return KronosSnapshot(regime=regime, bias=bias, confidence=confidence, note=note)


def build_smart_money_snapshot(
    smart_wallets_active: int,
    repeat_buyers_detected: bool,
    net_flow_positive: bool,
    holder_growth_24h: float,
) -> SmartMoneySnapshot:
    flow = "Positive (Buy > Sell)" if net_flow_positive else "Mixed / Flat"
    note_parts = []
    if smart_wallets_active >= 2:
        note_parts.append("Early accumulation behavior observed")
    if repeat_buyers_detected:
        note_parts.append("repeat entries detected")
    if holder_growth_24h >= 5:
        note_parts.append("wallet expansion is supportive")
    note = ", ".join(note_parts).capitalize() + "." if note_parts else "No strong smart money pattern detected yet."

    return SmartMoneySnapshot(
        smart_wallets_active=smart_wallets_active,
        repeat_buyers_detected=repeat_buyers_detected,
        net_flow=flow,
        holder_growth_24h=holder_growth_24h,
        note=note,
    )


def build_risk_summary(
    low_liquidity_penalty: bool,
    concentration_penalty: bool,
    suspicious_volume_penalty: bool,
) -> RiskSummary:
    liquidity = "Weak" if low_liquidity_penalty else "Strong"
    concentration = "Elevated" if concentration_penalty else "Moderate / Acceptable"
    distribution_signals = "Suspicious volume behavior detected" if suspicious_volume_penalty else "None detected"
    warnings = "Use tighter execution discipline." if any(
        [low_liquidity_penalty, concentration_penalty, suspicious_volume_penalty]
    ) else "No critical warning."
    return RiskSummary(
        liquidity=liquidity,
        concentration=concentration,
        distribution_signals=distribution_signals,
        warnings=warnings,
    )


def build_council(
    smart_money: SmartMoneySnapshot,
    kronos: KronosSnapshot,
    risk: RiskSummary,
    breakdown: MiroScoreBreakdown,
) -> List[CouncilAgent]:
    bull_text = (
        f"{smart_money.smart_wallets_active} smart wallets active. "
        f"{'Repeat buying pattern detected. ' if smart_money.repeat_buyers_detected else ''}"
        f"→ Early positioning likely."
    )

    bear_text = (
        f"Liquidity is {risk.liquidity.lower()} and concentration is {risk.concentration.lower()}. "
        f"→ Structural risk {'remains' if risk.concentration != 'Moderate / Acceptable' else 'is controlled for now'}."
    )

    quant_text = (
        f"{kronos.regime}. Bias: {kronos.bias}. "
        f"→ Model confidence at {kronos.confidence}%."
    )

    risk_manager_text = (
        f"Risk penalty at {breakdown.risk_penalty}/5. "
        f"→ {'Wait for cleaner confirmation before acting.' if breakdown.risk_penalty >= 2 else 'Conditions are tradable with discipline.'}"
    )

    return [
        CouncilAgent(title="Bull Whale", emoji="🐋", text=bull_text),
        CouncilAgent(title="Bear Risk", emoji="🐻", text=bear_text),
        CouncilAgent(title="Quant Brain", emoji="🤖", text=quant_text),
        CouncilAgent(title="Risk Manager", emoji="🛡", text=risk_manager_text),
    ]


def build_verdict(score: float, smart_money: SmartMoneySnapshot, kronos: KronosSnapshot) -> Tuple[str, List[str], str]:
    if score >= 11:
        title = "⚡ VERDICT: HIGH-CONVICTION MOMENTUM"
        bullets = [
            "Abnormal participation is present.",
            "Smart accumulation signals are supportive.",
            "Market structure favors continuation if follow-through appears.",
        ]
        action = "Act only on confirmed strength and disciplined risk sizing."
    elif score >= 8:
        title = "🟡 VERDICT: WATCH FOR BREAKOUT"
        bullets = [
            "Momentum conditions are forming.",
            "Structure is improving but not fully resolved.",
            "Smart money behavior adds credibility.",
        ]
        action = "Wait for confirmation candle or clean expansion trigger."
    elif score >= 5:
        title = "👁 VERDICT: WATCHLIST ONLY"
        bullets = [
            "Interesting candidate, but alignment is incomplete.",
            "Some participation exists, but conviction is not yet strong.",
            "Structure remains mixed.",
        ]
        action = "Monitor, do not force entry."
    else:
        title = "• VERDICT: NOISE"
        bullets = [
            "Signal quality is low.",
            "Participation and structure are not strong enough.",
            "No meaningful edge detected at current state.",
        ]
        action = "Ignore until the setup materially improves."

    return title, bullets, action


def generate_report_payload(
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
    repeat_buyers_detected: bool,
    net_flow_positive: bool,
    holder_growth_24h: float,
    price_above_ema20: bool,
    ema20_above_ema50: bool,
    low_liquidity_penalty: bool,
    concentration_penalty: bool,
    suspicious_volume_penalty: bool,
    client_name: str,
) -> ReportPayload:
    token = TokenContext(
        token_name=token_name,
        symbol=symbol,
        chain=chain,
        timeframe=timeframe,
        price=price,
        timestamp=datetime.now().strftime("%d %b %Y | %I:%M %p"),
    )

    breakdown = calculate_miro_v2(
        relative_volume=relative_volume,
        atr_multiple=atr_multiple,
        range_position=range_position,
        price_above_ema20=price_above_ema20,
        ema20_above_ema50=ema20_above_ema50,
        adx_strength=adx_strength,
        smart_wallets_active=smart_wallets_active,
        repeat_buyers_detected=repeat_buyers_detected,
        net_flow_positive=net_flow_positive,
        holder_growth_24h=holder_growth_24h,
        low_liquidity_penalty=low_liquidity_penalty,
        concentration_penalty=concentration_penalty,
        suspicious_volume_penalty=suspicious_volume_penalty,
    )

    total = total_miro_score(breakdown)
    status = score_status(total)
    smart_money = build_smart_money_snapshot(
        smart_wallets_active=smart_wallets_active,
        repeat_buyers_detected=repeat_buyers_detected,
        net_flow_positive=net_flow_positive,
        holder_growth_24h=holder_growth_24h,
    )
    kronos = build_kronos_snapshot(
        atr_multiple=atr_multiple,
        adx_strength=adx_strength,
        range_position=range_position,
    )
    risk = build_risk_summary(
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
    verdict_title, verdict_bullets, verdict_action = build_verdict(total, smart_money, kronos)

    return ReportPayload(
        token=token,
        miro_total=total,
        status_label=status,
        breakdown=breakdown,
        smart_money=smart_money,
        kronos=kronos,
        council=council,
        risk=risk,
        verdict_title=verdict_title,
        verdict_bullets=verdict_bullets,
        verdict_action=verdict_action,
        client_name=client_name or "Premium Client",
    )


# =========================
# PDF GENERATION
# =========================
def _pdf_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="BrandTitle",
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=22,
            textColor=colors.HexColor(TEXT_PRIMARY),
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Tagline",
            fontName="Helvetica",
            fontSize=9,
            leading=11,
            textColor=colors.HexColor(TEXT_MUTED),
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=18,
            textColor=colors.HexColor(TEXT_PRIMARY),
            alignment=TA_RIGHT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=12,
            textColor=colors.HexColor(ORANGE),
            alignment=TA_LEFT,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BodyDark",
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#DCE1E7"),
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallMuted",
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=colors.HexColor(TEXT_MUTED),
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ScoreBig",
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=26,
            textColor=colors.HexColor(GREEN),
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Verdict",
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=16,
            textColor=colors.HexColor(GREEN),
            alignment=TA_LEFT,
        )
    )
    return styles


def build_pdf(report: ReportPayload, logo_path: str = "assets/crypto_guru_logo.png") -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )

    styles = _pdf_styles()
    story = []

    # Header block
    header_left = []

    logo_file = Path(logo_path)
    if logo_file.exists():
        header_left.append(RLImage(str(logo_file), width=20 * mm, height=20 * mm))

    brand_text = Paragraph(
        f'<font color="{TEXT_SOFT}">crypto</font><font color="{GREEN}">.guru</font><br/>'
        f'<font size="9" color="{TEXT_MUTED}">{TAGLINE}</font>',
        styles["BrandTitle"],
    )
    header_left.append(brand_text)

    left_table = Table([[item] for item in header_left], colWidths=[58 * mm])
    left_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )

    right_block = Paragraph("CRYPTO INTELLIGENCE REPORT", styles["ReportTitle"])

    header = Table(
        [[left_table, right_block]],
        colWidths=[100 * mm, 70 * mm],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(header)

    meta_line = (
        f"Token: {report.token.token_name} ({report.token.symbol}) | "
        f"Chain: {report.token.chain} | "
        f"Timeframe: {report.token.timeframe} | "
        f"Generated: {report.token.timestamp} | "
        f"Prepared for: {report.client_name}"
    )
    story.append(Paragraph(meta_line, styles["SmallMuted"]))
    story.append(Spacer(1, 5 * mm))

    # Score summary
    story.append(Paragraph("01 · MIRO v2 SCORE", styles["Section"]))
    story.append(Paragraph(f"{report.miro_total:.1f} / 15 — {report.status_label}", styles["ScoreBig"]))
    story.append(Spacer(1, 3 * mm))

    score_rows = [
        ["Volume Expansion", f"{report.breakdown.volume_expansion} / 5"],
        ["Volatility Expansion", f"{report.breakdown.volatility_expansion} / 3"],
        ["Range Control", f"{report.breakdown.range_control} / 2"],
        ["Trend Quality", f"{report.breakdown.trend_quality} / 3"],
        ["On-Chain Confirmation", f"{report.breakdown.onchain_confirmation} / 4"],
        ["Risk Penalty", f"-{report.breakdown.risk_penalty}"],
    ]
    score_table = Table(score_rows, colWidths=[95 * mm, 35 * mm])
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(CARD_BG)),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor(TEXT_PRIMARY)),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor(BORDER)),
                ("INNERGRID", (0, 0), (-1, -1), 0.4, colors.HexColor(BORDER)),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(score_table)
    story.append(Spacer(1, 5 * mm))

    # Smart money
    story.append(Paragraph("02 · SMART MONEY SNAPSHOT", styles["Section"]))
    smart_money_text = (
        f"Active Smart Wallets: {report.smart_money.smart_wallets_active}<br/>"
        f"Repeat Buyers: {'Detected' if report.smart_money.repeat_buyers_detected else 'No'}<br/>"
        f"Net Flow: {report.smart_money.net_flow}<br/>"
        f"Holder Growth (24H): {report.smart_money.holder_growth_24h:.1f}%<br/><br/>"
        f"{report.smart_money.note}"
    )
    story.append(Paragraph(smart_money_text, styles["BodyDark"]))
    story.append(Spacer(1, 5 * mm))

    # Kronos
    story.append(Paragraph("03 · MARKET STRUCTURE", styles["Section"]))
    kronos_text = (
        f"Regime: {report.kronos.regime}<br/>"
        f"Directional Bias: {report.kronos.bias}<br/>"
        f"Confidence: {report.kronos.confidence}%<br/><br/>"
        f"{report.kronos.note}"
    )
    story.append(Paragraph(kronos_text, styles["BodyDark"]))
    story.append(Spacer(1, 5 * mm))

    # Council
    story.append(Paragraph("04 · AI COUNCIL", styles["Section"]))
    for agent in report.council:
        story.append(
            Paragraph(
                f"<b>{agent.emoji} {agent.title}</b><br/>{agent.text}",
                styles["BodyDark"],
            )
        )
        story.append(Spacer(1, 2.5 * mm))

    story.append(Spacer(1, 2 * mm))

    # Risk
    story.append(Paragraph("05 · RISK SUMMARY", styles["Section"]))
    risk_text = (
        f"Liquidity: {report.risk.liquidity}<br/>"
        f"Concentration: {report.risk.concentration}<br/>"
        f"Distribution Signals: {report.risk.distribution_signals}<br/>"
        f"Warning: {report.risk.warnings}"
    )
    story.append(Paragraph(risk_text, styles["BodyDark"]))
    story.append(Spacer(1, 5 * mm))

    # Verdict
    story.append(Paragraph("06 · FINAL VERDICT", styles["Section"]))
    story.append(Paragraph(report.verdict_title, styles["Verdict"]))

    verdict_lines = "<br/>".join([f"• {line}" for line in report.verdict_bullets])
    story.append(Paragraph(verdict_lines, styles["BodyDark"]))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"<b>Recommended Action:</b> {report.verdict_action}", styles["BodyDark"]))
    story.append(Spacer(1, 8 * mm))

    # Footer note
    story.append(
        Paragraph(
            "Generated by crypto.guru · Detect Early. Act Smart. · For informational and research purposes only. Not financial advice.",
            styles["SmallMuted"],
        )
    )

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# =========================
# UI RENDERING
# =========================
def render_metric_row(label: str, value_html: str) -> None:
    st.markdown(
        f"""
        <div class="metric-row">
            <div class="metric-label">{label}</div>
            <div class="metric-value">{value_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_breakdown_card(b: MiroScoreBreakdown) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">01 · Miro v2 Breakdown</div>', unsafe_allow_html=True)

    render_metric_row("Volume Expansion", f'{render_bar(b.volume_expansion, 5, "green")} {b.volume_expansion} / 5')
    render_metric_row("Volatility Expansion", f'{render_bar(b.volatility_expansion, 3, "green")} {b.volatility_expansion} / 3')
    render_metric_row("Range Control", f'{render_bar(b.range_control, 2, "amber")} {b.range_control} / 2')
    render_metric_row("Trend Quality", f'{render_bar(b.trend_quality, 3, "amber")} {b.trend_quality} / 3')
    render_metric_row("On-Chain Confirmation", f'{render_bar(b.onchain_confirmation, 4, "green")} {b.onchain_confirmation} / 4')
    render_metric_row("Risk Penalty", f'{render_bar(b.risk_penalty, 5, "red")} -{b.risk_penalty}')
    st.markdown("</div>", unsafe_allow_html=True)


def render_smart_money_card(s: SmartMoneySnapshot) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">02 · Smart Money Snapshot</div>', unsafe_allow_html=True)
    render_metric_row("Active Smart Wallets", str(s.smart_wallets_active))
    render_metric_row("Repeat Buyers", "Detected" if s.repeat_buyers_detected else "No")
    render_metric_row("Net Flow", s.net_flow)
    render_metric_row("Holder Growth (24H)", f"{s.holder_growth_24h:.1f}%")
    st.markdown(f'<div class="metric-label" style="margin-top:12px; line-height:1.7;">{s.note}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_kronos_card(k: KronosSnapshot) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">03 · Market Structure</div>', unsafe_allow_html=True)
    render_metric_row("Regime", k.regime)
    render_metric_row("Bias", k.bias)
    render_metric_row("Confidence", f"{k.confidence}%")
    st.markdown(f'<div class="metric-label" style="margin-top:12px; line-height:1.7;">{k.note}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_council_card(council: List[CouncilAgent]) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">04 · AI Council</div>', unsafe_allow_html=True)

    for agent in council:
        st.markdown(
            f"""
            <div class="agent-card">
                <div class="agent-title">{agent.emoji} {agent.title}</div>
                <div class="agent-body">{agent.text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


def render_risk_card(risk: RiskSummary) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">05 · Risk Summary</div>', unsafe_allow_html=True)
    render_metric_row("Liquidity", risk.liquidity)
    render_metric_row("Concentration", risk.concentration)
    render_metric_row("Distribution Signals", risk.distribution_signals)
    render_metric_row("Warning", risk.warnings)
    st.markdown("</div>", unsafe_allow_html=True)


def render_verdict_card(title: str, bullets: List[str], action: str) -> None:
    bullet_html = "".join([f'<div class="verdict-bullet">• {b}</div>' for b in bullets])
    st.markdown(
        f"""
        <div class="verdict-box">
            <div class="verdict-title">{title}</div>
            {bullet_html}
            <div class="verdict-bullet" style="margin-top:10px;"><b>Recommended Action:</b> {action}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================
# APP
# =========================
def main() -> None:
    inject_css()
    logo_b64 = load_logo_base64()

    st.markdown(create_brand_header_html(logo_b64), unsafe_allow_html=True)

    # Sidebar controls for now. Replace later with your live pipeline.
    with st.sidebar:
        st.header("Input Controls")
        token_name = st.text_input("Token Name", value="AAVE")
        symbol = st.text_input("Symbol", value="AAVE")
        chain = st.selectbox("Chain", ["Ethereum", "Base", "Solana", "Arbitrum", "BNB Chain"], index=0)
        timeframe = st.selectbox("Timeframe", ["1H", "4H", "1D"], index=1)
        price = st.number_input("Price", min_value=0.0, value=171.25, step=0.01)

        st.subheader("Miro v2 Inputs")
        relative_volume = st.number_input("Relative Volume", min_value=0.0, value=6.2, step=0.1)
        atr_multiple = st.number_input("ATR Multiple", min_value=0.0, value=2.4, step=0.1)
        range_position = st.slider("Range Position", min_value=0.0, max_value=1.0, value=0.82, step=0.01)
        adx_strength = st.number_input("ADX Strength", min_value=0.0, value=18.0, step=0.5)

        st.subheader("On-Chain Inputs")
        smart_wallets_active = st.number_input("Smart Wallets Active", min_value=0, value=3, step=1)
        repeat_buyers_detected = st.checkbox("Repeat Buyers Detected", value=True)
        net_flow_positive = st.checkbox("Net Flow Positive", value=True)
        holder_growth_24h = st.number_input("Holder Growth 24H (%)", min_value=-100.0, value=6.2, step=0.1)

        st.subheader("Trend Flags")
        price_above_ema20 = st.checkbox("Price Above EMA20", value=True)
        ema20_above_ema50 = st.checkbox("EMA20 Above EMA50", value=True)

        st.subheader("Penalty Flags")
        low_liquidity_penalty = st.checkbox("Low Liquidity Penalty", value=False)
        concentration_penalty = st.checkbox("Concentration Penalty", value=False)
        suspicious_volume_penalty = st.checkbox("Suspicious Volume Penalty", value=False)

        st.subheader("Premium PDF")
        client_name = st.text_input("Client Name", value="Premium Client")

    payload = generate_report_payload(
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
        repeat_buyers_detected=repeat_buyers_detected,
        net_flow_positive=net_flow_positive,
        holder_growth_24h=holder_growth_24h,
        price_above_ema20=price_above_ema20,
        ema20_above_ema50=ema20_above_ema50,
        low_liquidity_penalty=low_liquidity_penalty,
        concentration_penalty=concentration_penalty,
        suspicious_volume_penalty=suspicious_volume_penalty,
        client_name=client_name,
    )

    # Top token card
    st.markdown('<div class="token-meta-card">', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="token-line">
            <div>
                <div class="token-name">{payload.token.token_name} <span style="color:{TEXT_MUTED}; font-size:18px;">· {payload.token.chain}</span></div>
                <div class="token-sub">{payload.token.timestamp} · Timeframe: {payload.token.timeframe} · Price: ${payload.token.price:,.4f}</div>
            </div>
            <div style="text-align:right;">
                <div class="miro-score" style="color:{score_color(payload.miro_total)};">{payload.miro_total:.1f} / 15</div>
                <div class="status-pill">{payload.status_label}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)

    left, right = st.columns([1.1, 0.9], gap="large")

    with left:
        render_breakdown_card(payload.breakdown)
        render_smart_money_card(payload.smart_money)
        render_kronos_card(payload.kronos)

    with right:
        render_council_card(payload.council)
        render_risk_card(payload.risk)
        render_verdict_card(payload.verdict_title, payload.verdict_bullets, payload.verdict_action)

        pdf_bytes = build_pdf(payload)
        file_name = f"{payload.token.symbol}_intelligence_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"

        st.download_button(
            label="Download Intelligence Report (PDF)",
            data=pdf_bytes,
            file_name=file_name,
            mime="application/pdf",
            use_container_width=True,
        )

    st.markdown(
        f"""
        <div class="footer-note">
            crypto.guru · {TAGLINE}
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
