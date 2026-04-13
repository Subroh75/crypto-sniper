"""
Crypto Sniper
Single-page, no sidebar. User types a coin, gets a signal instantly.
Run: streamlit run app.py
"""

import warnings
import io
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

# ── optional imports ──────────────────────────────────────────────────────────
try:
    import ccxt
    HAS_CCXT = True
except ImportError:
    HAS_CCXT = False

try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False

try:
    import plotly.graph_objects as go
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Crypto Sniper",
    page_icon="🎯",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  /* Hide sidebar toggle and Streamlit branding */
  [data-testid="collapsedControl"]  { display: none !important; }
  #MainMenu, footer, header         { visibility: hidden; }
  section[data-testid="stSidebar"]  { display: none !important; }

  /* Page background */
  .stApp { background: #0a0e1a; }
  .block-container { padding-top: 2rem; max-width: 860px; }

  /* Title */
  .sniper-title {
    font-size: 2.4rem;
    font-weight: 800;
    letter-spacing: -1px;
    background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    text-align: center;
    margin-bottom: 0.2rem;
  }
  .sniper-sub {
    text-align: center;
    color: #475569;
    font-size: 0.9rem;
    margin-bottom: 2rem;
    letter-spacing: 0.05em;
  }

  /* Signal banner */
  .signal-strong {
    background: linear-gradient(135deg, #052e16, #14532d);
    border: 1px solid #16a34a;
    border-radius: 16px;
    padding: 1.6rem 2rem;
    text-align: center;
  }
  .signal-moderate {
    background: linear-gradient(135deg, #1c1002, #431407);
    border: 1px solid #d97706;
    border-radius: 16px;
    padding: 1.6rem 2rem;
    text-align: center;
  }
  .signal-weak {
    background: linear-gradient(135deg, #0f172a, #1e293b);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 1.6rem 2rem;
    text-align: center;
  }
  .signal-label {
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    opacity: 0.7;
    margin-bottom: 0.3rem;
  }
  .signal-text-strong   { color: #4ade80; font-size: 2rem; font-weight: 800; }
  .signal-text-moderate { color: #fbbf24; font-size: 2rem; font-weight: 800; }
  .signal-text-weak     { color: #64748b; font-size: 2rem; font-weight: 800; }
  .signal-score-strong   { color: #86efac; font-size: 1rem; margin-top: 0.3rem; }
  .signal-score-moderate { color: #fde68a; font-size: 1rem; margin-top: 0.3rem; }
  .signal-score-weak     { color: #475569; font-size: 1rem; margin-top: 0.3rem; }

  /* Metric card */
  .metric-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    margin: 1.2rem 0;
  }
  .mcard {
    background: #111827;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 14px 16px;
    text-align: center;
  }
  .mcard-label { font-size: 0.7rem; color: #64748b; font-weight: 600;
                 letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 4px; }
  .mcard-value { font-size: 1.25rem; font-weight: 700; color: #e2e8f0; }
  .mcard-sub   { font-size: 0.72rem; color: #475569; margin-top: 2px; }

  /* Score breakdown bar */
  .score-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 6px 0;
  }
  .score-label { font-size: 0.78rem; color: #94a3b8; width: 120px; }
  .score-bar-bg {
    flex: 1;
    background: #1e293b;
    border-radius: 999px;
    height: 8px;
    overflow: hidden;
  }
  .score-bar-fill {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, #00d4ff, #7c3aed);
    transition: width 0.4s ease;
  }
  .score-val { font-size: 0.78rem; color: #e2e8f0; font-weight: 700; width: 30px; text-align: right; }

  /* Section header */
  .section-hdr {
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: #475569;
    margin: 1.6rem 0 0.8rem;
    border-bottom: 1px solid #1e293b;
    padding-bottom: 6px;
  }

  /* Divider */
  hr { border-color: #1e293b !important; }

  /* Input field override */
  .stTextInput > div > div > input {
    background: #111827 !important;
    border: 1px solid #1e293b !important;
    color: #e2e8f0 !important;
    border-radius: 10px !important;
    font-size: 1.1rem !important;
    text-align: center;
  }
  .stTextInput > div > div > input:focus {
    border-color: #7c3aed !important;
    box-shadow: 0 0 0 2px rgba(124,58,237,0.3) !important;
  }

  /* Button */
  .stButton > button {
    width: 100%;
    background: linear-gradient(135deg, #00d4ff 0%, #7c3aed 100%) !important;
    color: #fff !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    font-size: 1rem !important;
    padding: 0.6rem 1rem !important;
    letter-spacing: 0.05em;
  }

  /* Interval pills */
  .stRadio > div { gap: 8px; justify-content: center; }
  .stRadio label { font-size: 0.85rem; }

  /* Download button */
  .stDownloadButton > button {
    background: #111827 !important;
    border: 1px solid #1e293b !important;
    color: #94a3b8 !important;
    border-radius: 8px !important;
    font-size: 0.8rem !important;
    width: 100%;
  }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# INDICATORS
# ══════════════════════════════════════════════════════════════════════════════

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_values("timestamp").reset_index(drop=True)
    if HAS_TA:
        df["ema20"]    = ta.ema(df["close"], length=20)
        df["ema50"]    = ta.ema(df["close"], length=50)
        df["atr14"]    = ta.atr(df["high"], df["low"], df["close"], length=14)
        adx_df         = ta.adx(df["high"], df["low"], df["close"], length=14)
        df["adx14"]    = adx_df["ADX_14"] if adx_df is not None else np.nan
        df["rsi14"]    = ta.rsi(df["close"], length=14)
        df["vol_ma20"] = ta.sma(df["volume"], length=20)
    else:
        df["ema20"]    = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"]    = df["close"].ewm(span=50, adjust=False).mean()
        hl = df["high"] - df["low"]
        hc = (df["high"] - df["close"].shift(1)).abs()
        lc = (df["low"]  - df["close"].shift(1)).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        df["atr14"]    = tr.ewm(span=14, adjust=False).mean()
        up   = df["high"].diff()
        down = -df["low"].diff()
        pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
        mdm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
        atr  = df["atr14"].replace(0, np.nan)
        pdi  = 100 * pdm.ewm(span=14, adjust=False).mean() / atr
        mdi  = 100 * mdm.ewm(span=14, adjust=False).mean() / atr
        dx   = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
        df["adx14"]    = dx.ewm(span=14, adjust=False).mean()
        delta          = df["close"].diff()
        gain           = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
        loss           = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
        df["rsi14"]    = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
        df["vol_ma20"] = df["volume"].rolling(20).mean()
    return df


# ══════════════════════════════════════════════════════════════════════════════
# SCORING
# ══════════════════════════════════════════════════════════════════════════════

def score_V(rv):
    if rv < 2:   return 0
    elif rv < 4: return 2
    elif rv < 8: return 3
    else:        return 5

def score_P(close_now, close_prev, atr_move):
    if close_now <= close_prev: return 0
    if atr_move < 1.5:          return 0
    elif atr_move < 2.5:        return 1
    elif atr_move < 4.0:        return 2
    else:                       return 3

def score_R(range_pos):
    if range_pos < 0.70:   return 0
    elif range_pos < 0.85: return 1
    else:                  return 2

def score_T(close, ema20, ema50, adx14):
    t = 0
    if close > ema20:  t += 1
    if ema20  > ema50: t += 1
    if adx14  >= 20:   t += 1
    return t

def compute_scores(df: pd.DataFrame) -> Optional[dict]:
    if len(df) < 2:
        return None
    row  = df.iloc[-1]
    prev = df.iloc[-2]
    rv        = float(row["volume"]) / float(row["vol_ma20"]) if float(row["vol_ma20"]) > 0 else 0.0
    atr_move  = (float(row["close"]) - float(prev["close"])) / float(row["atr14"]) if float(row["atr14"]) > 0 else 0.0
    hl        = float(row["high"]) - float(row["low"])
    range_pos = (float(row["close"]) - float(row["low"])) / hl if hl > 0 else 0.5
    v = score_V(rv)
    p = score_P(float(row["close"]), float(prev["close"]), atr_move)
    r = score_R(range_pos)
    t = score_T(float(row["close"]), float(row["ema20"]), float(row["ema50"]), float(row["adx14"]))
    return {
        "close":     float(row["close"]),
        "high":      float(row["high"]),
        "low":       float(row["low"]),
        "open":      float(row["open"]),
        "volume":    float(row["volume"]),
        "ema20":     float(row["ema20"]),
        "ema50":     float(row["ema50"]),
        "atr14":     float(row["atr14"]),
        "adx14":     float(row["adx14"]),
        "rsi14":     float(row["rsi14"]),
        "rv":        round(rv, 2),
        "atr_move":  round(atr_move, 2),
        "range_pos": round(range_pos, 3),
        "V": v, "P": p, "R": r, "T": t,
        "score": v + p + r + t,
        "timestamp": str(row["timestamp"])[:16],
    }


# ══════════════════════════════════════════════════════════════════════════════
# DATA
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60, show_spinner=False)
def fetch_ohlcv(symbol: str, interval: str, limit: int = 500) -> Optional[pd.DataFrame]:
    if not HAS_CCXT:
        return None
    try:
        exchange = ccxt.binance({"enableRateLimit": True})
        raw = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        df  = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.dropna().reset_index(drop=True)
    except Exception:
        # Try without /USDT suffix formatting issues
        return None

def normalise_symbol(raw: str) -> str:
    raw = raw.strip().upper().replace(" ", "")
    if "/" not in raw:
        # e.g. "BTC" → "BTC/USDT", "BTCUSDT" → "BTC/USDT"
        if raw.endswith("USDT"):
            base = raw[:-4]
            return f"{base}/USDT"
        elif raw.endswith("BTC"):
            base = raw[:-3]
            return f"{base}/BTC"
        else:
            return f"{raw}/USDT"
    return raw


# ══════════════════════════════════════════════════════════════════════════════
# CHART
# ══════════════════════════════════════════════════════════════════════════════

def make_chart(df: pd.DataFrame, symbol: str) -> Optional[object]:
    if not HAS_PLOTLY:
        return None
    show = df.tail(100).copy()
    fig  = go.Figure()
    fig.add_trace(go.Candlestick(
        x=show["timestamp"],
        open=show["open"], high=show["high"],
        low=show["low"],   close=show["close"],
        name="Price",
        increasing=dict(line=dict(color="#22c55e"), fillcolor="#16a34a"),
        decreasing=dict(line=dict(color="#ef4444"), fillcolor="#dc2626"),
    ))
    fig.add_trace(go.Scatter(
        x=show["timestamp"], y=show["ema20"],
        mode="lines", line=dict(color="#f59e0b", width=1.5), name="EMA 20",
    ))
    fig.add_trace(go.Scatter(
        x=show["timestamp"], y=show["ema50"],
        mode="lines", line=dict(color="#818cf8", width=1.5), name="EMA 50",
    ))
    fig.update_layout(
        paper_bgcolor="#0a0e1a",
        plot_bgcolor="#0a0e1a",
        font=dict(color="#94a3b8", family="Inter, sans-serif"),
        xaxis=dict(showgrid=False, color="#334155", rangeslider_visible=False),
        yaxis=dict(showgrid=True, gridcolor="#1e293b", color="#334155"),
        margin=dict(l=10, r=10, t=10, b=10),
        height=320,
        legend=dict(orientation="h", yanchor="bottom", y=1.01,
                    xanchor="right", x=1, font=dict(size=11)),
        hovermode="x unified",
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# CSV DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════

def build_csv(symbol: str, interval: str, scores: dict, df: pd.DataFrame) -> bytes:
    out = df.tail(100).copy()
    out["ema20"]     = out["ema20"].round(8)
    out["ema50"]     = out["ema50"].round(8)
    out["atr14"]     = out["atr14"].round(8)
    out["adx14"]     = out["adx14"].round(2)
    out["rsi14"]     = out["rsi14"].round(2)
    out["vol_ma20"]  = out["vol_ma20"].round(2)

    summary_rows = [
        ["=== CRYPTO SNIPER REPORT ==="],
        [f"Symbol:    {symbol}"],
        [f"Interval:  {interval}"],
        [f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"],
        [f"Last bar:  {scores['timestamp']}"],
        [],
        ["=== SIGNAL ==="],
        [f"Score:     {scores['score']} / 13"],
        [f"Signal:    {'STRONG BUY' if scores['score'] >= 9 else 'MODERATE' if scores['score'] >= 5 else 'WEAK / NO SIGNAL'}"],
        [f"V (Volume):    {scores['V']} / 5  (RV={scores['rv']}x)"],
        [f"P (Momentum):  {scores['P']} / 3  (ATR move={scores['atr_move']})"],
        [f"R (Range):     {scores['R']} / 2  (range_pos={scores['range_pos']})"],
        [f"T (Trend):     {scores['T']} / 3"],
        [],
        ["=== INDICATORS ==="],
        [f"Close:   {scores['close']}"],
        [f"EMA 20:  {scores['ema20']:.6g}"],
        [f"EMA 50:  {scores['ema50']:.6g}"],
        [f"ATR 14:  {scores['atr14']:.6g}"],
        [f"ADX 14:  {scores['adx14']:.2f}"],
        [f"RSI 14:  {scores['rsi14']:.2f}"],
        [],
        ["=== OHLCV (last 100 candles) ==="],
    ]
    buf = io.StringIO()
    for row in summary_rows:
        buf.write(",".join(str(c) for c in row) + "\n")
    out.to_csv(buf, index=False)
    return buf.getvalue().encode()


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="sniper-title">CRYPTO SNIPER</div>', unsafe_allow_html=True)
st.markdown('<div class="sniper-sub">REAL-TIME SIGNAL INTELLIGENCE</div>', unsafe_allow_html=True)

# ── Input row ────────────────────────────────────────────────────────────────
col_in, col_btn = st.columns([3, 1])
with col_in:
    coin_input = st.text_input(
        label="coin",
        placeholder="BTC, ETH, SOL, DOGE …",
        label_visibility="collapsed",
    )
with col_btn:
    analyse_btn = st.button("ANALYSE", use_container_width=True)

# Interval selector
interval_map = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
                "1H": "1h", "4H": "4h", "1D": "1d"}
interval_choice = st.radio(
    "interval", list(interval_map.keys()),
    index=4, horizontal=True, label_visibility="collapsed"
)
interval = interval_map[interval_choice]

if not HAS_CCXT:
    st.error("ccxt not installed. Add `ccxt` to requirements.txt")
    st.stop()

if not analyse_btn and not coin_input:
    st.markdown("""
<div style="text-align:center; color:#1e293b; font-size:0.85rem; margin-top:3rem;">
  Enter a coin symbol above and click ANALYSE
</div>
""", unsafe_allow_html=True)
    st.stop()

if not coin_input:
    st.warning("Enter a coin symbol to analyse.")
    st.stop()

# ── Fetch & score ─────────────────────────────────────────────────────────────
symbol = normalise_symbol(coin_input)

with st.spinner(f"Fetching {symbol} …"):
    df_raw = fetch_ohlcv(symbol, interval)

if df_raw is None or len(df_raw) < 60:
    st.error(f"Could not fetch data for **{symbol}**. Check the symbol and try again.")
    st.stop()

df = compute_indicators(df_raw)
df = df.dropna(subset=["ema20", "ema50", "atr14", "adx14"]).reset_index(drop=True)

if len(df) < 2:
    st.error("Not enough data to compute indicators.")
    st.stop()

scores = compute_scores(df)
if scores is None:
    st.error("Scoring failed — not enough candle data.")
    st.stop()

score  = scores["score"]
now_ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL BANNER
# ══════════════════════════════════════════════════════════════════════════════

if score >= 9:
    cls  = "signal-strong"
    tcls = "signal-text-strong"
    scls = "signal-score-strong"
    label = "STRONG BUY"
elif score >= 5:
    cls  = "signal-moderate"
    tcls = "signal-text-moderate"
    scls = "signal-score-moderate"
    label = "MODERATE"
else:
    cls  = "signal-weak"
    tcls = "signal-text-weak"
    scls = "signal-score-weak"
    label = "NO SIGNAL"

pct_change = (scores["close"] - scores["open"]) / scores["open"] * 100 if scores["open"] > 0 else 0
pct_color  = "#4ade80" if pct_change >= 0 else "#f87171"
pct_sign   = "+" if pct_change >= 0 else ""

st.markdown(f"""
<div class="{cls}" style="margin: 1.2rem 0;">
  <div class="signal-label">{symbol} · {interval_choice} · {now_ts}</div>
  <div class="{tcls}">{label}</div>
  <div class="{scls}">Score {score} / 13 &nbsp;·&nbsp;
    <span style="color:{pct_color}">{pct_sign}{pct_change:.2f}%</span>
    &nbsp;·&nbsp; Close {scores['close']:.6g}
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# METRIC CARDS
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-hdr">Indicators</div>', unsafe_allow_html=True)

st.markdown(f"""
<div class="metric-grid">
  <div class="mcard">
    <div class="mcard-label">EMA 20</div>
    <div class="mcard-value">{scores['ema20']:.6g}</div>
    <div class="mcard-sub">{'↑ above' if scores['close'] > scores['ema20'] else '↓ below'}</div>
  </div>
  <div class="mcard">
    <div class="mcard-label">EMA 50</div>
    <div class="mcard-value">{scores['ema50']:.6g}</div>
    <div class="mcard-sub">{'↑ above' if scores['ema20'] > scores['ema50'] else '↓ below'}</div>
  </div>
  <div class="mcard">
    <div class="mcard-label">ADX 14</div>
    <div class="mcard-value">{scores['adx14']:.1f}</div>
    <div class="mcard-sub">{'Trending' if scores['adx14'] >= 20 else 'Ranging'}</div>
  </div>
  <div class="mcard">
    <div class="mcard-label">RSI 14</div>
    <div class="mcard-value">{scores['rsi14']:.1f}</div>
    <div class="mcard-sub">{'Overbought' if scores['rsi14'] >= 70 else 'Oversold' if scores['rsi14'] <= 30 else 'Neutral'}</div>
  </div>
  <div class="mcard">
    <div class="mcard-label">ATR 14</div>
    <div class="mcard-value">{scores['atr14']:.4g}</div>
    <div class="mcard-sub">Volatility</div>
  </div>
  <div class="mcard">
    <div class="mcard-label">Rel. Volume</div>
    <div class="mcard-value">{scores['rv']:.2f}×</div>
    <div class="mcard-sub">vs 20-bar avg</div>
  </div>
  <div class="mcard">
    <div class="mcard-label">ATR Move</div>
    <div class="mcard-value">{scores['atr_move']:.2f}</div>
    <div class="mcard-sub">σ from prev</div>
  </div>
  <div class="mcard">
    <div class="mcard-label">Range Pos</div>
    <div class="mcard-value">{scores['range_pos']:.3f}</div>
    <div class="mcard-sub">0=low · 1=high</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SCORE BREAKDOWN
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-hdr">Score Breakdown</div>', unsafe_allow_html=True)

def bar(label, val, maxval, hint):
    pct = int(val / maxval * 100)
    return f"""
<div class="score-row">
  <div class="score-label">{label}</div>
  <div class="score-bar-bg">
    <div class="score-bar-fill" style="width:{pct}%"></div>
  </div>
  <div class="score-val">{val}/{maxval}</div>
  <div style="font-size:0.7rem;color:#475569;min-width:160px">{hint}</div>
</div>"""

st.markdown(
    bar("V  Volume",    scores["V"], 5, f"RV = {scores['rv']}×") +
    bar("P  Momentum",  scores["P"], 3, f"ATR move = {scores['atr_move']}") +
    bar("R  Range Pos", scores["R"], 2, f"range_pos = {scores['range_pos']}") +
    bar("T  Trend",     scores["T"], 3, f"ADX {scores['adx14']:.1f} · EMA stack"),
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════════════════════
# CHART
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-hdr">Price Chart · Last 100 Candles</div>', unsafe_allow_html=True)

fig = make_chart(df, symbol)
if fig:
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
else:
    st.info("Install plotly for charts: pip install plotly")

# ══════════════════════════════════════════════════════════════════════════════
# DOWNLOAD
# ══════════════════════════════════════════════════════════════════════════════

st.markdown('<div class="section-hdr">Export</div>', unsafe_allow_html=True)

csv_bytes = build_csv(symbol, interval, scores, df)
fname     = f"{symbol.replace('/', '')}-{interval}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.csv"

st.download_button(
    label="⬇  Download Report (CSV)",
    data=csv_bytes,
    file_name=fname,
    mime="text/csv",
    use_container_width=True,
)

st.markdown(f"""
<div style="text-align:center;color:#1e293b;font-size:0.7rem;margin-top:2rem;">
  Data via Binance · Signals are not financial advice · {now_ts}
</div>
""", unsafe_allow_html=True)
