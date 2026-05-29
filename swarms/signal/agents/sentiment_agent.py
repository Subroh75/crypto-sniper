"""
swarms/signal/agents/sentiment_agent.py
─────────────────────────────────────────────────────────────
Agent 3 of 5 — Market Sentiment Monitor

RESPONSIBILITY:
  Fetches three independent sentiment signals and synthesises
  them into a single sentiment_score and gate decision.

DATA SOURCES (all free, no API key required):
  1. Binance Futures — funding rate per symbol
  2. Binance Futures — open interest per symbol
  3. Alternative.me  — Fear & Greed index (crypto-wide)

FUNDING RATE INTERPRETATION:
  < -0.01% → BULLISH  (shorts paying longs — cheap to go long)
  -0.01 to 0.01% → NEUTRAL
  0.01 to 0.05% → CAUTIOUS (longs paying premium)
  > 0.05% → BEARISH  (extreme long crowding — contrarian warning)

FEAR & GREED GATE:
  0-15   → CAUTION  (extreme fear — wait for stabilisation)
  15-85  → PASS     (tradeable range)
  85-100 → AVOID    (extreme greed — too late to enter)

BLACKBOARD READS:  (none — independent data sources)
BLACKBOARD WRITES: funding_rate, oi_usd, fear_greed_value,
                   fear_greed_label, sentiment_score,
                   sentiment_gate, funding_bias
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

from platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent


class SentimentAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="sentiment",
        version="1.0.0",
        description="Funding rate, open interest and Fear & Greed sentiment synthesiser",
        reads=[],
        writes=[
            "funding_rate",
            "oi_usd",
            "fear_greed_value",
            "fear_greed_label",
            "sentiment_score",
            "sentiment_gate",
            "funding_bias",
        ],
        schedule_seconds=300,
    )

    # ── Core run ───────────────────────────────────────────────

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            symbol = asset.upper().replace("/", "")
            if not symbol.endswith("USDT"):
                symbol += "USDT"

            funding, oi   = await self._fetch_futures(symbol)
            fg_val, fg_lbl = await self._fetch_fear_greed()

            # Funding rate → directional bias
            if funding < -0.01:
                funding_bias = "BULLISH"
            elif funding < 0.01:
                funding_bias = "NEUTRAL"
            elif funding < 0.05:
                funding_bias = "CAUTIOUS"
            else:
                funding_bias = "BEARISH"

            # Base sentiment from Fear & Greed (0-100)
            fg_score = fg_val if fg_val is not None else 50

            # Adjust for funding rate
            score = float(fg_score)
            if funding_bias == "BULLISH":
                score = min(score + 15, 100)
            elif funding_bias == "CAUTIOUS":
                score = max(score - 10, 0)
            elif funding_bias == "BEARISH":
                score = max(score - 20, 0)

            # Gate decision
            if fg_score < 15:
                gate = "CAUTION"    # extreme fear — fragile market
            elif fg_score > 85:
                gate = "AVOID"      # extreme greed — overcrowded
            else:
                gate = "PASS"

            return self._ok({
                "funding_rate":     round(funding, 5),
                "oi_usd":           round(oi, 0),
                "fear_greed_value": fg_score,
                "fear_greed_label": fg_lbl,
                "sentiment_score":  round(score, 1),
                "sentiment_gate":   gate,
                "funding_bias":     funding_bias,
            }, t0)

        except Exception as e:
            return self._fail(str(e), t0)

    # ── Health check ───────────────────────────────────────────

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://fapi.binance.com/fapi/v1/ping",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as r:
                    return r.status == 200
        except Exception:
            return False

    # ── Private: data fetchers ─────────────────────────────────

    async def _fetch_futures(self, symbol: str) -> tuple[float, float]:
        """
        Fetch funding rate and open interest from Binance Futures.
        Returns (funding_rate, open_interest_usd).
        """
        funding, oi = 0.0, 0.0

        async with aiohttp.ClientSession() as session:
            # Funding rate
            try:
                async with session.get(
                    f"https://fapi.binance.com/fapi/v1/fundingRate"
                    f"?symbol={symbol}&limit=1",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data:
                            funding = float(data[-1].get("fundingRate", 0))
            except Exception as e:
                self._warn(f"Funding rate fetch failed for {symbol}: {e}")

            # Open interest
            try:
                async with session.get(
                    f"https://fapi.binance.com/fapi/v1/openInterest"
                    f"?symbol={symbol}",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        oi   = float(data.get("openInterest", 0))
            except Exception as e:
                self._warn(f"OI fetch failed for {symbol}: {e}")

        return funding, oi

    async def _fetch_fear_greed(self) -> tuple[Optional[int], str]:
        """
        Fetch the Crypto Fear & Greed Index from Alternative.me.
        Free API, no key required, updated every 24H.
        Returns (value 0-100, classification string).
        """
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.alternative.me/fng/?limit=1",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        data  = await r.json()
                        entry = data["data"][0]
                        return (
                            int(entry["value"]),
                            entry["value_classification"],
                        )
        except Exception as e:
            self._warn(f"Fear & Greed fetch failed: {e}")

        return 50, "Neutral"
