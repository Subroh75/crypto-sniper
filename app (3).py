"""
Crypto Sniper — Streamlit App
==============================
Multi-factor scoring engine (V, P, R, T) + optional Kronos AI forecast.

Run:
    streamlit run app.py

Install:
    pip install -r requirements.txt
"""

import warnings
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# Optional imports — app works without them (degraded features)
# ──────────────────────────────────────────────────────────────────────────────
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

try:
    from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
    HAS_KRONOS = True
except ImportError:
    HAS_KRONOS = False


# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG  (must be first Streamlit call)
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Crypto Sniper",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.2rem; }
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
        # Manual fallback calculations
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
        dsum = (pdi + mdi).replace(0, np.nan)
        dx   = 100 * (pdi - mdi).abs() / dsum
        df["adx14"]    = dx.ewm(span=14, adjust=False).mean()

        delta          = df["close"].diff()
        gain           = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
        loss           = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
        df["rsi14"]    = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))
        df["vol_ma20"] = df["volume"].rolling(20).mean()

    return df


# ══════════════════════════════════════════════════════════════════════════════
# SCORING  (V, P, R, T)
# ══════════════════════════════════════════════════════════════════════════════

def score_V(rv: float) -> int:
    """Volume score — relative volume vs 20-bar average."""
    if rv < 2:   return 0
    elif rv < 4: return 2
    elif rv < 8: return 3
    else:        return 5

def score_P(close_now: float, close_prev: float, atr_move: float) -> int:
    """Price momentum score — ATR-normalised move, only if bullish candle."""
    if close_now <= close_prev: return 0
    if atr_move < 1.5:          return 0
    elif atr_move < 2.5:        return 1
    elif atr_move < 4.0:        return 2
    else:                       return 3

def score_R(range_pos: float) -> int:
    """Range position score — where close sits in the candle range."""
    if range_pos < 0.70:   return 0
    elif range_pos < 0.85: return 1
    else:                  return 2

def score_T(close: float, ema20: float, ema50: float, adx14: float) -> int:
    """Trend alignment score — EMA stack + ADX strength."""
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
        "close":     round(float(row["close"]), 8),
        "ema20":     round(float(row["ema20"]), 8),
        "ema50":     round(float(row["ema50"]), 8),
        "atr14":     round(float(row["atr14"]), 8),
        "adx14":     round(float(row["adx14"]), 2),
        "rsi14":     round(float(row["rsi14"]), 2),
        "rv":        round(rv, 2),
        "atr_move":  round(atr_move, 2),
        "range_pos": round(range_pos, 3),
        "V": v, "P": p, "R": r, "T": t,
        "score": v + p + r + t,
        "timestamp": str(row["timestamp"])[:16],
    }


# ══════════════════════════════════════════════════════════════════════════════
# DATA FETCHING
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=60, show_spinner=False)
def fetch_ohlcv(symbol: str, interval: str, limit: int, exchange_id: str) -> Optional[pd.DataFrame]:
    if not HAS_CCXT:
        return None
    try:
        exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
        raw = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        df  = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.dropna().reset_index(drop=True)
    except Exception as e:
        st.warning(f"Could not fetch {symbol}: {e}")
        return None

@st.cache_data(ttl=120, show_spinner=False)
def get_top_usdt_pairs(n: int, exchange_id: str) -> list:
    if not HAS_CCXT:
        return []
    try:
        exchange = getattr(ccxt, exchange_id)({"enableRateLimit": True})
        tickers  = exchange.fetch_tickers()
        usdt     = {k: v for k, v in tickers.items()
                    if k.endswith("/USDT") and v.get("quoteVolume")}
        ranked   = sorted(usdt.items(), key=lambda x: x[1]["quoteVolume"] or 0, reverse=True)
        return [s for s, _ in ranked[:n]]
    except Exception as e:
        st.error(f"Could not fetch pairs: {e}")
        return []

def load_csv_file(uploaded) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(uploaded)
        df.columns = [c.lower().strip() for c in df.columns]
        for alias in ["date", "time", "datetime", "ts"]:
            if alias in df.columns and "timestamp" not in df.columns:
                df.rename(columns={alias: "timestamp"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        missing  = required - set(df.columns)
        if missing:
            st.error(f"CSV is missing columns: {missing}")
            return None
        return df.dropna(subset=["timestamp", "close"]).reset_index(drop=True)
    except Exception as e:
        st.error(f"CSV error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# KRONOS
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_resource(show_spinner=False)
def load_kronos_model(variant: str):
    if not HAS_KRONOS:
        return None
    try:
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model     = Kronos.from_pretrained(variant)
        return KronosPredictor(model, tokenizer, max_context=512)
    except Exception as e:
        st.error(f"Kronos load error: {e}")
        return None

def run_kronos_forecast(df: pd.DataFrame, pred_len: int, lookback: int, variant: str) -> Optional[pd.DataFrame]:
    predictor = load_kronos_model(variant)
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
            periods=pred_len,
            freq=delta,
        ))
        cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in ctx.columns]
        return predictor.predict(
            df=ctx[cols], x_timestamp=x_ts, y_timestamp=y_ts,
            pred_len=pred_len, T=1.0, top_p=0.9, sample_count=1,
        )
    except Exception as e:
        st.error(f"Kronos inference error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CHARTS
# ══════════════════════════════════════════════════════════════════════════════

def candlestick_chart(df: pd.DataFrame, symbol: str, forecast_df: Optional[pd.DataFrame] = None):
    if not HAS_PLOTLY:
        st.info("Install plotly for charts.")
        return
    show = df.tail(120).copy()
    fig  = go.Figure()
    fig.add_trace(go.Candlestick(
        x=show["timestamp"], open=show["open"], high=show["high"],
        low=show["low"], close=show["close"], name="Price",
        increasing_line_color="#22c55e", decreasing_line_color="#ef4444",
    ))
    fig.add_trace(go.Scatter(
        x=show["timestamp"], y=show["ema20"], mode="lines",
        line=dict(color="#f59e0b", width=1.5), name="EMA 20",
    ))
    fig.add_trace(go.Scatter(
        x=show["timestamp"], y=show["ema50"], mode="lines",
        line=dict(color="#818cf8", width=1.5), name="EMA 50",
    ))
    if forecast_df is not None and not forecast_df.empty:
        fig.add_trace(go.Scatter(
            x=list(forecast_df.index), y=forecast_df["close"],
            mode="lines+markers",
            line=dict(color="#06b6d4", width=2, dash="dot"),
            marker=dict(size=4), name="Kronos Forecast",
        ))
    fig.update_layout(
        title=f"{symbol}", xaxis_rangeslider_visible=False,
        template="plotly_dark", height=400,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

def volume_chart(df: pd.DataFrame):
    if not HAS_PLOTLY:
        return
    show   = df.tail(120).copy()
    colors = ["#22c55e" if c >= o else "#ef4444"
              for c, o in zip(show["close"], show["open"])]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=show["timestamp"], y=show["volume"],
        marker_color=colors, name="Volume",
    ))
    fig.add_trace(go.Scatter(
        x=show["timestamp"], y=show["vol_ma20"],
        mode="lines", line=dict(color="#f59e0b", width=1.5), name="Vol MA20",
    ))
    fig.update_layout(
        title="Volume", template="plotly_dark", height=180,
        margin=dict(l=10, r=10, t=30, b=10), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

def score_radar(scores: dict):
    if not HAS_PLOTLY:
        return
    categories = ["V (Volume)", "P (Momentum)", "R (Range)", "T (Trend)"]
    maxes      = [5, 3, 2, 3]
    vals       = [scores["V"], scores["P"], scores["R"], scores["T"]]
    pct        = [v / m for v, m in zip(vals, maxes)]
    fig = go.Figure(go.Scatterpolar(
        r=pct + [pct[0]], theta=categories + [categories[0]],
        fill="toself", fillcolor="rgba(99,102,241,0.25)",
        line=dict(color="#818cf8", width=2),
    ))
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 1], tickformat=".0%", color="#94a3b8")),
        template="plotly_dark", height=260,
        margin=dict(l=30, r=30, t=20, b=20), showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

def forecast_chart(forecast_df: pd.DataFrame, current_close: float):
    if not HAS_PLOTLY or forecast_df is None or forecast_df.empty:
        return
    fig = go.Figure()
    fig.add_hline(y=current_close, line_dash="dash", line_color="#94a3b8",
                  annotation_text="Current close")
    fig.add_trace(go.Scatter(
        x=list(forecast_df.index), y=forecast_df["close"],
        mode="lines+markers", line=dict(color="#06b6d4", width=2),
        fill="tozeroy", fillcolor="rgba(6,182,212,0.08)", name="Forecast close",
    ))
    fig.add_trace(go.Scatter(
        x=list(forecast_df.index), y=forecast_df["high"],
        mode="lines", line=dict(color="#22c55e", width=1, dash="dot"), name="High",
    ))
    fig.add_trace(go.Scatter(
        x=list(forecast_df.index), y=forecast_df["low"],
        mode="lines", line=dict(color="#ef4444", width=1, dash="dot"), name="Low",
        fill="tonexty", fillcolor="rgba(34,197,94,0.05)",
    ))
    fig.update_layout(
        title="Kronos — Forward Forecast", template="plotly_dark", height=280,
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.title("🎯 Crypto Sniper")
    st.caption(datetime.now(timezone.utc).strftime("Updated %H:%M UTC"))
    st.divider()

    mode = st.radio("Data source", ["Live (Exchange)", "Upload CSV"], horizontal=True)

    uploaded_csv = None
    if mode == "Upload CSV":
        uploaded_csv = st.file_uploader("Upload OHLCV CSV", type=["csv"])
        st.caption("Required columns: timestamp, open, high, low, close, volume")

    exchange_id   = "binance"
    interval      = "1h"
    limit         = 600
    source_mode   = "Auto top pairs"
    scan_top      = 20
    symbols_input = ""

    if mode == "Live (Exchange)":
        exchange_id = st.selectbox("Exchange", ["binance", "bybit", "okx", "kucoin"])
        interval    = st.selectbox("Interval", ["1m","5m","15m","30m","1h","4h","1d"], index=4)
        source_mode = st.radio("Symbols", ["Auto top pairs", "Custom list"], horizontal=True)
        if source_mode == "Auto top pairs":
            scan_top = st.slider("Top N pairs by volume", 5, 50, 20)
        else:
            symbols_input = st.text_area(
                "One symbol per line",
                value="BTC/USDT\nETH/USDT\nSOL/USDT\nBNB/USDT\nAVAX/USDT",
            )
        limit = st.slider("Candles to fetch", 100, 1000, 600, step=50)

    st.divider()
    st.subheader("Filters")
    min_score = st.slider("Min score", 0, 13, 0)
    top_n     = st.slider("Show top N", 1, 50, 20)

    st.divider()
    st.subheader("🔮 Kronos Forecast")
    kronos_help = "Requires Kronos: pip install git+https://github.com/shiyu-coder/Kronos.git"
    use_kronos  = st.toggle("Enable", value=False,
                             disabled=not HAS_KRONOS, help=kronos_help)
    if not HAS_KRONOS:
        st.caption("Kronos not installed.")

    kronos_model = "NeoQuasar/Kronos-small"
    pred_len     = 24
    lookback     = 400
    if use_kronos:
        kronos_model = st.selectbox("Model", [
            "NeoQuasar/Kronos-small",
            "NeoQuasar/Kronos-mini",
            "NeoQuasar/Kronos-base",
        ])
        pred_len = st.slider("Candles to forecast", 6, 120, 24)
        lookback = st.slider("Context candles",     100, 512, 400)

    st.divider()
    run_btn = st.button("▶  Run Scanner", type="primary", use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PAGE
# ══════════════════════════════════════════════════════════════════════════════

st.title("🎯 Crypto Sniper")

with st.expander("Score breakdown", expanded=False):
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown("**V — Volume** (max 5)")
        st.markdown("RV < 2 → **0**\n\n2–4 → **2**\n\n4–8 → **3**\n\n≥8 → **5**")
    with c2:
        st.markdown("**P — Momentum** (max 3)")
        st.markdown("Close ≤ prev → **0**\n\nATR move < 1.5 → **0**\n\n1.5–2.5 → **1**\n\n2.5–4 → **2**\n\n≥4 → **3**")
    with c3:
        st.markdown("**R — Range Position** (max 2)")
        st.markdown("< 0.70 → **0**\n\n0.70–0.85 → **1**\n\n≥ 0.85 → **2**")
    with c4:
        st.markdown("**T — Trend** (max 3)")
        st.markdown("+1 close > EMA20\n\n+1 EMA20 > EMA50\n\n+1 ADX ≥ 20")

if not run_btn:
    st.info("Configure settings in the sidebar and click **▶ Run Scanner**.")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# SCAN
# ══════════════════════════════════════════════════════════════════════════════

results    = []
symbol_dfs = {}

if mode == "Upload CSV":
    if uploaded_csv is None:
        st.error("Please upload a CSV file first.")
        st.stop()
    with st.spinner("Processing CSV…"):
        df_raw = load_csv_file(uploaded_csv)
        if df_raw is None:
            st.stop()
        df_ind = compute_indicators(df_raw)
        df_ind = df_ind.dropna(subset=["ema20","ema50","atr14","adx14"]).reset_index(drop=True)
        sc = compute_scores(df_ind)
        if sc:
            sc["symbol"] = uploaded_csv.name.replace(".csv", "")
            results.append(sc)
            symbol_dfs[sc["symbol"]] = df_ind

else:
    if not HAS_CCXT:
        st.error("ccxt is not installed. Run: `pip install ccxt`")
        st.stop()

    if source_mode == "Auto top pairs":
        with st.spinner(f"Fetching top {scan_top} USDT pairs…"):
            symbols = get_top_usdt_pairs(scan_top, exchange_id)
    else:
        raw = [s.strip() for s in symbols_input.strip().splitlines() if s.strip()]
        symbols = [s if "/" in s else s.upper() + "/USDT" for s in raw]

    if not symbols:
        st.error("No symbols found.")
        st.stop()

    prog = st.progress(0, text="Starting scan…")
    for i, sym in enumerate(symbols):
        prog.progress((i + 1) / len(symbols), text=f"Scanning {sym}…")
        df_raw = fetch_ohlcv(sym, interval, limit, exchange_id)
        if df_raw is None or len(df_raw) < 60:
            continue
        df_ind = compute_indicators(df_raw)
        df_ind = df_ind.dropna(subset=["ema20","ema50","atr14","adx14"]).reset_index(drop=True)
        sc = compute_scores(df_ind)
        if sc and sc["score"] >= min_score:
            sc["symbol"] = sym
            results.append(sc)
            symbol_dfs[sym] = df_ind
    prog.empty()

# Sort & trim
results.sort(key=lambda x: x["score"], reverse=True)
results = results[:top_n]

if not results:
    st.warning("No symbols matched. Try lowering the minimum score filter.")
    st.stop()


# ══════════════════════════════════════════════════════════════════════════════
# RESULTS TABLE
# ══════════════════════════════════════════════════════════════════════════════

st.subheader(f"Results — {len(results)} symbol{'s' if len(results) != 1 else ''}")

table_data = [{
    "Symbol":   r["symbol"],
    "Close":    r["close"],
    "RV":       r["rv"],
    "ATR Move": r["atr_move"],
    "ADX":      r["adx14"],
    "RSI":      r["rsi14"],
    "V":        r["V"],
    "P":        r["P"],
    "R":        r["R"],
    "T":        r["T"],
    "Score":    r["score"],
} for r in results]

df_table = pd.DataFrame(table_data)

def highlight_score(val):
    if val >= 9:   return "background-color:#14532d; color:#86efac; font-weight:700"
    elif val >= 5: return "background-color:#713f12; color:#fde68a; font-weight:700"
    else:          return "color:#6b7280"

# pandas 3.x uses .map() — not the old deprecated method
styled = df_table.style.map(highlight_score, subset=["Score"])

st.dataframe(
    styled,
    use_container_width=True,
    hide_index=True,
    height=min(55 + len(df_table) * 36, 600),
)


# ══════════════════════════════════════════════════════════════════════════════
# DETAIL VIEW
# ══════════════════════════════════════════════════════════════════════════════

st.divider()
st.subheader("Detail View")

selected   = st.selectbox("Select symbol", [r["symbol"] for r in results])
sel_scores = next(r for r in results if r["symbol"] == selected)
sel_df     = symbol_dfs.get(selected)
forecast_df = None

if use_kronos and sel_df is not None:
    with st.spinner(f"Running Kronos forecast for {selected}…"):
        forecast_df = run_kronos_forecast(sel_df, pred_len, lookback, kronos_model)

# Score metrics
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Score",        f"{sel_scores['score']} / 13")
m2.metric("V  Volume",    sel_scores["V"],  help="max 5")
m3.metric("P  Momentum",  sel_scores["P"],  help="max 3")
m4.metric("R  Range",     sel_scores["R"],  help="max 2")
m5.metric("T  Trend",     sel_scores["T"],  help="max 3")

# Indicator metrics
i1, i2, i3, i4, i5 = st.columns(5)
i1.metric("Close",        f"{sel_scores['close']:.6g}")
i2.metric("Rel. Volume",  f"{sel_scores['rv']:.2f}×")
i3.metric("ATR Move",     f"{sel_scores['atr_move']:.2f}")
i4.metric("ADX 14",       f"{sel_scores['adx14']:.1f}")
i5.metric("RSI 14",       f"{sel_scores['rsi14']:.1f}")

# Charts
if sel_df is not None:
    left, right = st.columns([3, 1])
    with left:
        candlestick_chart(sel_df, selected, forecast_df)
        volume_chart(sel_df)
    with right:
        st.markdown("**Signal Radar**")
        score_radar(sel_scores)
        score = sel_scores["score"]
        if score >= 9:
            st.success("🔥 Strong signal")
        elif score >= 5:
            st.warning("⚡ Moderate signal")
        else:
            st.info("Weak / no signal")
        st.markdown(f"""
| | |
|---|---|
| EMA 20 | `{sel_scores['ema20']:.6g}` |
| EMA 50 | `{sel_scores['ema50']:.6g}` |
| ATR 14 | `{sel_scores['atr14']:.6g}` |
| Range pos | `{sel_scores['range_pos']:.3f}` |
| Last bar | `{sel_scores['timestamp']}` |
""")

# Kronos panel
if use_kronos:
    st.divider()
    st.subheader("🔮 Kronos AI Forecast")
    if forecast_df is not None and not forecast_df.empty:
        fc_close = float(forecast_df["close"].iloc[-1])
        fc_pct   = (fc_close - sel_scores["close"]) / sel_scores["close"] * 100
        bull_pct = float((forecast_df["close"] > forecast_df["open"]).mean() * 100)

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Forecast Close",  f"{fc_close:.6g}")
        k2.metric("Expected Change", f"{fc_pct:+.2f}%", delta=f"{fc_pct:+.2f}%")
        k3.metric("High Target",     f"{float(forecast_df['high'].max()):.6g}")
        k4.metric("Bullish Candles", f"{bull_pct:.0f}%")
        forecast_chart(forecast_df, sel_scores["close"])
    else:
        st.warning("Kronos forecast unavailable for this symbol.")
