"""
swarms/signal/agents/sentiment_agent.py
─────────────────────────────────────────────────────────────
Agent 3 of 5 — Market Sentiment Monitor

Fetches: Binance Futures funding rate + OI,
         Alternative.me Fear & Greed index.
All free, no API keys required.

FUNDING BIAS:
  < -0.01% → BULLISH   (shorts paying longs)
  -0.01 to 0.01% → NEUTRAL
  0.01 to 0.05% → CAUTIOUS
  > 0.05% → BEARISH    (extreme long crowding)

FEAR & GREED GATE:
  0-15   → CAUTION  (extreme fear)
  15-85  → PASS
  85-100 → AVOID    (extreme greed)

BLACKBOARD READS:  (none — independent sources)
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

from cs_platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent


class SentimentAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="sentiment",
        version="1.0.0",
        description="Funding rate, OI and Fear & Greed sentiment synthesiser",
        reads=[],
        writes=[
            "funding_rate", "oi_usd", "fear_greed_value",
            "fear_greed_label", "sentiment_score",
            "sentiment_gate", "funding_bias",
        ],
        schedule_seconds=300,
    )

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            symbol = asset.upper().replace("/", "")
            if not symbol.endswith("USDT"):
                symbol += "USDT"

            funding, oi     = await self._fetch_futures(symbol)
            fg_val, fg_lbl  = await self._fetch_fear_greed()

            if funding < -0.01:
                funding_bias = "BULLISH"
            elif funding < 0.01:
                funding_bias = "NEUTRAL"
            elif funding < 0.05:
                funding_bias = "CAUTIOUS"
            else:
                funding_bias = "BEARISH"

            fg_score = fg_val if fg_val is not None else 50
            score    = float(fg_score)

            if funding_bias == "BULLISH":
                score = min(score + 15, 100)
            elif funding_bias == "CAUTIOUS":
                score = max(score - 10, 0)
            elif funding_bias == "BEARISH":
                score = max(score - 20, 0)

            if fg_score < 15:
                gate = "CAUTION"
            elif fg_score > 85:
                gate = "AVOID"
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

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://fapi.binance.com/fapi/v1/ping",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    return r.status == 200
        except Exception:
            return False

    async def _fetch_futures(self, symbol: str) -> tuple[float, float]:
        funding, oi = 0.0, 0.0
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={symbol}&limit=1",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        if data:
                            funding = float(data[-1].get("fundingRate", 0))
            except Exception as e:
                self._warn(f"Funding rate fetch failed: {e}")

            try:
                async with session.get(
                    f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        oi   = float(data.get("openInterest", 0))
            except Exception as e:
                self._warn(f"OI fetch failed: {e}")

        return funding, oi

    async def _fetch_fear_greed(self) -> tuple[Optional[int], str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "https://api.alternative.me/fng/?limit=1",
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as r:
                    if r.status == 200:
                        data  = await r.json()
                        entry = data["data"][0]
                        return int(entry["value"]), entry["value_classification"]
        except Exception as e:
            self._warn(f"Fear & Greed fetch failed: {e}")
        return 50, "Neutral"
