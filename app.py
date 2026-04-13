from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import requests
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="crypto.guru",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# BRAND / THEME
# ============================================================
BRAND_NAME = "crypto.guru"
TAGLINE = "Detect Early. Act Smart."

APP_BG = "#0A0E14"
APP_CARD = "#111722"
APP_CARD_2 = "#0F141D"
APP_BORDER = "#242E3F"
APP_TEXT = "#D9E1EC"
APP_TEXT_STRONG = "#F3F6FB"
APP_TEXT_MUTED = "#8692A3"
APP_GREEN = "#7CFF5B"
APP_GREEN_SOFT = "#67D84A"
APP_AMBER = "#D7A63A"
APP_RED = "#D96A6A"
APP_ORANGE = "#D48A2F"

PDF_BG_HEADER = "#10151D"
PDF_RULE = "#2B3442"
PDF_TEXT = "#111111"
PDF_TEXT_SOFT = "#333333"
PDF_MUTED = "#666666"
PDF_GREEN = "#2E7D32"
PDF_ORANGE = "#8C5A12"

DEXSCREENER_BASE = "https://api.dexscreener.com"
ETHERSCAN_V2_BASE = "https://api.etherscan.io/v2/api"

EVM_CHAIN_IDS: Dict[str, str] = {
    "ethereum": "1",
    "bsc": "56",
    "polygon": "137",
    "arbitrum": "42161",
    "base": "8453",
    "optimism": "10",
    "avalanche": "43114",
}

# ============================================================
# DATA MODELS
# ============================================================
@dataclass
class TokenPair:
    chain_id: str
    dex_id: str
    pair_address: str
    url: str
    base_symbol: str
    base_name: str
    base_address: str
    quote_symbol: str
    quote_address: str
    price_usd: float
    fdv: float
    market_cap: float
    liquidity_usd: float
    volume_24h: float
    buys_24h: int
    sells_24h: int
    pair_age_hours: float
    price_change_5m: float
    price_change_1h: float
    price_change_6h: float
    price_change_24h: float
    pair_created_at: Optional[int]


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
class OnChainMetrics:
    enabled: bool
    chain_supported: bool
    total_supply_raw: float
    holder_rows: List[Dict[str, Any]]
    top10_concentration_pct: float
    smart_wallets_active: int
    repeat_buyers: bool
    net_flow_label: str
    smart_wallet_net_units: float
    holder_growth_proxy: float
    notes: List[str]


@dataclass
class ReportData:
    token: TokenPair
    generated_at: str
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
    onchain_metrics: OnChainMetrics


# ============================================================
# STYLING
# ============================================================
def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: {APP_BG};
            color: {APP_TEXT};
        }}

        .block-container {{
            padding-top: 1.0rem;
            padding-bottom: 1.6rem;
            max-width: 1280px;
        }}

        section[data-testid="stSidebar"] {{
            background-color: {APP_CARD_2};
        }}

        .brand-box {{
            background: linear-gradient(180deg, {APP_CARD}, #0E141E);
            border: 1px solid {APP_BORDER};
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
            color: {APP_TEXT_MUTED};
            font-size: 0.92rem;
            margin-top: 0.22rem;
            font-weight: 500;
        }}

        .section-box {{
            background: linear-gradient(180deg, {APP_CARD}, #0F151F);
            border: 1px solid {APP_BORDER};
            border-radius: 15px;
            padding: 15px 17px;
            margin-bottom: 13px;
        }}

        .section-label {{
            color: {APP_ORANGE};
            font-size: 0.78rem;
            font-weight: 900;
            letter-spacing: 0.12rem;
            text-transform: uppercase;
            margin-bottom: 0.75rem;
        }}

        .score-text {{
            font-size: 2.05rem;
            font-weight: 900;
            margin-bottom: 0.14rem;
            letter-spacing: -0.03em;
        }}

        .status-pill {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 999px;
            border: 1px solid {APP_BORDER};
            background: #171F2C;
            font-size: 0.78rem;
            font-weight: 800;
            color: {APP_TEXT_STRONG};
        }}

        .small-note {{
            color: {APP_TEXT_MUTED};
            font-size: 0.88rem;
            line-height: 1.5;
            font-weight: 500;
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
            color: #C2CCD9;
            font-weight: 600;
        }}

        .compact-bar {{
            width: 70px;
            text-align: center;
            color: {APP_GREEN_SOFT};
            font-family: monospace;
            font-weight: 700;
        }}

        .compact-value {{
            width: 58px;
            text-align: right;
            color: {APP_TEXT};
            font-size: 0.90rem;
            font-weight: 700;
        }}

        .agent-box {{
            background: #0F151F;
            border: 1px solid {APP_BORDER};
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
            color: #C2CCD9;
        }}

        .verdict-box {{
            background: linear-gradient(180deg, #101912, #0D1510);
            border: 1px solid #29472D;
            border-radius: 14px;
            padding: 15px;
        }}

        .footer-note {{
            text-align: center;
            color: {APP_TEXT_MUTED};
            font-size: 0.83rem;
            margin-top: 18px;
        }}

        .signal-chip {{
            display:inline-block;
            padding: 5px 10px;
            border-radius: 999px;
            border: 1px solid {APP_BORDER};
            background: #171F2C;
            font-size: 0.75rem;
            font-weight: 700;
            margin-right: 6px;
            margin-bottom: 6px;
        }}

        .stDownloadButton > button {{
            background: linear-gradient(180deg, #16211A, #121A15);
            color: {APP_TEXT_STRONG};
            border: 1px solid #29472D;
            border-radius: 12px;
            font-weight: 800;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# HELPERS
# ============================================================
def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp_score(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def make_bar(value: int, max_value: int) -> str:
    value = max(0, min(value, max_value))
    return ("█" * value) + ("░" * (max_value - value))


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
        return APP_GREEN
    if score >= 8:
        return APP_AMBER
    if score >= 5:
        return "#C89C42"
    return APP_RED


def human_usd(v: float) -> str:
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:.0f}"


def format_pct(v: float) -> str:
    return f"{v:+.2f}%"


def parse_csv_wallets(text: str) -> List[str]:
    wallets: List[str] = []
    for raw in text.splitlines():
        addr = raw.strip()
        if not addr:
            continue
        wallets.append(addr.lower())
    return wallets


def get_etherscan_api_key() -> str:
    try:
        return st.secrets.get("ETHERSCAN_API_KEY", "")
    except Exception:
        return ""


# ============================================================
# DEXSCREENER
# ============================================================
def http_get_json(url: str, params: Optional[Dict[str, Any]] = None, timeout: int = 20) -> Dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={"Accept": "application/json", "User-Agent": "crypto.guru/1.0"},
    )
    response.raise_for_status()
    return response.json()


def parse_pair(raw: Dict[str, Any]) -> Optional[TokenPair]:
    try:
        base = raw.get("baseToken", {}) or {}
        quote = raw.get("quoteToken", {}) or {}
        volume = raw.get("volume", {}) or {}
        txns = raw.get("txns", {}) or {}
        price_change = raw.get("priceChange", {}) or {}
        liquidity = raw.get("liquidity", {}) or {}

        pair_created_at = raw.get("pairCreatedAt")
        age_hours = 99999.0
        if pair_created_at:
            age_hours = max(
                0.0,
                (datetime.now(timezone.utc).timestamp() * 1000 - float(pair_created_at)) / 1000 / 3600,
            )

        txns_h24 = txns.get("h24", {}) or {}
        return TokenPair(
            chain_id=str(raw.get("chainId", "")),
            dex_id=str(raw.get("dexId", "")),
            pair_address=str(raw.get("pairAddress", "")),
            url=str(raw.get("url", "")),
            base_symbol=str(base.get("symbol", "")),
            base_name=str(base.get("name", "")),
            base_address=str(base.get("address", "")),
            quote_symbol=str(quote.get("symbol", "")),
            quote_address=str(quote.get("address", "")),
            price_usd=safe_float(raw.get("priceUsd")),
            fdv=safe_float(raw.get("fdv")),
            market_cap=safe_float(raw.get("marketCap")),
            liquidity_usd=safe_float(liquidity.get("usd")),
            volume_24h=safe_float(volume.get("h24")),
            buys_24h=safe_int(txns_h24.get("buys")),
            sells_24h=safe_int(txns_h24.get("sells")),
            pair_age_hours=age_hours,
            price_change_5m=safe_float(price_change.get("m5")),
            price_change_1h=safe_float(price_change.get("h1")),
            price_change_6h=safe_float(price_change.get("h6")),
            price_change_24h=safe_float(price_change.get("h24")),
            pair_created_at=safe_int(pair_created_at) if pair_created_at else None,
        )
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def fetch_search_pairs(query: str) -> List[TokenPair]:
    if not query.strip():
        return []
    data = http_get_json(f"{DEXSCREENER_BASE}/latest/dex/search/", params={"q": query})
    pairs_raw = data.get("pairs", []) or []
    parsed: List[TokenPair] = []
    for raw in pairs_raw:
        pair = parse_pair(raw)
        if pair:
            parsed.append(pair)
    return parsed


@st.cache_data(ttl=300, show_spinner=False)
def fetch_trending_universe(seed_queries: Tuple[str, ...]) -> List[TokenPair]:
    seen: Dict[str, TokenPair] = {}
    for query in seed_queries:
        try:
            results = fetch_search_pairs(query)
        except Exception:
            results = []

        for pair in results:
            key = f"{pair.chain_id}:{pair.pair_address}"
            if key not in seen or pair.liquidity_usd > seen[key].liquidity_usd:
                seen[key] = pair
    return list(seen.values())


def universe_filter(
    pairs: List[TokenPair],
    min_liquidity: float,
    min_volume_24h: float,
    max_age_hours: float,
    allowed_chains: List[str],
) -> List[TokenPair]:
    filtered: List[TokenPair] = []
    for p in pairs:
        if allowed_chains and p.chain_id not in allowed_chains:
            continue
        if p.liquidity_usd < min_liquidity:
            continue
        if p.volume_24h < min_volume_24h:
            continue
        if p.pair_age_hours > max_age_hours:
            continue
        if p.price_usd <= 0:
            continue
        filtered.append(p)
    return filtered


# ============================================================
# ETHERSCAN V2 ON-CHAIN ENGINE
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def etherscan_v2(
    chainid: str,
    module: str,
    action: str,
    params: Dict[str, Any],
    api_key: str,
) -> Dict[str, Any]:
    if not api_key:
        return {"status": "0", "message": "NO_API_KEY", "result": []}

    merged = {
        "chainid": chainid,
        "module": module,
        "action": action,
        "apikey": api_key,
    }
    merged.update(params)

    try:
        data = http_get_json(ETHERSCAN_V2_BASE, params=merged, timeout=25)
        return data
    except Exception as e:
        return {"status": "0", "message": "ERROR", "result": str(e)}


def get_chainid_for_token(pair: TokenPair) -> Optional[str]:
    return EVM_CHAIN_IDS.get(pair.chain_id)


def is_evm_supported(pair: TokenPair) -> bool:
    return get_chainid_for_token(pair) is not None


def parse_decimal_token_value(raw_value: Any, token_decimal: Any) -> float:
    value = safe_float(raw_value)
    decimals = safe_int(token_decimal, 18)
    try:
        return value / (10 ** decimals)
    except Exception:
        return 0.0


@st.cache_data(ttl=300, show_spinner=False)
def fetch_token_supply(chainid: str, contract_address: str, api_key: str) -> float:
    data = etherscan_v2(
        chainid=chainid,
        module="stats",
        action="tokensupply",
        params={"contractaddress": contract_address},
        api_key=api_key,
    )
    result = data.get("result", "0")
    return safe_float(result, 0.0)


@st.cache_data(ttl=300, show_spinner=False)
def fetch_token_holders(chainid: str, contract_address: str, api_key: str, page: int = 1, offset: int = 100) -> List[Dict[str, Any]]:
    data = etherscan_v2(
        chainid=chainid,
        module="token",
        action="tokenholderlist",
        params={
            "contractaddress": contract_address,
            "page": page,
            "offset": offset,
        },
        api_key=api_key,
    )
    result = data.get("result", [])
    if isinstance(result, list):
        return result
    return []


@st.cache_data(ttl=300, show_spinner=False)
def fetch_wallet_token_transfers(
    chainid: str,
    wallet_address: str,
    contract_address: str,
    api_key: str,
    page: int = 1,
    offset: int = 100,
) -> List[Dict[str, Any]]:
    data = etherscan_v2(
        chainid=chainid,
        module="account",
        action="tokentx",
        params={
            "address": wallet_address,
            "contractaddress": contract_address,
            "page": page,
            "offset": offset,
            "sort": "desc",
        },
        api_key=api_key,
    )
    result = data.get("result", [])
    if isinstance(result, list):
        return result
    return []


def compute_top10_concentration_pct(holder_rows: List[Dict[str, Any]], total_supply_raw: float) -> float:
    if total_supply_raw <= 0:
        return 0.0
    top10_bal = 0.0
    for row in holder_rows[:10]:
        bal = safe_float(row.get("TokenHolderQuantity") or row.get("tokenHolderQuantity"))
        top10_bal += bal
    return round((top10_bal / total_supply_raw) * 100, 2)


def compute_smart_wallet_metrics_from_transfers(
    pair: TokenPair,
    watched_wallets: List[str],
    api_key: str,
) -> Tuple[int, bool, bool, float, List[str]]:
    chainid = get_chainid_for_token(pair)
    if not chainid or not watched_wallets or not api_key:
        return 0, False, False, 0.0, []

    active_wallets = 0
    repeat_buyers = False
    net_positive_wallets = 0
    total_net_units = 0.0
    notes: List[str] = []

    for wallet in watched_wallets[:25]:
        transfers = fetch_wallet_token_transfers(
            chainid=chainid,
            wallet_address=wallet,
            contract_address=pair.base_address,
            api_key=api_key,
            page=1,
            offset=100,
        )
        if not transfers:
            continue

        buys = 0.0
        sells = 0.0
        buy_count = 0
        token_symbol = pair.base_symbol

        for tx in transfers:
            tx_from = str(tx.get("from", "")).lower()
            tx_to = str(tx.get("to", "")).lower()
            token_decimal = tx.get("tokenDecimal", 18)
            value_units = parse_decimal_token_value(tx.get("value", 0), token_decimal)

            if tx_to == wallet:
                buys += value_units
                buy_count += 1
            elif tx_from == wallet:
                sells += value_units

        net_units = buys - sells
        if buys > 0 or sells > 0:
            active_wallets += 1
        if buy_count >= 2:
            repeat_buyers = True
        if net_units > 0:
            net_positive_wallets += 1
        total_net_units += net_units

        if buys > 0 or sells > 0:
            notes.append(
                f"{wallet[:6]}…{wallet[-4:]}: {token_symbol} net {net_units:.2f}"
            )

    net_flow_positive = total_net_units > 0
    holder_growth_proxy = min(15.0, active_wallets * 1.5 + (3.0 if repeat_buyers else 0.0))
    return active_wallets, repeat_buyers, net_flow_positive, holder_growth_proxy, notes[:6]


def build_onchain_metrics(pair: TokenPair, watched_wallets: List[str], api_key: str) -> OnChainMetrics:
    chainid = get_chainid_for_token(pair)
    if not chainid:
        return OnChainMetrics(
            enabled=False,
            chain_supported=False,
            total_supply_raw=0.0,
            holder_rows=[],
            top10_concentration_pct=0.0,
            smart_wallets_active=0,
            repeat_buyers=False,
            net_flow_label="Unavailable",
            smart_wallet_net_units=0.0,
            holder_growth_proxy=0.0,
            notes=["Chain is not wired into the EVM on-chain adapter yet."],
        )

    if not api_key:
        return OnChainMetrics(
            enabled=False,
            chain_supported=True,
            total_supply_raw=0.0,
            holder_rows=[],
            top10_concentration_pct=0.0,
            smart_wallets_active=0,
            repeat_buyers=False,
            net_flow_label="No API key",
            smart_wallet_net_units=0.0,
            holder_growth_proxy=0.0,
            notes=["Add ETHERSCAN_API_KEY to Streamlit secrets to enable real on-chain enrichment."],
        )

    total_supply_raw = fetch_token_supply(chainid, pair.base_address, api_key)
    holder_rows = fetch_token_holders(chainid, pair.base_address, api_key, page=1, offset=100)
    top10_concentration_pct = compute_top10_concentration_pct(holder_rows, total_supply_raw)

    smart_wallets_active, repeat_buyers, net_flow_positive, holder_growth_proxy, wallet_notes = (
        compute_smart_wallet_metrics_from_transfers(pair, watched_wallets, api_key)
    )

    return OnChainMetrics(
        enabled=True,
        chain_supported=True,
        total_supply_raw=total_supply_raw,
        holder_rows=holder_rows,
        top10_concentration_pct=top10_concentration_pct,
        smart_wallets_active=smart_wallets_active,
        repeat_buyers=repeat_buyers,
        net_flow_label="Positive" if net_flow_positive else "Mixed / Flat",
        smart_wallet_net_units=0.0,
        holder_growth_proxy=holder_growth_proxy,
        notes=wallet_notes if wallet_notes else ["No watched-wallet activity detected for this token."],
    )


# ============================================================
# MIRO + INTELLIGENCE
# ============================================================
def estimate_relative_volume(pair: TokenPair) -> float:
    txn_total = pair.buys_24h + pair.sells_24h
    if pair.liquidity_usd <= 0:
        return 0.0
    turnover = pair.volume_24h / max(pair.liquidity_usd, 1.0)
    activity_boost = min(txn_total / 100.0, 5.0)
    return turnover + activity_boost


def estimate_atr_multiple(pair: TokenPair) -> float:
    move = max(abs(pair.price_change_1h), abs(pair.price_change_6h), abs(pair.price_change_24h))
    return move / 4.0


def estimate_range_position(pair: TokenPair) -> float:
    x = 0.5 + (pair.price_change_1h / 20.0) + (pair.price_change_24h / 40.0)
    return max(0.0, min(1.0, x))


def estimate_trend_flags(pair: TokenPair) -> Tuple[bool, bool, float]:
    price_above_fast = pair.price_change_1h > 0
    fast_above_slow = pair.price_change_24h > 0
    adx_proxy = min(40.0, abs(pair.price_change_24h) + abs(pair.price_change_6h) / 2.0)
    return price_above_fast, fast_above_slow, adx_proxy


def estimate_penalties(pair: TokenPair, onchain: OnChainMetrics) -> Tuple[bool, bool, bool]:
    low_liquidity_penalty = pair.liquidity_usd < 100_000
    concentration_penalty = onchain.top10_concentration_pct > 60 if onchain.enabled else (
        pair.market_cap > 0 and pair.fdv > 0 and pair.market_cap < pair.fdv * 0.55
    )
    suspicious_volume_penalty = pair.volume_24h > 0 and pair.liquidity_usd > 0 and (pair.volume_24h / pair.liquidity_usd) > 40
    return low_liquidity_penalty, concentration_penalty, suspicious_volume_penalty


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
    onchain: OnChainMetrics,
) -> SmartMoneySnapshot:
    summary = (
        f"Watched-wallet flow is {onchain.net_flow_label.lower()}, "
        f"{'repeat buys detected' if onchain.repeat_buyers else 'no repeat buys'}, "
        f"holder-growth proxy {onchain.holder_growth_proxy:.1f}."
        if onchain.enabled
        else "On-chain engine not active; using lighter heuristics."
    )

    return SmartMoneySnapshot(
        smart_wallets_active=onchain.smart_wallets_active,
        repeat_buyers=onchain.repeat_buyers,
        net_flow=onchain.net_flow_label,
        holder_growth_24h=onchain.holder_growth_proxy,
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
    onchain: OnChainMetrics,
) -> RiskSummary:
    liquidity = "Weak" if low_liquidity_penalty else "Strong"
    concentration = (
        f"Top10 {onchain.top10_concentration_pct:.1f}%"
        if onchain.enabled and onchain.top10_concentration_pct > 0
        else ("Elevated" if concentration_penalty else "Moderate")
    )
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
                f"{smart_money.smart_wallets_active} watched wallets active. "
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


def build_report_data(pair: TokenPair, watched_wallets: List[str], api_key: str) -> ReportData:
    onchain = build_onchain_metrics(pair, watched_wallets, api_key)

    relative_volume = estimate_relative_volume(pair)
    atr_multiple = estimate_atr_multiple(pair)
    range_position = estimate_range_position(pair)
    price_above_ema20, ema20_above_ema50, adx_strength = estimate_trend_flags(pair)
    low_liquidity_penalty, concentration_penalty, suspicious_volume_penalty = estimate_penalties(pair, onchain)

    breakdown = calculate_miro_v2(
        relative_volume=relative_volume,
        atr_multiple=atr_multiple,
        range_position=range_position,
        price_above_ema20=price_above_ema20,
        ema20_above_ema50=ema20_above_ema50,
        adx_strength=adx_strength,
        smart_wallets_active=onchain.smart_wallets_active,
        repeat_buyers=onchain.repeat_buyers,
        net_flow_positive=onchain.net_flow_label == "Positive",
        holder_growth_24h=onchain.holder_growth_proxy,
        low_liquidity_penalty=low_liquidity_penalty,
        concentration_penalty=concentration_penalty,
        suspicious_volume_penalty=suspicious_volume_penalty,
    )

    miro_total = total_miro_score(breakdown)
    status = score_status(miro_total)
    smart_money = build_smart_money(onchain)
    kronos = build_kronos(
        atr_multiple=atr_multiple,
        adx_strength=adx_strength,
        range_position=range_position,
    )
    risk = build_risk(
        low_liquidity_penalty=low_liquidity_penalty,
        concentration_penalty=concentration_penalty,
        suspicious_volume_penalty=suspicious_volume_penalty,
        onchain=onchain,
    )
    council = build_council(
        smart_money=smart_money,
        kronos=kronos,
        risk=risk,
        breakdown=breakdown,
    )
    verdict_title, verdict_points, action_note = build_verdict(miro_total)

    return ReportData(
        token=pair,
        generated_at=datetime.now().strftime("%d %b %Y | %I:%M %p"),
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
        onchain_metrics=onchain,
    )


# ============================================================
# PDF
# ============================================================
def pdf_header_band(canvas, doc):
    canvas.saveState()
    page_width, page_height = A4
    canvas.setFillColor(colors.HexColor(PDF_BG_HEADER))
    canvas.rect(0, page_height - 28 * mm, page_width, 28 * mm, fill=1, stroke=0)
    canvas.setStrokeColor(colors.HexColor(PDF_RULE))
    canvas.setLineWidth(0.6)
    canvas.line(16 * mm, page_height - 29 * mm, page_width - 16 * mm, page_height - 29 * mm)
    canvas.restoreState()


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
        fontSize=14.5,
        leading=15.5,
        textColor=colors.white,
    )
    report_title_style = ParagraphStyle(
        name="ReportTitleStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12.6,
        leading=13.5,
        textColor=colors.white,
        alignment=TA_RIGHT,
    )
    small_style = ParagraphStyle(
        name="SmallStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.3,
        leading=10.3,
        textColor=colors.HexColor(PDF_MUTED),
    )
    body_style = ParagraphStyle(
        name="BodyStyle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=12.4,
        textColor=colors.HexColor(PDF_TEXT),
    )
    section_style = ParagraphStyle(
        name="SectionStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.1,
        leading=12.2,
        textColor=colors.HexColor(PDF_ORANGE),
        spaceAfter=2,
    )
    verdict_style = ParagraphStyle(
        name="VerdictStyle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12.3,
        leading=14.5,
        textColor=colors.HexColor(PDF_GREEN),
    )

    story = []

    brand_copy = Paragraph(
        f'<font color="#D9E1EC">crypto</font><font color="#7CFF5B">.guru</font><br/><font size="7.4" color="#9AA7B8">{TAGLINE}</font>',
        brand_style,
    )
    report_title = Paragraph("CRYPTO INTELLIGENCE REPORT", report_title_style)
    header_table = Table([[brand_copy, report_title]], colWidths=[92 * mm, 78 * mm])
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
                f"Token: {report.token.base_name} ({report.token.base_symbol}) | "
                f"Chain: {report.token.chain_id} | "
                f"Timeframe: Live | "
                f"Generated: {report.generated_at}"
            ),
            small_style,
        )
    )
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("01 · MIRO v2 SCORE", section_style))
    score_header_table = Table(
        [["", f"{report.miro_total:.1f} / 15", report.status]],
        colWidths=[10 * mm, 32 * mm, 55 * mm],
    )
    score_header_table.setStyle(
        TableStyle(
            [
                ("TEXTCOLOR", (1, 0), (1, 0), colors.HexColor(PDF_GREEN)),
                ("TEXTCOLOR", (2, 0), (2, 0), colors.HexColor(PDF_TEXT)),
                ("FONTNAME", (1, 0), (1, 0), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, 0), "Helvetica-Bold"),
                ("FONTSIZE", (1, 0), (1, 0), 20),
                ("FONTSIZE", (2, 0), (2, 0), 11),
                ("ALIGN", (1, 0), (1, 0), "LEFT"),
                ("ALIGN", (2, 0), (2, 0), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    story.append(score_header_table)

    compact_score_table = Table(
        [
            ["", "Volume", f"{report.breakdown.volume_expansion}/5"],
            ["", "Volatility", f"{report.breakdown.volatility_expansion}/3"],
            ["", "Range", f"{report.breakdown.range_control}/2"],
            ["", "Trend", f"{report.breakdown.trend_quality}/3"],
            ["", "On-Chain", f"{report.breakdown.onchain_confirmation}/4"],
            ["", "Risk", f"-{report.breakdown.risk_penalty}"],
        ],
        colWidths=[10 * mm, 34 * mm, 14 * mm],
    )
    compact_score_table.setStyle(
        TableStyle(
            [
                ("TEXTCOLOR", (1, 0), (-1, -1), colors.HexColor(PDF_TEXT_SOFT)),
                ("FONTNAME", (1, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (1, 0), (-1, -1), 9.5),
                ("ALIGN", (1, 0), (1, -1), "LEFT"),
                ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
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
                f"<b>Holder Growth Proxy:</b> {report.smart_money.holder_growth_24h:.1f}<br/><br/>"
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

    story.append(Paragraph("04 · RISK SUMMARY", section_style))
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

    story.append(Paragraph("05 · FINAL VERDICT", section_style))
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


# ============================================================
# UI COMPONENTS
# ============================================================
def render_brand_header() -> None:
    st.markdown(
        f"""
        <div class="brand-box">
            <div class="brand-title">
                <span style="color:#C2CCD9;">crypto</span><span style="color:{APP_GREEN_SOFT};">.guru</span>
            </div>
            <div class="brand-subtitle">{TAGLINE}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_token_header(report: ReportData) -> None:
    p = report.token
    st.markdown(
        f"""
        <div class="section-box">
            <div class="section-label">Live Signal</div>
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:16px; flex-wrap:wrap;">
                <div>
                    <div style="font-size:1.9rem; font-weight:900; color:{APP_TEXT_STRONG}; letter-spacing:-0.02em;">{p.base_name} <span style="color:{APP_TEXT_MUTED}; font-size:1rem; font-weight:700;">· {p.chain_id}</span></div>
                    <div class="small-note">{report.generated_at} · Price: ${p.price_usd:,.6f} · Liquidity: {human_usd(p.liquidity_usd)} · Vol 24H: {human_usd(p.volume_24h)}</div>
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

    st.markdown('<div class="section-box"><div class="section-label">01 · Miro v2 Breakdown</div>', unsafe_allow_html=True)
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


def render_onchain_panel(report: ReportData) -> None:
    o = report.onchain_metrics
    st.markdown('<div class="section-box"><div class="section-label">02 · On-Chain Engine</div>', unsafe_allow_html=True)

    st.write(f"**Engine Enabled:** {'Yes' if o.enabled else 'No'}")
    st.write(f"**Chain Supported:** {'Yes' if o.chain_supported else 'No'}")
    st.write(f"**Watched Wallets Active:** {o.smart_wallets_active}")
    st.write(f"**Repeat Buyers:** {'Detected' if o.repeat_buyers else 'No'}")
    st.write(f"**Net Flow:** {o.net_flow_label}")
    if o.enabled and o.top10_concentration_pct > 0:
        st.write(f"**Top 10 Holder Concentration:** {o.top10_concentration_pct:.2f}%")

    if o.notes:
        st.markdown("**Notes:**")
        for note in o.notes:
            st.markdown(f"- {note}")

    st.markdown("</div>", unsafe_allow_html=True)


def render_smart_money(report: ReportData) -> None:
    s = report.smart_money
    st.markdown('<div class="section-box"><div class="section-label">03 · Smart Money Snapshot</div>', unsafe_allow_html=True)
    st.write(f"**Active Smart Wallets:** {s.smart_wallets_active}")
    st.write(f"**Repeat Buyers:** {'Detected' if s.repeat_buyers else 'No'}")
    st.write(f"**Net Flow:** {s.net_flow}")
    st.write(f"**Holder Growth Proxy:** {s.holder_growth_24h:.1f}")
    st.caption(s.summary)
    st.markdown("</div>", unsafe_allow_html=True)


def render_kronos(report: ReportData) -> None:
    k = report.kronos
    st.markdown('<div class="section-box"><div class="section-label">04 · Market Structure</div>', unsafe_allow_html=True)
    st.write(f"**Regime:** {k.regime}")
    st.write(f"**Bias:** {k.bias}")
    st.write(f"**Confidence:** {k.confidence}%")
    st.caption(k.summary)
    st.markdown("</div>", unsafe_allow_html=True)


def render_council(report: ReportData) -> None:
    st.markdown('<div class="section-box"><div class="section-label">05 · AI Council</div>', unsafe_allow_html=True)
    for agent in report.council:
        st.markdown(
            f"""
            <div class="agent-box">
                <div class="agent-title">{agent.emoji} {agent.name}</div>
                <div style="color:#C2CCD9; font-weight:600;">{agent.text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def render_risk(report: ReportData) -> None:
    r = report.risk
    st.markdown('<div class="section-box"><div class="section-label">06 · Risk Summary</div>', unsafe_allow_html=True)
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
            <div class="section-label" style="margin-bottom:0.45rem;">07 · Final Verdict</div>
            <div style="font-size:1.2rem; font-weight:900; color:{APP_GREEN_SOFT}; margin-bottom:0.55rem; letter-spacing:-0.01em;">{report.verdict_title}</div>
            <ul style="margin-top:0.15rem; margin-bottom:0.7rem; color:#C2CCD9; font-weight:600;">{bullets}</ul>
            <div style="color:{APP_TEXT_STRONG};"><b>Recommended Action:</b> {report.action_note}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# MAIN
# ============================================================
def main() -> None:
    inject_css()
    render_brand_header()

    with st.sidebar:
        st.header("Live Engine Controls")

        seed_query_string = st.text_area(
            "Seed Queries",
            value="SOL\nETH\nBASE\nPEPE\nDOGE\nAI\nMEME\nDEFI\nBTC",
            height=180,
        )
        seed_queries = tuple([q.strip() for q in seed_query_string.splitlines() if q.strip()])

        allowed_chains = st.multiselect(
            "Chains",
            options=["ethereum", "solana", "base", "bsc", "arbitrum", "polygon", "avalanche", "optimism"],
            default=["ethereum", "base", "bsc", "arbitrum", "polygon", "optimism"],
        )

        min_liquidity = st.number_input("Min Liquidity ($)", min_value=0, value=100000, step=10000)
        min_volume_24h = st.number_input("Min 24H Volume ($)", min_value=0, value=250000, step=25000)
        max_age_hours = st.number_input("Max Pair Age (hours)", min_value=1, value=24 * 14, step=24)
        max_results = st.slider("Max Ranked Signals", min_value=10, max_value=200, value=40, step=10)

        st.subheader("On-Chain")
        watched_wallets_text = st.text_area(
            "Watched Smart Wallets (one per line)",
            value="",
            height=160,
            help="Paste EVM wallet addresses you want tracked for token accumulation.",
        )
        watched_wallets = parse_csv_wallets(watched_wallets_text)

        refresh_now = st.button("Refresh Live Universe", use_container_width=True)

    if refresh_now:
        st.cache_data.clear()

    api_key = get_etherscan_api_key()

    with st.spinner("Building live universe..."):
        try:
            universe = fetch_trending_universe(seed_queries)
        except Exception as e:
            st.error(f"Failed to fetch live universe: {e}")
            return

    filtered = universe_filter(
        pairs=universe,
        min_liquidity=float(min_liquidity),
        min_volume_24h=float(min_volume_24h),
        max_age_hours=float(max_age_hours),
        allowed_chains=allowed_chains,
    )

    reports: List[ReportData] = [build_report_data(pair, watched_wallets, api_key) for pair in filtered]
    reports.sort(key=lambda r: (r.miro_total, r.token.volume_24h, r.token.liquidity_usd), reverse=True)
    reports = reports[:max_results]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Live Universe", len(universe))
    c2.metric("Filtered Candidates", len(filtered))
    c3.metric("Ranked Signals", len(reports))
    c4.metric("Etherscan Key", "Loaded" if api_key else "Missing")

    if not reports:
        st.warning("No live candidates matched your filters.")
        return

    st.markdown('<div class="section-box"><div class="section-label">Live Signal Board</div>', unsafe_allow_html=True)

    options = {
        f"{r.token.base_symbol} · {r.token.chain_id} · Score {r.miro_total:.1f} · Vol {human_usd(r.token.volume_24h)}": i
        for i, r in enumerate(reports)
    }
    selected_label = st.selectbox("Select Signal", list(options.keys()))
    selected_report = reports[options[selected_label]]

    rows: List[Dict[str, Any]] = []
    for r in reports:
        rows.append(
            {
                "symbol": r.token.base_symbol,
                "chain": r.token.chain_id,
                "score": r.miro_total,
                "status": r.status,
                "price": r.token.price_usd,
                "liq": r.token.liquidity_usd,
                "vol24h": r.token.volume_24h,
                "chg1h": r.token.price_change_1h,
                "chg24h": r.token.price_change_24h,
                "age_h": round(r.token.pair_age_hours, 1),
            }
        )

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
        column_config={
            "symbol": "Symbol",
            "chain": "Chain",
            "score": st.column_config.NumberColumn("Score", format="%.1f"),
            "status": "Status",
            "price": st.column_config.NumberColumn("Price", format="$%.6f"),
            "liq": st.column_config.NumberColumn("Liquidity", format="$%.0f"),
            "vol24h": st.column_config.NumberColumn("24H Volume", format="$%.0f"),
            "chg1h": st.column_config.NumberColumn("1H %", format="%.2f%%"),
            "chg24h": st.column_config.NumberColumn("24H %", format="%.2f%%"),
            "age_h": st.column_config.NumberColumn("Age (h)", format="%.1f"),
        },
    )
    st.markdown("</div>", unsafe_allow_html=True)

    render_token_header(selected_report)

    left_col, right_col = st.columns([1.1, 0.9])

    with left_col:
        render_breakdown(selected_report)
        render_onchain_panel(selected_report)
        render_smart_money(selected_report)
        render_kronos(selected_report)

        st.markdown('<div class="section-box"><div class="section-label">Pair Snapshot</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <span class="signal-chip">DEX: {selected_report.token.dex_id}</span>
            <span class="signal-chip">Pair Age: {selected_report.token.pair_age_hours:.1f}h</span>
            <span class="signal-chip">1H: {format_pct(selected_report.token.price_change_1h)}</span>
            <span class="signal-chip">24H: {format_pct(selected_report.token.price_change_24h)}</span>
            <span class="signal-chip">Liquidity: {human_usd(selected_report.token.liquidity_usd)}</span>
            <span class="signal-chip">Volume: {human_usd(selected_report.token.volume_24h)}</span>
            """,
            unsafe_allow_html=True,
        )
        if selected_report.token.url:
            st.markdown(f"[Open pair on Dexscreener]({selected_report.token.url})")
        st.markdown("</div>", unsafe_allow_html=True)

    with right_col:
        render_council(selected_report)
        render_risk(selected_report)
        render_verdict(selected_report)

        pdf_bytes = build_pdf(selected_report)
        filename = (
            f"{selected_report.token.base_symbol}_"
            f"{selected_report.token.chain_id}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )

        st.download_button(
            label="Download Intelligence Report (PDF)",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=True,
        )

    st.markdown(f'<div class="footer-note">{BRAND_NAME} · {TAGLINE}</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
