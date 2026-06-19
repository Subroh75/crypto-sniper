"""
swarms/signal/agents/whale_agent.py
─────────────────────────────────────────────────────────────
Agent — Whale Wallet Tracker (Size + Accumulation Conviction)

RESPONSIBILITY:
  For assets with tracked whale wallets (see TRACKED_WALLETS / tokens.py),
  fetch recent transfers + current balances, score both a size signal
  (large single transfers) and an accumulation signal (net balance change
  over 7d), and combine into one conviction score (0-100).

  Assets with no tracked wallets yet return a neutral (success, score=0)
  result rather than failing — this runs per-asset every cycle alongside
  Kalman/GARCH/Sentiment/Signal, and most of the ~200-coin universe won't
  have wallets mapped initially.

DATA SOURCES:
  ETH + BSC  — Moralis (single key, both chains)
  Solana     — Solscan

BLACKBOARD WRITES:
  whale_conviction, whale_size_score, whale_accumulation_score,
  whale_largest_transfer_usd, whale_net_change_pct_7d, whale_flags,
  whale_wallets_tracked

NOTE: TRACKED_WALLETS is still a placeholder — needs real wallet
addresses populated (tokens.py) before this produces non-zero scores
for any asset. Balance-snapshot job (7d-ago lookup) also not yet built;
accumulation_score is stubbed at 0 until that lands.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Optional

import aiohttp
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cs_platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent

# ── Config ─────────────────────────────────────────────────────────
MORALIS_KEY = os.environ.get("MORALIS_API_KEY", "")
SOLSCAN_KEY = os.environ.get("SOLSCAN_API_KEY", "")

MORALIS_BASE = "https://deep-index.moralis.io/api/v2.2"
SOLSCAN_BASE = "https://pro-api.solscan.io/v2.0"

# Tiered size thresholds (USD) — mirrors SNPR's tiered burn pattern
SIZE_TIERS = [
    (1_000_000, 40),
    (500_000,   25),
    (100_000,   10),
]

WEIGHT_ACCUMULATION = 0.6
WEIGHT_SIZE         = 0.4

# TODO: populate from tokens.py — symbol -> list of tracked wallet addresses
# per chain. Placeholder empty until wallet-discovery work is done.
TRACKED_WALLETS: dict[str, dict[str, list[str]]] = {
    # "ETH": {"eth": ["0x..."], "bsc": []},
    # "SOL": {"sol": ["..."]},
}


class WhaleAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="whale",
        version="1.0.0",
        description=(
            "Tracks large transfers + net accumulation across tracked "
            "whale wallets (ETH/BSC via Moralis, Solana via Solscan) — "
            "combined size + accumulation conviction score"
        ),
        reads=[],
        writes=[
            "whale_conviction", "whale_size_score", "whale_accumulation_score",
            "whale_largest_transfer_usd", "whale_net_change_pct_7d",
            "whale_flags", "whale_wallets_tracked",
        ],
        schedule_seconds=300,
    )

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            wallets_by_chain = TRACKED_WALLETS.get(asset.upper(), {})
            all_wallets = [
                (chain, w)
                for chain, ws in wallets_by_chain.items()
                for w in ws
            ]

            if not all_wallets:
                # Neutral result — not a failure. Most assets won't have
                # tracked wallets until wallet-discovery work lands.
                return self._ok({
                    "whale_conviction":           0,
                    "whale_size_score":           0,
                    "whale_accumulation_score":   0,
                    "whale_largest_transfer_usd": 0.0,
                    "whale_net_change_pct_7d":    0.0,
                    "whale_flags":                [],
                    "whale_wallets_tracked":       0,
                }, t0)

            best_signal = {"conviction": -1}
            for chain, wallet in all_wallets:
                sig = await self._score_wallet(wallet, chain, asset)
                if sig is None:
                    continue
                if sig["conviction"] > best_signal["conviction"]:
                    best_signal = sig

            if best_signal["conviction"] < 0:
                return self._fail(
                    f"All {len(all_wallets)} tracked wallet(s) for {asset} "
                    f"failed to fetch data", t0
                )

            return self._ok({
                "whale_conviction":           best_signal["conviction"],
                "whale_size_score":           best_signal["size_score"],
                "whale_accumulation_score":   best_signal["accumulation_score"],
                "whale_largest_transfer_usd": best_signal["largest_transfer_usd"],
                "whale_net_change_pct_7d":    best_signal["net_change_pct_7d"],
                "whale_flags":                best_signal["flags"],
                "whale_wallets_tracked":      len(all_wallets),
            }, t0)

        except Exception as e:
            return self._fail(str(e), t0)

    async def health_check(self) -> bool:
        """Ping Moralis (EVM coverage). Solscan checked best-effort."""
        if not MORALIS_KEY:
            return False
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{MORALIS_BASE}/dateToBlock",
                    headers={"X-API-Key": MORALIS_KEY},
                    params={"chain": "eth", "date": "2024-01-01"},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    return r.status == 200
        except Exception:
            return False

    # ── Per-wallet scoring ──────────────────────────────────────────

    async def _score_wallet(
        self, wallet: str, chain: str, symbol: str
    ) -> Optional[dict]:
        try:
            if chain in ("eth", "bsc"):
                transfers = self._get_evm_transfers(wallet, chain)
                balance_now = self._get_evm_balance_usd(wallet, chain)
            elif chain == "sol":
                transfers = self._get_sol_transfers(wallet)
                balance_now = self._get_sol_balance_usd(wallet)
            else:
                self._warn(f"Unsupported chain for whale tracking: {chain}")
                return None

            # TODO: balance-snapshot job not yet built — needs a daily
            # (wallet, symbol, balance_usd, ts) table in Supabase to
            # compare against. Stubbed at 0 until that lands, which
            # means accumulation_score is always 0 for now.
            balance_7d_ago = 0.0

            size_score, largest_usd, size_flags = self._score_size(transfers)
            accum_score, pct_change, accum_flags = self._score_accumulation(
                balance_now, balance_7d_ago
            )

            conviction = (
                accum_score * WEIGHT_ACCUMULATION
                + size_score * WEIGHT_SIZE
            )

            return {
                "conviction":           round(conviction, 1),
                "size_score":           round(size_score, 1),
                "accumulation_score":   round(accum_score, 1),
                "largest_transfer_usd": largest_usd,
                "net_change_pct_7d":    round(pct_change, 2),
                "flags":                size_flags + accum_flags,
            }

        except Exception as e:
            self._warn(f"Wallet scan failed ({wallet[:10]}... on {chain}): {e}")
            return None

    # ── Moralis (ETH + BSC) ───────────────────────────────────────────

    def _get_evm_transfers(self, address: str, chain: str, limit: int = 100) -> list:
        if not MORALIS_KEY:
            return []
        try:
            r = requests.get(
                f"{MORALIS_BASE}/{address}/erc20/transfers",
                headers={"X-API-Key": MORALIS_KEY},
                params={"chain": chain, "limit": limit},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("result", [])
        except Exception as e:
            self._warn(f"Moralis transfers fetch failed ({chain}): {e}")
            return []

    def _get_evm_balance_usd(self, address: str, chain: str) -> float:
        if not MORALIS_KEY:
            return 0.0
        try:
            r = requests.get(
                f"{MORALIS_BASE}/{address}/erc20",
                headers={"X-API-Key": MORALIS_KEY},
                params={"chain": chain},
                timeout=15,
            )
            r.raise_for_status()
            tokens = r.json()
            if not isinstance(tokens, list):
                return 0.0
            # NOTE: Moralis's plain /erc20 balance endpoint doesn't include
            # USD value directly — would need a follow-up price lookup per
            # token (or Moralis's /erc20/{address}/price-batch endpoint) to
            # get real USD totals. Returning 0 for now; flagged as a gap.
            return 0.0
        except Exception as e:
            self._warn(f"Moralis balance fetch failed ({chain}): {e}")
            return 0.0

    # ── Solscan (Solana) ──────────────────────────────────────────────

    def _get_sol_transfers(self, address: str, limit: int = 100) -> list:
        if not SOLSCAN_KEY:
            return []
        try:
            r = requests.get(
                f"{SOLSCAN_BASE}/account/transfer",
                headers={"token": SOLSCAN_KEY},
                params={"address": address, "limit": limit},
                timeout=15,
            )
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception as e:
            self._warn(f"Solscan transfers fetch failed: {e}")
            return []

    def _get_sol_balance_usd(self, address: str) -> float:
        # NOTE: same gap as EVM — needs a price lookup per token to get
        # a real USD total. Returning 0 for now.
        return 0.0

    # ── Scoring helpers ─────────────────────────────────────────────

    def _score_size(self, transfers: list) -> tuple[float, float, list]:
        if not transfers:
            return 0.0, 0.0, []

        largest = max(
            (float(t.get("value_usd", 0) or 0) for t in transfers),
            default=0.0,
        )
        score = 0.0
        flags = []
        for threshold, pts in SIZE_TIERS:
            if largest >= threshold:
                score = pts
                flags.append(f"Single transfer ${largest:,.0f}+ (tier ${threshold:,.0f}+)")
                break

        return min(100.0, score * 2.5), largest, flags

    def _score_accumulation(
        self, balance_now: float, balance_7d_ago: float
    ) -> tuple[float, float, list]:
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
            score = 20.0

        return score, pct_change, flags
