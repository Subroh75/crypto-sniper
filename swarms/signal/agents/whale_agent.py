"""
swarms/signal/agents/whale_agent.py
─────────────────────────────────────────────────────────────
Agent — Whale Exchange Flow Tracker (per DESIGN.md v2.0, Phase 1)

RESPONSIBILITY:
  For an asset's token contract, detect large transfers (> $500K) into
  and out of KNOWN EXCHANGE WALLETS. Net flow direction is the signal:
  tokens leaving exchanges = accumulation (bullish, holders taking
  custody); tokens flowing into exchanges = distribution (bearish,
  likely sell pressure).

  Only runs for the TOP-20 assets by SignalAgent's `conviction` field
  each pipeline cycle (not the full ~200-coin universe) — see scheduler.py
  two-stage pipeline.

READS:
  raw_price (from blackboard, written by KalmanAgent)

WRITES:
  whale_exchange_inflow, whale_exchange_outflow, whale_net_flow,
  whale_signal, whale_confidence, large_txn_count_1h

whale_signal values: ACCUMULATING | DISTRIBUTING | NEUTRAL

DATA SOURCES:
  Etherscan API V2 (unified) — ETH (chainid=1) + BSC (chainid=56),
                                 single key covers both chains
  Solscan        — Solana (free tier)
  Whale Alert    — cross-chain $500K+ txns (free tier)
  Nansen         — labelled wallets (future, $150/mo, gated on revenue)

THRESHOLD: transactions > $500,000 USD flagged as large.

NOTE: KNOWN_EXCHANGE_WALLETS is a placeholder — needs real exchange
deposit/withdrawal addresses populated per chain before inflow/outflow
classification produces meaningful results. Common sources: Etherscan's
"Labels" API, Nansen's public wallet labels, or community-maintained
lists (e.g. ccxt's exchange address registries).
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
ETHERSCAN_KEY   = os.environ.get("ETHERSCAN_API_KEY", "")
SOLSCAN_KEY     = os.environ.get("SOLSCAN_API_KEY", "")
WHALE_ALERT_KEY = os.environ.get("WHALE_ALERT_API_KEY", "")

# Etherscan V2 unified API — one key, multi-chain via chainid param.
# chainid=1 (ETH), chainid=56 (BSC). No separate BSCScan key needed.
ETHERSCAN_V2_BASE = "https://api.etherscan.io/v2/api"
CHAIN_IDS = {"eth": 1, "bsc": 56}

SOLSCAN_BASE     = "https://pro-api.solscan.io/v2.0"
WHALE_ALERT_BASE = "https://api.whale-alert.io/v1"

LARGE_TXN_THRESHOLD_USD = 500_000

# ERC20/BEP20 contract addresses per asset — reuse onchain.py's EVM_CONTRACT
# mapping where possible. Placeholder subset shown; extend as needed.
TOKEN_CONTRACTS: dict[str, dict[str, str]] = {
    # "LINK": {"eth": "0x514910771af9ca656af840dff83e8264ecf986ca"},
}

# TODO: populate with real known exchange wallet addresses per chain.
# Without this, inflow/outflow classification cannot distinguish
# exchange-bound transfers from any other large transfer.
KNOWN_EXCHANGE_WALLETS: dict[str, set[str]] = {
    "eth": set(),
    "bsc": set(),
    "sol": set(),
}


class WhaleAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="whale",
        version="1.0.0",
        description=(
            "Tracks large (>$500K) transfers into/out of known exchange "
            "wallets per asset — net flow signals accumulation vs "
            "distribution. Runs only for top-20 conviction assets/cycle."
        ),
        reads=["raw_price"],
        writes=[
            "whale_exchange_inflow", "whale_exchange_outflow",
            "whale_net_flow", "whale_signal", "whale_confidence",
            "large_txn_count_1h",
        ],
        schedule_seconds=300,
    )

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            raw_price = context.get("raw_price")
            if raw_price is None:
                return self._fail(
                    f"raw_price not in blackboard context for {asset} "
                    f"(KalmanAgent must run first)", t0
                )

            contracts = TOKEN_CONTRACTS.get(asset.upper())
            if not contracts:
                # No contract mapped yet — neutral, not a failure.
                return self._ok(self._neutral_result(), t0)

            inflow_usd  = 0.0
            outflow_usd = 0.0
            large_count = 0

            for chain, contract in contracts.items():
                txns = self._get_large_transfers(chain, contract, raw_price)
                exch_wallets = KNOWN_EXCHANGE_WALLETS.get(chain, set())

                for txn in txns:
                    usd_value = txn.get("usd_value", 0)
                    if usd_value < LARGE_TXN_THRESHOLD_USD:
                        continue
                    large_count += 1

                    to_addr   = (txn.get("to") or "").lower()
                    from_addr = (txn.get("from") or "").lower()

                    if to_addr in exch_wallets:
                        inflow_usd += usd_value      # moving TO exchange = inflow
                    elif from_addr in exch_wallets:
                        outflow_usd += usd_value     # moving FROM exchange = outflow

            # Cross-chain Whale Alert supplement (covers chains/assets
            # without a mapped contract above, best-effort).
            wa_inflow, wa_outflow, wa_count = self._get_whale_alert_flows(asset)
            inflow_usd  += wa_inflow
            outflow_usd += wa_outflow
            large_count += wa_count

            net_flow = outflow_usd - inflow_usd

            if not contracts and large_count == 0:
                return self._ok(self._neutral_result(), t0)

            signal, confidence = self._classify_flow(inflow_usd, outflow_usd, net_flow)

            return self._ok({
                "whale_exchange_inflow":  round(inflow_usd, 2),
                "whale_exchange_outflow": round(outflow_usd, 2),
                "whale_net_flow":         round(net_flow, 2),
                "whale_signal":           signal,
                "whale_confidence":       confidence,
                "large_txn_count_1h":     large_count,
            }, t0)

        except Exception as e:
            return self._fail(str(e), t0)

    async def health_check(self) -> bool:
        if not ETHERSCAN_KEY:
            return False
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    ETHERSCAN_V2_BASE,
                    params={"chainid": 1, "module": "stats", "action": "ethsupply", "apikey": ETHERSCAN_KEY},
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    return r.status == 200
        except Exception:
            return False

    # ── Helpers ───────────────────────────────────────────────────

    def _neutral_result(self) -> dict:
        return {
            "whale_exchange_inflow":  0.0,
            "whale_exchange_outflow": 0.0,
            "whale_net_flow":         0.0,
            "whale_signal":           "NEUTRAL",
            "whale_confidence":       0.0,
            "large_txn_count_1h":     0,
        }

    def _classify_flow(
        self, inflow: float, outflow: float, net_flow: float
    ) -> tuple[str, float]:
        """
        Classify net flow into ACCUMULATING / DISTRIBUTING / NEUTRAL.
        Confidence scales with the magnitude of imbalance between
        inflow and outflow (0-100), not just the raw net_flow size.
        """
        total = inflow + outflow
        if total <= 0:
            return "NEUTRAL", 0.0

        imbalance = abs(net_flow) / total  # 0 = perfectly balanced, 1 = one-directional

        if net_flow > 0 and imbalance >= 0.2:
            signal = "ACCUMULATING"
        elif net_flow < 0 and imbalance >= 0.2:
            signal = "DISTRIBUTING"
        else:
            signal = "NEUTRAL"

        confidence = round(min(100.0, imbalance * 100), 1)
        return signal, confidence

    # ── Etherscan / BSCScan (large ERC20/BEP20 transfers for a contract) ──

    def _get_large_transfers(
        self, chain: str, contract: str, raw_price: float
    ) -> list[dict]:
        if chain in ("eth", "bsc"):
            return self._get_evm_transfers(CHAIN_IDS[chain], contract, raw_price)
        elif chain == "sol":
            return self._get_sol_transfers(contract, raw_price)
        return []

    def _get_evm_transfers(
        self, chainid: int, contract: str, raw_price: float
    ) -> list[dict]:
        if not ETHERSCAN_KEY:
            return []
        try:
            r = requests.get(
                ETHERSCAN_V2_BASE,
                params={
                    "chainid": chainid,
                    "module": "account",
                    "action": "tokentx",
                    "contractaddress": contract,
                    "page": 1,
                    "offset": 100,
                    "sort": "desc",
                    "apikey": ETHERSCAN_KEY,
                },
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("status") != "1":
                return []

            out = []
            for tx in data.get("result", []):
                try:
                    decimals = int(tx.get("tokenDecimal", 18))
                    raw_value = int(tx.get("value", 0))
                    token_amount = raw_value / (10 ** decimals)
                    usd_value = token_amount * raw_price
                    out.append({
                        "to": tx.get("to", ""),
                        "from": tx.get("from", ""),
                        "usd_value": usd_value,
                    })
                except (ValueError, TypeError):
                    continue
            return out
        except Exception as e:
            self._warn(f"Etherscan V2 transfer fetch failed (chainid={chainid}): {e}")
            return []

    def _get_sol_transfers(self, token_address: str, raw_price: float) -> list[dict]:
        if not SOLSCAN_KEY:
            return []
        try:
            r = requests.get(
                f"{SOLSCAN_BASE}/token/transfer",
                headers={"token": SOLSCAN_KEY},
                params={"address": token_address, "page_size": 100},
                timeout=15,
            )
            r.raise_for_status()
            data = r.json().get("data", [])
            out = []
            for tx in data:
                try:
                    amount = float(tx.get("amount", 0)) / (10 ** int(tx.get("token_decimals", 9)))
                    usd_value = amount * raw_price
                    out.append({
                        "to": tx.get("to_address", ""),
                        "from": tx.get("from_address", ""),
                        "usd_value": usd_value,
                    })
                except (ValueError, TypeError):
                    continue
            return out
        except Exception as e:
            self._warn(f"Solscan transfer fetch failed: {e}")
            return []

    # ── Whale Alert (cross-chain $500K+ supplement) ────────────────

    def _get_whale_alert_flows(self, asset: str) -> tuple[float, float, int]:
        if not WHALE_ALERT_KEY:
            return 0.0, 0.0, 0
        try:
            r = requests.get(
                f"{WHALE_ALERT_BASE}/transactions",
                params={
                    "api_key": WHALE_ALERT_KEY,
                    "min_value": LARGE_TXN_THRESHOLD_USD,
                    "currency": asset.lower(),
                },
                timeout=15,
            )
            r.raise_for_status()
            txns = r.json().get("transactions", [])

            inflow = outflow = 0.0
            count = 0
            for tx in txns:
                usd_value = tx.get("amount_usd", 0)
                if usd_value < LARGE_TXN_THRESHOLD_USD:
                    continue
                count += 1
                to_type = (tx.get("to") or {}).get("owner_type", "")
                from_type = (tx.get("from") or {}).get("owner_type", "")
                if to_type == "exchange":
                    inflow += usd_value
                elif from_type == "exchange":
                    outflow += usd_value

            return inflow, outflow, count
        except Exception as e:
            self._warn(f"Whale Alert fetch failed: {e}")
            return 0.0, 0.0, 0
