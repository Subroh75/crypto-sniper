crypto Sniper — Streamlit App
==============================
Multi-factor scoring engine (V, P, R, T) + optional Kronos AI forecast.

Run:
    streamlit run app.py

Install:
    pip install streamlit ccxt pandas numpy pandas-ta plotly torch huggingface_hub
    pip install git+https://github.com/shiyu-coder/Kronos.git   # optional
"""

import warnings
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# Optional imports
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
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

try:
    import torch
    from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
    HAS_KRONOS = True
except ImportError:
    HAS_KRONOS = False


# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(
    page_title="Crypto Sniper",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .score-pill {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 999px;
        font-weight: 700;
        font-size: 1rem;
    }
    .score-high  { background:#16a34a; color:#fff; }
    .score-med   { background:#ca8a04; color:#fff; }
    .score-low   { background:#374151; color:#9ca3af; }
    .metric-card {
        background: #1e293b;
        border-radius: 10px;
        padding: 14px 18px;
        text-align: center;
    }
    .metric-label { font-size:0.78rem; color:#94a3b8; margin-bottom:4px; }
    .metric-value { font-size:1.4rem; font-weight:700; color:#f1f5f9; }
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
        pdm  = pd.Series(np.where((up > down) & (up > 0), up, 0.0))
        mdm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0))
        pdi  = 100 * pdm.ewm(span=14, adjust=False).mean() / df["atr14"]
        mdi  = 100 * mdm.ewm(span=14, adjust=False).mean() / df["atr14"]
        dx   = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
        df["adx14"]    = dx.ewm(span=14, adjust=False).mean()

        delta = df["close"].diff()
        gain  = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
        loss  = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
        df["rsi14"]    = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

        df["vol_ma20"] = df["volume"].rolling(20).mean()

    return df


# ══════════════════════════════════════════════════════════════════════════════
# SCORING
# ══════════════════════════════════════════════════════════════════════════════

def score_V(rv: float) -> int:
    if rv < 2:   return 0
    elif rv < 4: return 2
    elif rv < 8: return 3
    else:        return 5

def score_P(close_now: float, close_prev: float, atr_move: float) -> int:
    if close_now <= close_prev: return 0
    if atr_move < 1.5:          return 0
    elif atr_move < 2.5:        return 1
    elif atr_move < 4.0:        return 2
    else:                       return 3

def score_R(range_pos: float) -> int:
    if range_pos < 0.70:   return 0
    elif range_pos < 0.85: return 1
    else:                  return 2

def score_T(close: float, ema20: float, ema50: float, adx14: float) -> int:
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

    rv        = row["volume"] / row["vol_ma20"] if row["vol_ma20"] > 0 else 0.0
    atr_move  = (row["close"] - prev["close"]) / row["atr14"] if row["atr14"] > 0 else 0.0
    hl        = row["high"] - row["low"]
    range_pos = (row["close"] - row["low"]) / hl if hl > 0 else 0.5

    v = score_V(rv)
    p = score_P(row["close"], prev["close"], atr_move)
    r = score_R(range_pos)
    t = score_T(row["close"], row["ema20"], row["ema50"], row["adx14"])

    return {
        "close": row["close"],
        "ema20": row["ema20"],
        "ema50": row["ema50"],
        "atr14": row["atr14"],
        "adx14": row["adx14"],
        "rsi14": row["rsi14"],
        "rv":        round(rv, 2),
        "atr_move":  round(atr_move, 2),
        "range_pos": round(range_pos, 3),
        "V": v, "P": p, "R": r, "T": t,
        "score": v + p + r + t,
        "timestamp": row["timestamp"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# DATA
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
        return df.dropna()
    except Exception as e:
        st.error(f"Fetch error for {symbol}: {e}")
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

def load_csv(uploaded) -> Optional[pd.DataFrame]:
    try:
        df = pd.read_csv(uploaded)
        df.columns = [c.lower().strip() for c in df.columns]
        for alias in ["date", "time", "datetime", "ts"]:
            if alias in df.columns and "timestamp" not in df.columns:
                df.rename(columns={alias: "timestamp"}, inplace=True)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
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

def run_kronos(df: pd.DataFrame, pred_len: int, lookback: int, variant: str) -> Optional[pd.DataFrame]:
    predictor = load_kronos_model(variant)
    if predictor is None:
        return None

    df       = df.sort_values("timestamp").reset_index(drop=True)
    lookback = min(lookback, len(df), 512)
    ctx      = df.tail(lookback).reset_index(drop=True)
    x_ts     = ctx["timestamp"]

    delta    = ctx["timestamp"].iloc[-1] - ctx["timestamp"].iloc[-2]
    y_ts     = pd.Series(pd.date_range(
        start=ctx["timestamp"].iloc[-1] + delta, periods=pred_len, freq=delta
    ))

    cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in ctx.columns]
    try:
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
        st.info("Install plotly for charts: pip install plotly")
        return

    show = df.tail(120).copy()
    fig  = go.Figure()

    # Candles
    fig.add_trace(go.Candlestick(
        x=show["timestamp"
