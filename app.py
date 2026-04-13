import io
import json
import math
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# =========================================================
# STREAMLIT PAGE
# =========================================================
st.set_page_config(
    page_title="Crypto Guru",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =========================================================
# BRANDING
# =========================================================
LOGO_PATH = "assets/crypto_guru_logo.png"
APP_HEADING = "Crypto Guru"
APP_TAGLINE = "Precision crypto intelligence."

# =========================================================
# SECRETS / CONFIG
# Put these in Streamlit secrets:
#
# ETHERSCAN_API_KEY="your_key"
# CRYPTOCOMPARE_API_KEY="your_key"
#
# Optional comma-separated smart wallets:
# SMART_WALLETS="0xabc...,0xdef..."
#
# Optional comma-separated exchange wallets:
# EXCHANGE_WALLETS="0x123...,0x456..."
#
# Optional JSON string map for ERC20 token contracts:
# TOKEN_MAP_JSON='{
#   "FET":{"contract":"0x....","chainid":"1"},
#   "LINK":{"contract":"0x....","chainid":"1"}
# }'
# =========================================================
ETHERSCAN_API_KEY = st.secrets.get("ETHERSCAN_API_KEY", "")
CRYPTOCOMPARE_API_KEY = st.secrets.get("CRYPTOCOMPARE_API_KEY", "")

SMART_WALLETS = [
    w.strip().lower()
    for w in st.secrets.get("SMART_WALLETS", "").split(",")
    if w.strip()
]
EXCHANGE_WALLETS = [
    w.strip().lower()
    for w in st.secrets.get("EXCHANGE_WALLETS", "").split(",")
    if w.strip()
]

try:
    TOKEN_MAP = json.loads(st.secrets.get("TOKEN_MAP_JSON", "{}"))
except Exception:
    TOKEN_MAP = {}

HOLDER_CACHE_FILE = "holder_cache.json"

# =========================================================
# DATA MODELS
# =========================================================
@dataclass
class CoinMetrics:
    rv: float
    close_now: float
    close_prev: float
    atr_move: float
    range_pos: float
    ema20: float
    ema50: float
    adx14: float
    smart_wallet_accumulation: bool
    repeat_buyer_presence: bool
    net_large_buyer_flow_positive: bool
    holder_growth_positive: bool
    penalty_low_liquidity: int
    penalty_concentration: int
    penalty_exchange_inflow: int
    penalty_wash_like_volume: int
    penalty_high_slippage: int
    avg_dollar_volume: float
    top10_concentration: Optional[float]
    exchange_inflow_tokens: float
    smart_wallet_net_flow_tokens: float
    holder_count: Optional[int]
    miro_components: Dict[str, float]


@dataclass
class EngineSignal:
    label: str
    bias: str
    confidence: str
    score: float
    summary: str


@dataclass
class AILabDecision:
    bull: str
    bear: str
    risk_manager: str
    chief_strategist: str
    final_bias: str
    final_confidence: str
    final_score: float


@dataclass
class FinalResponse:
    coin: str
    answer: str
    bias: str
    confidence: str
    risk: str
    action: str
    reasons: List[str]
    miro_score: float
    kronos_score: float
    ai_lab_score: float
    bull_case: str
    bear_case: str
    risk_case: str
    chief_strategist: str


# =========================================================
# STYLES
# =========================================================
def inject_styles() -> None:
    st.markdown(
        """
        <style>
            :root {
                --bg: #000000;
                --panel: #0a0a0a;
                --panel-2: #111111;
                --border: rgba(255,153,51,0.22);
                --text: #ffffff;
                --muted: #d7b37a;
                --accent: #ff9933;
            }

            .stApp {
                background:
                    radial-gradient(circle at top left, rgba(255,153,51,0.11), transparent 24%),
                    radial-gradient(circle at top right, rgba(255,153,51,0.08), transparent 20%),
                    linear-gradient(180deg, #000000 0%, #050505 100%);
            }

            .block-container {
                max-width: 980px;
                padding-top: 3rem;
                padding-bottom: 3rem;
            }

            header[data-testid="stHeader"] {
                background: transparent;
            }

            [data-testid="collapsedControl"] {
                display: none;
            }

            section[data-testid="stSidebar"] {
                display: none !important;
            }

            .hero-wrap {
                text-align: center;
                margin-bottom: 1.75rem;
            }

            .hero-logo-wrap {
                display: flex;
                justify-content: center;
                align-items: center;
                margin-bottom: 0.65rem;
                animation: floaty 4.5s ease-in-out infinite;
            }

            .hero-logo-glow {
                display: inline-flex;
                justify-content: center;
                align-items: center;
                padding: 14px;
                border-radius: 24px;
                background:
                    radial-gradient(circle, rgba(255,153,51,0.16) 0%, rgba(255,153,51,0.05) 45%, rgba(255,153,51,0.00) 72%);
                box-shadow:
                    0 0 0 1px rgba(255,153,51,0.05),
                    0 0 28px rgba(255,153,51,0.14),
                    0 0 56px rgba(255,153,51,0.08);
                transition: transform 0.25s ease, box-shadow 0.25s ease;
            }

            .hero-logo-glow:hover {
                transform: translateY(-1px) scale(1.01);
                box-shadow:
                    0 0 0 1px rgba(255,153,51,0.08),
                    0 0 36px rgba(255,153,51,0.18),
                    0 0 68px rgba(255,153,51,0.11);
            }

            @keyframes floaty {
                0% { transform: translateY(0px); }
                50% { transform: translateY(-3px); }
                100% { transform: translateY(0px); }
            }

            .hero-title {
                color: #ffffff;
                font-size: 2.7rem;
                font-weight: 800;
                letter-spacing: -0.03em;
                margin-top: 0.3rem;
                margin-bottom: 0.35rem;
            }

            .hero-tagline {
                color: var(--muted);
                font-size: 1rem;
                margin-bottom: 0;
            }

            .search-shell {
                background: linear-gradient(180deg, rgba(10,10,10,0.98) 0%, rgba(18,18,18,0.98) 100%);
                border: 1px solid rgba(255,153,51,0.20);
                border-radius: 22px;
                padding: 1rem;
                box-shadow:
                    0 0 0 1px rgba(255,153,51,0.03),
                    0 20px 60px rgba(0,0,0,0.45);
                margin-bottom: 1.15rem;
            }

            .result-card {
                background: linear-gradient(180deg, rgba(10,10,10,0.98) 0%, rgba(18,18,18,0.98) 100%);
                border: 1px solid rgba(255,153,51,0.20);
                border-radius: 20px;
                padding: 1.15rem 1.2rem;
                margin-top: 1rem;
                box-shadow: 0 12px 36px rgba(0,0,0,0.28);
            }

            .result-title {
                color: #ffffff;
                font-size: 1.1rem;
                font-weight: 750;
                margin-bottom: 0.7rem;
            }

            .answer-text {
                color: #fff7ed;
                font-size: 1.02rem;
                line-height: 1.7;
                margin-bottom: 0.95rem;
            }

            .signal-grid {
                display: grid;
                grid-template-columns: repeat(4, minmax(0, 1fr));
                gap: 0.8rem;
            }

            .signal-box {
                background: rgba(255,153,51,0.04);
                border: 1px solid rgba(255,153,51,0.12);
                border-radius: 16px;
                padding: 0.85rem 0.9rem;
            }

            .signal-label {
                color: #d7b37a;
                font-size: 0.8rem;
                margin-bottom: 0.3rem;
            }

            .signal-value {
                color: #ffffff;
                font-size: 0.95rem;
                font-weight: 700;
                line-height: 1.4;
            }

            .why-line {
                color: #fff7ed;
                line-height: 1.6;
                margin-bottom: 0.45rem;
                opacity: 1 !important;
            }

            .stTextInput > div > div > input {
                background: linear-gradient(180deg, rgba(18,18,18,0.94) 0%, rgba(8,8,8,0.98) 100%) !important;
                color: #ffffff !important;
                border-radius: 16px !important;
                border: 1px solid rgba(255,153,51,0.24) !important;
                padding: 1rem 1rem !important;
                font-size: 1.05rem !important;
                text-align: center !important;
                caret-color: #ff9933 !important;
                transition: all 0.22s ease !important;
            }

            .stTextInput > div > div > input::placeholder {
                color: #c49352 !important;
                opacity: 1 !important;
            }

            .stTextInput > div > div > input:focus {
                background: linear-gradient(180deg, rgba(18,18,18,0.98) 0%, rgba(8,8,8,1) 100%) !important;
                color: #ffffff !important;
                border: 1px solid #ff9933 !important;
                outline: none !important;
                box-shadow:
                    0 0 0 1px rgba(255,153,51,0.08),
                    0 0 18px rgba(255,153,51,0.13) !important;
                transform: translateY(-1px);
            }

            [data-testid="stTextInput"] input {
                color: #ffffff !important;
                background-color: #0d0d0d !important;
            }

            .stButton > button,
            .stDownloadButton > button {
                width: 100%;
                min-height: 2.45rem;
                border-radius: 12px;
                font-weight: 700;
                font-size: 0.92rem;
                border: 1px solid rgba(255,153,51,0.20);
                background: linear-gradient(180deg, #ff9933 0%, #d97706 100%);
                color: #000000;
                padding: 0.35rem 0.7rem;
                transition: all 0.2s ease;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover {
                color: #000000;
                border: 1px solid rgba(255,153,51,0.32);
                background: linear-gradient(180deg, #ffad5c 0%, #e68613 100%);
                box-shadow: 0 8px 22px rgba(255,153,51,0.14);
                transform: translateY(-1px);
            }

            div[data-testid="stExpander"] {
                border: 1px solid rgba(255,153,51,0.16) !important;
                border-radius: 16px !important;
                background: rgba(255,153,51,0.03) !important;
                overflow: hidden !important;
            }

            div[data-testid="stExpander"] summary {
                background: rgba(255,153,51,0.04) !important;
                color: #ffffff !important;
                border-radius: 16px !important;
            }

            div[data-testid="stExpander"] summary p {
                color: #ffffff !important;
                font-weight: 700 !important;
                opacity: 1 !important;
            }

            div[data-testid="stExpander"] summary svg {
                fill: #ff9933 !important;
                color: #ff9933 !important;
                opacity: 1 !important;
            }

            div[data-testid="stExpanderDetails"] {
                color: #fff7ed !important;
                opacity: 1 !important;
            }

            div[data-testid="stExpanderDetails"] p,
            div[data-testid="stExpanderDetails"] div,
            div[data-testid="stExpanderDetails"] span,
            div[data-testid="stExpanderDetails"] label {
                color: #fff7ed !important;
                opacity: 1 !important;
            }

            @media (max-width: 820px) {
                .hero-title { font-size: 2.15rem; }
                .signal-grid { grid-template-columns: 1fr 1fr; }
            }

            @media (max-width: 580px) {
                .signal-grid { grid-template-columns: 1fr; }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# STATE
# =========================================================
def init_state() -> None:
    defaults = {
        "coin_input": "",
        "last_coin": "",
        "last_response": None,
        "last_signals": None,
        "last_pdf": None,
        "last_metrics": None,
        "last_ai_lab": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# =========================================================
# HELPERS
# =========================================================
def normalize_coin(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", raw.strip().upper())


def score_to_bias(score: float) -> str:
    if score >= 11.0:
        return "strong bullish"
    if score >= 8.5:
        return "bullish"
    if score >= 6.0:
        return "constructive"
    if score >= 3.5:
        return "neutral"
    return "cautious"


def score_to_confidence(score: float) -> str:
    if score >= 10.0:
        return "high"
    if score >= 6.0:
        return "medium"
    return "low"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def get_token_map_entry(symbol: str) -> Optional[Dict[str, str]]:
    entry = TOKEN_MAP.get(symbol.upper())
    if isinstance(entry, dict):
        return entry
    return None


def load_holder_cache() -> Dict[str, Any]:
    if not os.path.exists(HOLDER_CACHE_FILE):
        return {}
    try:
        with open(HOLDER_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_holder_cache(data: Dict[str, Any]) -> None:
    try:
        with open(HOLDER_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def update_holder_growth(symbol: str, chainid: str, holder_count: Optional[int]) -> bool:
    if holder_count is None:
        return False
    cache = load_holder_cache()
    key = f"{chainid}:{symbol.upper()}"
    prev = cache.get(key, {}).get("holder_count")
    cache[key] = {
        "holder_count": holder_count,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_holder_cache(cache)
    if prev is None:
        return False
    return holder_count > int(prev)


# =========================================================
# MARKET DATA - CRYPTOCOMPARE
# =========================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_ohlcv_cryptocompare(symbol: str, limit: int = 240) -> pd.DataFrame:
    """
    Uses the widely deployed CryptoCompare histohour endpoint.
    Replace only this function if you move to a different CoinDesk Data API path.
    """
    url = "https://min-api.cryptocompare.com/data/v2/histohour"
    params = {
        "fsym": symbol.upper(),
        "tsym": "USD",
        "limit": limit,
        "aggregate": 1,
    }
    headers = {}
    if CRYPTOCOMPARE_API_KEY:
        headers["authorization"] = f"Apikey {CRYPTOCOMPARE_API_KEY}"

    resp = requests.get(url, params=params, headers=headers, timeout=20)
    resp.raise_for_status()
    payload = resp.json()

    data = payload.get("Data", {}).get("Data", [])
    if not data:
        raise ValueError(f"No market data returned for {symbol}")

    df = pd.DataFrame(data)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.rename(
        columns={
            "volumefrom": "volume_base",
            "volumeto": "volume_quote",
        }
    )
    required = ["time", "open", "high", "low", "close", "volume_base", "volume_quote"]
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing market column: {col}")
    return df[required].copy()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    out["ema20"] = out["close"].ewm(span=20, adjust=False).mean()
    out["ema50"] = out["close"].ewm(span=50, adjust=False).mean()

    prev_close = out["close"].shift(1)
    tr_components = pd.concat(
        [
            (out["high"] - out["low"]).abs(),
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    out["tr"] = tr_components.max(axis=1)
    out["atr14"] = out["tr"].rolling(14).mean()

    up_move = out["high"].diff()
    down_move = -out["low"].diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    atr14 = out["atr14"].replace(0, np.nan)
    plus_di = 100 * pd.Series(plus_dm, index=out.index).rolling(14).mean() / atr14
    minus_di = 100 * pd.Series(minus_dm, index=out.index).rolling(14).mean() / atr14
    dx = (abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)) * 100
    out["adx14"] = dx.rolling(14).mean()

    return out


# =========================================================
# ON-CHAIN DATA - ETHERSCAN
# =========================================================
@st.cache_data(ttl=300, show_spinner=False)
def etherscan_get(params: Dict[str, Any]) -> Dict[str, Any]:
    if not ETHERSCAN_API_KEY:
        return {"status": "0", "message": "Missing Etherscan API key", "result": []}

    query = {"apikey": ETHERSCAN_API_KEY}
    query.update(params)
    resp = requests.get("https://api.etherscan.io/v2/api", params=query, timeout=20)
    resp.raise_for_status()
    return resp.json()


def fetch_top_holders(contract: str, chainid: str) -> Tuple[Optional[List[Dict[str, Any]]], bool]:
    payload = etherscan_get(
        {
            "chainid": chainid,
            "module": "token",
            "action": "topholders",
            "contractaddress": contract,
            "offset": 10,
        }
    )
    ok = payload.get("status") == "1" and isinstance(payload.get("result"), list)
    return (payload.get("result") if ok else None, ok)


def fetch_holder_count(contract: str, chainid: str) -> Optional[int]:
    payload = etherscan_get(
        {
            "chainid": chainid,
            "module": "token",
            "action": "tokenholdercount",
            "contractaddress": contract,
        }
    )
    if payload.get("status") == "1":
        try:
            return int(payload.get("result"))
        except Exception:
            return None
    return None


def fetch_total_supply(contract: str, chainid: str) -> Optional[float]:
    payload = etherscan_get(
        {
            "chainid": chainid,
            "module": "stats",
            "action": "tokensupply",
            "contractaddress": contract,
        }
    )
    if payload.get("status") == "1":
        return safe_float(payload.get("result"), None)
    return None


def fetch_wallet_token_transfers(
    wallet: str,
    contract: str,
    chainid: str,
    offset: int = 100,
) -> List[Dict[str, Any]]:
    payload = etherscan_get(
        {
            "chainid": chainid,
            "module": "account",
            "action": "tokentx",
            "address": wallet,
            "contractaddress": contract,
            "startblock": 0,
            "endblock": 999999999,
            "page": 1,
            "offset": offset,
            "sort": "desc",
        }
    )
    if payload.get("status") == "1" and isinstance(payload.get("result"), list):
        return payload["result"]
    return []


def compute_wallet_net_flow(wallet: str, transfers: List[Dict[str, Any]]) -> float:
    wallet = wallet.lower()
    net = 0.0
    for tx in transfers:
        decimals = int(tx.get("tokenDecimal", "18"))
        value = safe_float(tx.get("value")) / (10 ** decimals)
        to_addr = str(tx.get("to", "")).lower()
        from_addr = str(tx.get("from", "")).lower()

        if to_addr == wallet:
            net += value
        elif from_addr == wallet:
            net -= value
    return net


def analyze_onchain(symbol: str) -> Dict[str, Any]:
    token = get_token_map_entry(symbol)
    if not token:
        return {
            "enabled": False,
            "smart_wallet_accumulation": False,
            "repeat_buyer_presence": False,
            "net_large_buyer_flow_positive": False,
            "holder_growth_positive": False,
            "top10_concentration": None,
            "holder_count": None,
            "exchange_inflow_tokens": 0.0,
            "smart_wallet_net_flow_tokens": 0.0,
            "penalty_concentration": 0,
            "penalty_exchange_inflow": 0,
            "notes": "No contract mapping found for this token.",
        }

    contract = token["contract"]
    chainid = token.get("chainid", "1")

    top_holders, got_top_holders = fetch_top_holders(contract, chainid)
    holder_count = fetch_holder_count(contract, chainid)
    total_supply = fetch_total_supply(contract, chainid)
    holder_growth_positive = update_holder_growth(symbol, chainid, holder_count)

    top10_concentration = None
    penalty_concentration = 0
    if got_top_holders and top_holders and total_supply and total_supply > 0:
        top_qty = sum(safe_float(x.get("TokenHolderQuantity")) for x in top_holders)
        top10_concentration = top_qty / total_supply
        penalty_concentration = 1 if top10_concentration >= 0.50 else 0

    smart_positive_wallets = 0
    smart_wallet_net_flow = 0.0
    for wallet in SMART_WALLETS:
        txs = fetch_wallet_token_transfers(wallet, contract, chainid)
        net = compute_wallet_net_flow(wallet, txs)
        smart_wallet_net_flow += net
        if net > 0:
            smart_positive_wallets += 1

    exchange_inflow_tokens = 0.0
    for wallet in EXCHANGE_WALLETS:
        txs = fetch_wallet_token_transfers(wallet, contract, chainid)
        net = compute_wallet_net_flow(wallet, txs)
        if net > 0:
            exchange_inflow_tokens += net

    smart_wallet_accumulation = smart_positive_wallets >= 1
    repeat_buyer_presence = smart_positive_wallets >= 2
    net_large_buyer_flow_positive = smart_wallet_net_flow > 0
    penalty_exchange_inflow = 1 if exchange_inflow_tokens > 0 else 0

    return {
        "enabled": True,
        "smart_wallet_accumulation": smart_wallet_accumulation,
        "repeat_buyer_presence": repeat_buyer_presence,
        "net_large_buyer_flow_positive": net_large_buyer_flow_positive,
        "holder_growth_positive": holder_growth_positive,
        "top10_concentration": top10_concentration,
        "holder_count": holder_count,
        "exchange_inflow_tokens": exchange_inflow_tokens,
        "smart_wallet_net_flow_tokens": smart_wallet_net_flow,
        "penalty_concentration": penalty_concentration,
        "penalty_exchange_inflow": penalty_exchange_inflow,
        "notes": "On-chain analysis active.",
    }


# =========================================================
# MIRO V2
# =========================================================
def compute_miro_components(metrics: CoinMetrics) -> Dict[str, float]:
    if metrics.rv < 2:
        v = 0
    elif metrics.rv < 4:
        v = 2
    elif metrics.rv < 8:
        v = 3
    else:
        v = 5

    if metrics.close_now <= metrics.close_prev:
        p = 0
    elif metrics.atr_move < 1.5:
        p = 0
    elif metrics.atr_move < 2.5:
        p = 1
    elif metrics.atr_move < 4:
        p = 2
    else:
        p = 3

    if metrics.range_pos < 0.70:
        r = 0
    elif metrics.range_pos < 0.85:
        r = 1
    else:
        r = 2

    t = 0
    if metrics.close_now > metrics.ema20:
        t += 1
    if metrics.ema20 > metrics.ema50:
        t += 1
    if metrics.adx14 >= 20:
        t += 1

    o = 0
    if metrics.smart_wallet_accumulation:
        o += 2
    if metrics.repeat_buyer_presence:
        o += 2
    if metrics.net_large_buyer_flow_positive:
        o += 1
    if metrics.holder_growth_positive:
        o += 1
    o = min(o, 4)

    x = (
        metrics.penalty_low_liquidity
        + metrics.penalty_concentration
        + metrics.penalty_exchange_inflow
        + metrics.penalty_wash_like_volume
        + metrics.penalty_high_slippage
    )
    x = min(x, 5)

    total = v + p + r + t + o - x
    return {"V": v, "P": p, "R": r, "T": t, "O": o, "X": x, "total": total}


def build_live_metrics(symbol: str) -> Tuple[CoinMetrics, pd.DataFrame]:
    raw = fetch_ohlcv_cryptocompare(symbol)
    df = add_indicators(raw)
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    vol_window = df["volume_quote"].tail(24)
    prev_vol_mean = max(df["volume_quote"].tail(48).head(24).mean(), 1.0)
    rv = latest["volume_quote"] / prev_vol_mean

    atr14 = max(float(latest["atr14"]) if not math.isnan(latest["atr14"]) else 0.0, 1e-9)
    atr_move = abs(float(latest["close"]) - float(prev["close"])) / atr14

    lookback = df.tail(20)
    range_high = float(lookback["high"].max())
    range_low = float(lookback["low"].min())
    if range_high <= range_low:
        range_pos = 0.5
    else:
        range_pos = (float(latest["close"]) - range_low) / (range_high - range_low)

    avg_dollar_volume = float(vol_window.mean())

    penalty_low_liquidity = 1 if avg_dollar_volume < 500_000 else 0

    true_range_pct = float(latest["tr"]) / max(float(latest["close"]), 1e-9)
    penalty_wash_like_volume = 1 if rv >= 4 and true_range_pct < 0.01 else 0

    hourly_range_pct = (float(latest["high"]) - float(latest["low"])) / max(float(latest["close"]), 1e-9)
    penalty_high_slippage = 1 if avg_dollar_volume < 1_000_000 and hourly_range_pct > 0.03 else 0

    onchain = analyze_onchain(symbol)

    metrics = CoinMetrics(
        rv=float(rv),
        close_now=float(latest["close"]),
        close_prev=float(prev["close"]),
        atr_move=float(atr_move),
        range_pos=float(range_pos),
        ema20=float(latest["ema20"]),
        ema50=float(latest["ema50"]),
        adx14=float(latest["adx14"]) if not math.isnan(latest["adx14"]) else 0.0,
        smart_wallet_accumulation=bool(onchain["smart_wallet_accumulation"]),
        repeat_buyer_presence=bool(onchain["repeat_buyer_presence"]),
        net_large_buyer_flow_positive=bool(onchain["net_large_buyer_flow_positive"]),
        holder_growth_positive=bool(onchain["holder_growth_positive"]),
        penalty_low_liquidity=penalty_low_liquidity,
        penalty_concentration=int(onchain["penalty_concentration"]),
        penalty_exchange_inflow=int(onchain["penalty_exchange_inflow"]),
        penalty_wash_like_volume=penalty_wash_like_volume,
        penalty_high_slippage=penalty_high_slippage,
        avg_dollar_volume=avg_dollar_volume,
        top10_concentration=onchain["top10_concentration"],
        exchange_inflow_tokens=float(onchain["exchange_inflow_tokens"]),
        smart_wallet_net_flow_tokens=float(onchain["smart_wallet_net_flow_tokens"]),
        holder_count=onchain["holder_count"],
        miro_components={},
    )
    metrics.miro_components = compute_miro_components(metrics)
    return metrics, df


# =========================================================
# ENGINES
# =========================================================
def run_miro_score(symbol: str) -> Tuple[EngineSignal, CoinMetrics, pd.DataFrame]:
    metrics, df = build_live_metrics(symbol)
    comp = metrics.miro_components
    score = float(comp["total"])

    summary = (
        f"Miro v2 = V({comp['V']}) + P({comp['P']}) + R({comp['R']}) + "
        f"T({comp['T']}) + O({comp['O']}) - X({comp['X']}) = {comp['total']:.1f}."
    )

    signal = EngineSignal(
        label="Miro Score",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=summary,
    )
    return signal, metrics, df


def run_kronos_logic(symbol: str, df: pd.DataFrame, miro_score: float) -> EngineSignal:
    """
    Live timing engine wrapper.
    This is fed by live OHLCV now.
    Replace only this function later if you install the Kronos model itself.
    """
    closes = df["close"].tail(24).reset_index(drop=True)
    ema20 = float(df["ema20"].iloc[-1])
    atr14 = max(float(df["atr14"].iloc[-1]) if not math.isnan(df["atr14"].iloc[-1]) else 0.0, 1e-9)
    last_close = float(df["close"].iloc[-1])

    x = np.arange(len(closes))
    slope = np.polyfit(x, closes.values, 1)[0]
    slope_norm = slope / max(last_close, 1e-9)

    realized_vol = float(df["close"].pct_change().tail(24).std())
    breakout = last_close > float(df["high"].tail(20).iloc[:-1].max())
    above_ema = last_close > ema20
    stable = realized_vol < 0.03

    score = 4.5
    if slope_norm > 0.0015:
        score += 1.8
    elif slope_norm > 0:
        score += 0.9

    if above_ema:
        score += 1.2
    if stable:
        score += 1.0
    if breakout:
        score += 1.2

    if miro_score >= 8.5:
        score += 0.8
    elif miro_score < 3.5:
        score -= 0.6

    score = round(max(0.0, min(10.0, score)), 1)

    summary = (
        f"Kronos Logic reads live timing from the recent OHLCV path and scores "
        f"{symbol} at {score:.1f}/10."
    )

    return EngineSignal(
        label="Kronos Logic",
        bias=score_to_bias(score),
        confidence=score_to_confidence(score),
        score=score,
        summary=summary,
    )


def run_ai_lab(symbol: str, miro: EngineSignal, kronos: EngineSignal, metrics: CoinMetrics) -> AILabDecision:
    bull_points = []
    bear_points = []
    risk_points = []

    if miro.score >= 8.5:
        bull_points.append("Miro is already in the bullish zone.")
    if kronos.score >= 7.0:
        bull_points.append("Timing is supportive rather than fading.")
    if metrics.smart_wallet_accumulation:
        bull_points.append("Smart wallet accumulation is positive.")
    if metrics.repeat_buyer_presence:
        bull_points.append("More than one repeat buyer is showing up.")
    if metrics.range_pos >= 0.85:
        bull_points.append("Price is closing near the top of its recent range.")
    if metrics.adx14 >= 20:
        bull_points.append("Trend strength is not weak.")

    if miro.score < 6.0:
        bear_points.append("Miro structure is not strong enough.")
    if kronos.score < 6.0:
        bear_points.append("Timing is not clean.")
    if metrics.penalty_concentration:
        bear_points.append("Holder concentration is elevated.")
    if metrics.penalty_exchange_inflow:
        bear_points.append("Exchange inflow pressure is present.")
    if metrics.penalty_low_liquidity:
        bear_points.append("Liquidity is thin.")
    if metrics.penalty_wash_like_volume:
        bear_points.append("Volume quality looks suspicious.")
    if metrics.penalty_high_slippage:
        bear_points.append("Slippage risk is high.")

    if metrics.penalty_concentration:
        risk_points.append("Concentration can break market quality quickly.")
    if metrics.penalty_exchange_inflow:
        risk_points.append("Exchange deposits can precede distribution.")
    if metrics.penalty_low_liquidity:
        risk_points.append("Low liquidity can distort the signal.")
    if metrics.penalty_high_slippage:
        risk_points.append("Execution quality may be poor.")
    if not risk_points:
        risk_points.append("Risk is present but not dominant.")

    bull = "Bull Agent: " + (
        " ".join(bull_points) if bull_points else "Upside exists, but the setup is not screaming yet."
    )
    bear = "Bear Agent: " + (
        " ".join(bear_points) if bear_points else "The downside case is present but not overwhelming."
    )
    risk_manager = "Risk Manager: " + " ".join(risk_points)

    final_score = round((miro.score * 0.65) + (kronos.score * 0.35), 1)

    if metrics.miro_components["X"] >= 3:
        final_score -= 0.8
    if metrics.miro_components["O"] >= 3:
        final_score += 0.5
    if metrics.range_pos >= 0.85 and metrics.close_now > metrics.ema20:
        final_score += 0.3

    final_score = round(max(0.0, final_score), 1)
    final_bias = score_to_bias(final_score)
    final_confidence = score_to_confidence(final_score)

    chief_strategist = (
        f"Chief Strategist: Final read is {final_bias} with {final_confidence} confidence. "
        f"Miro contributes the structural edge, Kronos contributes timing quality, and the "
        f"risk layer decides whether the setup should be pressed or handled cautiously."
    )

    return AILabDecision(
        bull=bull,
        bear=bear,
        risk_manager=risk_manager,
        chief_strategist=chief_strategist,
        final_bias=final_bias,
        final_confidence=final_confidence,
        final_score=final_score,
    )


def run_engines(symbol: str) -> Tuple[Dict[str, EngineSignal], CoinMetrics, AILabDecision]:
    miro, metrics, df = run_miro_score(symbol)
    kronos = run_kronos_logic(symbol, df, miro.score)

    ai_lab_decision = run_ai_lab(symbol, miro, kronos, metrics)
    ai_lab_signal = EngineSignal(
        label="AI Lab",
        bias=ai_lab_decision.final_bias,
        confidence=ai_lab_decision.final_confidence,
        score=ai_lab_decision.final_score,
        summary=ai_lab_decision.chief_strategist,
    )

    return {
        "miro": miro,
        "kronos": kronos,
        "ai_lab": ai_lab_signal,
    }, metrics, ai_lab_decision


# =========================================================
# RESPONSE COMPOSITION
# =========================================================
def compose_response(
    symbol: str,
    signals: Dict[str, EngineSignal],
    ai_lab: AILabDecision,
) -> FinalResponse:
    final_score = signals["ai_lab"].score
    bias = signals["ai_lab"].bias
    confidence = signals["ai_lab"].confidence

    if bias == "strong bullish":
        action = "Strong watch"
        risk = "Crowding and reversal risk if the move gets extended."
    elif bias == "bullish":
        action = "Watch closely"
        risk = "Pullback risk if timing fades."
    elif bias == "constructive":
        action = "Early watch"
        risk = "Still not a full confirmation."
    elif bias == "neutral":
        action = "Stay selective"
        risk = "Directional edge is limited."
    else:
        action = "Avoid forcing"
        risk = "Weak structure and penalty risk remain elevated."

    answer = (
        f"{symbol} currently reads as {bias} with {confidence} confidence after "
        f"Miro Score, Kronos Logic, and AI Lab."
    )

    reasons = [
        f"Miro Score: {signals['miro'].summary}",
        f"Kronos Logic: {signals['kronos'].summary}",
        f"AI Lab: {signals['ai_lab'].summary}",
    ]

    return FinalResponse(
        coin=symbol,
        answer=answer,
        bias=bias,
        confidence=confidence,
        risk=risk,
        action=action,
        reasons=reasons,
        miro_score=signals["miro"].score,
        kronos_score=signals["kronos"].score,
        ai_lab_score=final_score,
        bull_case=ai_lab.bull,
        bear_case=ai_lab.bear,
        risk_case=ai_lab.risk_manager,
        chief_strategist=ai_lab.chief_strategist,
    )


# =========================================================
# PDF
# =========================================================
def wrap_text(text: str, font_name: str, font_size: int, max_width: float) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        test = word if not current else f"{current} {word}"
        if stringWidth(test, font_name, font_size) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_wrapped_text(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_name: str = "Helvetica",
    font_size: int = 11,
    line_gap: int = 15,
    color: HexColor = HexColor("#FFF7ED"),
) -> float:
    pdf.setFillColor(color)
    pdf.setFont(font_name, font_size)
    for line in wrap_text(text, font_name, font_size, max_width):
        pdf.drawString(x, y, line)
        y -= line_gap
    return y


def generate_pdf(response: FinalResponse) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    margin_x = 18 * mm
    y = height - 22 * mm
    content_width = width - (2 * margin_x)

    pdf.setFillColor(HexColor("#000000"))
    pdf.rect(0, 0, width, height, fill=1, stroke=0)

    pdf.setFillColor(HexColor("#FFFFFF"))
    pdf.setFont("Helvetica-Bold", 22)
    pdf.drawString(margin_x, y, APP_HEADING)
    y -= 8 * mm

    pdf.setFillColor(HexColor("#D7B37A"))
    pdf.setFont("Helvetica", 11)
    pdf.drawString(margin_x, y, APP_TAGLINE)
    y -= 12 * mm

    pdf.setFillColor(HexColor("#FF9933"))
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(margin_x, y, f"{response.coin} Signal Output")
    y -= 8 * mm

    y = draw_wrapped_text(pdf, response.answer, margin_x, y, content_width)
    y -= 5 * mm

    pdf.setFillColor(HexColor("#111111"))
    pdf.roundRect(margin_x, y - 32 * mm, content_width, 30 * mm, 8, fill=1, stroke=0)

    stat_y = y - 7 * mm
    stats = [
        ("Bias", response.bias.title()),
        ("Confidence", response.confidence.title()),
        ("Risk", response.risk),
        ("Action", response.action),
    ]

    col_width = content_width / 2
    row_gap = 15 * mm

    for i, (label, value) in enumerate(stats):
        col = i % 2
        row = i // 2
        x = margin_x + (col * col_width) + 5 * mm
        sy = stat_y - (row * row_gap)

        pdf.setFillColor(HexColor("#D7B37A"))
        pdf.setFont("Helvetica", 9)
        pdf.drawString(x, sy, label)

        pdf.setFillColor(HexColor("#FFFFFF"))
        pdf.setFont("Helvetica-Bold", 10)
        value_lines = wrap_text(value, "Helvetica-Bold", 10, col_width - 12 * mm)
        for idx, line in enumerate(value_lines[:2]):
            pdf.drawString(x, sy - 5 - (idx * 11), line)

    y -= 40 * mm

    pdf.setFillColor(HexColor("#FF9933"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(margin_x, y, "Engine Scores")
    y -= 8 * mm

    for line in [
        f"Miro Score: {response.miro_score:.1f} / 15",
        f"Kronos Logic: {response.kronos_score:.1f} / 10",
        f"AI Lab: {response.ai_lab_score:.1f}",
    ]:
        y = draw_wrapped_text(pdf, line, margin_x, y, content_width)

    y -= 4 * mm

    pdf.setFillColor(HexColor("#FF9933"))
    pdf.setFont("Helvetica-Bold", 13)
    pdf.drawString(margin_x, y, "AI Lab")
    y -= 8 * mm

    for text in [
        response.bull_case,
        response.bear_case,
        response.risk_case,
        response.chief_strategist,
    ]:
        y = draw_wrapped_text(pdf, f"• {text}", margin_x, y, content_width)
        y -= 1 * mm
        if y < 25 * mm:
            pdf.showPage()
            pdf.setFillColor(HexColor("#000000"))
            pdf.rect(0, 0, width, height, fill=1, stroke=0)
            y = height - 22 * mm

    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


# =========================================================
# UI
# =========================================================
def render_header() -> None:
    st.markdown('<div class="hero-wrap">', unsafe_allow_html=True)

    if os.path.exists(LOGO_PATH):
        st.markdown('<div class="hero-logo-wrap"><div class="hero-logo-glow">', unsafe_allow_html=True)
        st.image(LOGO_PATH, width=120)
        st.markdown("</div></div>", unsafe_allow_html=True)

    st.markdown(
        f"""
        <div class="hero-title">{APP_HEADING}</div>
        <div class="hero-tagline">{APP_TAGLINE}</div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("</div>", unsafe_allow_html=True)


def render_search() -> None:
    st.markdown('<div class="search-shell">', unsafe_allow_html=True)

    coin = st.text_input(
        "",
        value=st.session_state.coin_input,
        placeholder="Enter coin",
        label_visibility="collapsed",
        key="coin_input_widget",
    )

    col1, col2, col3 = st.columns([3.4, 1.1, 1.1])
    with col2:
        analyze_clicked = st.button("Run Signal", use_container_width=True)
    with col3:
        clear_clicked = st.button("Clear", use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)

    if clear_clicked:
        st.session_state.coin_input = ""
        st.session_state.last_coin = ""
        st.session_state.last_response = None
        st.session_state.last_signals = None
        st.session_state.last_pdf = None
        st.session_state.last_metrics = None
        st.session_state.last_ai_lab = None
        st.rerun()

    if analyze_clicked:
        symbol = normalize_coin(coin)
        if not symbol:
            st.warning("Enter a valid coin.")
            return

        st.session_state.coin_input = symbol
        st.session_state.last_coin = symbol

        with st.spinner("Running live engines..."):
            time.sleep(0.2)
            signals, metrics, ai_lab = run_engines(symbol)
            response = compose_response(symbol, signals, ai_lab)
            pdf_bytes = generate_pdf(response)

        st.session_state.last_signals = signals
        st.session_state.last_response = response
        st.session_state.last_pdf = pdf_bytes
        st.session_state.last_metrics = metrics
        st.session_state.last_ai_lab = ai_lab
        st.rerun()


def render_output(response: FinalResponse, signals: Dict[str, EngineSignal], metrics: CoinMetrics) -> None:
    st.markdown(
        f"""
        <div class="result-card">
            <div class="result-title">{response.coin} Signal Output</div>
            <div class="answer-text">{response.answer}</div>
            <div class="signal-grid">
                <div class="signal-box">
                    <div class="signal-label">Bias</div>
                    <div class="signal-value">{response.bias.title()}</div>
                </div>
                <div class="signal-box">
                    <div class="signal-label">Confidence</div>
                    <div class="signal-value">{response.confidence.title()}</div>
                </div>
                <div class="signal-box">
                    <div class="signal-label">Risk</div>
                    <div class="signal-value">{response.risk}</div>
                </div>
                <div class="signal-box">
                    <div class="signal-label">Action</div>
                    <div class="signal-value">{response.action}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Why"):
        for reason in response.reasons:
            st.markdown(f'<div class="why-line">• {reason}</div>', unsafe_allow_html=True)

    with st.expander("Engine Scores"):
        st.markdown(
            f'<div class="why-line">Miro Score: {signals["miro"].score:.1f} / 15 · {signals["miro"].confidence.title()}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="why-line">Kronos Logic: {signals["kronos"].score:.1f} / 10 · {signals["kronos"].confidence.title()}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="why-line">AI Lab: {signals["ai_lab"].score:.1f} · {signals["ai_lab"].confidence.title()}</div>',
            unsafe_allow_html=True,
        )

    with st.expander("AI Lab"):
        st.markdown(f'<div class="why-line">• {response.bull_case}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="why-line">• {response.bear_case}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="why-line">• {response.risk_case}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="why-line">• {response.chief_strategist}</div>', unsafe_allow_html=True)

    with st.expander("Miro Breakdown"):
        comp = metrics.miro_components
        st.markdown(f'<div class="why-line">V = {comp["V"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="why-line">P = {comp["P"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="why-line">R = {comp["R"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="why-line">T = {comp["T"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="why-line">O = {comp["O"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="why-line">X = {comp["X"]}</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="why-line">RV={metrics.rv:.2f} · ATR_move={metrics.atr_move:.2f} · '
            f'RangePos={metrics.range_pos:.2f} · ADX14={metrics.adx14:.2f}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="why-line">Avg $ Volume={metrics.avg_dollar_volume:,.0f}</div>',
            unsafe_allow_html=True,
        )
        if metrics.top10_concentration is not None:
            st.markdown(
                f'<div class="why-line">Top-10 Concentration={metrics.top10_concentration:.2%}</div>',
                unsafe_allow_html=True,
            )
        if metrics.holder_count is not None:
            st.markdown(
                f'<div class="why-line">Holder Count={metrics.holder_count:,}</div>',
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div class="why-line">Smart Wallet Net Flow={metrics.smart_wallet_net_flow_tokens:,.4f} tokens</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="why-line">Exchange Inflow={metrics.exchange_inflow_tokens:,.4f} tokens</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.last_pdf:
        st.download_button(
            label="Download PDF",
            data=st.session_state.last_pdf,
            file_name=f"{response.coin.lower()}_signal_output.pdf",
            mime="application/pdf",
            use_container_width=False,
        )


def main() -> None:
    init_state()
    inject_styles()
    render_header()
    render_search()

    if st.session_state.last_response and st.session_state.last_signals and st.session_state.last_metrics:
        render_output(
            st.session_state.last_response,
            st.session_state.last_signals,
            st.session_state.last_metrics,
        )


if __name__ == "__main__":
    main()
