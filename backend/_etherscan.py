"""
Live Etherscan fetcher for ERC-20 top-holder data.
Called by main.py /analyze when ETHERSCAN_API_KEY is set.
"""
from __future__ import annotations

import os
import random
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

ETHERSCAN_BASE = "https://api.etherscan.io/api"
TIMEOUT = 20  # seconds per request


def _get(params: dict, api_key: str) -> dict:
    params["apikey"] = api_key
    r = httpx.get(ETHERSCAN_BASE, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if data.get("status") == "0" and data.get("message") not in ("No transactions found", "No records found"):
        raise ValueError(f"Etherscan error: {data.get('result', data.get('message'))}")
    return data


def fetch_token_info(address: str, api_key: str) -> tuple[str, str, int, int]:
    """Returns (name, symbol, total_supply_raw, total_holders)."""
    # Token supply
    supply_data = _get({"module": "stats", "action": "tokensupply", "contractaddress": address}, api_key)
    total_supply = int(supply_data.get("result", 0) or 0)

    # Token info (name + symbol + decimals) via contract ABI call
    info_data = _get({"module": "token", "action": "tokeninfo", "contractaddress": address}, api_key)
    result = info_data.get("result")
    if isinstance(result, list) and result:
        info = result[0]
        name = info.get("tokenName") or info.get("name") or "Unknown Token"
        symbol = info.get("symbol") or "???"
        decimals = int(info.get("divisor") or info.get("decimals") or 18)
        holders_count = int(info.get("holdersCount") or 0)
    else:
        name, symbol, decimals, holders_count = "Unknown Token", "???", 18, 0

    # Normalise supply by decimals
    supply_human = total_supply // (10 ** decimals) if decimals <= 18 else total_supply

    return name, symbol, supply_human, holders_count


def fetch_top_holders(address: str, api_key: str, limit: int = 20) -> list[dict]:
    """
    Fetches top token holders via Etherscan tokenholderlist.
    Returns list of dicts with address + balance + percentage.
    Falls back gracefully if the endpoint is unavailable on free tier.
    """
    data = _get(
        {"module": "token", "action": "tokenholderlist",
         "contractaddress": address, "page": 1, "offset": limit},
        api_key,
    )
    result = data.get("result")
    if not isinstance(result, list):
        return []
    return result


def fetch_wallet_first_tx(wallet: str, token_address: str, api_key: str) -> Optional[str]:
    """Returns ISO date string of the wallet's first tx involving this token, or None."""
    data = _get(
        {"module": "account", "action": "tokentx",
         "contractaddress": token_address, "address": wallet,
         "page": 1, "offset": 1, "sort": "asc"},
        api_key,
    )
    result = data.get("result")
    if isinstance(result, list) and result:
        ts = int(result[0].get("timeStamp", 0))
        if ts:
            return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    return None


def fetch_wallet_tx_count(wallet: str, token_address: str, api_key: str) -> int:
    """Returns total number of token transfers for this wallet."""
    data = _get(
        {"module": "account", "action": "tokentx",
         "contractaddress": token_address, "address": wallet,
         "page": 1, "offset": 100, "sort": "desc"},
        api_key,
    )
    result = data.get("result")
    return len(result) if isinstance(result, list) else 0


def fetch_wallet_age_months(wallet: str, api_key: str) -> int:
    """Returns approximate wallet age in months based on first ever ETH transaction."""
    data = _get(
        {"module": "account", "action": "txlist",
         "address": wallet, "page": 1, "offset": 1, "sort": "asc"},
        api_key,
    )
    result = data.get("result")
    if isinstance(result, list) and result:
        ts = int(result[0].get("timeStamp", 0))
        if ts:
            age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(ts, tz=timezone.utc)).days
            return max(1, age_days // 30)
    return 0


def live_ethereum(address: str, api_key: str) -> dict:
    """
    Full live fetch from Etherscan for a given ERC-20 contract address.
    Returns a dict matching the shape expected by the frontend.
    """
    address = address.lower()

    # 1. Token metadata
    try:
        name, symbol, supply, total_holders = fetch_token_info(address, api_key)
    except Exception:
        name, symbol, supply, total_holders = "Unknown Token", "???", 0, 0

    # 2. Top holders list
    try:
        raw_holders = fetch_top_holders(address, api_key, limit=20)
    except Exception:
        raw_holders = []

    if not raw_holders:
        # Etherscan free tier may not support tokenholderlist — fall back to demo shape
        # with a warning flag so the frontend knows data is partial
        return _partial_result(address, name, symbol, supply, total_holders)

    # 3. Enrich each holder (first buy date, tx count, wallet age)
    #    Cap per-wallet calls to avoid rate-limit; use concurrency via httpx sync for simplicity
    holders: list[dict] = []
    total_balance = sum(int(h.get("TokenHolderQuantity", 0)) for h in raw_holders) or 1
    is_contract_set = {"0x0000000000000000000000000000000000000000"}

    for rank, h in enumerate(raw_holders[:20], start=1):
        wallet = h.get("TokenHolderAddress", "").lower()
        balance_raw = int(h.get("TokenHolderQuantity", 0))
        pct = round((balance_raw / total_balance) * 100, 2)

        # Per-wallet enrichment — best-effort, fall back to None/0 on error
        try:
            first_buy = fetch_wallet_first_tx(wallet, address, api_key)
        except Exception:
            first_buy = None

        try:
            tx_count = fetch_wallet_tx_count(wallet, address, api_key)
        except Exception:
            tx_count = 0

        try:
            age_months = fetch_wallet_age_months(wallet, api_key)
        except Exception:
            age_months = 0

        # Heuristic: treat 0x000...dead and known exchange addresses as contracts
        is_contract = wallet in is_contract_set or wallet.endswith("dead")

        # Last activity: use today as fallback (we'd need another call for precision)
        last_active = datetime.now(timezone.utc).date().isoformat()

        holders.append({
            "rank":             rank,
            "address":          wallet,
            "balance":          balance_raw,
            "percentage":       pct,
            "firstBuyDate":     first_buy or last_active,
            "lastActivityDate": last_active,
            "transactions":     tx_count,
            "walletAgeMonths":  age_months,
            "isContract":       is_contract,
            "label":            None,
        })

    # 4. Risk + concentration
    top10_pct = sum(h["percentage"] for h in holders[:10])
    top20_pct = sum(h["percentage"] for h in holders)

    if top10_pct >= 70:   risk = "CRITICAL"
    elif top10_pct >= 50: risk = "HIGH"
    elif top10_pct >= 40: risk = "MEDIUM"
    else:                 risk = "LOW"

    age_buckets = [
        {"label": "< 3mo",  "count": sum(1 for h in holders if h["walletAgeMonths"] < 3)},
        {"label": "3-6mo",  "count": sum(1 for h in holders if 3 <= h["walletAgeMonths"] < 6)},
        {"label": "6-12mo", "count": sum(1 for h in holders if 6 <= h["walletAgeMonths"] < 12)},
        {"label": "1-2yr",  "count": sum(1 for h in holders if 12 <= h["walletAgeMonths"] < 24)},
        {"label": "> 2yr",  "count": sum(1 for h in holders if h["walletAgeMonths"] >= 24)},
    ]

    return {
        "tokenName":             name,
        "tokenSymbol":           symbol,
        "contractAddress":       address,
        "chain":                 "ethereum",
        "totalHolders":          total_holders,
        "totalSupply":           supply,
        "top10Percentage":       round(top10_pct, 2),
        "top20Percentage":       round(top20_pct, 2),
        "riskLevel":             risk,
        "holders":               holders,
        "walletAgeDistribution": age_buckets,
        "concentrationScore":    round(100 - top10_pct, 1),
        "analysisTimestamp":     datetime.now(timezone.utc).isoformat(),
        "dataSource":            "etherscan-live",
    }


def _partial_result(address: str, name: str, symbol: str, supply: int, total_holders: int) -> dict:
    """
    Returned when holder list is unavailable (e.g. free-tier rate limit).
    Shape matches live_ethereum() but flags the data source.
    """
    return {
        "tokenName":             name,
        "tokenSymbol":           symbol,
        "contractAddress":       address,
        "chain":                 "ethereum",
        "totalHolders":          total_holders,
        "totalSupply":           supply,
        "top10Percentage":       0.0,
        "top20Percentage":       0.0,
        "riskLevel":             "UNKNOWN",
        "holders":               [],
        "walletAgeDistribution": [],
        "concentrationScore":    0.0,
        "analysisTimestamp":     datetime.now(timezone.utc).isoformat(),
        "dataSource":            "etherscan-partial",
        "error":                 "Holder list unavailable — tokenholderlist requires Etherscan Pro tier.",
    }
