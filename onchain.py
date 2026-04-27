"""
onchain.py — On-Chain Intelligence Module for Crypto Sniper V2

Data sources (all free-tier capable):
  - CoinGecko /coins/markets  : supply, FDV, volume, market cap (batch-friendly, not rate-limited)
  - DeFiLlama                 : TVL for DeFi protocols + token unlock schedule
  - Etherscan                 : top-holder concentration for EVM tokens (needs key)
  - Derived metrics           : NVT proxy, MC/FDV ratio, risk score
"""

import os, time, logging, requests
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

# ── API keys ─────────────────────────────────────────────────────────────────
CG_KEY      = os.getenv("COINGECKO_API_KEY", "")
ETHSCAN_KEY = os.getenv("ETHERSCAN_API_KEY", "")

# ── CoinGecko IDs ─────────────────────────────────────────────────────────────
CG_ID: dict[str, str] = {
    "BTC":   "bitcoin",            "ETH":  "ethereum",
    "SOL":   "solana",             "BNB":  "binancecoin",
    "XRP":   "ripple",             "ADA":  "cardano",
    "DOGE":  "dogecoin",           "DOT":  "polkadot",
    "AVAX":  "avalanche-2",        "LINK": "chainlink",
    "UNI":   "uniswap",            "ATOM": "cosmos",
    "LTC":   "litecoin",           "MATIC":"matic-network",
    "PEPE":  "pepe",               "WIF":  "dogwifhat",
    "HYPE":  "hyperliquid",        "RENDER":"render-token",
    "KAVA":  "kava",               "SEI":  "sei-network",
    "SUI":   "sui",                "APT":  "aptos",
    "ARB":   "arbitrum",           "OP":   "optimism",
    "INJ":   "injective-protocol", "TIA":  "celestia",
    "BONK":  "bonk",               "FET":  "fetch-ai",
    "NEAR":  "near",               "ALGO": "algorand",
    "ICP":   "internet-computer",  "FIL":  "filecoin",
    "HBAR":  "hedera-hashgraph",   "PENGU":"pudgy-penguins",
    "TON":   "the-open-network",   "SHIB": "shiba-inu",
    "NOT":   "notcoin",            "DOGS": "dogs-2",
    "STRK":  "starknet",           "BLUR": "blur",
    "LDO":   "lido-dao",           "MKR":  "maker",
    "AAVE":  "aave",               "SNX":  "havven",
    "CRV":   "curve-dao-token",    "GMX":  "gmx",
    "JUP":   "jupiter-exchange-solana",
    "PYTH":  "pyth-network",
    "WLD":   "worldcoin-wld",
    "ORDI":  "ordinals",
    "TAO":   "bittensor",
    "ENA":   "ethena",
    "EIGEN": "eigenlayer",
}

# ── EVM contract addresses for Etherscan top-holder lookup ───────────────────
EVM_CONTRACT: dict[str, str] = {
    "LINK":   "0x514910771af9ca656af840dff83e8264ecf986ca",
    "UNI":    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984",
    "MATIC":  "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0",
    "RENDER": "0x6de037ef9ad2725eb40118bb1702ebb27e4aeb24",
    "ARB":    "0xb50721bcf8d664c30412cfbc6cf7a15145234ad1",
    "OP":     "0x4200000000000000000000000000000000000042",
    "INJ":    "0xe28b3b32b6c345a34ff64674606124dd5aceca30",
    "FET":    "0xaea46a60368a7bd060eec7df8cba43b7ef41ad85",
    "LDO":    "0x5a98fcbea516cf06857215779fd812ca3bef1b32",
    "AAVE":   "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9",
    "MKR":    "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2",
    "CRV":    "0xd533a949740bb3306d119cc777fa900ba034cd52",
    "BLUR":   "0x5283d291dbcf85356a21ba090e6db59121208b44",
    "LDO":    "0x5a98fcbea516cf06857215779fd812ca3bef1b32",
}

# ── DeFiLlama slugs for TVL lookup ────────────────────────────────────────────
DEFILLAMA_SLUG: dict[str, str] = {
    "AAVE":  "aave",     "UNI":   "uniswap",   "COMP":  "compound",
    "MKR":   "maker",    "CRV":   "curve",      "SUSHI": "sushi",
    "YFI":   "yearn",    "SNX":   "synthetix",  "BAL":   "balancer",
    "1INCH": "1inch",    "LDO":   "lido",       "DYDX":  "dydx",
    "GMX":   "gmx",      "ARB":   "arbitrum",   "OP":    "optimism",
    "INJ":   "injective","KAVA":  "kava",       "JUP":   "jupiter",
    "ENA":   "ethena",
}

_ONCHAIN_TTL   = 300   # 5-min cache
_MARKET_TTL    = 300   # 5-min cache for batch market data
_UNLOCKS_TTL   = 3600  # 1-hour cache for unlock schedule


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
def _get(url: str, params: dict = None, timeout: int = 10) -> Optional[dict | list]:
    """Safe GET — returns None on any failure, never raises."""
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
# 1.  CoinGecko /coins/markets  — batched, NOT per-symbol
#     Returns a dict keyed by CoinGecko id for quick lookup.
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=4)
def _cg_markets_cached(ids_key: str, ts: int) -> dict[str, dict]:
    """Fetch market data for a comma-separated list of CoinGecko IDs."""
    params: dict = {
        "vs_currency":            "usd",
        "ids":                    ids_key,
        "order":                  "market_cap_desc",
        "per_page":               "250",
        "page":                   "1",
        "sparkline":              "false",
        "price_change_percentage":"24h",
    }
    if CG_KEY:
        params["x_cg_demo_api_key"] = CG_KEY

    data = _get(
        "https://api.coingecko.com/api/v3/coins/markets",
        params, timeout=15,
    )
    if not isinstance(data, list):
        return {}
    return {item["id"]: item for item in data if "id" in item}


# Pre-built sorted key of all known CG IDs (stable → good cache key)
_ALL_CG_IDS_KEY = ",".join(sorted(set(CG_ID.values())))


def _get_cg_market(symbol: str) -> Optional[dict]:
    """Return the CoinGecko market row for a symbol (from batch cache)."""
    cg_id = CG_ID.get(symbol.upper())
    if not cg_id:
        return None
    ts = int(time.time() // _MARKET_TTL)
    market_map = _cg_markets_cached(_ALL_CG_IDS_KEY, ts)
    return market_map.get(cg_id)


# ─────────────────────────────────────────────────────────────────────────────
# 2.  DeFiLlama — TVL + unlock schedule
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=64)
def _defillama_tvl_cached(slug: str, ts: int) -> Optional[float]:
    data = _get(f"https://api.llama.fi/protocol/{slug}", timeout=10)
    if isinstance(data, dict):
        tvl = data.get("tvl")
        if isinstance(tvl, (int, float)):
            return float(tvl)
        # tvl can also be a list of {date, totalLiquidityUSD}
        if isinstance(tvl, list) and tvl:
            return float(tvl[-1].get("totalLiquidityUSD", 0))
    return None


@lru_cache(maxsize=1)
def _defillama_unlocks_cached(ts: int) -> list:
    data = _get("https://api.llama.fi/unlocks", timeout=12)
    return data if isinstance(data, list) else []


def _get_defillama_tvl(symbol: str) -> Optional[float]:
    slug = DEFILLAMA_SLUG.get(symbol.upper())
    if not slug:
        return None
    ts = int(time.time() // _ONCHAIN_TTL)
    return _defillama_tvl_cached(slug, ts)


def _get_upcoming_unlocks(symbol: str) -> Optional[dict]:
    ts = int(time.time() // _UNLOCKS_TTL)
    items = _defillama_unlocks_cached(ts)
    if not items:
        return None
    cg_id   = CG_ID.get(symbol.upper(), "").lower()
    sym_lc  = symbol.lower()
    for item in items:
        item_cg  = (item.get("coingeckoId") or "").lower()
        tickers  = item.get("tickers") or []
        item_sym = tickers[0].get("ticker", "").lower() if tickers else ""
        if item_cg == cg_id or item_sym == sym_lc:
            events   = item.get("events") or []
            now      = time.time()
            future   = sorted(
                [e for e in events if e.get("timestamp", 0) > now],
                key=lambda e: e["timestamp"],
            )
            next_event = None
            if future:
                ne = future[0]
                next_event = {
                    "date":       ne.get("timestamp"),
                    "amount_usd": ne.get("totalNotional"),
                    "label":      ne.get("description", "Token Unlock"),
                }
            return {
                "total_locked_usd": item.get("totalNotional"),
                "next_unlock":      next_event,
            }
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 3.  Etherscan — top holder concentration (EVM tokens only)
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=32)
def _ethscan_holders_cached(contract: str, ts: int) -> Optional[list]:
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
    if isinstance(data, dict) and data.get("status") == "1":
        return data.get("result") or []
    return None


def _get_holder_concentration(symbol: str) -> Optional[dict]:
    contract = EVM_CONTRACT.get(symbol.upper())
    if not contract:
        return None
    ts      = int(time.time() // 600)
    holders = _ethscan_holders_cached(contract, ts)
    if not holders:
        return None
    try:
        quantities = [
            int(h.get("TokenHolderQuantity", "0").replace(",", ""))
            for h in holders
        ]
        return {
            "top10_holders":  len(quantities),
            "top10_quantity": sum(quantities),
            "source":         "etherscan",
        }
    except Exception as e:
        logger.warning(f"Holder concentration parse error: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 4.  Main orchestrator
# ─────────────────────────────────────────────────────────────────────────────
@lru_cache(maxsize=128)
def _onchain_cached(symbol: str, ts: int) -> dict:
    symbol = symbol.upper()
    result: dict = {
        "symbol":             symbol,
        "source":             [],
        "circulating_supply": None,
        "total_supply":       None,
        "max_supply":         None,
        "supply_pct":         None,
        "holder_count":       None,
        "holder_count_change":None,
        "market_cap_usd":     None,
        "fdv_usd":            None,
        "mc_fdv_ratio":       None,
        "volume_24h":         None,
        "nvt_proxy":          None,
        "tvl_usd":            None,
        "tvl_mc_ratio":       None,
        "unlock":             None,
        "concentration":      None,
        "signals":            [],
        "risk_score":         None,
    }

    # ── CoinGecko markets batch ─────────────────────────────────────────────
    cg = _get_cg_market(symbol)
    if cg:
        result["source"].append("CoinGecko")

        circ  = cg.get("circulating_supply")
        total = cg.get("total_supply")
        maxs  = cg.get("max_supply")
        result["circulating_supply"] = circ
        result["total_supply"]       = total
        result["max_supply"]         = maxs

        if circ and maxs and maxs > 0:
            result["supply_pct"] = round((circ / maxs) * 100, 1)
        elif circ and total and total > 0:
            result["supply_pct"] = round((circ / total) * 100, 1)

        mc  = cg.get("market_cap")
        fdv = cg.get("fully_diluted_valuation")
        result["market_cap_usd"] = mc
        result["fdv_usd"]        = fdv
        if mc and fdv and fdv > 0:
            result["mc_fdv_ratio"] = round(mc / fdv, 3)

        vol = cg.get("total_volume")
        result["volume_24h"] = vol
        if mc and vol and vol > 0:
            result["nvt_proxy"] = round(mc / vol, 1)

    # ── DeFiLlama TVL ───────────────────────────────────────────────────────
    tvl = _get_defillama_tvl(symbol)
    if tvl is not None:
        result["source"].append("DeFiLlama")
        result["tvl_usd"] = tvl
        mc = result.get("market_cap_usd")
        if mc and mc > 0 and tvl > 0:
            result["tvl_mc_ratio"] = round(tvl / mc, 3)

    # ── Unlock schedule ─────────────────────────────────────────────────────
    unlock = _get_upcoming_unlocks(symbol)
    if unlock:
        if "DeFiLlama" not in result["source"]:
            result["source"].append("DeFiLlama")
        result["unlock"] = unlock

    # ── Etherscan concentration ─────────────────────────────────────────────
    concentration = _get_holder_concentration(symbol)
    if concentration:
        if "Etherscan" not in result["source"]:
            result["source"].append("Etherscan")
        result["concentration"] = concentration

    # ── Derived signals ─────────────────────────────────────────────────────
    signals:   list[dict] = []
    risk_pts:  int        = 0

    mc_fdv = result.get("mc_fdv_ratio")
    if mc_fdv is not None:
        if mc_fdv < 0.3:
            signals.append({"type": "risk",     "label": "High dilution risk",    "detail": f"MC/FDV = {mc_fdv:.0%}"})
            risk_pts += 2
        elif mc_fdv < 0.6:
            signals.append({"type": "caution",  "label": "Moderate dilution",     "detail": f"MC/FDV = {mc_fdv:.0%}"})
            risk_pts += 1
        else:
            signals.append({"type": "positive", "label": "Low dilution risk",     "detail": f"MC/FDV = {mc_fdv:.0%}"})

    supply_pct = result.get("supply_pct")
    if supply_pct is not None:
        if supply_pct > 90:
            signals.append({"type": "positive", "label": "Supply mostly circulating", "detail": f"{supply_pct:.1f}% in circulation"})
        elif supply_pct < 40:
            signals.append({"type": "risk",     "label": "Large unreleased supply",   "detail": f"Only {supply_pct:.1f}% circulating"})
            risk_pts += 2

    nvt = result.get("nvt_proxy")
    if nvt is not None:
        if nvt > 200:
            signals.append({"type": "caution",  "label": "Low on-chain activity",  "detail": f"NVT = {nvt:.0f}x (high = dormant chain)"})
            risk_pts += 1
        elif nvt < 30:
            signals.append({"type": "positive", "label": "High on-chain activity", "detail": f"NVT = {nvt:.0f}x (capital utilisation)"})

    tvl_ratio = result.get("tvl_mc_ratio")
    if tvl_ratio is not None:
        if tvl_ratio >= 1.0:
            signals.append({"type": "positive", "label": "TVL exceeds market cap", "detail": f"TVL/MC = {tvl_ratio:.2f}x — fundamentally undervalued"})
        elif tvl_ratio >= 0.3:
            signals.append({"type": "positive", "label": "Strong TVL backing",     "detail": f"TVL/MC = {tvl_ratio:.2f}x"})

    if unlock and unlock.get("next_unlock"):
        nu         = unlock["next_unlock"]
        days_away  = (nu["date"] - time.time()) / 86400 if nu.get("date") else 999
        label_days = f"in {int(days_away)}d" if days_away < 365 else "scheduled"
        if days_away < 14:
            signals.append({"type": "risk",    "label": f"Unlock {label_days}", "detail": nu.get("label", "Token unlock event")})
            risk_pts += 2
        elif days_away < 30:
            signals.append({"type": "caution", "label": f"Unlock {label_days}", "detail": nu.get("label", "Token unlock event")})
            risk_pts += 1

    result["signals"]    = signals
    result["risk_score"] = min(100, risk_pts * 20) if signals else 0

    return result


def get_onchain(symbol: str) -> dict:
    """Public entry point — on-chain data for a symbol, 5-min LRU cache."""
    ts = int(time.time() // _ONCHAIN_TTL)
    return _onchain_cached(symbol.upper(), ts)
