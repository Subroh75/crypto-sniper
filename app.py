"""
Crypto Sniper - Professional Signal Intelligence
Single-page Streamlit app. Enter a base asset (BTC, ETH, SOL...).
Sections: Signal Output . Signal Components . Market Structure .
          Timing Quality . Kronos AI Forecast . AI Lab . PDF Download
"""

import sys
import os
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

# Add backend/ to path so we can import core.py
_backend_dir = str(Path(__file__).resolve().parent / "backend")
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from core import (           # noqa: E402
    clean_symbol,
    fetch_ohlcv,
    compute_indicators,
    compute_scores,
    generate_agent_debate,
)

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

try:
    from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
    HAS_KRONOS = True
except ImportError:
    HAS_KRONOS = False

# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Crypto Sniper",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&family=JetBrains+Mono:wght@400;700&display=swap');

html, body, [class*="css"] {
  font-family: 'Inter', sans-serif !important;
}

/* Hide Streamlit chrome */
[data-testid="collapsedControl"], #MainMenu, footer, header { display:none !important; }
section[data-testid="stSidebar"] { display:none !important; }

/* Background */
.stApp { background: #060912; }
.block-container { padding: 2rem 1rem 4rem; max-width: 900px; }

/* ── Typography ── */
h1,h2,h3,h4 { color: #f1f5f9 !important; }

/* ── Hero title ── */
.hero-wrap { text-align:center; padding: 2rem 0 1.5rem; }
.hero-logo {
  font-size: 0.7rem; font-weight: 800; letter-spacing: 0.35em;
  color: #7c3aed; text-transform: uppercase; margin-bottom: 0.5rem;
}
.hero-title {
  font-size: 3rem; font-weight: 900; letter-spacing: -2px;
  color: #ffffff; line-height: 1;
}
.hero-title span {
  background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.hero-sub {
  font-size: 0.85rem; font-weight: 500; color: #94a3b8;
  letter-spacing: 0.08em; margin-top: 0.6rem;
  text-transform: uppercase;
}

/* ── Input + button ── */
div[data-testid="stTextInput"] input {
  background: #0f1629 !important;
  border: 1.5px solid #334155 !important;
  color: #ffffff !important;
  border-radius: 12px !important;
  font-size: 1.2rem !important;
  font-weight: 700 !important;
  text-align: center;
  letter-spacing: 0.06em;
  padding: 0.75rem 1rem !important;
}
div[data-testid="stTextInput"] input::placeholder {
  color: #64748b !important;
  font-weight: 500 !important;
}
div[data-testid="stTextInput"] input:focus {
  border-color: #7c3aed !important;
  box-shadow: 0 0 0 3px rgba(124,58,237,0.25) !important;
}
.stButton > button,
.stFormSubmitButton > button {
  width: 100%;
  background: linear-gradient(135deg, #7c3aed, #38bdf8) !important;
  color: #fff !important; border: none !important;
  border-radius: 12px !important;
  font-weight: 800 !important; font-size: 0.95rem !important;
  letter-spacing: 0.1em; padding: 0.75rem !important;
  text-transform: uppercase;
  transition: opacity 0.2s;
}
.stButton > button:hover,
.stFormSubmitButton > button:hover { opacity: 0.88; }

/* ── Radio interval pills ── */
div[data-testid="stRadio"] > div { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
div[data-testid="stRadio"] label {
  background: #111827 !important; border: 1.5px solid #475569 !important;
  border-radius: 8px !important; padding: 5px 18px !important;
  color: #e2e8f0 !important; font-size: 0.85rem !important;
  font-weight: 700 !important; cursor: pointer; letter-spacing: 0.06em;
}
div[data-testid="stRadio"] label p {
  color: #e2e8f0 !important; font-weight: 700 !important;
  font-size: 0.85rem !important; margin: 0 !important;
}
div[data-testid="stRadio"] label:has(input:checked) {
  border-color: #7c3aed !important;
  background: linear-gradient(135deg, #1a0f3a, #0f1a2e) !important;
  box-shadow: 0 0 12px rgba(124,58,237,0.4) !important;
}
div[data-testid="stRadio"] label:has(input:checked) p {
  color: #ffffff !important;
}

/* ── Section header ── */
.sec-hdr {
  display: flex; align-items: center; gap: 10px;
  margin: 2.5rem 0 1.2rem;
}
.sec-hdr-line {
  flex: 1; height: 1px; background: #1e293b;
}
.sec-hdr-text {
  font-size: 0.68rem; font-weight: 800; letter-spacing: 0.2em;
  color: #94a3b8; text-transform: uppercase; white-space: nowrap;
}
.sec-hdr-dot {
  width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0;
}

/* ── Signal banner ── */
.sig-banner {
  border-radius: 20px; padding: 2rem 2.5rem; text-align: center;
  position: relative; overflow: hidden; margin-bottom: 1rem;
}
.sig-banner-strong {
  background: linear-gradient(135deg, #052e16 0%, #064e3b 100%);
  border: 1px solid #10b981;
  box-shadow: 0 0 40px rgba(16,185,129,0.15);
}
.sig-banner-moderate {
  background: linear-gradient(135deg, #1c1207 0%, #422006 100%);
  border: 1px solid #f59e0b;
  box-shadow: 0 0 40px rgba(245,158,11,0.12);
}
.sig-banner-weak {
  background: linear-gradient(135deg, #0a0e1a 0%, #0f172a 100%);
  border: 1px solid #1e293b;
}
.sig-symbol { font-size: 0.75rem; font-weight: 800; letter-spacing: 0.2em; color: #94a3b8; margin-bottom:0.5rem; text-transform:uppercase; }
.sig-label-strong   { font-size: 2.8rem; font-weight: 900; color: #10b981; letter-spacing: -1px; line-height:1; }
.sig-label-moderate { font-size: 2.8rem; font-weight: 900; color: #f59e0b; letter-spacing: -1px; line-height:1; }
.sig-label-weak     { font-size: 2.8rem; font-weight: 900; color: #334155; letter-spacing: -1px; line-height:1; }
.sig-score { font-size: 1rem; font-weight: 700; margin-top: 0.6rem; }
.sig-meta  { font-size: 0.78rem; color: #94a3b8; margin-top: 0.4rem; font-family: 'JetBrains Mono', monospace; }

/* ── Metric grid ── */
.mgrid { display:grid; grid-template-columns: repeat(4,1fr); gap:10px; margin: 1rem 0; }
.mcard {
  background: #0c1225; border: 1px solid #1a2540;
  border-radius: 14px; padding: 1rem; text-align:center;
}
.mcard-lbl { font-size:0.65rem; font-weight:700; letter-spacing:0.15em; color:#94a3b8; text-transform:uppercase; margin-bottom:5px; }
.mcard-val { font-size:1.3rem; font-weight:800; color:#e2e8f0; }
.mcard-sub { font-size:0.68rem; font-weight:600; margin-top:3px; }

/* ── Score bars ── */
.sbar-wrap { margin: 0.5rem 0; }
.sbar-row { display:flex; align-items:center; gap:12px; margin:8px 0; }
.sbar-lbl { font-size:0.8rem; font-weight:700; color:#cbd5e1; width:140px; flex-shrink:0; }
.sbar-bg { flex:1; background:#0f172a; border-radius:999px; height:9px; overflow:hidden; }
.sbar-fill { height:100%; border-radius:999px; }
.sbar-num { font-size:0.78rem; font-weight:800; color:#f1f5f9; width:35px; text-align:right; font-family:'JetBrains Mono',monospace; }
.sbar-hint { font-size:0.68rem; color:#94a3b8; min-width:170px; }

/* ── Market structure table ── */
.mkt-table { width:100%; border-collapse:collapse; margin:0.5rem 0; }
.mkt-table td { padding: 10px 14px; font-size:0.82rem; border-bottom:1px solid #0f172a; }
.mkt-table tr:last-child td { border-bottom:none; }
.mkt-table .mkt-lbl { color:#94a3b8; font-weight:600; width:45%; }
.mkt-table .mkt-val { color:#e2e8f0; font-weight:700; font-family:'JetBrains Mono',monospace; }

/* ── Timing quality ── */
.tq-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:0.8rem 0; }
.tq-card {
  background:#0c1225; border:1px solid #1a2540;
  border-radius:14px; padding:1rem; text-align:center;
}
.tq-lbl { font-size:0.65rem; font-weight:700; letter-spacing:0.15em; color:#94a3b8; text-transform:uppercase; margin-bottom:5px; }
.tq-val { font-size:1.1rem; font-weight:800; color:#e2e8f0; }
.tq-sub { font-size:0.7rem; margin-top:3px; }

/* ── AI Agent cards ── */
.agent-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; margin:0.8rem 0; }
.agent-card {
  border-radius:16px; padding:1.2rem 1.4rem;
  border:1px solid transparent; position:relative;
}
.agent-bull { background:#041a0d; border-color:#065f46; }
.agent-bear { background:#1a0404; border-color:#7f1d1d; }
.agent-risk { background:#0d0d1a; border-color:#312e81; }
.agent-cio  { background:#160b24; border-color:#581c87; }
.agent-role {
  font-size:0.62rem; font-weight:800; letter-spacing:0.18em;
  text-transform:uppercase; margin-bottom:0.35rem;
}
.agent-bull .agent-role { color:#10b981; }
.agent-bear .agent-role { color:#f87171; }
.agent-risk .agent-role { color:#818cf8; }
.agent-cio  .agent-role { color:#c084fc; }
.agent-name { font-size:1rem; font-weight:800; color:#f1f5f9; margin-bottom:0.5rem; }
.agent-text { font-size:0.78rem; color:#94a3b8; line-height:1.5; }
.agent-verdict {
  font-size:0.72rem; font-weight:700; margin-top:0.7rem;
  padding: 3px 10px; border-radius:999px; display:inline-block;
}
.verdict-buy      { background:#052e16; color:#10b981; }
.verdict-sell     { background:#450a0a; color:#f87171; }
.verdict-hold     { background:#0d0d2e; color:#818cf8; }
.verdict-watchlist{ background:#1a0533; color:#c084fc; }

/* ── Download button ── */
.stDownloadButton > button {
  width:100%; background:#0c1225 !important;
  border:1px solid #1e293b !important; color:#94a3b8 !important;
  border-radius:12px !important; font-weight:700 !important;
  font-size:0.85rem !important;
}
.stDownloadButton > button:hover {
  border-color:#7c3aed !important; color:#c4b5fd !important;
}
</style>
""", unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════
# DATA (thin caching wrapper around core.fetch_ohlcv)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60, show_spinner=False)
def cached_fetch_ohlcv(base: str, interval: str, limit: int = 500) -> Optional[pd.DataFrame]:
    return fetch_ohlcv(base, interval, limit)


# ══════════════════════════════════════════════════════════════════════════════
# KRONOS
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# KRONOS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def load_kronos_model():
    """Load Kronos-mini once and cache for the session lifetime."""
    if not HAS_KRONOS:
        return None
    try:
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model     = Kronos.from_pretrained("NeoQuasar/Kronos-mini")
        return KronosPredictor(model, tokenizer, max_context=512)
    except Exception:
        return None


def run_kronos_forecast(df, pred_len=24, lookback=256):
    """Run Kronos-mini forecast. Returns predicted OHLCV DataFrame or None."""
    predictor = load_kronos_model()
    if predictor is None:
        return None
    try:
        df       = df.sort_values("timestamp").reset_index(drop=True)
        lookback = min(lookback, len(df), 512)
        ctx      = df.tail(lookback).reset_index(drop=True)
        x_ts     = ctx["timestamp"]
        delta    = ctx["timestamp"].iloc[-1] - ctx["timestamp"].iloc[-2]
        y_ts     = pd.Series(pd.date_range(
            start=ctx["timestamp"].iloc[-1] + delta,
            periods=pred_len, freq=delta,
        ))
        cols = [c for c in ["open","high","low","close","volume"] if c in ctx.columns]
        pred = predictor.predict(
            df=ctx[cols], x_timestamp=x_ts, y_timestamp=y_ts,
            pred_len=pred_len, T=1.0, top_p=0.9, sample_count=1,
        )
        return pred
    except Exception:
        return None


def summarise_kronos(pred, current_close):
    """Extract key stats from a Kronos forecast DataFrame."""
    if pred is None or pred.empty:
        return {}
    closes    = pred["close"].values
    final     = float(closes[-1])
    peak      = float(pred["high"].max())
    trough    = float(pred["low"].min())
    pct       = (final - current_close) / current_close * 100
    bull_pct  = float((pred["close"] > pred["open"]).mean() * 100)
    direction = "UP" if final > current_close else "DOWN"
    return {
        "final_close": round(final, 6),
        "pct_change":  round(pct, 2),
        "peak":        round(peak, 6),
        "trough":      round(trough, 6),
        "bull_pct":    round(bull_pct, 1),
        "direction":   direction,
        "candles":     len(pred),
    }


def make_kronos_chart(pred_df, current_close, symbol):
    """Build a Plotly forecast chart from Kronos predictions."""
    if pred_df is None or not HAS_PLOTLY:
        return None
    color = "#10b981" if float(pred_df["close"].iloc[-1]) > current_close else "#f87171"
    fill_rgba = "rgba(16,185,129,0.06)" if color == "#10b981" else "rgba(248,113,113,0.06)"
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=list(range(len(pred_df))), y=pred_df["close"].tolist(),
        mode="lines", name="Predicted Close",
        line=dict(color=color, width=2.5),
        fill="tozeroy", fillcolor=fill_rgba,
    ))
    if "high" in pred_df.columns and "low" in pred_df.columns:
        xs = list(range(len(pred_df))) + list(range(len(pred_df)-1, -1, -1))
        ys = pred_df["high"].tolist() + pred_df["low"].tolist()[::-1]
        fig.add_trace(go.Scatter(
            x=xs, y=ys,
            fill="toself",
            fillcolor="rgba(124,58,237,0.08)",
            line=dict(color="rgba(124,58,237,0.3)", width=1),
            name="High/Low Band",
        ))
    fig.add_hline(
        y=current_close, line_dash="dot",
        line_color="#475569", annotation_text="Current",
        annotation_font_color="#94a3b8",
    )
    fig.update_layout(
        paper_bgcolor="#060912", plot_bgcolor="#060912",
        font=dict(color="#94a3b8", family="Inter, sans-serif", size=11),
        xaxis=dict(showgrid=False, tickfont=dict(color="#475569"), title=dict(text="Future Candles", font=dict(color="#64748b", size=10))),
        yaxis=dict(showgrid=True, gridcolor="#0f172a", tickfont=dict(color="#475569")),
        margin=dict(l=10, r=10, t=40, b=30), height=220,
        legend=dict(orientation="h", y=1.08, x=1, xanchor="right", font=dict(size=10, color="#94a3b8")),
        hovermode="x unified",
        title=dict(text=f"Kronos-mini \u2014 Predicted Close ({len(pred_df)} candles forward)",
                   font=dict(color="#94a3b8", size=11), x=0.5),
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# PDF
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# PDF
# ══════════════════════════════════════════════════════════════════════════════

def _p(text: str) -> str:
    """Sanitise text to Latin-1 safe ASCII for fpdf2 core fonts."""
    replacements = {
        "\u2014": "-",   # em dash
        "\u2013": "-",   # en dash
        "\u00d7": "x",   # multiplication sign
        "\u00b7": ".",   # middle dot
        "\u2019": "'",   # right single quote
        "\u2018": "'",   # left single quote
        "\u201c": '"',   # left double quote
        "\u201d": '"',   # right double quote
        "\u2022": "-",   # bullet
        "\u2026": "...", # ellipsis
        "\u2192": "->",  # arrow
        "\u2713": "OK",  # check mark
        "\u2717": "X",   # cross
        "\u25b2": "^",   # up triangle
        "\u25bc": "v",   # down triangle
    }
    for ch, rep in replacements.items():
        text = text.replace(ch, rep)
    # Strip any remaining non-Latin-1 characters
    return text.encode("latin-1", errors="ignore").decode("latin-1")

def build_pdf(symbol: str, interval: str, sc: dict, debate: dict, now: str, kronos_summary: dict = None) -> bytes:
    if not HAS_FPDF:
        return b""

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Title
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 12, _p("CRYPTO SNIPER - SIGNAL REPORT"), ln=True, align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(0, 6, _p(f"{symbol}/USDT  |  {interval}  |  {now}"), ln=True, align="C")
    pdf.ln(4)

    # Signal
    score = sc["score"]
    label = "STRONG BUY" if score >= 9 else "MODERATE" if score >= 5 else "NO SIGNAL"
    pdf.set_font("Helvetica", "B", 18)
    color = (16, 185, 129) if score >= 9 else (245, 158, 11) if score >= 5 else (100, 116, 139)
    pdf.set_text_color(*color)
    pdf.cell(0, 10, _p(f"SIGNAL: {label}  ({score}/13)"), ln=True, align="C")
    pdf.ln(3)

    def section(title):
        pdf.set_font("Helvetica", "B", 11)
        pdf.set_text_color(30, 41, 59)
        pdf.set_fill_color(241, 245, 249)
        pdf.cell(0, 8, _p(f"  {title}"), ln=True, fill=True)
        pdf.ln(2)

    def row(lbl, value):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(60, 6, _p(lbl))
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 6, _p(str(value)), ln=True)

    def body(text):
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(51, 65, 85)
        pdf.multi_cell(0, 5, _p(text))
        pdf.ln(2)

    # Score breakdown
    section("SIGNAL COMPONENTS")
    row("V - Volume (max 5)",        f"{sc['V']}/5   RV = {sc['rv']}x")
    row("P - Momentum (max 3)",      f"{sc['P']}/3   ATR move = {sc['atr_move']}")
    row("R - Range Position (max 2)",f"{sc['R']}/2   range_pos = {sc['range_pos']}")
    row("T - Trend Alignment (max 3)",f"{sc['T']}/3   ADX = {sc['adx14']:.1f}")
    pdf.ln(2)

    # Market structure
    section("MARKET STRUCTURE")
    row("Close",          f"{sc['close']:.6g}")
    row("EMA 20",         f"{sc['ema20']:.6g}  ({'above' if sc['close'] > sc['ema20'] else 'below'})")
    row("EMA 50",         f"{sc['ema50']:.6g}  ({'above' if sc['close'] > sc['ema50'] else 'below'})")
    row("EMA 200",        f"{sc['ema200']:.6g}  ({'above' if sc['close'] > sc['ema200'] else 'below'})")
    row("VWAP",           f"{sc['vwap']:.6g}  ({'above' if sc['close'] > sc['vwap'] else 'below'})")
    row("BB Upper/Lower", f"{sc['bb_upper']:.6g}  /  {sc['bb_lower']:.6g}")
    pdf.ln(2)

    # Timing
    section("TIMING QUALITY")
    row("RSI 14",    f"{sc['rsi14']:.1f}")
    row("ADX 14",    f"{sc['adx14']:.1f}  ({'Trending' if sc['adx14'] >= 20 else 'Ranging'})")
    row("+DI / -DI", f"{sc['plus_di']:.1f}  /  {sc['minus_di']:.1f}")
    row("ATR 14",    f"{sc['atr14']:.4g}  ({sc['atr14']/sc['close']*100:.2f}% of price)")
    pdf.ln(2)

    # AI debate
    section("AI LAB - AGENT DEBATE")
    for agent, lbl in [("bull", "BULL"), ("bear", "BEAR"), ("risk", "RISK MANAGER"), ("cio", "CIO")]:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(15, 23, 42)
        pdf.cell(0, 6, _p(f"{lbl} - Verdict: {debate[agent]['verdict']}"), ln=True)
        body(debate[agent]["text"])

    # Kronos forecast section (if available)
    if kronos_summary:
        section("KRONOS-MINI AI FORECAST")
        direction_label = "UP" if kronos_summary.get("direction") == "UP" else "DOWN"
        row("Direction",        direction_label)
        row("Predicted Change",  f"{kronos_summary.get('pct_change', 0):+.2f}%")
        row("Predicted Close",   f"{kronos_summary.get('final_close', 0):.6g}")
        row("Forecast Peak",     f"{kronos_summary.get('peak', 0):.6g}")
        row("Forecast Trough",   f"{kronos_summary.get('trough', 0):.6g}")
        row("Bull Candle %",     f"{kronos_summary.get('bull_pct', 0):.1f}%")
        row("Candles Forecast",  str(kronos_summary.get('candles', 0)))
        pdf.ln(2)

    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 7)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(0, 5, _p("Data via Yahoo Finance. Signals are not financial advice. Past performance does not guarantee future results."), ln=True, align="C")

    return bytes(pdf.output())



# ══════════════════════════════════════════════════════════════════════════════
# CHART
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# CHART
# ══════════════════════════════════════════════════════════════════════════════

def make_chart(df: pd.DataFrame, sc: dict, symbol: str) -> Optional[object]:
    if not HAS_PLOTLY:
        return None
    show = df.tail(80).copy()
    fig  = go.Figure()
    fig.add_trace(go.Candlestick(
        x=show["timestamp"], open=show["open"], high=show["high"],
        low=show["low"], close=show["close"], name="Price",
        increasing=dict(line=dict(color="#10b981"), fillcolor="#059669"),
        decreasing=dict(line=dict(color="#f87171"), fillcolor="#dc2626"),
    ))
    for col, color, name in [("ema20","#10b981","EMA20"),("ema50","#818cf8","EMA50"),("ema200","#fb923c","EMA200"),("bb_upper","#334155","BB+"),("bb_lower","#334155","BB-")]:
        if col in show.columns:
            fig.add_trace(go.Scatter(
                x=show["timestamp"], y=show[col], mode="lines",
                line=dict(color=color, width=1.5 if "ema" in col else 1, dash="dot" if "bb" in col else "solid"),
                name=name, opacity=0.85,
            ))
    fig.update_layout(
        paper_bgcolor="#060912", plot_bgcolor="#060912",
        font=dict(color="#94a3b8", family="Inter, sans-serif", size=11),
        xaxis=dict(showgrid=False, color="#1e293b", rangeslider_visible=False, tickfont=dict(color="#475569")),
        yaxis=dict(showgrid=True, gridcolor="#0f172a", color="#475569", tickfont=dict(color="#475569")),
        margin=dict(l=10, r=10, t=10, b=10), height=340,
        legend=dict(orientation="h", y=1.02, x=1, xanchor="right", font=dict(size=10, color="#94a3b8")),
        hovermode="x unified",
    )
    return fig



# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def sec(title: str, dot_color: str = "#7c3aed"):
    st.markdown(f"""
<div class="sec-hdr">
  <div class="sec-hdr-line"></div>
  <div class="sec-hdr-dot" style="background:{dot_color}"></div>
  <div class="sec-hdr-text">{title}</div>
  <div class="sec-hdr-dot" style="background:{dot_color}"></div>
  <div class="sec-hdr-line"></div>
</div>""", unsafe_allow_html=True)

def mcard(label: str, value: str, sub: str = "", sub_color: str = "#475569"):
    return f"""<div class="mcard">
  <div class="mcard-lbl">{label}</div>
  <div class="mcard-val">{value}</div>
  <div class="mcard-sub" style="color:{sub_color}">{sub}</div>
</div>"""

def sbar(label: str, val: int, maxval: int, hint: str, color: str = "#7c3aed"):
    pct = int(val / maxval * 100)
    return f"""<div class="sbar-row">
  <div class="sbar-lbl">{label}</div>
  <div class="sbar-bg"><div class="sbar-fill" style="width:{pct}%;background:{color}"></div></div>
  <div class="sbar-num">{val}/{maxval}</div>
  <div class="sbar-hint">{hint}</div>
</div>"""


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT
# ══════════════════════════════════════════════════════════════════════════════

st.markdown("""
<div class="hero-wrap">
  <div class="hero-logo">&#9679; Signal Intelligence</div>
  <div class="hero-title">CRYPTO <span>SNIPER</span></div>
  <div class="hero-sub">Real-time · Multi-factor · AI-powered</div>
</div>
""", unsafe_allow_html=True)

# Interval selector — outside the form so it persists across re-runs
interval_map = {"1m":"1m","5m":"5m","15m":"15m","30m":"30m","1H":"1h","4H":"4h","1D":"1d"}
interval_lbl = st.radio("", list(interval_map.keys()), index=4, horizontal=True, label_visibility="collapsed")
interval     = interval_map[interval_lbl]

# st.form submits on Enter key OR button click
with st.form(key="sniper_form", enter_to_submit=True, border=False):
    c1, c2 = st.columns([3, 1])
    with c1:
        coin_raw = st.text_input(
            "",
            placeholder="BTC  ·  ETH  ·  SOL  ·  KAVA",
            label_visibility="collapsed",
        )
    with c2:
        go_btn = st.form_submit_button("ANALYSE", use_container_width=True)

# Run if form was submitted (Enter or button) AND a coin was typed
should_run = go_btn and bool(coin_raw)

if not should_run:
    st.markdown("""
<div style="text-align:center;padding:3rem 0;color:#64748b;
            font-size:0.88rem;letter-spacing:0.1em;font-weight:600;">
TYPE A COIN ABOVE &nbsp;&nbsp;&middot;&nbsp;&nbsp; PRESS ENTER OR CLICK ANALYSE
</div>""", unsafe_allow_html=True)
    st.stop()

base = clean_symbol(coin_raw)

with st.spinner(f"Fetching {base} data…"):
    df_raw = cached_fetch_ohlcv(base, interval)

if df_raw is None or len(df_raw) < 60:
    st.error(f"Could not find **{base}** on Yahoo Finance. Try: BTC · ETH · SOL · BNB · KAVA · DOGE")
    st.stop()

df = compute_indicators(df_raw)
df = df.dropna(subset=["ema20","ema50","atr14","adx14"]).reset_index(drop=True)

if len(df) < 2:
    st.error("Not enough data to compute indicators.")
    st.stop()

sc = compute_scores(df)
if sc is None:
    st.error("Scoring failed.")
    st.stop()

# Run Kronos silently here so kronos_summary is ready for the debate
kronos_summary = None
pred_df        = None
if HAS_KRONOS:
    with st.spinner("Running Kronos-mini forecast… (~60-90s on first load, cached after)"):
        pred_df = run_kronos_forecast(df, pred_len=24)
    if pred_df is not None and not pred_df.empty:
        kronos_summary = summarise_kronos(pred_df, sc["close"])

debate  = generate_agent_debate(base, sc, interval, kronos_summary=kronos_summary)
score   = sc["score"]
now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ─── 1. SIGNAL OUTPUT ────────────────────────────────────────────────────────
sec("01 — Signal Output", "#10b981" if score >= 9 else "#f59e0b" if score >= 5 else "#334155")

if score >= 9:
    bcls, lcls, scls = "sig-banner-strong", "sig-label-strong", "#10b981"
    label = "STRONG BUY"
elif score >= 5:
    bcls, lcls, scls = "sig-banner-moderate", "sig-label-moderate", "#f59e0b"
    label = "MODERATE"
else:
    bcls, lcls, scls = "sig-banner-weak", "sig-label-weak", "#334155"
    label = "NO SIGNAL"

pct_color = "#10b981" if sc["pct"] >= 0 else "#f87171"
pct_sign  = "+" if sc["pct"] >= 0 else ""

st.markdown(f"""
<div class="sig-banner {bcls}">
  <div class="sig-symbol">{base}/USDT  ·  {interval_lbl}  ·  {now_str}</div>
  <div class="{lcls}">{label}</div>
  <div class="sig-score" style="color:{scls}">{score} / 13</div>
  <div class="sig-meta">
    CLOSE {sc['close']:.6g}
    &nbsp;&nbsp;·&nbsp;&nbsp;
    <span style="color:{pct_color}">{pct_sign}{sc['pct']:.2f}%</span>
    &nbsp;&nbsp;·&nbsp;&nbsp;
    VOL {sc['rv']:.1f}×
    &nbsp;&nbsp;·&nbsp;&nbsp;
    RSI {sc['rsi14']:.0f}
    &nbsp;&nbsp;·&nbsp;&nbsp;
    ADX {sc['adx14']:.0f}
  </div>
</div>
""", unsafe_allow_html=True)

# ─── 2. SIGNAL COMPONENTS ────────────────────────────────────────────────────
sec("02 — Signal Components", "#818cf8")

st.markdown(
    '<div class="sbar-wrap">' +
    sbar("V  Volume",    sc["V"], 5, f"RV = {sc['rv']}×  (vs 20-bar avg)", "#10b981") +
    sbar("P  Momentum",  sc["P"], 3, f"ATR move = {sc['atr_move']}σ", "#38bdf8") +
    sbar("R  Range Pos", sc["R"], 2, f"range_pos = {sc['range_pos']}", "#f59e0b") +
    sbar("T  Trend",     sc["T"], 3, f"ADX {sc['adx14']:.0f}  ·  EMA stack {'✓' if sc['ema20'] > sc['ema50'] else '✗'}", "#c084fc") +
    '</div>',
    unsafe_allow_html=True
)

# ─── 3. MARKET STRUCTURE ─────────────────────────────────────────────────────
sec("03 — Market Structure", "#38bdf8")

above = lambda val: (f"<span style='color:#10b981'>▲ above</span>" if sc['close'] > val
                     else f"<span style='color:#f87171'>▼ below</span>")

st.markdown(f"""
<table class="mkt-table">
  <tr><td class="mkt-lbl">Close</td>
      <td class="mkt-val">{sc['close']:.6g}</td></tr>
  <tr><td class="mkt-lbl">EMA 20</td>
      <td class="mkt-val">{sc['ema20']:.6g}&nbsp;&nbsp;{above(sc['ema20'])}</td></tr>
  <tr><td class="mkt-lbl">EMA 50</td>
      <td class="mkt-val">{sc['ema50']:.6g}&nbsp;&nbsp;{above(sc['ema50'])}</td></tr>
  <tr><td class="mkt-lbl">EMA 200</td>
      <td class="mkt-val">{sc['ema200']:.6g}&nbsp;&nbsp;{above(sc['ema200'])}</td></tr>
  <tr><td class="mkt-lbl">VWAP</td>
      <td class="mkt-val">{sc['vwap']:.6g}&nbsp;&nbsp;{above(sc['vwap'])}</td></tr>
  <tr><td class="mkt-lbl">Bollinger Bands</td>
      <td class="mkt-val">{sc['bb_upper']:.6g} / {sc['bb_lower']:.6g}</td></tr>
  <tr><td class="mkt-lbl">24h Change</td>
      <td class="mkt-val" style="color:{'#10b981' if sc['pct']>=0 else '#f87171'}">
        {'+' if sc['pct']>=0 else ''}{sc['pct']:.2f}%</td></tr>
</table>
""", unsafe_allow_html=True)

# Chart
fig = make_chart(df, sc, base)
if fig:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ─── 4. TIMING QUALITY ───────────────────────────────────────────────────────
sec("04 — Timing Quality", "#f59e0b")

rsi_color = "#f87171" if sc["rsi14"] >= 70 else "#10b981" if sc["rsi14"] <= 30 else "#94a3b8"
rsi_label = "OVERBOUGHT" if sc["rsi14"] >= 70 else "OVERSOLD" if sc["rsi14"] <= 30 else "NEUTRAL"
adx_label = "TRENDING" if sc["adx14"] >= 20 else "RANGING"
atr_pct   = sc["atr14"] / sc["close"] * 100

st.markdown(f"""
<div class="tq-grid">
  <div class="tq-card">
    <div class="tq-lbl">RSI 14</div>
    <div class="tq-val" style="color:{rsi_color}">{sc['rsi14']:.1f}</div>
    <div class="tq-sub" style="color:{rsi_color}">{rsi_label}</div>
  </div>
  <div class="tq-card">
    <div class="tq-lbl">ADX 14</div>
    <div class="tq-val">{sc['adx14']:.1f}</div>
    <div class="tq-sub" style="color:{'#10b981' if sc['adx14']>=20 else '#f59e0b'}">{adx_label}</div>
  </div>
  <div class="tq-card">
    <div class="tq-lbl">ATR 14</div>
    <div class="tq-val">{sc['atr14']:.4g}</div>
    <div class="tq-sub" style="color:#64748b">{atr_pct:.2f}% of price</div>
  </div>
  <div class="tq-card">
    <div class="tq-lbl">+DI / -DI</div>
    <div class="tq-val">{sc['plus_di']:.1f} / {sc['minus_di']:.1f}</div>
    <div class="tq-sub" style="color:{'#10b981' if sc['plus_di']>sc['minus_di'] else '#f87171'}">
      {'Bulls in control' if sc['plus_di']>sc['minus_di'] else 'Bears in control'}</div>
  </div>
  <div class="tq-card">
    <div class="tq-lbl">Rel. Volume</div>
    <div class="tq-val">{sc['rv']:.2f}×</div>
    <div class="tq-sub" style="color:{'#10b981' if sc['rv']>=2 else '#64748b'}">
      {'Volume spike' if sc['rv']>=4 else 'Elevated' if sc['rv']>=2 else 'Normal'}</div>
  </div>
  <div class="tq-card">
    <div class="tq-lbl">ATR Move</div>
    <div class="tq-val">{sc['atr_move']:.2f}σ</div>
    <div class="tq-sub" style="color:{'#10b981' if sc['atr_move']>=1.5 else '#64748b'}">
      {'Strong' if sc['atr_move']>=2.5 else 'Moderate' if sc['atr_move']>=1.5 else 'Weak'}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ─── 5. KRONOS AI FORECAST ──────────────────────────────────────────────────
sec("05 — Kronos AI Forecast", "#7c3aed")

if not HAS_KRONOS:
    st.markdown(
        '<div style="text-align:center;padding:1.5rem 0;color:#334155;'
        'font-size:0.78rem;letter-spacing:0.08em;font-weight:600;">'
        'KRONOS-MINI NOT INSTALLED &nbsp;·&nbsp; '
        'uncomment <code>torch</code> and <code>kronos-ts</code> '
        'in requirements.txt to enable AI forecasting</div>',
        unsafe_allow_html=True,
    )
elif kronos_summary is not None:
    kdir_color = "#10b981" if kronos_summary["direction"] == "UP" else "#f87171"
    kfig = make_kronos_chart(pred_df, sc["close"], base)
    if kfig:
        st.plotly_chart(kfig, use_container_width=True, config={"displayModeBar": False})
    bull_color = "#10b981" if kronos_summary["bull_pct"] >= 50 else "#f87171"
    st.markdown(f"""
<div class="tq-grid">
  <div class="tq-card">
    <div class="tq-lbl">Direction</div>
    <div class="tq-val" style="color:{kdir_color}">{kronos_summary["direction"]}</div>
    <div class="tq-sub" style="color:{kdir_color}">next {kronos_summary["candles"]} candles</div>
  </div>
  <div class="tq-card">
    <div class="tq-lbl">Predicted Change</div>
    <div class="tq-val" style="color:{kdir_color}">{kronos_summary["pct_change"]:+.2f}%</div>
    <div class="tq-sub" style="color:#64748b">vs current close</div>
  </div>
  <div class="tq-card">
    <div class="tq-lbl">Peak / Trough</div>
    <div class="tq-val" style="font-size:0.9rem;color:#e2e8f0">{kronos_summary["peak"]:.5g}</div>
    <div class="tq-sub" style="color:#f87171">{kronos_summary["trough"]:.5g}</div>
  </div>
  <div class="tq-card">
    <div class="tq-lbl">Bull Candles</div>
    <div class="tq-val" style="color:{bull_color}">{kronos_summary["bull_pct"]:.0f}%</div>
    <div class="tq-sub" style="color:#64748b">of forecast candles</div>
  </div>
</div>
""", unsafe_allow_html=True)
else:
    st.warning("Kronos forecast unavailable for this symbol.")

# ─── 6. AI LAB ───────────────────────────────────────────────────────────────
sec("06 — AI Lab", "#c084fc")

VERDICT_CLASS = {"BUY": "verdict-buy", "SELL": "verdict-sell",
                 "HOLD": "verdict-hold", "WATCHLIST": "verdict-watchlist"}

def agent_card(cls, role, name, data):
    v = data["verdict"]
    vcls = VERDICT_CLASS.get(v, "verdict-hold")
    return f"""<div class="agent-card {cls}">
  <div class="agent-role">{role}</div>
  <div class="agent-name">{name}</div>
  <div class="agent-text">{data['text']}</div>
  <span class="agent-verdict {vcls}">{v}</span>
</div>"""

st.markdown(f"""
<div class="agent-grid">
  {agent_card("agent-bull", "🐂 Bull Case", "Alex — Long Desk",  debate['bull'])}
  {agent_card("agent-bear", "🐻 Bear Case", "Sam — Short Desk",  debate['bear'])}
  {agent_card("agent-risk", "🛡 Risk Manager", "Jordan — Risk",   debate['risk'])}
  {agent_card("agent-cio",  "👁 CIO Verdict",  "Morgan — CIO",    debate['cio'])}
</div>
""", unsafe_allow_html=True)

# ─── 6. DOWNLOAD ─────────────────────────────────────────────────────────────
sec("07 — Export", "#334155")

fname = f"{base}-{interval_lbl}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"

_, col_pdf, _ = st.columns([1, 2, 1])
with col_pdf:
    if HAS_FPDF:
        pdf_bytes = build_pdf(base, interval_lbl, sc, debate, now_str, kronos_summary=kronos_summary)
        st.download_button(
            label="⬇  Download Report (PDF)",
            data=pdf_bytes,
            file_name=f"{fname}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
    else:
        st.info("Install fpdf2 for PDF export.")

st.markdown(f"""
<div style="text-align:center;color:#475569;font-size:0.68rem;
            letter-spacing:0.1em;margin-top:3rem;text-transform:uppercase;">
  Data via Yahoo Finance &nbsp;·&nbsp; Not financial advice &nbsp;·&nbsp; {now_str}
</div>""", unsafe_allow_html=True)
