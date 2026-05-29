"""
swarms/signal/agents/dex_agent.py
─────────────────────────────────────────────────────────────
Agent 5 of 5 (optional) — DEX Context Provider

RESPONSIBILITY:
  Fetch DEX market data for each swarm asset via DexScreener.
  Provides on-chain price, volume, liquidity, and buy pressure
  as additional conviction inputs for the orchestrator.

  This is NOT a replacement for KalmanAgent — it runs in parallel
  and enriches the blackboard with DEX-side data so the orchestrator
  can compare CEX vs DEX momentum and detect cross-venue divergence.

DATA SOURCE:
  DexScreener /latest/dex/tokens/{address} — free, no key required.

ASSET → CHAIN MAPPING:
  BTC  → Bitcoin (not on DEX — skipped, CEX-only)
  ETH  → Ethereum mainnet (Uniswap V3)
  SOL  → Solana (Raydium/Orca)
  BNB  → BSC (PancakeSwap)

  For assets without a meaningful DEX presence (BTC), the agent
  writes dex_available=False and exits cleanly — orchestrator
  uses CEX data only for those assets.

BLACKBOARD WRITES:
  dex_available, dex_exchange, dex_chain,
  dex_price, dex_price_change_1h, dex_price_change_24h,
  dex_vol_24h, dex_vol_1h, dex_liquidity,
  dex_buy_ratio_1h, dex_rel_vol,
  dex_signal_label, dex_score,
  cex_dex_spread_pct   (% diff between CEX and DEX price)
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Optional

import aiohttp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cs_platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent

DEXSCREENER = "https://api.dexscreener.com"

# DexScreener token search query per asset
# Using well-known token symbols — DexScreener returns the most liquid pair
ASSET_DEX_CONFIG = {
    "BTC": None,   # Bitcoin has no meaningful DEX presence — CEX only
    "ETH": {
        "search": "WETH",
        "chain":  "ethereum",
        "dex":    "Uniswap V3",
        "quote":  "USDC",        # prefer WETH/USDC pairs
    },
    "SOL": {
        "search": "SOL",
        "chain":  "solana",
        "dex":    "Raydium",
        "quote":  "USDC",
    },
    "BNB": {
        "search": "WBNB",
        "chain":  "bsc",
        "dex":    "PancakeSwap",
        "quote":  "USDT",
    },
}

# Min liquidity to trust a DEX pair as representative
MIN_LIQUIDITY_USD = 500_000


class DEXAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="dex",
        version="1.0.0",
        description=(
            "Fetches DEX market data via DexScreener — price, vol, "
            "liquidity, buy pressure for CEX/DEX divergence scoring"
        ),
        reads=["raw_price"],          # reads CEX price from blackboard for spread calc
        writes=[
            "dex_available", "dex_exchange", "dex_chain",
            "dex_price", "dex_price_change_1h", "dex_price_change_24h",
            "dex_vol_24h", "dex_vol_1h", "dex_liquidity",
            "dex_buy_ratio_1h", "dex_rel_vol",
            "dex_signal_label", "dex_score",
            "cex_dex_spread_pct",
        ],
        schedule_seconds=300,
    )

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()

        config = ASSET_DEX_CONFIG.get(asset.upper())

        # BTC or unknown asset — no DEX data, write clean skip state
        if config is None:
            return self._ok({
                "dex_available":         False,
                "dex_exchange":          None,
                "dex_chain":             None,
                "dex_price":             0.0,
                "dex_price_change_1h":   0.0,
                "dex_price_change_24h":  0.0,
                "dex_vol_24h":           0.0,
                "dex_vol_1h":            0.0,
                "dex_liquidity":         0.0,
                "dex_buy_ratio_1h":      0.5,
                "dex_rel_vol":           1.0,
                "dex_signal_label":      "CEX_ONLY",
                "dex_score":             0,
                "cex_dex_spread_pct":    0.0,
            }, t0)

        try:
            pair = await self._fetch_best_pair(
                config["search"],
                config["chain"],
                config.get("quote", "USDT"),
            )

            if not pair:
                return self._ok(_empty_dex_state("NO_PAIR_FOUND"), t0)

            # Extract market fields
            liq     = float((pair.get("liquidity") or {}).get("usd", 0) or 0)
            if liq < MIN_LIQUIDITY_USD:
                return self._ok(_empty_dex_state("LOW_LIQUIDITY"), t0)

            vol     = pair.get("volume") or {}
            txns    = pair.get("txns") or {}
            chg     = pair.get("priceChange") or {}
            txns_1h = txns.get("h1") or {}

            price      = float(pair.get("priceUsd", 0) or 0)
            vol_24h    = float(vol.get("h24", 0) or 0)
            vol_h6     = float(vol.get("h6", 0) or 0)
            vol_h1     = float(vol.get("h1", 0) or 0)
            chg_1h     = float(chg.get("h1", 0) or 0)
            chg_24h    = float(chg.get("h24", 0) or 0)
            buys_1h    = int(txns_1h.get("buys", 0) or 0)
            sells_1h   = int(txns_1h.get("sells", 0) or 0)
            dex_name   = pair.get("dexId", config["dex"])
            chain      = pair.get("chainId", config["chain"])

            # Relative volume: 1h vs 6h hourly average
            avg_hourly = vol_h6 / 6 if vol_h6 > 0 else (vol_24h / 24 if vol_24h > 0 else 1)
            rel_vol    = round(vol_h1 / avg_hourly, 2) if avg_hourly > 0 and vol_h1 > 0 else 1.0

            # Buy pressure
            total_txns = buys_1h + sells_1h
            buy_ratio  = round(buys_1h / total_txns, 3) if total_txns > 0 else 0.5

            # Simple signal from DEX data
            v_ok = rel_vol >= 1.8
            t_ok = chg_1h > 0 and chg_24h > 0
            p_ok = chg_1h > 1.0 and chg_24h > 3.0
            r_ok = buy_ratio > 0.55

            if v_ok and t_ok and p_ok and r_ok:
                dex_label = "STRONG BUY"
                dex_score = 9
            elif v_ok and t_ok:
                dex_label = "BUY"
                dex_score = 5
            else:
                dex_label = "NO SIGNAL"
                dex_score = 0

            # CEX/DEX spread — measure of divergence
            cex_price = context.get("raw_price", 0)
            spread_pct = 0.0
            if cex_price and price:
                spread_pct = round((price - cex_price) / cex_price * 100, 3)

            return self._ok({
                "dex_available":         True,
                "dex_exchange":          dex_name,
                "dex_chain":             chain,
                "dex_price":             round(price, 6),
                "dex_price_change_1h":   round(chg_1h, 3),
                "dex_price_change_24h":  round(chg_24h, 3),
                "dex_vol_24h":           round(vol_24h, 2),
                "dex_vol_1h":            round(vol_h1, 2),
                "dex_liquidity":         round(liq, 2),
                "dex_buy_ratio_1h":      buy_ratio,
                "dex_rel_vol":           rel_vol,
                "dex_signal_label":      dex_label,
                "dex_score":             dex_score,
                "cex_dex_spread_pct":    spread_pct,
            }, t0)

        except Exception as e:
            return self._fail(str(e), t0)

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    f"{DEXSCREENER}/latest/dex/search?q=WETH",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    return r.status == 200
        except Exception:
            return False

    async def _fetch_best_pair(
        self,
        search_term: str,
        chain: str,
        preferred_quote: str = "USDT",
    ) -> Optional[dict]:
        """
        Search DexScreener for the most liquid pair matching
        the asset on the target chain.
        Prefers preferred_quote pairs, falls back to any USDT/USDC pair.
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{DEXSCREENER}/latest/dex/search",
                    params={"q": search_term},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()

            pairs = data.get("pairs") or []
            if not pairs:
                return None

            # Filter to target chain + stable quote pairs
            stable_quotes = {"USDT", "USDC", "BUSD", "DAI"}
            chain_pairs = [
                p for p in pairs
                if p.get("chainId", "").lower() == chain.lower()
                and (p.get("quoteToken") or {}).get("symbol", "").upper() in stable_quotes
            ]

            if not chain_pairs:
                return None

            # Sort by liquidity descending — most liquid pair is most representative
            chain_pairs.sort(
                key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0),
                reverse=True,
            )

            # Prefer the preferred quote token if available with decent liquidity
            preferred = [
                p for p in chain_pairs
                if (p.get("quoteToken") or {}).get("symbol", "").upper() == preferred_quote.upper()
            ]
            if preferred:
                return preferred[0]

            return chain_pairs[0]

        except Exception as e:
            self._warn(f"DexScreener search failed ({search_term}/{chain}): {e}")
            return None


def _empty_dex_state(reason: str) -> dict:
    return {
        "dex_available":         False,
        "dex_exchange":          None,
        "dex_chain":             None,
        "dex_price":             0.0,
        "dex_price_change_1h":   0.0,
        "dex_price_change_24h":  0.0,
        "dex_vol_24h":           0.0,
        "dex_vol_1h":            0.0,
        "dex_liquidity":         0.0,
        "dex_buy_ratio_1h":      0.5,
        "dex_rel_vol":           1.0,
        "dex_signal_label":      reason,
        "dex_score":             0,
        "cex_dex_spread_pct":    0.0,
    }
