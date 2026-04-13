


All tasks
Crypto Sniper App Logic in Python

app
,
+1
1 min ago
Crypto Sniper App Logic in Python
I am building a crypto sniper app with the below logic V =
0 if RV < 2
2 if 2 <= RV < 4
3 if 4 <= RV < 8
5 if RV >= 8

P =
0 if close_now <= close_prev
0 if ATR_move < 1.5
1 if 1.5 <= ATR_move < 2.5
2 if 2.5 <= ATR_move < 4
3 if ATR_move >= 4

R =
0 if range_pos < 0.70
1 if 0.70 <= range_pos < 0.85
2 if range_pos >= 0.85

T =
1 if close_now > EMA20
+1 if EMA20 > EMA50
+1 if ADX14 >= 20
and also looking to implement this https://github.com/shiyu-coder/Kronos to this app. design this app in python and give me entire code as app.py

Let me fetch the Kronos repository directly to understand its structure and API.


Fetch Kronos repo
Claude Sonnet 4.6
Here is the complete extraction of the Kronos repository:

1. Repository File Structure (Complete)
text
Kronos/
├── .gitignore
├── LICENSE
├── README.md
├── requirements.txt
├── model/                         ⭐ Core library
│   ├── __init__.py                Exports: KronosTokenizer, Kronos, KronosPredictor
│   ├── kronos.py                  Main classes + inference logic (662 lines)
│   └── module.py                  Building blocks (570 lines)
├── examples/
│   ├── prediction_example.py
│   ├── prediction_batch_example.py
│   ├── prediction_wo_vol_example.py
│   ├── prediction_akshare_2024-2025.py
│   ├── prediction_cn_markets_day.py
│   ├── prediction_new.py / prediction_new_GUI.py
│   ├── run_backtest_kronos.py
│   └── yuce/ (JSON/PNG outputs + historical_backtest.py)
├── finetune/                      Qlib-based finetuning pipeline
│   ├── config.py
│   ├── dataset.py
│   ├── qlib_data_preprocess.py
│   ├── qlib_test.py (backtest)
│   ├── train_predictor.py
│   ├── train_tokenizer.py
│   └── utils/
├── finetune_csv/                  CSV-based finetuning alternative
│   ├── config_loader.py, configs/*.yaml
│   ├── finetune_base_model.py
│   ├── finetune_tokenizer.py
│   └── train_sequential.py
├── tests/
│   ├── test_kronos_regression.py
│   └── data/ (regression_input.csv, outputs)
└── webui/
    ├── app.py, run.py, start.sh
    └── templates/index.html
2. Three Key Classes in model/kronos.py
KronosTokenizer (nn.Module + PyTorchModelHubMixin)
Encoder-Decoder Transformer with Binary Spherical Quantization (BSQ) that converts OHLCV data into hierarchical discrete tokens.

.from_pretrained("NeoQuasar/Kronos-Tokenizer-base") — loads from HuggingFace

.encode(x, half=True) → returns (s1_indices, s2_indices) tuple

.decode(indices, half=True) → reconstructs OHLCV values

Kronos (the autoregressive LLM-style model)
Stacked Transformer with HierarchicalEmbedding + TemporalEmbedding + DualHead.

.from_pretrained("NeoQuasar/Kronos-small") / Kronos-mini / Kronos-base

.decode_s1(s1_ids, s2_ids, stamp) → (s1_logits, context) — predicts coarse tokens

.decode_s2(context, s1_ids) → s2_logits — predicts fine tokens conditioned on s1

KronosPredictor (high-level API)
python
predictor = KronosPredictor(model, tokenizer, max_context=512)
3. How to Use Programmatically
python
import pandas as pd
from model import Kronos, KronosTokenizer, KronosPredictor

# Load from HuggingFace
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")

# KronosPredictor auto-detects CUDA → MPS → CPU
predictor = KronosPredictor(model, tokenizer, max_context=512)

# Prepare your OHLCV DataFrame (volume/amount optional)
df = pd.read_csv("data.csv")
df['timestamps'] = pd.to_datetime(df['timestamps'])

lookback, pred_len = 400, 120  # lookback must be ≤ 512

pred_df = predictor.predict(
    df=df.loc[:lookback-1, ['open','high','low','close','volume','amount']],
    x_timestamp=df.loc[:lookback-1, 'timestamps'],
    y_timestamp=df.loc[lookback:lookback+pred_len-1, 'timestamps'],
    pred_len=pred_len,
    T=1.0,       # temperature
    top_p=0.9,   # nucleus sampling
    sample_count=1
)
# pred_df has columns: open, high, low, close, volume, amount, indexed by y_timestamp
For batch prediction (all series must have equal lookback & pred_len):

python
pred_dfs = predictor.predict_batch(df_list, x_ts_list, y_ts_list, pred_len=120)
4. Architecture Key Points
Component	Detail
Tokenizer	BSQ quantizes OHLCV into s1 (coarse) + s2 (fine) binary tokens
Model	Decoder-only Transformer, max context 512 tokens
Inference	Autoregressive generation with sliding buffer; two-stage: predict s1 → condition to predict s2
Temporal features	minute, hour, weekday, day, month embedded via TemporalEmbedding
Normalization	Per-series Z-score normalization (μ, σ per column), clipped to ±5
Attention	Causal self-attention with RoPE, SwiGLU FFN, RMSNorm
The full analysis with all file contents has been saved to kronos_analysis.md.



Now I have everything I need. Let me build the full app.



app.py
Python





app.py
Python
Here's your complete app.py — 755 lines, fully self-contained.

Architecture
The app is split into 7 clean sections:

Scoring Engine
All four signals are implemented exactly as specified:

Signal	Max	Logic
V (Volume)	5	RV = current vol / 20-period vol MA
P (Price momentum)	3	ATR-normalised move, only if close > prev close
R (Range position)	2	(close − low) / (high − low)
T (Trend alignment)	3	EMA20/50 stack + ADX ≥ 20
Total	13	V + P + R + T
Kronos Integration
The app loads KronosPredictor from HuggingFace (NeoQuasar/Kronos-small by default) as a singleton and calls predictor.predict() on the top-scoring symbols. The forecast summary includes expected close, % change, high/low targets, and bullish candle ratio.

Install
bash
pip install ccxt pandas numpy pandas-ta rich torch huggingface_hub
pip install git+https://github.com/shiyu-coder/Kronos.git
Usage
bash
# Auto-scan top 30 USDT pairs on Binance
python app.py

# Single symbol with Kronos forecast (24 candles ahead)
python app.py --symbol BTCUSDT --interval 1h --kronos

# Custom watchlist + Kronos, show top 5 only
python app.py --watchlist BTC ETH SOL BNB AVAX --interval 15m --kronos --top 5

# Filter: only show signals with score ≥ 7
python app.py --min-score 7

# Load from local CSV
python app.py --csv mydata.csv --kronos

# Use larger Kronos model variant
python app.py --kronos --kronos-model NeoQuasar/Kronos-base
Key design notes
ccxt, pandas_ta, and rich all degrade gracefully if not installed — the core scoring engine works with just pandas and numpy

Kronos is loaded once and cached for multi-symbol scans

The --lookback flag controls how many historical candles (up to 512) are fed as Kronos context; --pred-len sets how many candles to forecast ahead


app.py
Python
Oh no.
Error running app. If you need help, try the Streamlit docs and forums.
Could you paste the full error traceback? That will tell me exactly which line is failing and why.

this is the only thing visible in streamlit
The error message suggests it's being run via Streamlit, but the app was built as a plain CLI script — not a Streamlit app. Let me rebuild it as a proper Streamlit app.




app.py
Python





app.py
Python
The app has been fully rebuilt as a native Streamlit app. Run it with:

bash
streamlit run app.py
What's in the UI
Sidebar controls

Data source: live exchange (Binance/Bybit/OKX/KuCoin) or upload a CSV

Interval, candle limit, auto top-N pairs or custom watchlist

Score filter and top-N display

Kronos toggle with model variant, forecast length, and lookback sliders

Results table

All symbols ranked by composite score (colour-coded: green ≥ 9, yellow ≥ 5)

Columns: Close, RV, ATR Move, ADX, RSI, V, P, R, T, Score

Detail view (select any symbol)

Score metrics row + indicator metrics row

Candlestick chart with EMA20/50 overlays + Kronos forecast line

Volume bar chart with 20-period MA

Signal radar chart (V/P/R/T as % of max)

Kronos panel with forecast close, % change, high target, bullish candle %, and a full forward chart

Install dependencies
bash
pip install streamlit ccxt pandas numpy pandas-ta plotly torch huggingface_hub
# For Kronos AI forecast (optional):
pip install git+https://github.com/shiyu-coder/Kronos.git

app.py
Python
Follow-up

Add error logging to the Streamlit app so any failed symbol fetch or Kronos inference shows a visible warning instead of silently breaking
app
"""
Crypto Sniper — Streamlit App
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
