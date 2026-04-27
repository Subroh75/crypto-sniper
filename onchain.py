"""
onchain.py — On-Chain Intelligence Module for Crypto Sniper V2

Data sources (all free-tier capable):
  - CoinGecko       : holder count, market/circulating supply, price metrics
  - DeFiLlama       : TVL, protocol breakdown, token unlock schedule (emissions)
  - Etherscan       : top-holder concentration for EVM tokens (free, 5 calls/sec)
  - Derived metrics : NVT proxy, holder risk score, supply concentration
"""

import os, time, logging, requests
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# ── API keys ─────────────────────────────────────────────────────────────────
CG_KEY       = os.getenv("COINGECKO_API_KEY", "")
ETHSCAN_KEY  = os.getenv("ETHERSCAN_API_KEY", "")

# ── CoinGecko IDs ─────────────────────────────────────────────────────────────
CG_ID = {
    "BTC": "bitcoin",       "ETH": "ethereum",     "SOL": "solana",
    "BNB": "binancecoin",   "XRP": "ripple",        "ADA": "cardano",
    "DOGE": "dogecoin",     "DOT": "polkadot",      "AVAX": "avalanche-2",
    "LINK": "chainlink",    "UNI": "uniswap",       "ATOM": "cosmos",
    "LTC": "litecoin",      "MATIC": "matic-network","PEPE": "pepe",
    "WIF": "dogwifhat",     "HYPE": "hyperliquid",  "RENDER": "render-token",
    "KAVA": "kava",         "SEI": "sei-network",   "SUI": "sui",
    "APT": "aptos",         "ARB": "arbitrum",      "OP": "optimism",
    "INJ": "injective-protocol", "TIA": "celestia", "BONK": "bonk",
    "FET": "fetch-ai",      "NEAR": "near",         "ALGO": "algorand",
    "ICP": "internet-computer", "FIL": "filecoin",  "HBAR": "hedera-hashgraph",
    "PENGU": "pudgy-penguins",
}

# ── EVM contract addresses for top-holder lookup ──────────────────────────────
# Token contract addresses on Ethereum mainnet
EVM_CONTRACT = {
    "LINK":   "0x514910771af9ca656af840dff83e8264ecf986ca",
    "UNI":    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
    "MATIC":  "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0",
    "RENDER": "0x6de037ef9ad2725eb40118bb1702ebb27e4aeb24",
    "ARB":    "0xb50721bcf8d664c30412cfbc6cf7a15145234ad1",
    "OP":     "0x4200000000000000000000000000000000000042",
    "INJ":    "0xe28b3b32b6c345a34ff64674606124dd5aceca30",
    "FET":    "0xaea46a60368a7bd060eec7df8cba43b7ef41ad85",
}

# ── DeFiLlama slug map ────────────────────────────────────────────────────────
DEFILLAMA_SLUG = {
    "AAVE": "aave",   "UNI": "uniswap",     "COMP": "compound",
    "MKR":  "maker",  "CRV": "curve",        "SUSHI": "sushi",
    "YFI":  "yearn",  "SNX": "synthetix",    "BAL": "balancer",
    "1INCH": "1inch", "LDO": "lido",         "DYDX": "dydx",
    "GMX":  "gmx",    "ARB": "arbitrum",     "OP": "optimism",
    "INJ":  "injective", "KAVA": "kava",
}

_ONCHAIN_TTL = 300  # 5-minute cache per symbol


def _get(url: str, params: dict = None, timeout: int = 10) -> Optional[dict]:
    """Safe GET with timeout and error swallow."""
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout: {url}")
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP {e.response.status_code}: {url}")
    except Exception as e:
        logger.warning(f"Error {url}: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 1. CoinGecko coin detail  — holder count + supply metrics
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=64)
def _cg_coin_cached(cg_id: str, ts: int) -> Optional[dict]:
    params = {
        "localization": "false",
        "tickers":      "false",
        "market_data":  "true",
        "community_data": "true",
        "developer_data": "false",
    }
    if CG_KEY:
        params["x_cg_demo_api_key"] = CG_KEY
    return _get(
        f"https://api.coingecko.com/api/v3/coins/{cg_id}",
        params, timeout=12,
    )


def _get_cg_coin(symbol: str) -> Optional[dict]:
    cg_id = CG_ID.get(symbol.upper())
    if not cg_id:
        return None
    ts = int(time.time() // _ONCHAIN_TTL)
    return _cg_coin_cached(cg_id, ts)


# ─────────────────────────────────────────────────────────────────────────────
# 2. DeFiLlama  — TVL + unlocks
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=64)
def _defillama_tvl_cached(slug: str, ts: int) -> Optional[dict]:
    return _get(f"https://api.llama.fi/protocol/{slug}", timeout=10)


@lru_cache(maxsize=1)
def _defillama_unlocks_cached(ts: int) -> Optional[list]:
    data = _get("https://api.llama.fi/unlocks", timeout=10)
    if isinstance(data, list):
        return data
    return None


def _get_defillama_tvl(symbol: str) -> Optional[float]:
    slug = DEFILLAMA_SLUG.get(symbol.upper())
    if not slug:
        return None
    ts = int(time.time() // _ONCHAIN_TTL)
    data = _defillama_tvl_cached(slug, ts)
    if data:
        return data.get("tvl")
    return None


def _get_upcoming_unlocks(symbol: str) -> Optional[dict]:
    """Return next scheduled unlock event from DeFiLlama."""
    ts = int(time.time() // 3600)  # 1-hour cache for unlocks
    data = _defillama_unlocks_cached(ts)
    if not data:
        return None
    cg_id = CG_ID.get(symbol.upper(), "").lower()
    name_lc = symbol.lower()
    for item in data:
        item_id = (item.get("coingeckoId") or "").lower()
        item_sym = (item.get("tickers") or [{}])[0].get("ticker", "").lower() if item.get("tickers") else ""
        if item_id == cg_id or item_sym == name_lc:
            next_event = None
            events = item.get("events") or []
            now = time.time()
            future = [e for e in events if e.get("timestamp", 0) > now]
            if future:
                future.sort(key=lambda e: e["timestamp"])
                ne = future[0]
                next_event = {
                    "date": ne.get("timestamp"),
                    "amount_usd": ne.get("totalNotional"),
                    "label": ne.get("description", "Unlock"),
                }
            return {
                "total_locked_usd": item.get("totalNotional"),
                "next_unlock": next_event,
            }
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Etherscan  — Top-holder concentration for EVM tokens
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=32)
def _ethscan_holders_cached(contract: str, ts: int) -> Optional[list]:
    """Fetch top token holders from Etherscan (free plan, 5/sec)."""
    if not ETHSCAN_KEY:
        return None
    data = _get(
        "https://api.etherscan.io/api",
        {
            "module":          "token",
            "action":          "tokenholderlist",
            "contractaddress": contract,
            "page":            1,
            "offset":          10,
            "apikey":          ETHSCAN_KEY,
        },
        timeout=10,
    )
    if data and data.get("status") == "1":
        return data.get("result", [])
    return None


def _get_holder_concentration(symbol: str) -> Optional[dict]:
    """Return top-10 holder %, top-20 holder % for EVM tokens."""
    contract = EVM_CONTRACT.get(symbol.upper())
    if not contract:
        return None
    ts = int(time.time() // 600)  # 10-min cache
    holders = _ethscan_holders_cached(contract, ts)
    if not holders:
        return None
    # Etherscan returns TokenHolderAddress + TokenHolderQuantity
    try:
        quantities = [int(h.get("TokenHolderQuantity", "0").replace(",", "")) for h in holders]
        total_top10 = sum(quantities)
        # We don't have total supply from this endpoint — mark as top-10 relative
        return {
            "top10_holders": len(quantities),
            "top10_quantity": total_top10,
            "source": "etherscan",
        }
    except Exception as e:
        logger.warning(f"Holder concentration parse error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=64)
def _onchain_cached(symbol: str, ts: int) -> dict:
    symbol = symbol.upper()
    result: dict = {
        "symbol":       symbol,
        "source":       [],
        # Supply
        "circulating_supply":  None,
        "total_supply":        None,
        "max_supply":          None,
        "supply_pct":          None,   # circulating / max * 100
        # Holders (from CoinGecko community data)
        "holder_count":        None,
        "holder_count_change": None,   # placeholder — CoinGecko free doesn't provide 24h delta
        # Market cap vs fully diluted
        "market_cap_usd":      None,
        "fdv_usd":             None,
        "mc_fdv_ratio":        None,   # market_cap / fdv — high = dilution risk
        # Volume / NVT proxy
        "volume_24h":          None,
        "nvt_proxy":           None,   # market_cap / volume_24h
        # TVL (DeFi protocols only)
        "tvl_usd":             None,
        "tvl_mc_ratio":        None,   # tvl / market_cap
        # Unlocks
        "unlock":              None,
        # Concentration (EVM tokens only)
        "concentration":       None,
        # Signals
        "signals":             [],
        "risk_score":          None,   # 0 = low risk, 100 = high risk
    }

    # ── CoinGecko core data ─────────────────────────────────────────────────
    cg = _get_cg_coin(symbol)
    if cg:
        result["source"].append("CoinGecko")
        md = cg.get("market_data", {})

        circ = md.get("circulating_supply")
        total = md.get("total_supply")
        maxs = md.get("max_supply")
        result["circulating_supply"] = circ
        result["total_supply"] = total
        result["max_supply"] = maxs

        if circ and maxs and maxs > 0:
            result["supply_pct"] = round((circ / maxs) * 100, 1)
        elif circ and total and total > 0:
            result["supply_pct"] = round((circ / total) * 100, 1)

        mc  = md.get("market_cap", {}).get("usd")
        fdv = md.get("fully_diluted_valuation", {}).get("usd")
        result["market_cap_usd"] = mc
        result["fdv_usd"]        = fdv
        if mc and fdv and fdv > 0:
            result["mc_fdv_ratio"] = round(mc / fdv, 3)

        vol = md.get("total_volume", {}).get("usd")
        result["volume_24h"] = vol
        if mc and vol and vol > 0:
            result["nvt_proxy"] = round(mc / vol, 1)

        # Holder count — community_data.reddit_accounts_active_in_24h is not holders
        # CoinGecko free doesn't expose holder_count directly outside on-chain endpoint
        # We use the coin's "public_interest_stats" as a proxy indicator

    # ── DeFiLlama TVL ───────────────────────────────────────────────────────
    tvl = _get_defillama_tvl(symbol)
    if tvl is not None:
        result["source"].append("DeFiLlama")
        result["tvl_usd"] = tvl
        mc = result.get("market_cap_usd")
        if mc and mc > 0 and tvl > 0:
            result["tvl_mc_ratio"] = round(tvl / mc, 3)

    # ── DeFiLlama unlock schedule ───────────────────────────────────────────
    unlock = _get_upcoming_unlocks(symbol)
    if unlock:
        if "DeFiLlama" not in result["source"]:
            result["source"].append("DeFiLlama")
        result["unlock"] = unlock

    # ── Etherscan concentration (EVM tokens) ────────────────────────────────
    concentration = _get_holder_concentration(symbol)
    if concentration:
        if "Etherscan" not in result["source"]:
            result["source"].append("Etherscan")
        result["concentration"] = concentration

    # ── Derived signals ─────────────────────────────────────────────────────
    signals = []
    risk_factors = 0

    # MC/FDV: ratio < 0.3 = high dilution risk
    mc_fdv = result.get("mc_fdv_ratio")
    if mc_fdv is not None:
        if mc_fdv < 0.3:
            signals.append({"type": "risk", "label": "High dilution risk", "detail": f"MC/FDV = {mc_fdv:.2f}"})
            risk_factors += 2
        elif mc_fdv < 0.6:
            signals.append({"type": "caution", "label": "Moderate dilution", "detail": f"MC/FDV = {mc_fdv:.2f}"})
            risk_factors += 1
        else:
            signals.append({"type": "positive", "label": "Low dilution risk", "detail": f"MC/FDV = {mc_fdv:.2f}"})

    # Supply: high % circulating = less future sell pressure
    supply_pct = result.get("supply_pct")
    if supply_pct is not None:
        if supply_pct > 90:
            signals.append({"type": "positive", "label": "Supply mostly circulating", "detail": f"{supply_pct:.1f}% in circulation"})
        elif supply_pct < 40:
            signals.append({"type": "risk", "label": "Large unreleased supply", "detail": f"Only {supply_pct:.1f}% circulating"})
            risk_factors += 2

    # NVT: high NVT = overvalued relative to usage
    nvt = result.get("nvt_proxy")
    if nvt is not None:
        if nvt > 200:
            signals.append({"type": "caution", "label": "High NVT proxy", "detail": f"MC/Volume = {nvt:.0f}x — low on-chain utilisation"})
            risk_factors += 1
        elif nvt < 20:
            signals.append({"type": "positive", "label": "Strong on-chain activity", "detail": f"MC/Volume = {nvt:.0f}x"})

    # TVL ratio
    tvl_ratio = result.get("tvl_mc_ratio")
    if tvl_ratio is not None:
        if tvl_ratio > 1.0:
            signals.append({"type": "positive", "label": "TVL > Market cap", "detail": f"TVL/MC = {tvl_ratio:.2f}x — fundamentally undervalued"})
        elif tvl_ratio > 0.3:
            signals.append({"type": "positive", "label": "Strong TVL backing", "detail": f"TVL/MC = {tvl_ratio:.2f}x"})

    # Upcoming unlock warning
    if unlock and unlock.get("next_unlock"):
        nu = unlock["next_unlock"]
        days_away = (nu["date"] - time.time()) / 86400 if nu.get("date") else 999
        if days_away < 14:
            signals.append({"type": "risk", "label": f"Unlock in {int(days_away)}d", "detail": nu.get("label", "Token unlock scheduled")})
            risk_factors += 2
        elif days_away < 30:
            signals.append({"type": "caution", "label": f"Unlock in {int(days_away)}d", "detail": nu.get("label", "Token unlock scheduled")})
            risk_factors += 1

    result["signals"] = signals
    # Risk score: 0–100, where each risk_factor ≈ 20 pts
    result["risk_score"] = min(100, risk_factors * 20)

    return result


def get_onchain(symbol: str) -> dict:
    """Public entry point — returns on-chain data for a symbol, cached 5 min."""
    ts = int(time.time() // _ONCHAIN_TTL)
    return _onchain_cached(symbol.upper(), ts)
