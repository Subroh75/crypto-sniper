"""
swarms/signal/agents/signal_agent.py
─────────────────────────────────────────────────────────────
Agent 4 of 5 — V/P/R/T Signal Scoring Engine v2.0

Reads OHLCV arrays from blackboard (KalmanAgent).
Runs V/P/R/T scoring with ATR-calibrated stops.
Gates signals at minimum R:R of 1.5.

SCORING (max 13 pts):
  V — Volume    0-5  relative vol vs 20-bar avg
  P — Momentum  0-3  ATR-normalised price move
  R — Range Pos 0-2  close position in bar range
  T — Trend     0-3  EMA stack + Kalman velocity

LABELS:  >= 9 = STRONG BUY | >= 5 = BUY | < 5 = NO SIGNAL
R:R GATE: conviction = 0 if R:R < 1.5

BLACKBOARD READS:  closes, highs, lows, vols, raw_price,
                   kalman_velocity_pct, position_modifier
BLACKBOARD WRITES: vprt_score, signal_label, entry, stop,
                   target, rr_ratio, conviction, atr,
                   signal_direction, v/p/r/t_score
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

from cs_platform.registry.agent_base import AgentIdentity, AgentResult, BaseAgent


class SignalAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="vprt",
        version="2.0.0",
        description="V/P/R/T scoring with ATR stops, R:R gating and GARCH conviction modifier",
        reads=[
            "closes", "highs", "lows", "vols",
            "raw_price", "kalman_velocity_pct", "position_modifier",
        ],
        writes=[
            "vprt_score", "signal_label", "entry", "stop", "target",
            "rr_ratio", "conviction", "atr", "signal_direction",
            "v_score", "p_score", "r_score", "t_score",
        ],
        schedule_seconds=300,
    )

    MIN_RR    = 1.5
    MAX_SCORE = 13

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
                    f"{len(closes)} closes price={price}", t0
                )

            atr     = self._calc_atr(highs, lows, closes, 14)
            v_score = self._vol_score(vols, closes)
            p_score = self._momentum_score(closes, atr)
            r_score = self._range_score(closes, highs, lows)
            t_score = self._trend_score(closes, vel)
            total   = v_score + p_score + r_score + t_score

            if total >= 9:
                label = "STRONG BUY"
            elif total >= 5:
                label = "BUY"
            else:
                label = "NO SIGNAL"

            entry     = price
            atr_stop  = 1.5 * atr if atr > 0 else entry * 0.07
            stop      = entry - atr_stop
            stop_pct  = atr_stop / entry if entry > 0 else 0.07

            vel_proj  = abs(vel) * 72 / 100
            min_pct   = stop_pct * self.MIN_RR
            target_pct = max(vel_proj, min_pct)
            target    = entry * (1 + target_pct)
            rr        = target_pct / stop_pct if stop_pct > 0 else 0

            if rr < self.MIN_RR or label == "NO SIGNAL":
                conviction = 0
                direction  = "NEUTRAL"
            else:
                vol_mod    = context.get("position_modifier", 0.6)
                conviction = int(min((total / self.MAX_SCORE) * 100 * vol_mod, 100))
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

    def _calc_atr(self, highs, lows, closes, period=14) -> float:
        if len(closes) < 2 or not highs or not lows:
            return 0.0
        trs = [
            max(highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i]  - closes[i - 1]))
            for i in range(1, len(closes))
        ]
        window = trs[-period:] if len(trs) >= period else trs
        return sum(window) / len(window) if window else 0.0

    def _calc_ema(self, prices, period) -> Optional[float]:
        if len(prices) < period:
            return None
        k   = 2 / (period + 1)
        ema = sum(prices[:period]) / period
        for p in prices[period:]:
            ema = p * k + ema * (1 - k)
        return ema

    def _vol_score(self, vols, closes) -> int:
        if vols and len(vols) >= 21:
            avg = sum(vols[-21:-1]) / 20
            rel = vols[-1] / avg if avg > 0 else 1.0
        elif len(closes) >= 2:
            chg = abs(closes[-1] - closes[-2]) / closes[-2] * 100
            rel = 1.0 + chg / 10
        else:
            return 0
        if rel >= 5:     return 5
        elif rel >= 2:   return 3
        elif rel >= 1.5: return 2
        elif rel >= 1:   return 1
        return 0

    def _momentum_score(self, closes, atr) -> int:
        if len(closes) < 2 or atr <= 0:
            return 0
        sigma = (closes[-1] - closes[-2]) / atr
        if sigma >= 1.5:   return 3
        elif sigma >= 0.8: return 2
        elif sigma >= 0.3: return 1
        return 0

    def _range_score(self, closes, highs, lows) -> int:
        if not highs or not lows:
            return 0
        rng = highs[-1] - lows[-1]
        if rng <= 0:
            return 0
        pos = (closes[-1] - lows[-1]) / rng
        if pos >= 0.75: return 2
        elif pos >= 0.5: return 1
        return 0

    def _trend_score(self, closes, vel_pct) -> int:
        score = 0
        ema20 = self._calc_ema(closes, 20)
        ema50 = self._calc_ema(closes, 50)
        if ema20 and ema50 and closes[-1] > ema20 > ema50:
            score += 2
        if vel_pct > 0.5:
            score += 1
        return min(score, 3)
