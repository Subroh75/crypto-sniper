"""
swarms/signal/agents/kalman_agent.py
─────────────────────────────────────────────────────────────
Agent 1 of 5 — Kalman Filter Price Cleaner and OHLCV Provider

RESPONSIBILITY:
  Fetch OHLCV once per cycle and run the Kalman filter.
  All downstream agents read from the blackboard rather
  than fetching their own price data. One API call per cycle
  regardless of how many agents run.

KALMAN MODEL:
  State vector : [price, velocity]
  Transition   : price_t = price_{t-1} + velocity_{t-1}
                 velocity_t = velocity_{t-1}
  Observation  : price only (close)
  Q = 1e-4  (process noise — lower = smoother)
  R = 1e-2  (obs noise — higher = more smoothing)

BLACKBOARD WRITES:
  kalman_price, kalman_velocity, kalman_velocity_pct,
  kalman_uncertainty, kalman_vol_ratio,
  log_returns, closes, highs, lows, vols,
  raw_price, trend_label, bars_count, accelerating
"""

from __future__ import annotations

import math
import os
import sys
import time
from typing import Any

import aiohttp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from cs_platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent


class KalmanAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="kalman",
        version="1.0.0",
        description="Fetches OHLCV and runs Kalman filter — price + velocity for all agents",
        reads=[],
        writes=[
            "kalman_price", "kalman_velocity", "kalman_velocity_pct",
            "kalman_uncertainty", "kalman_vol_ratio",
            "log_returns", "closes", "highs", "lows", "vols",
            "raw_price", "trend_label", "bars_count", "accelerating",
        ],
        schedule_seconds=300,
    )

    Q = 1e-4
    R = 1e-2

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            ohlcv = await self._fetch_ohlcv(asset)

            if not ohlcv or len(ohlcv) < 30:
                return self._fail(
                    f"Insufficient OHLCV for {asset}: {len(ohlcv or [])} bars", t0
                )

            closes = [float(b[4]) for b in ohlcv]
            highs  = [float(b[2]) for b in ohlcv]
            lows   = [float(b[3]) for b in ohlcv]
            vols   = [float(b[5]) for b in ohlcv if len(b) > 5]

            log_returns = [
                math.log(closes[i] / closes[i - 1])
                for i in range(1, len(closes))
                if closes[i - 1] > 0
            ]

            filtered, velocities = self._kalman_filter(closes)
            vol_baseline         = self._kalman_vol_baseline(vols) if vols else None

            kalman_price    = filtered[-1]
            kalman_velocity = velocities[-1]
            prev_velocity   = velocities[-2] if len(velocities) > 1 else 0.0

            vol_ratio = (
                vols[-1] / vol_baseline
                if vol_baseline and vol_baseline > 0 and vols
                else 1.0
            )
            vel_pct = (kalman_velocity / kalman_price * 100) if kalman_price else 0.0

            if vel_pct > 1.5:
                trend_label = "STRONG MOMENTUM"
            elif vel_pct > 0.5:
                trend_label = "BUILDING MOMENTUM"
            elif vel_pct > 0.0:
                trend_label = "EARLY TREND"
            else:
                trend_label = "NO TREND"

            return self._ok({
                "kalman_price":        round(kalman_price, 6),
                "kalman_velocity":     round(kalman_velocity, 8),
                "kalman_velocity_pct": round(vel_pct, 4),
                "kalman_uncertainty":  round(self.Q * len(closes), 6),
                "kalman_vol_ratio":    round(vol_ratio, 3),
                "log_returns":         log_returns[-50:],
                "closes":              closes[-50:],
                "highs":               highs[-50:],
                "lows":                lows[-50:],
                "vols":                vols[-50:] if vols else [],
                "raw_price":           closes[-1],
                "trend_label":         trend_label,
                "bars_count":          len(closes),
                "prev_velocity":       round(prev_velocity, 8),
                "accelerating":        kalman_velocity > prev_velocity,
            }, t0)

        except Exception as e:
            return self._fail(str(e), t0)

    async def health_check(self) -> bool:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(
                    "https://api.binance.com/api/v3/ping",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as r:
                    return r.status == 200
        except Exception:
            return False

    async def _fetch_ohlcv(
        self,
        asset:    str,
        interval: str = "1h",
        limit:    int = 100,
    ) -> list:
        symbol = asset.upper().replace("/", "")
        if not symbol.endswith("USDT"):
            symbol += "USDT"

        urls = [
            f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
            f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}",
        ]
        async with aiohttp.ClientSession() as session:
            for url in urls:
                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if isinstance(data, list) and len(data) > 0:
                                return data
                except Exception as e:
                    self._warn(f"OHLCV fetch failed: {e}")
        return []

    def _kalman_filter(
        self, prices: list[float]
    ) -> tuple[list[float], list[float]]:
        x, v = prices[0], 0.0
        p00, p01, p10, p11 = 1.0, 0.0, 0.0, 1.0
        Q, R = self.Q, self.R
        filtered, velocities = [], []

        for z in prices:
            x_pred   = x + v
            v_pred   = v
            p00_pred = p00 + p01 + p10 + p11 + Q
            p01_pred = p01 + p11
            p10_pred = p10 + p11
            p11_pred = p11 + Q

            s  = p00_pred + R
            k0 = p00_pred / s
            k1 = p10_pred / s

            innov = z - x_pred
            x = x_pred + k0 * innov
            v = v_pred + k1 * innov

            p00 = (1 - k0) * p00_pred
            p01 = (1 - k0) * p01_pred
            p10 = p10_pred  - k1 * p00_pred
            p11 = p11_pred  - k1 * p01_pred

            filtered.append(x)
            velocities.append(v)

        return filtered, velocities

    def _kalman_vol_baseline(self, volumes: list[float]) -> float:
        if not volumes:
            return 0.0
        x, p = volumes[0], 1.0
        Q_v, R_v = 1e-3, 0.1
        for z in volumes:
            p_pred = p + Q_v
            k = p_pred / (p_pred + R_v)
            x = x + k * (z - x)
            p = (1 - k) * p_pred
        return x
