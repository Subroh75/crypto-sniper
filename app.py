# app.py
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="Crypto Sniper",
    page_icon="🎯",
    layout="wide",
)

# =========================================================
# STYLES
# =========================================================
st.markdown(
    """
    <style>
    .block-container {
        max-width: 1180px;
        padding-top: 1.4rem;
        padding-bottom: 2rem;
    }

    html, body, [class*="css"] {
        color: #111111 !important;
    }

    .app-shell {
        background: #ffffff;
        border: 1px solid #ececec;
        border-radius: 24px;
        padding: 22px;
        box-shadow: 0 8px 24px rgba(0,0,0,0.04);
        margin-bottom: 18px;
    }

    .hero-title {
        font-size: 2rem;
        font-weight: 900;
        color: #111111;
        margin-bottom: 0.15rem;
    }

    .hero-subtitle {
        color: #4a4a4a;
        font-size: 0.98rem;
        margin-bottom: 1.1rem;
    }

    .section-card {
        background: #ffffff;
        border: 1px solid #ececec;
        border-radius: 18px;
        padding: 18px;
        margin-bottom: 14px;
        box-shadow: 0 3px 14px rgba(0,0,0,0.03);
    }

    .section-title {
        font-size: 1.08rem;
        font-weight: 900;
        color: #111111;
        margin-bottom: 0.75rem;
    }

    .signal-title {
        font-size: 1.9rem;
        font-weight: 900;
        color: #111111;
        line-height: 1.1;
        margin-bottom: 0.55rem;
    }

    .signal-sub {
        font-size: 0.92rem;
        color: #444444;
        line-height: 1.5;
    }

    .metric-label {
        font-size: 0.78rem;
        color: #666666;
        margin-bottom: 0.15rem;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        font-weight: 700;
    }

    .metric-value {
        font-size: 1.22rem;
        font-weight: 900;
        color: #111111;
    }

    .pill {
        display: inline-block;
        padding: 0.28rem 0.7rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 800;
        margin-right: 0.4rem;
        margin-bottom: 0.4rem;
        border: 1px solid #e6e6e6;
        background: #f5f5f5;
        color: #111111;
    }

    .pill-good {
        background: #ecfdf3;
        border-color: #b9e7c6;
    }

    .pill-bad {
        background: #fef2f2;
        border-color: #efb2b2;
    }

    .pill-warn {
        background: #fff7ed;
        border-color: #f5d0a8;
    }

    .component-box {
        background: #fafafa;
        border: 1px solid #ececec;
        border-radius: 14px;
        padding: 14px;
        height: 100%;
    }

    .component-name {
        font-size: 0.84rem;
        font-weight: 900;
        color: #111111;
        margin-bottom: 0.3rem;
    }

    .component-score {
        font-size: 1.08rem;
        font-weight: 900;
        color: #111111;
        margin-bottom: 0.35rem;
    }

    .component-text {
        font-size: 0.9rem;
        color: #333333;
        line-height: 1.5;
    }

    .narrative {
        font-size: 0.98rem;
        color: #191919;
        line-height: 1.7;
    }

    .control-shell {
        background: #ffffff;
        border: 1px solid #ececec;
        border-radius: 18px;
        padding: 14px 16px 6px 16px;
        margin-bottom: 16px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.025);
    }

    .stDownloadButton button,
    .stButton button {
        border-radius: 12px !important;
        font-weight: 800 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# CONSTANTS
# =========================================================
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

PAIR_OPTIONS = [
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "SUIUSDT",
    "PEPEUSDT",
    "WIFUSDT",
]

INTERVAL_OPTIONS = ["5m", "15m", "1h", "4h", "1d"]

LOOKBACK_MAP = {
    "Fast": 120,
    "Balanced": 240,
    "Deep": 500,
}


# =========================================================
# DATA MODEL
# =========================================================
@dataclass
class SignalAnalysis:
    signal_label: str
    signal_bias: str
    conviction_score: float
    timing_score: float
    current_price: float
    change_pct_24h: float
    volume_strength: int
    price_expansion: int
    position_in_range: int
    trend_alignment: int
    short_term_direction: int
    price_stability: int
    breakout_potential: int
    noise_level: int
    market_structure: str
    timing_quality: str
    ai_lab: str
    component_summary: List[Tuple[str, str, str]]
    facts: Dict[str, float]


# =========================================================
# DATA FETCH
# =========================================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }
    response = requests.get(BINANCE_KLINES_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()

    columns = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        "ignore",
    ]

    df = pd.DataFrame(data, columns=columns)

    for col in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df = df.sort_values("open_time").reset_index(drop=True)
    return df


# =========================================================
# INDICATORS
# =========================================================
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr1 = df["high"] - df["low"]
    tr2 = (df["high"] - prev_close).abs()
    tr3 = (df["low"] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / period, adjust=False).mean()


def rolling_slope(series: pd.Series, window: int = 20) -> pd.Series:
    x = np.arange(window)
    out = []

    for i in range(len(series)):
        if i < window - 1:
            out.append(np.nan)
            continue
        y = series.iloc[i - window + 1 : i + 1].values
        slope = np.polyfit(x, y, 1)[0]
        out.append(slope)

    return pd.Series(out, index=series.index)


def clamp_int(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, round(value))))


# =========================================================
# ENGINE
# =========================================================
def analyze_signal(df: pd.DataFrame) -> SignalAnalysis:
    df = df.copy()

    df["ema_20"] = ema(df["close"], 20)
    df["ema_50"] = ema(df["close"], 50)
    df["rsi_14"] = rsi(df["close"], 14)
    df["atr_14"] = atr(df, 14)
    df["vol_ma_20"] = df["volume"].rolling(20).mean()
    df["slope_20"] = rolling_slope(df["close"], 20)

    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
    lookback_24 = df.iloc[max(0, len(df) - 25)] if len(df) >= 25 else df.iloc[0]

    current_price = float(last["close"])
    open_price = float(last["open"])
    atr_now = float(last["atr_14"]) if not pd.isna(last["atr_14"]) else 0.0
    rel_volume = float(last["volume"] / last["vol_ma_20"]) if last["vol_ma_20"] and not pd.isna(last["vol_ma_20"]) else 1.0

    high_20 = float(df["high"].tail(20).max())
    low_20 = float(df["low"].tail(20).min())
    range_20 = max(high_20 - low_20, 1e-9)

    body = abs(current_price - open_price)
    candle_range = max(float(last["high"] - last["low"]), 1e-9)
    body_ratio = body / candle_range

    pos_in_range_ratio = (current_price - low_20) / range_20
    trend_bull = current_price > float(last["ema_20"]) > float(last["ema_50"])
    trend_bear = current_price < float(last["ema_20"]) < float(last["ema_50"])

    breakout_distance = current_price - high_20
    slope_value = float(last["slope_20"]) if not pd.isna(last["slope_20"]) else 0.0
    rsi_now = float(last["rsi_14"]) if not pd.isna(last["rsi_14"]) else 50.0
    atr_pct = (atr_now / current_price) if current_price else 0.0
    change_pct_24h = ((current_price / float(lookback_24["close"])) - 1.0) * 100.0 if float(lookback_24["close"]) else 0.0

    # Miro compact translation
    volume_strength = clamp_int(rel_volume * 2.2, 0, 5)

    expansion_raw = 0.0
    if atr_now > 0:
        expansion_raw = max(0.0, breakout_distance / atr_now) + (body_ratio * 1.3)
    price_expansion = clamp_int(expansion_raw * 2.0, 0, 5)

    position_in_range = clamp_int(pos_in_range_ratio * 3.0, 0, 3)

    if trend_bull:
        trend_alignment = 2
    elif current_price > float(last["ema_50"]):
        trend_alignment = 1
    else:
        trend_alignment = 0

    # Kronos compact translation
    short_term_direction = clamp_int(((slope_value / max(current_price, 1e-9)) + 0.002) / 0.004 * 100, 0, 100)
    price_stability = clamp_int((1.0 - min(atr_pct / 0.05, 1.0)) * 100, 0, 100)
    breakout_potential = clamp_int(((pos_in_range_ratio * 0.6) + min(max(rel_volume - 1.0, 0.0), 1.5) / 1.5 * 0.4) * 100, 0, 100)
    noise_level = clamp_int(min(atr_pct / 0.06, 1.0) * 100, 0, 100)

    miro_total = volume_strength + price_expansion + position_in_range + trend_alignment
    kronos_support = (
        short_term_direction * 0.30
        + price_stability * 0.20
        + breakout_potential * 0.30
        + (100 - noise_level) * 0.20
    )

    conviction_score = round((miro_total / 15.0) * 65 + (kronos_support / 100.0) * 35, 1)

    timing_raw = (
        (position_in_range / 3.0) * 0.25
        + (price_expansion / 5.0) * 0.25
        + (trend_alignment / 2.0) * 0.25
        + ((100 - noise_level) / 100.0) * 0.25
    )
    timing_score = round(timing_raw * 100, 1)

    bullish_checks = [
        current_price > float(last["ema_20"]),
        float(last["ema_20"]) > float(last["ema_50"]),
        rsi_now > 52,
        rel_volume > 1.05,
        pos_in_range_ratio > 0.60,
    ]
    bearish_checks = [
        current_price < float(last["ema_20"]),
        float(last["ema_20"]) < float(last["ema_50"]),
        rsi_now < 48,
        rel_volume > 1.05 and current_price < float(prev["close"]),
        pos_in_range_ratio < 0.40,
    ]

    bull_count = sum(bool(x) for x in bullish_checks)
    bear_count = sum(bool(x) for x in bearish_checks)

    if bull_count >= 4 and conviction_score >= 60:
        signal_bias = "Bullish"
        signal_label = "HIGH-CONVICTION LONG" if conviction_score >= 75 else "LONG SETUP"
    elif bear_count >= 4 and conviction_score >= 55:
        signal_bias = "Bearish"
        signal_label = "HIGH-CONVICTION SHORT" if conviction_score >= 75 else "SHORT SETUP"
    else:
        signal_bias = "Neutral"
        signal_label = "WAIT / WATCH"

    # Market Structure
    structure_lines = []

    if trend_bull:
        structure_lines.append("Price is trading above both the short-term and medium-term trend baselines, which keeps the structure constructive.")
    elif trend_bear:
        structure_lines.append("Price is trading below both the short-term and medium-term trend baselines, which keeps the structure defensive.")
    else:
        structure_lines.append("Price is trapped in a mixed zone between key trend baselines, so structure is not fully resolved.")

    if pos_in_range_ratio >= 0.75:
        structure_lines.append("It is also holding near the top of its recent range, which usually reflects stronger control from buyers.")
    elif pos_in_range_ratio <= 0.25:
        structure_lines.append("It is sitting near the bottom of its recent range, which shows weaker positioning and limited upward control.")
    else:
        structure_lines.append("It is positioned around the middle of its recent range, so directional pressure is present but not dominant.")

    if rel_volume >= 1.40:
        structure_lines.append("Volume is expanding above normal levels, so participation is confirming the move.")
    elif rel_volume <= 0.80:
        structure_lines.append("Volume is below normal, so the move lacks strong participation and may be fragile.")
    else:
        structure_lines.append("Volume is close to normal, so confirmation is adequate but not emphatic.")

    if rsi_now >= 60:
        structure_lines.append("Momentum is supportive and consistent with trend continuation.")
    elif rsi_now <= 40:
        structure_lines.append("Momentum remains soft, which limits confidence in immediate upside expansion.")
    else:
        structure_lines.append("Momentum is balanced rather than forceful, so the market still needs clearer follow-through.")

    market_structure = " ".join(structure_lines)

    # Timing Quality
    if timing_score >= 75:
        timing_quality = (
            "Decision clarity is strong. The setup is aligned, price is positioned on the stronger side of the recent range, "
            "and market noise is controlled enough to support cleaner execution."
        )
    elif timing_score >= 55:
        timing_quality = (
            "Decision clarity is acceptable but not ideal. There is enough structure to stay interested, "
            "but the setup still benefits from added confirmation before acting aggressively."
        )
    else:
        timing_quality = (
            "Decision clarity is weak. The structure is incomplete or noisy, so patience is better than forcing an entry here."
        )

    # AI Lab
    ai_parts = []

    if signal_bias == "Bullish":
        ai_parts.append(
            "The engine leans bullish because trend alignment, relative positioning, and participation are working together rather than conflicting."
        )
    elif signal_bias == "Bearish":
        ai_parts.append(
            "The engine leans bearish because price structure is weaker, trend support is absent, and the market is failing to hold stronger zones."
        )
    else:
        ai_parts.append(
            "The engine stays neutral because trend, momentum, and participation do not yet agree strongly enough to justify conviction."
        )

    if rel_volume > 1.25:
        ai_parts.append(
            "Volume adds credibility to the current move, which improves the odds that this is a genuine directional push rather than random drift."
        )
    else:
        ai_parts.append(
            "Volume is not fully decisive, so the move still carries some risk of fading or stalling."
        )

    if noise_level > 70:
        ai_parts.append(
            "Noise is elevated, which means execution quality matters more than raw directional bias."
        )
    elif noise_level < 35:
        ai_parts.append(
            "Noise is relatively contained, which improves the probability of cleaner continuation."
        )

    if breakout_potential > 70:
        ai_parts.append(
            "Breakout potential is meaningful because price is pressing the stronger side of the range with enough participation to matter."
        )
    elif breakout_potential < 35:
        ai_parts.append(
            "Breakout pressure is still limited, so there is little reason to chase."
        )

    if rsi_now > 65:
        ai_parts.append(
            "Momentum is already quite advanced, so the opportunity is stronger for continuation traders than for late chasers."
        )
    elif rsi_now < 45:
        ai_parts.append(
            "Momentum remains subdued, which suggests the market still has something to prove before a decisive directional move."
        )

    ai_lab = " ".join(ai_parts)

    component_summary = [
        ("Volume Strength", f"{volume_strength}/5", "How strong current activity is versus normal participation."),
        ("Price Expansion", f"{price_expansion}/5", "How forcefully price is pushing away from recent balance."),
        ("Position in Range", f"{position_in_range}/3", "Where price is sitting inside the recent trading range."),
        ("Trend Alignment", f"{trend_alignment}/2", "Whether price is aligned with its trend base."),
        ("Short-Term Direction", f"{short_term_direction}/100", "Immediate directional slope of price."),
        ("Price Stability", f"{price_stability}/100", "Higher score means smoother price behavior."),
        ("Breakout Potential", f"{breakout_potential}/100", "Likelihood that pressure can expand into a move."),
        ("Noise Level", f"{noise_level}/100", "Higher score means a choppier environment."),
    ]

    facts = {
        "rel_volume": rel_volume,
        "rsi": rsi_now,
        "atr_pct": atr_pct * 100,
        "pos_in_range_pct": pos_in_range_ratio * 100,
        "ema20": float(last["ema_20"]),
        "ema50": float(last["ema_50"]),
        "high_20": high_20,
        "low_20": low_20,
    }

    return SignalAnalysis(
        signal_label=signal_label,
        signal_bias=signal_bias,
        conviction_score=conviction_score,
        timing_score=timing_score,
        current_price=current_price,
        change_pct_24h=change_pct_24h,
        volume_strength=volume_strength,
        price_expansion=price_expansion,
        position_in_range=position_in_range,
        trend_alignment=trend_alignment,
        short_term_direction=short_term_direction,
        price_stability=price_stability,
        breakout_potential=breakout_potential,
        noise_level=noise_level,
        market_structure=market_structure,
        timing_quality=timing_quality,
        ai_lab=ai_lab,
        component_summary=component_summary,
        facts=facts,
    )


# =========================================================
# PDF
# =========================================================
def build_pdf(symbol: str, interval: str, analysis: SignalAnalysis) -> bytes:
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

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#111111"),
        alignment=TA_LEFT,
        spaceAfter=8,
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#111111"),
        alignment=TA_LEFT,
        spaceBefore=6,
        spaceAfter=5,
    )

    text_style = ParagraphStyle(
        "CustomText",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#222222"),
        alignment=TA_LEFT,
        spaceAfter=6,
    )

    story = []

    story.append(Paragraph(f"Crypto Sniper Report — {symbol} ({interval})", title_style))
    story.append(
        Paragraph(
            f"<b>Signal Output:</b> {analysis.signal_label}<br/>"
            f"<b>Bias:</b> {analysis.signal_bias}<br/>"
            f"<b>Conviction:</b> {analysis.conviction_score}/100<br/>"
            f"<b>Timing Quality:</b> {analysis.timing_score}/100<br/>"
            f"<b>Current Price:</b> {analysis.current_price:,.6f}<br/>"
            f"<b>24h Change:</b> {analysis.change_pct_24h:+.2f}%",
            text_style,
        )
    )

    story.append(Spacer(1, 4))
    story.append(Paragraph("Signal Components", heading_style))

    table_data = [["Component", "Score", "Meaning"]]
    for name, score, desc in analysis.component_summary:
        table_data.append([name, score, desc])

    table = Table(table_data, colWidths=[48 * mm, 24 * mm, 100 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f3f4f6")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#111111")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d7d7d7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)

    story.append(Paragraph("Market Structure", heading_style))
    story.append(Paragraph(analysis.market_structure, text_style))

    story.append(Paragraph("Timing Quality", heading_style))
    story.append(Paragraph(analysis.timing_quality, text_style))

    story.append(Paragraph("AI Lab", heading_style))
    story.append(Paragraph(analysis.ai_lab, text_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes


# =========================================================
# RENDER HELPERS
# =========================================================
def bias_pill_class(bias: str) -> str:
    if bias == "Bullish":
        return "pill pill-good"
    if bias == "Bearish":
        return "pill pill-bad"
    return "pill pill-warn"


def render_signal_output(symbol: str, interval: str, analysis: SignalAnalysis) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Signal Output</div>', unsafe_allow_html=True)

    left, r1, r2, r3 = st.columns([2.2, 1, 1, 1])

    with left:
        st.markdown(f'<div class="signal-title">{analysis.signal_label}</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <span class="{bias_pill_class(analysis.signal_bias)}">{analysis.signal_bias}</span>
            <span class="pill">{symbol}</span>
            <span class="pill">{interval}</span>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            '<div class="signal-sub">A direct decision layer that translates live market structure into an actionable bias.</div>',
            unsafe_allow_html=True,
        )

    with r1:
        st.markdown('<div class="metric-label">Current Price</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{analysis.current_price:,.6f}</div>', unsafe_allow_html=True)

    with r2:
        st.markdown('<div class="metric-label">Conviction</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{analysis.conviction_score:.1f}/100</div>', unsafe_allow_html=True)

    with r3:
        st.markdown('<div class="metric-label">24h Change</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{analysis.change_pct_24h:+.2f}%</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def render_signal_components(analysis: SignalAnalysis) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Signal Components</div>', unsafe_allow_html=True)

    row1 = analysis.component_summary[:4]
    row2 = analysis.component_summary[4:]

    cols1 = st.columns(4)
    for col, item in zip(cols1, row1):
        name, score, desc = item
        with col:
            st.markdown(
                f"""
                <div class="component-box">
                    <div class="component-name">{name}</div>
                    <div class="component-score">{score}</div>
                    <div class="component-text">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    cols2 = st.columns(4)
    for col, item in zip(cols2, row2):
        name, score, desc = item
        with col:
            st.markdown(
                f"""
                <div class="component-box">
                    <div class="component-name">{name}</div>
                    <div class="component-score">{score}</div>
                    <div class="component-text">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("</div>", unsafe_allow_html=True)


def render_narrative_card(title: str, text: str) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="narrative">{text}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# APP HEADER
# =========================================================
st.markdown('<div class="app-shell">', unsafe_allow_html=True)
st.markdown('<div class="hero-title">🎯 Crypto Sniper</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-subtitle">Signal Output → Signal Components → Market Structure → Timing Quality → AI Lab → Download PDF</div>',
    unsafe_allow_html=True,
)
st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# TOP CONTROLS ONLY - NO SIDEBAR
# =========================================================
st.markdown('<div class="control-shell">', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns([1.2, 1.0, 1.0, 0.9])

with c1:
    symbol = st.selectbox("Pair", PAIR_OPTIONS, index=0)

with c2:
    interval = st.selectbox("Timeframe", INTERVAL_OPTIONS, index=2)

with c3:
    depth_label = st.selectbox("Scan Depth", list(LOOKBACK_MAP.keys()), index=1)

with c4:
    run_scan = st.button("Run Scan", use_container_width=True, type="primary")

st.markdown("</div>", unsafe_allow_html=True)

# =========================================================
# MAIN FLOW
# =========================================================
if run_scan:
    try:
        with st.spinner("Generating signal..."):
            limit = LOOKBACK_MAP[depth_label]
            df = fetch_klines(symbol=symbol, interval=interval, limit=limit)
            analysis = analyze_signal(df)
            pdf_bytes = build_pdf(symbol, interval, analysis)

        # Exact required order
        render_signal_output(symbol, interval, analysis)
        render_signal_components(analysis)
        render_narrative_card("Market Structure", analysis.market_structure)
        render_narrative_card("Timing Quality", analysis.timing_quality)
        render_narrative_card("AI Lab", analysis.ai_lab)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">Download PDF</div>', unsafe_allow_html=True)
        st.download_button(
            label="Download PDF Report",
            data=pdf_bytes,
            file_name=f"crypto_sniper_{symbol.lower()}_{interval}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

    except requests.HTTPError as e:
        st.error(f"Binance API error: {e}")
    except Exception as e:
        st.error(f"App error: {e}")

else:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Ready</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="narrative">Select a pair, timeframe, and scan depth above, then click <b>Run Scan</b>. '
        'The page will render in the exact order you asked for, with no left sidebar.</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)
