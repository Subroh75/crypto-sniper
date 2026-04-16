"""
Live Helius/Solana fetcher for SPL token top-holder data.
Called by main.py /analyze when HELIUS_API_KEY is set and chain == 'solana'.

Endpoints used (all via Helius mainnet RPC):
  - getTokenLargestAccounts  : top-20 token accounts by balance
  - getAccountInfo           : resolve token account → owner wallet
  - getTokenSupply           : total supply + decimals
  - getAsset (DAS)           : token name, symbol, holder count
  - getSignaturesForAddress  : wallet tx count + first-seen date
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Optional

import httpx

HELIUS_BASE = "https://mainnet.helius-rpc.com/"
TIMEOUT = 20  # seconds


def _rpc(method: str, params: list, api_key: str) -> dict:
    url = f"{HELIUS_BASE}?api-key={api_key}"
    payload = {"jsonrpc": "2.0", "id": "1", "method": method, "params": params}
    r = httpx.post(url, json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise ValueError(f"Helius RPC error ({method}): {data['error']}")
    return data.get("result", {})


# ── Token metadata ────────────────────────────────────────────────────────────

def fetch_token_supply(mint: str, api_key: str) -> tuple[int, int]:
    """Returns (ui_supply_rounded, decimals)."""
    result = _rpc("getTokenSupply", [mint], api_key)
    value = result.get("value", {})
    decimals = int(value.get("decimals", 9))
    ui_amount = float(value.get("uiAmount") or 0)
    return int(ui_amount), decimals


def fetch_token_metadata(mint: str, api_key: str) -> tuple[str, str, int]:
    """
    Uses Helius DAS getAsset to get name, symbol, and holder count.
    Falls back to (UnknownToken, ???, 0) on error.
    """
    try:
        result = _rpc("getAsset", [{"id": mint, "options": {"showFungible": True}}], api_key)
        content = result.get("content", {})
        meta = content.get("metadata", {})
        name = meta.get("name") or result.get("name") or "Unknown Token"
        symbol = meta.get("symbol") or "???"
        # holder count not always in DAS response — use 0 as fallback
        holders = int(result.get("token_info", {}).get("supply", 0) or 0)
        return name, symbol, 0  # holder count not reliably in DAS
    except Exception:
        return "Unknown Token", "???", 0


# ── Holder list ───────────────────────────────────────────────────────────────

def fetch_largest_token_accounts(mint: str, api_key: str) -> list[dict]:
    """
    Returns up to 20 dicts with keys: token_account, ui_amount, decimals.
    """
    result = _rpc("getTokenLargestAccounts", [mint, {"commitment": "finalized"}], api_key)
    accounts = result.get("value", [])
    out = []
    for acc in accounts[:20]:
        out.append({
            "token_account": acc.get("address", ""),
            "ui_amount":     float(acc.get("uiAmount") or 0),
            "decimals":      int(acc.get("decimals", 9)),
        })
    return out


def resolve_owner(token_account: str, api_key: str) -> str:
    """
    Calls getAccountInfo with jsonParsed encoding to get the owner wallet
    from a token account address.
    """
    result = _rpc(
        "getAccountInfo",
        [token_account, {"encoding": "jsonParsed", "commitment": "finalized"}],
        api_key,
    )
    try:
        parsed = result["value"]["data"]["parsed"]["info"]
        return parsed.get("owner", token_account)
    except (KeyError, TypeError):
        return token_account  # fall back to token account itself


# ── Wallet enrichment ─────────────────────────────────────────────────────────

def fetch_wallet_signatures(wallet: str, api_key: str, limit: int = 100) -> list[dict]:
    """Returns a list of signature objects (newest-first)."""
    try:
        result = _rpc(
            "getSignaturesForAddress",
            [wallet, {"limit": limit, "commitment": "finalized"}],
            api_key,
        )
        return result if isinstance(result, list) else []
    except Exception:
        return []


def wallet_first_tx_date(sigs: list[dict]) -> Optional[str]:
    """Returns ISO date of the oldest signature, or None."""
    if not sigs:
        return None
    oldest = sigs[-1]
    ts = oldest.get("blockTime")
    if ts:
        return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
    return None


def wallet_age_months(sigs: list[dict]) -> int:
    """Approximate wallet age in months from the oldest tx."""
    if not sigs:
        return 0
    ts = sigs[-1].get("blockTime", 0)
    if ts:
        age_days = (datetime.now(timezone.utc) - datetime.fromtimestamp(ts, tz=timezone.utc)).days
        return max(1, age_days // 30)
    return 0


# ── Main pipeline ─────────────────────────────────────────────────────────────

def live_solana(mint: str, api_key: str) -> dict:
    """
    Full live fetch from Helius for a given SPL token mint address.
    Returns a dict matching the shape expected by the frontend.
    """
    # 1. Token metadata
    try:
        name, symbol, _ = fetch_token_metadata(mint, api_key)
    except Exception:
        name, symbol = "Unknown Token", "???"

    try:
        total_supply, decimals = fetch_token_supply(mint, api_key)
    except Exception:
        total_supply, decimals = 0, 9

    # 2. Top 20 token accounts by balance
    try:
        token_accounts = fetch_largest_token_accounts(mint, api_key)
    except Exception as exc:
        raise RuntimeError(f"Could not fetch Solana holder list: {exc}")

    if not token_accounts:
        return _partial_result(mint, name, symbol, total_supply)

    # Total balance across top 20 (for percentage calculation)
    total_top20 = sum(a["ui_amount"] for a in token_accounts) or 1

    # Use total_supply for percentages if available, else use top-20 sum
    denom = float(total_supply) if total_supply > 0 else total_top20

    # 3. Enrich each holder
    holders: list[dict] = []
    for rank, acc in enumerate(token_accounts, start=1):
        token_acct = acc["token_account"]
        ui_amount = acc["ui_amount"]
        pct = round((ui_amount / denom) * 100, 2)

        # Resolve owner wallet
        try:
            owner = resolve_owner(token_acct, api_key)
        except Exception:
            owner = token_acct

        # Wallet signatures for enrichment
        sigs = fetch_wallet_signatures(owner, api_key, limit=50)
        first_buy = wallet_first_tx_date(sigs) or datetime.now(timezone.utc).date().isoformat()
        age_months = wallet_age_months(sigs)
        tx_count = len(sigs)

        holders.append({
            "rank":             rank,
            "address":          owner,
            "balance":          int(ui_amount),
            "percentage":       pct,
            "firstBuyDate":     first_buy,
            "lastActivityDate": wallet_first_tx_date(sigs[:1]) or first_buy,
            "transactions":     tx_count,
            "walletAgeMonths":  age_months,
            "isContract":       False,  # Solana doesn't have EVM-style contracts
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
        "contractAddress":       mint,
        "chain":                 "solana",
        "totalHolders":          0,      # full holder count requires paginated getTokenAccounts
        "totalSupply":           total_supply,
        "top10Percentage":       round(top10_pct, 2),
        "top20Percentage":       round(top20_pct, 2),
        "riskLevel":             risk,
        "holders":               holders,
        "walletAgeDistribution": age_buckets,
        "concentrationScore":    round(100 - top10_pct, 1),
        "analysisTimestamp":     datetime.now(timezone.utc).isoformat(),
        "dataSource":            "helius-live",
    }


def _partial_result(mint: str, name: str, symbol: str, supply: int) -> dict:
    return {
        "tokenName":             name,
        "tokenSymbol":           symbol,
        "contractAddress":       mint,
        "chain":                 "solana",
        "totalHolders":          0,
        "totalSupply":           supply,
        "top10Percentage":       0.0,
        "top20Percentage":       0.0,
        "riskLevel":             "UNKNOWN",
        "holders":               [],
        "walletAgeDistribution": [],
        "concentrationScore":    0.0,
        "analysisTimestamp":     datetime.now(timezone.utc).isoformat(),
        "dataSource":            "helius-partial",
        "error":                 "No holder accounts returned from Helius.",
    }
