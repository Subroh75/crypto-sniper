"""
swarms/signal/agents/kalman_agent.py
───────────────────────────────────────────────
Agent 1 of 5 in the signal swarm pipeline.

RESPONSIBILITY:
  Fetch OHLCV once per cycle and run the Kalman filter.
    All downstream agents read from the blackboard rather
      than fetching their own price data. This means one API
        call per cycle regardless of how many agents run.

        KALMAN MODEL (same as kalman_scanner.py, promoted to agent):
          State vector : [price, velocity]
            Transition   : price_t = price_{t-1} + velocity_{t-1}
                             velocity_t = velocity_{t-1}  (constant vel)
                               Observation  : price only (close)
                                 Process noise: Q = 1e-4 (tune lower = smoother)
                                   Obs noise    : R = 1e-2 (tune higher = more smoothing)

                                   BLACKBOARD WRITES:
                                     kalman_price      - Kalman-filtered price estimate
                                       kalman_velocity   - rate of change per bar (% per bar)
                                         kalman_uncertainty- filter uncertainty (P matrix trace)
                                           kalman_vol_ratio  - current vol vs Kalman vol baseline
                                             log_returns       - list of log returns (for GARCH agent)
                                               closes            - raw close prices (for signal agent)
                                                 highs/lows/vols   - OHLCV arrays (for signal agent)
                                                   raw_price         - latest close (unfiltered)
                                                     trend_label       - STRONG MOMENTUM / BUILDING / EARLY TREND
                                                       bars_count        - number of bars fetched
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

from platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent


class KalmanAgent(BaseAgent):

      identity = AgentIdentity(
                department="signal",
                name="kalman",
                version="1.0.0",
                description="Fetches OHLCV and runs Kalman filter to produce clean price + velocity",
                reads=[],
                writes=[
                              "kalman_price", "kalman_velocity", "kalman_uncertainty",
                              "kalman_vol_ratio", "log_returns", "closes",
                              "highs", "lows", "vols", "raw_price", "trend_label", "bars_count"
                ],
                schedule_seconds=300,  # every 5 minutes
      )

    # Kalman tuning parameters
      Q = 1e-4   # process noise (lower = smoother price)
    R = 1e-2   # observation noise (higher = more smoothing)

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
              t0 = time.monotonic()
              try:
                            ohlcv = await self._fetch_ohlcv(asset, interval="1h", limit=100)
                            if not ohlcv or len(ohlcv) < 30:
                                              return self._fail(
                                                                    f"Insufficient OHLCV data for {asset}: {len(ohlcv or [])} bars",
                                                                    t0
                                              )

                            closes = [float(bar[4]) for bar in ohlcv]  # index 4 = close
            highs  = [float(bar[2]) for bar in ohlcv]
            lows   = [float(bar[3]) for bar in ohlcv]
            vols   = [float(bar[5]) for bar in ohlcv if len(bar) > 5]

            # Log returns for GARCH agent
            log_returns = [
                              math.log(closes[i] / closes[i-1])
                              for i in range(1, len(closes))
                              if closes[i-1] > 0
            ]

            # Run Kalman on price
            filtered, velocities = self._kalman_filter(closes)

            # Run Kalman on volume baseline
            vol_baseline = self._kalman_vol_baseline(vols) if vols else None

            kalman_price    = filtered[-1]
            kalman_velocity = velocities[-1]
            prev_velocity   = velocities[-2] if len(velocities) > 1 else 0

            # Volume ratio vs Kalman baseline
            if vol_baseline and vols:
                              vol_ratio = vols[-1] / vol_baseline if vol_baseline > 0 else 1.0
else:
                  vol_ratio = 1.0

            # Uncertainty = trace of P matrix (simplified: position variance)
              uncertainty = self.Q * len(closes)

            # Trend label
            vel_pct = (kalman_velocity / kalman_price * 100) if kalman_price else 0
            if vel_pct > 1.5:
                              trend_label = "STRONG MOMENTUM"
elif vel_pct > 0.5:
                  trend_label = "BUILDING MOMENTUM"
elif vel_pct > 0.0:
                  trend_label = "EARLY TREND"
else:
                  trend_label = "NO TREND"

            return self._ok({
                              "kalman_price":       round(kalman_price, 6),
                              "kalman_velocity":    round(kalman_velocity, 8),
                              "kalman_velocity_pct": round(vel_pct, 4),
                              "kalman_uncertainty": round(uncertainty, 6),
                              "kalman_vol_ratio":   round(vol_ratio, 3),
                              "log_returns":        log_returns[-50:],  # last 50 for GARCH
                              "closes":             closes[-50:],
                              "highs":              highs[-50:],
                              "lows":               lows[-50:],
                              "vols":               vols[-50:] if vols else [],
                              "raw_price":          closes[-1],
                              "trend_label":        trend_label,
                              "bars_count":         len(closes),
                              "prev_velocity":      round(prev_velocity, 8),
                              "accelerating":       kalman_velocity > prev_velocity,
            }, t0)

except Exception as e:
            return self._fail(str(e), t0)

    async def health_check(self) -> bool:
              """Check Binance API is reachable."""
              try:
                            async with aiohttp.ClientSession() as s:
                                              async with s.get(
                                                                    "https://api.binance.com/api/v3/ping",
                                                                    timeout=aiohttp.ClientTimeout(total=5)
                                              ) as r:
                                                                    return r.status == 200
              except Exception:
                            return False

          # ── Private helpers ───────────────────────────────────

    async def _fetch_ohlcv(
              self,
              asset: str,
              interval: str = "1h",
              limit: int = 100,
    ) -> list:
              """
                      Fet
