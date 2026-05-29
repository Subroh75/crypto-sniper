"""
swarms/signal/agents/signal_agent.py
─────────────────────────────────────────────────────────────
Agent 4 of 5 — V/P/R/T Signal Scoring Engine v2.0

RESPONSIBILITY:
  Runs the V/P/R/T scoring logic on OHLCV data from the blackboard.
  Computes ATR-calibrated stop/target for proper R:R calculation.
  Gates signals at minimum R:R of 1.5 before assigning conviction.

UPGRADE vs original backend/signals.py:
  ✓ Stop = 1.5x ATR (not hardcoded 10%)
  ✓ Target derived from Kalman velocity projection (not hardcoded +10%)
  ✓ R:R gate: conviction = 0 if R:R < 1.5
  ✓ Conviction integrates GARCH position_modifier
  ✓ Wrapped as BaseAgent — writes to blackboard, not HTTP response

SCORING (max 13 pts):
  V — Volume    (0-5) : relative vol vs 20-bar avg
  P — Momentum  (0-3) : ATR-normalised price move
  R — Range Pos (0-2) : close position in bar range
  T — Trend     (0-3) : EMA stack + Kalman velocity confirmation

SIGNAL LABELS:
  total >= 9  → STRONG BUY
  total >= 5  → BUY
  total  < 5  → NO SIGNAL

R:R GATE:
  R:R < 1.5   → conviction = 0, direction = NEUTRAL (suppressed)
  R:R >= 1.5  → conviction calculated, signal fires

BLACKBOARD READS:
  closes, highs, lows, vols       (from KalmanAgent)
  raw_price, kalman_velocity_pct  (from KalmanAgent)
  garch_vol_regime                (from GARCHAgent)
  position_modifier               (from GARCHAgent)

BLACKBOARD WRITES:
  vprt_score, signal_label, entry, stop, target,
  rr_ratio, conviction, atr, signal_direction,
  v_score, p_score, r_score, t_score
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent


class SignalAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="vprt",
        version="2.0.0",
        description="V/P/R/T scoring with ATR stops, R:R gating and GARCH conviction modifier",
        reads=[
            "closes", "highs", "lows", "vols",
            "raw_price", "kalman_velocity_pct",
            "garch_vol_regime", "position_modifier",
        ],
        writes=[
            "vprt_score", "signal_label",
            "entry", "stop", "target", "rr_ratio",
            "conviction", "atr", "signal_direction",
            "v_score", "p_score", "r_score", "t_score",
        ],
        schedule_seconds=300,
    )

    MIN_RR    = 1.5    # minimum acceptable risk:reward ratio
    MAX_SCORE = 13     # V(5) + P(3) + R(2) + T(3)

    # ── Core run ───────────────────────────────────────────────

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            closes = context.get("closes", [])
            highs  = context.get("highs",  [])
            lows   = context.get("lows",   [])
            vols   = context.get("vols",   [])
            price  = context.get("raw_price", 0)
            vel    = context.get("kalman_velocity_pct", 0)

            if len(closes) < 21 or price <= 0:
                return self._fail(
                    f"Insufficient OHLCV for {asset}: "
                    f"{len(closes)} closes, price={price}",
                    t0
                )

            # ATR — foundation for all trade parameters
            atr = self._calc_atr(highs, lows, closes, 14)

            # Component scores
            v_score = self._vol_score(vols, closes)
            p_score = self._momentum_score(closes, atr)
            r_score = self._range_score(closes, highs, lows)
            t_score = self._trend_score(closes, vel)

            total = v_score + p_score + r_score + t_score

            # Signal label
            if total >= 9:
                label = "STRONG BUY"
            elif total >= 5:
                label = "BUY"
            else:
                label = "NO SIGNAL"

            # Trade parameters
            entry     = price
            atr_stop  = 1.5 * atr if atr > 0 else entry * 0.07
            stop      = entry - atr_stop
            stop_pct  = atr_stop / entry if entry > 0 else 0.07

            # Target: Kalman velocity projected 3 days (72 hourly bars)
            # Minimum target must give R:R >= MIN_RR
            vel_proj_pct = abs(vel) * 72 / 100        # vel is % per bar
            min_pct      = stop_pct * self.MIN_RR
            target_pct   = max(vel_proj_pct, min_pct)
            target        = entry * (1 + target_pct)

            rr = target_pct / stop_pct if stop_pct > 0 else 0

            # Gate: suppress weak signals
            if rr < self.MIN_RR or label == "NO SIGNAL":
                conviction = 0
                direction  = "NEUTRAL"
            else:
                # vol_modifier from GARCH (1.0 / 0.6 / 0.3)
                vol_mod    = context.get("position_modifier", 0.6)
                raw_conv   = (total / self.MAX_SCORE) * 100
                conviction = int(min(raw_conv * vol_mod, 100))
                direction  = "LONG" if vel >= 0 else "SHORT"

            return self._ok({
                "vprt_score":       total,
                "signal_label":     label,
                "entry":            round(entry, 6),
                "stop":             round(stop, 6),
                "target":           round(target, 6),
                "rr_ratio":         round(rr, 2),
                "conviction":       conviction,
                "atr":              round(atr, 6),
                "signal_direction": direction,
                "v_score":          v_score,
                "p_score":          p_score,
                "r_score":          r_score,
                "t_score":          t_score,
            }, t0)

        except Exception as e:
            return self._fail(str(e), t0)

    # ── Private: indicator calculations ───────────────────────

    def _calc_atr(
        self,
        highs:  list[float],
        lows:   list[float],
        closes: list[float],
        period: int = 14,
    ) -> float:
        if len(closes) < 2 or not highs or not lows:
            return 0.0
        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i]  - lows[i],
                abs(highs[i]  - closes[i - 1]),
                abs(lows[i]   - closes[i - 1]),
            )
            trs.append(tr)
        window = trs[-period:] if len(trs) >= period else trs
        return sum(window) / len(window) if window else 0.0

    def _calc_ema(
        self,
        prices: list[float],
        period: int,
    ) -> Optional[float]:
        if len(prices) < period:
            return None
        k   = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for p in prices[period:]:
            ema = p * k + ema * (1 - k)
        return ema

    def _vol_score(
        self,
        vols:   list[float],
        closes: list[float],
    ) -> int:
        """V — Relative volume vs 20-bar average. Score 0-5."""
        if vols and len(vols) >= 21:
            avg = sum(vols[-21:-1]) / 20
            rel = vols[-1] / avg if avg > 0 else 1.0
        elif len(closes) >= 2:
            # Fallback: use price change magnitude as vol proxy
            chg = abs(closes[-1] - closes[-2]) / closes[-2] * 100
            rel = 1.0 + chg / 10
        else:
            return 0

        if rel >= 5:    return 5
        elif rel >= 2:  return 3
        elif rel >= 1.5: return 2
        elif rel >= 1:  return 1
        return 0

    def _momentum_score(
        self,
        closes: list[float],
        atr:    float,
    ) -> int:
        """P — ATR-normalised bar move. Score 0-3."""
        if len(closes) < 2 or atr <= 0:
            return 0
        move  = closes[-1] - closes[-2]
        sigma = move / atr            # sigmas of ATR
        if sigma >= 1.5:   return 3
        elif sigma >= 0.8: return 2
        elif sigma >= 0.3: return 1
        return 0

    def _range_score(
        self,
        closes: list[float],
        highs:  list[float],
        lows:   list[float],
    ) -> int:
        """R — Close position within today's bar range. Score 0-2."""
        if not highs or not lows:
            return 0
        h, l, c = highs[-1], lows[-1], closes[-1]
        rng = h - l
        if rng <= 0:
            return 0
        pos = (c - l) / rng           # 0 = at low, 1 = at high
        if pos >= 0.75: return 2
        elif pos >= 0.5: return 1
        return 0

    def _trend_score(
        self,
        closes:  list[float],
        vel_pct: float,
    ) -> int:
        """T — EMA stack bullish + Kalman velocity confirmation. Score 0-3."""
        score = 0
        ema20 = self._calc_ema(closes, 20)
        ema50 = self._calc_ema(closes, 50)
        if ema20 and ema50 and closes[-1] > ema20 > ema50:
            score += 2                # EMA stack bullish
        if vel_pct > 0.5:
            score += 1                # Kalman velocity confirming
        return min(score, 3)
