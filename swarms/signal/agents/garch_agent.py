"""
swarms/signal/agents/garch_agent.py
─────────────────────────────────────────────────────────────
Agent 2 of 5 — GARCH(1,1) Volatility Regime Estimator

Pure-Python GARCH — no scipy, no external ML libs.
Reads log_returns from blackboard (written by KalmanAgent).

GARCH(1,1): sigma_t^2 = omega + alpha*eps_{t-1}^2 + beta*sigma_{t-1}^2
alpha=0.10 (shock sensitivity), beta=0.85 (persistence)

REGIME THRESHOLDS (annualised vol %):
  < 60%   → LOW    modifier=1.0  gate=PASS
  60-120% → MEDIUM modifier=0.6  gate=PASS
  > 120%  → HIGH   modifier=0.3  gate=SUPPRESS

BLACKBOARD READS:  log_returns
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

from cs_platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent


class GARCHAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="garch",
        version="1.0.0",
        description="Pure-Python GARCH(1,1) vol regime estimator and position size modifier",
        reads=["log_returns"],
        writes=[
            "garch_vol_current", "garch_vol_regime",
            "garch_vol_percentile", "position_modifier",
            "vol_trending_up", "garch_signal_gate",
        ],
        schedule_seconds=300,
    )

    ALPHA          = 0.10
    BETA           = 0.85
    ANNUALISE      = math.sqrt(24 * 365)
    LOW_THRESHOLD  = 60.0
    HIGH_THRESHOLD = 120.0

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            log_returns = context.get("log_returns", [])

            if len(log_returns) < 20:
                return self._ok({
                    "garch_vol_current":    50.0,
                    "garch_vol_regime":     "MEDIUM",
                    "garch_vol_percentile": 50.0,
                    "position_modifier":    0.6,
                    "vol_trending_up":      False,
                    "garch_signal_gate":    "PASS",
                }, t0, warnings=["Insufficient log_returns — neutral defaults used"])

            sigma_series = self._fit_garch(log_returns)
            if not sigma_series:
                return self._fail("GARCH returned empty series", t0)

            sigma_now  = sigma_series[-1]
            vol_annual = sigma_now * self.ANNUALISE * 100
            vol_pct    = self._percentile(sigma_series, sigma_now)

            if vol_annual < self.LOW_THRESHOLD:
                regime, modifier, gate = "LOW", 1.0, "PASS"
            elif vol_annual < self.HIGH_THRESHOLD:
                regime, modifier, gate = "MEDIUM", 0.6, "PASS"
            else:
                regime, modifier, gate = "HIGH", 0.3, "SUPPRESS"

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

    def _fit_garch(self, rets: list[float]) -> list[float]:
        n      = len(rets)
        mean_r = sum(rets) / n
        var    = sum((r - mean_r) ** 2 for r in rets) / n
        omega  = max(var * (1 - self.ALPHA - self.BETA), 1e-8)
        sigma2 = var
        series = []
        for r in rets:
            sigma2 = omega + self.ALPHA * (r - mean_r) ** 2 + self.BETA * sigma2
            sigma2 = max(sigma2, 1e-10)
            series.append(math.sqrt(sigma2))
        return series

    def _percentile(self, series: list[float], val: float) -> float:
        if not series:
            return 50.0
        return round(sum(1 for v in series if v < val) / len(series) * 100, 1)
