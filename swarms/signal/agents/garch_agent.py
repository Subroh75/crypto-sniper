"""
swarms/signal/agents/garch_agent.py
─────────────────────────────────────────────────────────────
Agent 2 of 5 — GARCH(1,1) Volatility Regime Estimator

RESPONSIBILITY:
  Reads log_returns from the blackboard (written by KalmanAgent).
  Estimates current volatility regime using a pure-Python GARCH(1,1).
  No scipy, no external ML libraries. Pure math, zero dependencies.

WHY THIS IS THE MOST IMPORTANT AGENT:
  Per Roan's framework: GARCH position sizing does MORE work than
  the directional signal. A 52% accurate signal with vol-scaled
  sizing outperforms a 60% accurate signal with fixed sizing.
  This agent IS the risk management brain of the entire swarm.

GARCH(1,1) MODEL:
  sigma_t^2 = omega + alpha * epsilon_{t-1}^2 + beta * sigma_{t-1}^2
  Parameters via moment matching (no optimisation needed):
    omega = variance * (1 - alpha - beta)
    alpha = 0.10  (shock sensitivity — standard crypto value)
    beta  = 0.85  (persistence — crypto vols are very persistent)
  Constraint: alpha + beta < 1.0 (0.95 here — mean reverting)

REGIME THRESHOLDS (annualised vol %):
  < 60%  → LOW    → Full position (modifier = 1.0) → PASS
  60-120% → MEDIUM → Reduced (modifier = 0.6)      → PASS
  > 120% → HIGH   → Minimum (modifier = 0.3)       → SUPPRESS

BLACKBOARD READS:  log_returns (from KalmanAgent)
BLACKBOARD WRITES: garch_vol_current, garch_vol_regime,
                   garch_vol_percentile, position_modifier,
                   vol_trending_up, garch_signal_gate
"""

from __future__ import annotations

import math
import os
import sys
import time
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent


class GARCHAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="garch",
        version="1.0.0",
        description="Pure-Python GARCH(1,1) vol regime estimator and position size modifier",
        reads=["log_returns"],
        writes=[
            "garch_vol_current",
            "garch_vol_regime",
            "garch_vol_percentile",
            "position_modifier",
            "vol_trending_up",
            "garch_signal_gate",
        ],
        schedule_seconds=300,
    )

    # GARCH parameters
    ALPHA = 0.10          # reaction to shocks
    BETA  = 0.85          # vol persistence (alpha + beta = 0.95 < 1.0)
    ANNUALISE = math.sqrt(24 * 365)  # hourly bars → annual

    # Regime thresholds (annualised vol %)
    LOW_THRESHOLD  = 60.0
    HIGH_THRESHOLD = 120.0

    # ── Core run ───────────────────────────────────────────────

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            log_returns = context.get("log_returns", [])

            if len(log_returns) < 20:
                self._warn(f"Only {len(log_returns)} log_returns — using neutral defaults")
                return self._ok({
                    "garch_vol_current":    50.0,
                    "garch_vol_regime":     "MEDIUM",
                    "garch_vol_percentile": 50.0,
                    "position_modifier":    0.6,
                    "vol_trending_up":      False,
                    "garch_signal_gate":    "PASS",
                }, t0, warnings=["Insufficient log_returns for GARCH — neutral defaults used"])

            sigma_series = self._fit_garch(log_returns)

            if not sigma_series:
                return self._fail("GARCH estimation produced empty series", t0)

            sigma_now  = sigma_series[-1]
            vol_annual = sigma_now * self.ANNUALISE * 100
            vol_pct    = self._percentile(sigma_series, sigma_now)

            # Regime + position modifier
            if vol_annual < self.LOW_THRESHOLD:
                regime   = "LOW"
                modifier = 1.0
                gate     = "PASS"
            elif vol_annual < self.HIGH_THRESHOLD:
                regime   = "MEDIUM"
                modifier = 0.6
                gate     = "PASS"
            else:
                regime   = "HIGH"
                modifier = 0.3
                gate     = "SUPPRESS"   # extreme vol = no new entries

            # Is vol accelerating?
            vol_trending_up = False
            if len(sigma_series) >= 10:
                recent = sum(sigma_series[-5:]) / 5
                prior  = sum(sigma_series[-10:-5]) / 5
                vol_trending_up = recent > prior * 1.05

            return self._ok({
                "garch_vol_current":    round(vol_annual, 2),
                "garch_vol_regime":     regime,
                "garch_vol_percentile": round(vol_pct, 1),
                "position_modifier":    modifier,
                "vol_trending_up":      vol_trending_up,
                "garch_signal_gate":    gate,
            }, t0)

        except Exception as e:
            return self._fail(str(e), t0)

    # ── Private: GARCH(1,1) fitting ───────────────────────────

    def _fit_garch(self, log_returns: list[float]) -> list[float]:
        """
        Fit GARCH(1,1) via moment matching.
        Returns conditional standard deviation series.
        No external dependencies — pure Python.
        """
        n      = len(log_returns)
        mean_r = sum(log_returns) / n
        var    = sum((r - mean_r) ** 2 for r in log_returns) / n
        omega  = max(var * (1 - self.ALPHA - self.BETA), 1e-8)

        sigma2   = var  # initialise at unconditional variance
        series   = []

        for r in log_returns:
            eps2   = (r - mean_r) ** 2
            sigma2 = omega + self.ALPHA * eps2 + self.BETA * sigma2
            sigma2 = max(sigma2, 1e-10)          # numerical floor
            series.append(math.sqrt(sigma2))

        return series

    def _percentile(self, series: list[float], value: float) -> float:
        """
        Percentile rank of value within series.
        80.0 = current vol higher than 80% of recent history.
        """
        if not series:
            return 50.0
        below = sum(1 for v in series if v < value)
        return round(below / len(series) * 100, 1)
