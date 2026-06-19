"""
whale_agent.py — WhaleAgent for Crypto-Swarm
Tracks large/accumulating wallets across ETH, BSC, and Solana.
Combines size-based and accumulation-based signals into one conviction score.

Env vars needed:
  MORALIS_API_KEY   — covers ETH + BSC
  SOLSCAN_API_KEY   — covers Solana

NOTE: tokens.py / tracked-wallet list is still a placeholder — needs real
wallet addresses populated before this can run against live data.
"""

import os
import time
import logging
import requests
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

MORALIS_KEY  = os.environ.get("MORALIS_API_KEY", "")
SOLSCAN_KEY  = os.environ.get("SOLSCAN_API_KEY", "")

MORALIS_BASE = "https://deep-index.moralis.io/api/v2.2"
SOLSCAN_BASE = "https://pro-api.solscan.io/v2.0"

# ── Tiered size thresholds (USD) — mirrors SNPR's tiered burn pattern ────────
SIZE_TIERS = [
    (1_000_000, 40),   # $1M+ single transfer → 40 pts
    (500_000,   25),   # $500k+ → 25 pts
    (100_000,   10),   # $100k+ → 10 pts
]

# Weighting for combined conviction score
WEIGHT_ACCUMULATION = 0.6
WEIGHT_SIZE         = 0.4
CONVICTION_THRESHOLD = 72   # matches Crypto-Swarm's existing signal threshold


@dataclass
class WhaleSignal:
    wallet: str
    chain: str
    symbol: str
    size_score: float = 0.0
    accumulation_score: float = 0.0
    conviction: float = 0.0
    largest_transfer_usd: float = 0.0
    net_change_pct_7d: float = 0.0
    flags: list = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# EVM adapter (Moralis) — ETH + BSC
# ─────────────────────────────────────────────────────────────────────────────
def _moralis_get(path: str, chain: str, params: Optional[dict] = None) -> Optional[dict]:
    if not MORALIS_KEY:
        logger.warning("MORALIS_API_KEY not set")
        return None
    headers = {"X-API-Key": MORALIS_KEY, "accept": "application/json"}
    p = {"chain": chain, **(params or {})}
    try:
        r = requests.get(f"{MORALIS_BASE}{path}", headers=headers, params=p, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"Moralis error {path}: {e}")
        return None


def get_evm_wallet_transfers(address: str, chain: str = "eth", limit: int = 100) -> list:
    """Recent ERC20 transfers for a wallet — used for size-signal detection."""
    data = _moralis_get(f"/{address}/erc20/transfers", chain, {"limit": limit})
    return (data or {}).get("result", [])


def get_evm_wallet_token_balances(address: str, chain: str = "eth") -> list:
    """Current token holdings — used as accumulation-signal baseline."""
    data = _moralis_get(f"/{address}/erc20", chain)
    return data if isinstance(data, list) else []


# ─────────────────────────────────────────────────────────────────────────────
# Solana adapter (Solscan)
# ─────────────────────────────────────────────────────────────────────────────
def _solscan_get(path: str, params: Optional[dict] = None) -> Optional[dict]:
    if not SOLSCAN_KEY:
        logger.warning("SOLSCAN_API_KEY not set")
        return None
    headers = {"token": SOLSCAN_KEY}
    try:
        r = requests.get(f"{SOLSCAN_BASE}{path}", headers=headers, params=params, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning(f"Solscan error {path}: {e}")
        return None


def get_sol_wallet_transfers(address: str, limit: int = 100) -> list:
    data = _solscan_get("/account/transfer", {"address": address, "limit": limit})
    return (data or {}).get("data", [])


def get_sol_wallet_balance(address: str) -> list:
    data = _solscan_get("/account/token-accounts", {"address": address, "type": "token"})
    return (data or {}).get("data", [])


# ─────────────────────────────────────────────────────────────────────────────
# Scoring — combines size + accumulation into one conviction number
# ─────────────────────────────────────────────────────────────────────────────
def _score_size(transfers: list, usd_field: str = "value_usd") -> tuple[float, float, list]:
    """
    Score the largest single transfer in the lookback window against tiers.
    Returns (score_0_100, largest_usd, flags).
    """
    if not transfers:
        return 0.0, 0.0, []

    largest = max((t.get(usd_field, 0) or 0 for t in transfers), default=0.0)
    score = 0.0
    flags = []
    for threshold, pts in SIZE_TIERS:
        if largest >= threshold:
            score = pts
            flags.append(f"Single transfer ${largest:,.0f}+ (tier ${threshold:,.0f}+)")
            break
    # Normalise to 0-100 (max tier is 40 pts -> scale up)
    return min(100.0, score * 2.5), largest, flags


def _score_accumulation(balance_now: float, balance_7d_ago: float) -> tuple[float, float, list]:
    """
    Score net wallet balance change over a window.
    Sustained accumulation (positive, consistent growth) scores higher
    than a single large in-and-out transfer.
    Returns (score_0_100, pct_change, flags).
    """
    if balance_7d_ago <= 0:
        return 0.0, 0.0, []

    pct_change = ((balance_now - balance_7d_ago) / balance_7d_ago) * 100
    flags = []

    if pct_change >= 50:
        score = 100.0
        flags.append(f"Strong accumulation +{pct_change:.0f}% (7d)")
    elif pct_change >= 20:
        score = 70.0
        flags.append(f"Moderate accumulation +{pct_change:.0f}% (7d)")
    elif pct_change >= 5:
        score = 40.0
        flags.append(f"Mild accumulation +{pct_change:.0f}% (7d)")
    elif pct_change <= -20:
        score = 0.0
        flags.append(f"Distribution {pct_change:.0f}% (7d) — bearish")
    else:
        score = 20.0  # roughly flat — neutral baseline

    return score, pct_change, flags


def score_whale_wallet(
    wallet: str,
    chain: str,
    symbol: str,
    transfers: list,
    balance_now: float,
    balance_7d_ago: float,
) -> WhaleSignal:
    """
    Unified conviction score combining size + accumulation signals.
    Weighted 60% accumulation / 40% size — sustained accumulation is
    treated as a stronger signal than a single large transfer.
    """
    size_score, largest_usd, size_flags = _score_size(transfers)
    accum_score, pct_change, accum_flags = _score_accumulation(balance_now, balance_7d_ago)

    conviction = (accum_score * WEIGHT_ACCUMULATION) + (size_score * WEIGHT_SIZE)

    return WhaleSignal(
        wallet=wallet,
        chain=chain,
        symbol=symbol,
        size_score=round(size_score, 1),
        accumulation_score=round(accum_score, 1),
        conviction=round(conviction, 1),
        largest_transfer_usd=largest_usd,
        net_change_pct_7d=round(pct_change, 2),
        flags=size_flags + accum_flags,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator — placeholder, needs tracked-wallet list (tokens.py) populated
# ─────────────────────────────────────────────────────────────────────────────
def scan_whale_wallet(wallet: str, chain: str, symbol: str) -> Optional[WhaleSignal]:
    """
    Single-wallet scan entry point. Dispatches to the right adapter
    based on chain, then runs the unified scoring.
    NOTE: balance_7d_ago currently has no historical source wired up —
    needs a small local cache/DB to snapshot balances daily before this
    produces real accumulation scores. Stubbed at 0 for now.
    """
    if chain in ("eth", "bsc"):
        transfers = get_evm_wallet_transfers(wallet, chain=chain)
        balances  = get_evm_wallet_token_balances(wallet, chain=chain)
    elif chain == "sol":
        transfers = get_sol_wallet_transfers(wallet)
        balances  = get_sol_wallet_balance(wallet)
    else:
        logger.warning(f"Unsupported chain: {chain}")
        return None

    # TODO: resolve actual USD value for current balance + 7d-ago snapshot.
    # Needs a small local snapshot table (wallet, symbol, balance, ts) —
    # not yet built. Placeholder values below.
    balance_now    = 0.0
    balance_7d_ago = 0.0

    signal = score_whale_wallet(wallet, chain, symbol, transfers, balance_now, balance_7d_ago)

    if signal.conviction >= CONVICTION_THRESHOLD:
        logger.info(f"WHALE SIGNAL: {symbol} ({chain}) wallet={wallet[:10]}... conviction={signal.conviction}")

    return signal
