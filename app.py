# app.py
# Crypto Sniper - production-style Streamlit app
# Required packages:
# pip install streamlit pandas numpy requests reportlab

from __future__ import annotations

import io
import math
import time
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


# ---------------------------------------------------------
# Page config
# ---------------------------------------------------------
st.set_page_config(
    page_title="Crypto Sniper",
    page_icon="🎯",
    layout="wide",
)

# ---------------------------------------------------------
# Styling
# ---------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1.25rem;
        padding-bottom: 2rem;
        max-width: 1380px;
    }

    html, body, [class*="css"]  {
        color: #111111 !important;
    }

    .main-title {
        font-size: 2rem;
        font-weight: 800;
        color: #111111;
        margin-bottom: 0.2rem;
    }

    .subtitle {
        color: #333333;
        font-size: 0.98rem;
        margin-bottom: 1rem;
    }

    .signal-card {
        background: #ffffff;
        border: 1px solid #e7e7e7;
        border-radius: 18px;
        padding: 18px 18px 16px 18px;
        box-shadow: 0 3px 14px rgba(0,0,0,0.04);
        margin-bottom: 14px;
    }

    .section-card {
        background: #ffffff;
        border: 1px solid #ebebeb;
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.03);
        margin-bottom: 14px;
    }

    .metric-label {
        font-size: 0.78rem;
        color: #5b5b5b;
        margin-bottom: 0.2rem;
    }

    .metric-value {
        font-size: 1.25rem;
        font-weight: 800;
        color: #111111;
    }

    .score-pill {
        display: inline-block;
        padding: 0.3rem 0.65rem;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 700;
        margin-right: 0.4rem;
        margin-bottom: 0.4rem;
        color: #111111;
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
    }

    .good-pill {
        background: #ecfdf3;
        border: 1px solid #b7ebc6;
    }

    .warn-pill {
        background: #fff7ed;
        border: 1px solid #f7d2a8;
    }

    .bad-pill {
        background: #fef2f2;
        border: 1px solid #f1b5b5;
    }

    .tiny-heading {
        font-size: 0.8rem;
        color: #666666;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        margin-bottom: 0.35rem;
        font-weight: 700;
    }

    .big-signal {
        font-size: 1.9rem;
        font-weight: 900;
        color: #111111;
        line-height: 1.1;
    }

    .narrative {
        font-size: 0.98rem;
        line-height: 1.6;
        color: #171717;
    }

    .component-box {
        background: #fafafa;
        border: 1px solid #ebebeb;
        border-radius: 14px;
        padding: 12px;
        height: 100%;
    }

    .component-title {
        font-size: 0.86rem;
        font-weight: 800;
        margin-bottom: 0.35rem;
        color: #111111;
    }

    .component-value {
        font-size: 1.1rem;
        font-weight: 800;
        color: #111111;
        margin-bottom: 0.35rem;
    }

    .component-desc {
        font-size: 0.9rem;
        color: #333333;
        line-height: 1.5;
    }

    .stDownloadButton button {
        width: 100%;
        border-radius: 12px;
        font-weight: 800;
    }

    section[data-testid="stSidebar"] .stRadio label,
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stSlider label,
    section[data-testid="stSidebar"] .stCheckbox label,
    section[data-testid="stSidebar"] .stNumberInput label {
        color: #111111 !important;
        font-weight: 700 !important;
    }

    section[data-testid="stSidebar"] {
        background: #fafafa;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------
# Constants
# ---------------------------------------------------------
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
LOOKBACK_OPTIONS = {
    "Fast": 120,
    "Balanced": 240,
    "Deep": 500,
}


# ---------------------------------------------------------
# Dataclass
# ---------------------------------------------------------
@dataclass
class SignalAnalysis:
    signal_label: str
    signal_bias: str
    conviction_score: float
    entry_quality_score: float
    current_price: float
    change_pct_24h: float
    volume_strength: int
    price_expansion: int
    position_in_range: int
    trend_alignment: int
    kronos_slope: int
    kronos_stability: int
    kronos_breakout: int
    kronos_volatility: int
    market_structure: str
    timing_quality: str
    ai_lab: str
    component_summary: List[Tuple[str, str, str]]
    raw_facts: Dict[str, float]


# ---------------------------------------------------------
# Data fetch
# ---------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def fetch_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    params = {
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": limit,
    }
    resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()

    cols = [
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
    df = pd.DataFrame(data, columns=cols)

    numeric_cols = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
    ]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df["close_time"] = pd.to_datetime(df["close_time"], unit="ms", utc=True)
    df = df.sort_values("open_time").reset_index(drop=True)
    return df


# ---------------------------------------------------------
# Indicators
# ---------------------------------------------------------
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
    tr = true_range(df)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def rolling_slope(series: pd.Series, window: int = 20) -> pd.Series:
    idx = np.arange(window)
    vals = []

    for i in range(len(series)):
        if i < window - 1:
            vals.append(np.nan)
            continue
        y = series.iloc[i - window + 1 : i + 1].values
        coeff = np.polyfit(idx, y, 1)[0]
        vals.append(coeff)
    return pd.Series(vals, index=series.index)


def clamp_int(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, round(value))))


def safe_pct(a: float, b: float) -> float:
    if b == 0 or pd.isna(b):
        return 0.0
    return (a / b) * 100.0


# ---------------------------------------------------------
# Signal engine
# ---------------------------------------------------------
def analyze_signal(df: pd.DataFrame) -> SignalAnalysis:
    df = df.copy()

    df["ema_20"] = ema(df["close"], 20)
    df["ema_50"] = ema(df["close"], 50)
    df["rsi_14"] = rsi(df["close"], 14)
    df["atr_14"] = atr(df, 14)
    df["vol_ma_20"] = df["volume"].rolling(20).mean()
    df["slope_20"] = rolling_slope(df["close"], 20)

    last = df.iloc[-1]
    prev = df.iloc[-2]
    last_24 = df.iloc[max(0, len(df) - 25)] if len(df) >= 25 else df.iloc[0]

    current_price = float(last["close"])
    atr_now = float(last["atr_14"]) if not pd.isna(last["atr_14"]) else 0.0
    high_20 = float(df["high"].tail(20).max())
    low_20 = float(df["low"].tail(20).min())
    range_20 = max(high_20 - low_20, 1e-9)

    rel_volume = float(last["volume"] / last["vol_ma_20"]) if last["vol_ma_20"] and not pd.isna(last["vol_ma_20"]) else 1.0
    body = abs(float(last["close"] - last["open"]))
    candle_range = max(float(last["high"] - last["low"]), 1e-9)
    body_ratio = body / candle_range
    breakout_distance = current_price - high_20
    drawdown_from_high = (high_20 - current_price) / high_20 if high_20 else 0.0
    pos_in_range_ratio = (current_price - low_20) / range_20
    trend_ratio = (current_price - float(last["ema_50"])) / max(float(last["ema_50"]), 1e-9)
    slope_value = float(last["slope_20"]) if not pd.isna(last["slope_20"]) else 0.0
    rsi_now = float(last["rsi_14"]) if not pd.isna(last["rsi_14"]) else 50.0
    atr_pct = (atr_now / current_price) if current_price else 0.0
    change_pct_24h = ((current_price / float(last_24["close"])) - 1.0) * 100.0 if float(last_24["close"]) else 0.0

    # MIRO components
    volume_strength = clamp_int(rel_volume * 2.2, 0, 5)

    expansion_raw = 0.0
    if atr_now > 0:
        expansion_raw = max(0.0, breakout_distance / atr_now) + (body_ratio * 1.4)
    price_expansion = clamp_int(expansion_raw * 2.0, 0, 5)

    position_in_range = clamp_int(pos_in_range_ratio * 3.0, 0, 3)

    trend_alignment_raw = 0
    if current_price > last["ema_20"] > last["ema_50"]:
        trend_alignment_raw = 2
    elif current_price > last["ema_50"]:
        trend_alignment_raw = 1
    trend_alignment = clamp_int(trend_alignment_raw, 0, 2)

    # Kronos components
    slope_score = clamp_int((safe_pct(slope_value, current_price) + 0.18) / 0.36 * 100, 0, 100)
    stability_score = clamp_int((1.0 - min(atr_pct / 0.05, 1.0)) * 100, 0, 100)
    breakout_score = clamp_int(((pos_in_range_ratio * 0.6) + min(max(rel_volume - 1.0, 0.0), 1.5) / 1.5 * 0.4) * 100, 0, 100)
    volatility_score = clamp_int(min(atr_pct / 0.06, 1.0) * 100, 0, 100)

    # Conviction and timing
    miro_total = volume_strength + price_expansion + position_in_range + trend_alignment  # 15 max
    kronos_support = (
        slope_score * 0.30
        + stability_score * 0.20
        + breakout_score * 0.30
        + (100 - volatility_score) * 0.20
    )
    conviction_score = round((miro_total / 15.0) * 65 + (kronos_support / 100.0) * 35, 1)

    timing_raw = (
        (position_in_range / 3.0) * 0.25
        + (price_expansion / 5.0) * 0.25
        + (trend_alignment / 2.0) * 0.25
        + ((100 - volatility_score) / 100.0) * 0.25
    )
    entry_quality_score = round(timing_raw * 100, 1)

    # Bias
    bullish_checks = [
        current_price > float(last["ema_20"]),
        float(last["ema_20"]) > float(last["ema_50"]),
        rsi_now > 52,
        rel_volume > 1.05,
        pos_in_range_ratio > 0.6,
    ]
    bearish_checks = [
        current_price < float(last["ema_20"]),
        float(last["ema_20"]) < float(last["ema_50"]),
        rsi_now < 48,
        rel_volume > 1.05 and current_price < float(prev["close"]),
        pos_in_range_ratio < 0.4,
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

    # Clear narratives
    market_structure_bits = []
    if current_price > float(last["ema_20"]) > float(last["ema_50"]):
        market_structure_bits.append("price is trading above both short and medium trend baselines")
    elif current_price < float(last["ema_20"]) < float(last["ema_50"]):
        market_structure_bits.append("price is trading below both short and medium trend baselines")
    else:
        market_structure_bits.append("price is in a mixed zone between short and medium trend baselines")

    if pos_in_range_ratio >= 0.75:
        market_structure_bits.append("the market is holding near the top of its recent range")
    elif pos_in_range_ratio <= 0.25:
        market_structure_bits.append("the market is sitting near the bottom of its recent range")
    else:
        market_structure_bits.append("the market is positioned around the middle of its recent range")

    if rel_volume >= 1.4:
        market_structure_bits.append("participation is expanding with above-normal volume")
    elif rel_volume <= 0.8:
        market_structure_bits.append("participation is light and conviction from volume is limited")
    else:
        market_structure_bits.append("volume is close to normal and not yet fully confirming a breakout")

    if rsi_now >= 60:
        market_structure_bits.append("momentum is supportive")
    elif rsi_now <= 40:
        market_structure_bits.append("momentum remains soft")
    else:
        market_structure_bits.append("momentum is balanced rather than aggressive")

    market_structure = ". ".join(s.capitalize() for s in market_structure_bits) + "."

    if entry_quality_score >= 75:
        timing_quality = (
            "Timing quality is strong. The setup is aligned, the market is near the stronger side "
            "of its range, and noise is controlled enough for a cleaner decision."
        )
    elif entry_quality_score >= 55:
        timing_quality = (
            "Timing quality is acceptable but not perfect. The setup has usable structure, though "
            "some confirmation is still desirable before sizing aggressively."
        )
    else:
        timing_quality = (
            "Timing quality is weak. Structure and momentum are not yet clean enough, so patience "
            "is favored over forcing an entry."
        )

    ai_lab_parts = []
    if signal_bias == "Bullish":
        ai_lab_parts.append(
            "The engine sees upside conditions because trend alignment is positive, price is not fighting its moving averages, and the market is holding in the stronger half of the recent range."
        )
    elif signal_bias == "Bearish":
        ai_lab_parts.append(
            "The engine sees downside conditions because price structure is weaker, trend support is absent, and sellers are keeping price in the lower half of the recent range."
        )
    else:
        ai_lab_parts.append(
            "The engine is deliberately neutral because the tape does not yet offer enough agreement across trend, momentum, and participation."
        )

    if rel_volume > 1.25:
        ai_lab_parts.append(
            "Volume is contributing useful confirmation, which raises confidence that the current move has real participation behind it."
        )
    else:
        ai_lab_parts.append(
            "Volume is not fully decisive, so the market may still be vulnerable to fake acceleration or stall-outs."
        )

    if volatility_score > 70:
        ai_lab_parts.append(
            "Noise is elevated, so even if direction is right, execution quality matters more than usual."
        )
    elif volatility_score < 35:
        ai_lab_parts.append(
            "Noise is relatively contained, which improves the odds of cleaner follow-through."
        )

    if breakout_score > 70:
        ai_lab_parts.append(
            "Breakout potential is notable because price is pressing the upper part of its recent range with improving activity."
        )
    elif breakout_score < 35:
        ai_lab_parts.append(
            "Breakout pressure is limited, which reduces the urgency to chase price."
        )

    ai_lab = " ".join(ai_lab_parts)

    component_summary = [
        ("Volume Strength", f"{volume_strength}/5", "Measures how strong current participation is versus normal activity."),
        ("Price Expansion", f"{price_expansion}/5", "Measures how forcefully price is extending from recent balance."),
        ("Position in Range", f"{position_in_range}/3", "Shows where price sits inside the recent trading range."),
        ("Trend Alignment", f"{trend_alignment}/2", "Checks whether price is aligned with its trend base."),
        ("Short-Term Direction", f"{kronos_slope}/100", "Captures the immediate directional slope."),
        ("Price Stability", f"{kronos_stability}/100", "Higher values mean smoother price behavior."),
        ("Breakout Potential", f"{kronos_breakout}/100", "Estimates whether the market is ready to expand."),
        ("Noise Level", f"{kronos_volatility}/100", "Higher values mean the environment is choppier."),
    ]

    raw_facts = {
        "rel_volume": rel_volume,
        "rsi": rsi_now,
        "atr_pct": atr_pct * 100,
        "pos_in_range_pct": pos_in_range_ratio * 100,
        "ema20": float(last["ema_20"]),
        "ema50": float(last["ema_50"]),
        "high_20": high_20,
        "low_20": low_20,
        "drawdown_from_high_pct": drawdown_from_high * 100,
    }

    return SignalAnalysis(
        signal_label=signal_label,
        signal_bias=signal_bias,
        conviction_score=conviction_score,
        entry_quality_score=entry_quality_score,
        current_price=current_price,
        change_pct_24h=change_pct_24h,
        volume_strength=volume_strength,
        price_expansion=price_expansion,
        position_in_range=position_in_range,
        trend_alignment=trend_alignment,
        kronos_slope=slope_score,
        kronos_stability=stability_score,
        kronos_breakout=breakout_score,
        kronos_volatility=volatility_score,
        market_structure=market_structure,
        timing_quality=timing_quality,
        ai_lab=ai_lab,
        component_summary=component_summary,
        raw_facts=raw_facts,
    )


# ---------------------------------------------------------
# PDF builder
# ---------------------------------------------------------
def build_pdf_bytes(symbol: str, interval: str, analysis: SignalAnalysis) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleCustom",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#111111"),
        alignment=TA_LEFT,
        spaceAfter=10,
    )
    h_style = ParagraphStyle(
        "HeadingCustom",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#111111"),
        alignment=TA_LEFT,
        spaceBefore=8,
        spaceAfter=6,
    )
    p_style = ParagraphStyle(
        "ParagraphCustom",
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
            f"<b>Signal Output:</b> {analysis.signal_label} | <b>Bias:</b> {analysis.signal_bias} | "
            f"<b>Conviction:</b> {analysis.conviction_score}/100 | "
            f"<b>Timing:</b> {analysis.entry_quality_score}/100",
            p_style,
        )
    )
    story.append(
        Paragraph(
            f"<b>Current Price:</b> {analysis.current_price:,.6f} | "
            f"<b>24h Change:</b> {analysis.change_pct_24h:+.2f}%",
            p_style,
        )
    )

    story.append(Spacer(1, 4))
    story.append(Paragraph("Signal Components", h_style))

    data = [["Component", "Score", "Meaning"]]
    for name, score, meaning in analysis.component_summary:
        data.append([name, score, meaning])

    tbl = Table(data, colWidths=[48 * mm, 24 * mm, 100 * mm])
    tbl.setStyle(
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
    story.append(tbl)

    story.append(Paragraph("Market Structure", h_style))
    story.append(Paragraph(analysis.market_structure, p_style))

    story.append(Paragraph("Timing Quality", h_style))
    story.append(Paragraph(analysis.timing_quality, p_style))

    story.append(Paragraph("AI Lab", h_style))
    story.append(Paragraph(analysis.ai_lab, p_style))

    story.append(Paragraph("Key Facts", h_style))
    facts = (
        f"Relative Volume: {analysis.raw_facts['rel_volume']:.2f}x<br/>"
        f"RSI(14): {analysis.raw_facts['rsi']:.2f}<br/>"
        f"ATR % of Price: {analysis.raw_facts['atr_pct']:.2f}%<br/>"
        f"Position in Range: {analysis.raw_facts['pos_in_range_pct']:.2f}%<br/>"
        f"EMA 20: {analysis.raw_facts['ema20']:.6f}<br/>"
        f"EMA 50: {analysis.raw_facts['ema50']:.6f}<br/>"
        f"20-Bar High: {analysis.raw_facts['high_20']:.6f}<br/>"
        f"20-Bar Low: {analysis.raw_facts['low_20']:.6f}<br/>"
        f"Distance from 20-Bar High: {analysis.raw_facts['drawdown_from_high_pct']:.2f}%"
    )
    story.append(Paragraph(facts, p_style))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# ---------------------------------------------------------
# UI helpers
# ---------------------------------------------------------
def pill_class(label: str) -> str:
    if label in {"Bullish", "HIGH-CONVICTION LONG", "LONG SETUP"}:
        return "score-pill good-pill"
    if label in {"Bearish", "HIGH-CONVICTION SHORT", "SHORT SETUP"}:
        return "score-pill bad-pill"
    return "score-pill warn-pill"


def render_signal_header(symbol: str, interval: str, analysis: SignalAnalysis) -> None:
    st.markdown('<div class="signal-card">', unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns([2.2, 1.2, 1.1, 1.1])

    with c1:
        st.markdown('<div class="tiny-heading">Signal Output</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="big-signal">{analysis.signal_label}</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div style="margin-top: 0.55rem;">
                <span class="{pill_class(analysis.signal_bias)}">{analysis.signal_bias}</span>
                <span class="score-pill">Pair: {symbol}</span>
                <span class="score-pill">Timeframe: {interval}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with c2:
        st.markdown('<div class="metric-label">Current Price</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{analysis.current_price:,.6f}</div>', unsafe_allow_html=True)

    with c3:
        st.markdown('<div class="metric-label">Conviction</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{analysis.conviction_score:.1f}/100</div>', unsafe_allow_html=True)

    with c4:
        st.markdown('<div class="metric-label">24h Change</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="metric-value">{analysis.change_pct_24h:+.2f}%</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


def render_component_grid(analysis: SignalAnalysis) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### Signal Components")

    rows = [analysis.component_summary[:4], analysis.component_summary[4:]]
    for row in rows:
        cols = st.columns(4)
        for col, item in zip(cols, row):
            name, score, desc = item
            with col:
                st.markdown(
                    f"""
                    <div class="component-box">
                        <div class="component-title">{name}</div>
                        <div class="component-value">{score}</div>
                        <div class="component-desc">{desc}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown("</div>", unsafe_allow_html=True)


def render_narrative_section(title: str, body: str) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown(f"### {title}")
    st.markdown(f'<div class="narrative">{body}</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_key_facts(analysis: SignalAnalysis) -> None:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### Key Facts")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Relative Volume", f"{analysis.raw_facts['rel_volume']:.2f}x")
        st.metric("RSI(14)", f"{analysis.raw_facts['rsi']:.1f}")
    with c2:
        st.metric("ATR % of Price", f"{analysis.raw_facts['atr_pct']:.2f}%")
        st.metric("Position in Range", f"{analysis.raw_facts['pos_in_range_pct']:.1f}%")
    with c3:
        st.metric("EMA 20", f"{analysis.raw_facts['ema20']:.6f}")
        st.metric("EMA 50", f"{analysis.raw_facts['ema50']:.6f}")
    with c4:
        st.metric("20-Bar High", f"{analysis.raw_facts['high_20']:.6f}")
        st.metric("20-Bar Low", f"{analysis.raw_facts['low_20']:.6f}")
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------
# App layout
# ---------------------------------------------------------
st.markdown('<div class="main-title">🎯 Crypto Sniper</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="subtitle">Clear signal output, translated components, market structure, timing clarity, deeper AI reasoning, and one-click PDF export.</div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("## Configure Scan")
    symbol = st.selectbox("Trading Pair", PAIR_OPTIONS, index=0)
    interval = st.selectbox("Timeframe", INTERVAL_OPTIONS, index=2)
    depth_label = st.radio("Scan Depth", list(LOOKBACK_OPTIONS.keys()), horizontal=True, index=1)
    limit = LOOKBACK_OPTIONS[depth_label]

    st.markdown("## Display")
    auto_refresh = st.checkbox("Auto refresh every 60 seconds", value=False)
    show_price_chart = st.checkbox("Show price chart", value=True)
    show_raw_table = st.checkbox("Show recent candles", value=False)

    st.markdown("## Signal Flow")
    st.caption(
        "Signal Output → Signal Components → Market Structure → Timing Quality → AI Lab → Download PDF"
    )

    run_scan = st.button("Run Scan", use_container_width=True, type="primary")

if auto_refresh:
    time.sleep(0.2)

if run_scan or auto_refresh:
    try:
        with st.spinner("Fetching live market data and generating signal..."):
            df = fetch_klines(symbol=symbol, interval=interval, limit=limit)
            analysis = analyze_signal(df)

        # Optional chart
        if show_price_chart:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### Market View")
            chart_df = df[["open_time", "close", "ema_20", "ema_50"]].copy()
            chart_df = chart_df.set_index("open_time")
            st.line_chart(chart_df[["close", "ema_20", "ema_50"]], height=320)
            st.markdown("</div>", unsafe_allow_html=True)

        # Exact requested order
        render_signal_header(symbol, interval, analysis)
        render_component_grid(analysis)
        render_narrative_section("Market Structure", analysis.market_structure)
        render_narrative_section("Timing Quality", analysis.timing_quality)
        render_narrative_section("AI Lab", analysis.ai_lab)
        render_key_facts(analysis)

        pdf_bytes = build_pdf_bytes(symbol=symbol, interval=interval, analysis=analysis)

        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown("### Download PDF")
        st.download_button(
            label="Download PDF Report",
            data=pdf_bytes,
            file_name=f"crypto_sniper_{symbol.lower()}_{interval}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if show_raw_table:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown("### Recent Candles")
            display_df = df.tail(20).copy()
            display_df = display_df[
                ["open_time", "open", "high", "low", "close", "volume"]
            ].reset_index(drop=True)
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            st.markdown("</div>", unsafe_allow_html=True)

    except requests.HTTPError as e:
        st.error(f"Binance API error: {e}")
    except Exception as e:
        st.error(f"App error: {e}")
else:
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown("### Ready")
    st.write(
        "Choose a pair and timeframe from the sidebar, then click **Run Scan**. "
        "The output will appear in the exact order you requested."
    )
    st.markdown("</div>", unsafe_allow_html=True)
