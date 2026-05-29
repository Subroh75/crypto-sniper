"""
swarms/signal/agents/kalman_agent.py
─────────────────────────────────────────────────────────────
Agent 1 of 5 — Kalman Filter Price Cleaner and OHLCV Provider

RESPONSIBILITY:
  Fetch OHLCV once per cycle and run the Kalman filter.
  All downstream agents read from the blackboard rather
  than fetching their own price data. One API call per cycle
  regardless of how many agents run.

DATA SOURCES (priority order):
  1. MEXC      — primary (Render = Singapore, Binance geo-blocked)
  2. Binance   — fallback
  3. Gate.io   — second fallback (different kline format)

BLACKBOARD WRITES:
  kalman_price, kalman_velocity, kalman_velocity_pct,
  kalman_uncertainty, kalman_vol_ratio,
  log_returns, closes, highs, lows, vols,
  raw_price, trend_label, bars_count, accelerating,
  exchange, exchange_source
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


# ── Exchange endpoints ─────────────────────────────────────────────
MEXC_KLINES    = "https://api.mexc.com/api/v3/klines"
BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
GATE_KLINES    = "https://api.gateio.ws/api/v4/spot/candlesticks"

# Gate.io kline field order: [timestamp, vol, close, high, low, open, ...]
# Binance/MEXC:              [ts, open, high, low, close, vol, ...]
GATE_IDX = {"ts": 0, "vol": 1, "close": 2, "high": 3, "low": 4, "open": 5}


class KalmanAgent(BaseAgent):

    identity = AgentIdentity(
        department="signal",
        name="kalman",
        version="1.1.0",
        description=(
            "Fetches OHLCV (MEXC→Binance→Gate.io) and runs Kalman filter "
            "— price + velocity for all agents"
        ),
        reads=[],
        writes=[
            "kalman_price", "kalman_velocity", "kalman_velocity_pct",
            "kalman_uncertainty", "kalman_vol_ratio",
            "log_returns", "closes", "highs", "lows", "vols",
            "raw_price", "trend_label", "bars_count", "accelerating",
            "exchange", "exchange_source",
        ],
        schedule_seconds=300,
    )

    Q = 1e-4
    R = 1e-2

    async def run(self, asset: str, context: dict[str, Any]) -> AgentResult:
        t0 = time.monotonic()
        try:
            ohlcv, exchange_used = await self._fetch_ohlcv(asset)

            if not ohlcv or len(ohlcv) < 30:
                return self._fail(
                    f"Insufficient OHLCV for {asset}: "
                    f"{len(ohlcv or [])} bars (tried MEXC→Binance→Gate)", t0
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
                # Exchange provenance — consumed by orchestrator
                "exchange":            exchange_used,
                "exchange_source":     "cex",
            }, t0)

        except Exception as e:
            return self._fail(str(e), t0)

    async def health_check(self) -> bool:
        """Ping MEXC first, Binance fallback."""
        for url in [
            "https://api.mexc.com/api/v3/ping",
            "https://api.binance.com/api/v3/ping",
        ]:
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        url, timeout=aiohttp.ClientTimeout(total=5)
                    ) as r:
                        if r.status == 200:
                            return True
            except Exception:
                continue
        return False

    # ── OHLCV fetch: MEXC → Binance → Gate.io ─────────────────────

    async def _fetch_ohlcv(
        self,
        asset:    str,
        interval: str = "1h",
        limit:    int = 100,
    ) -> tuple[list, str]:
        """
        Try MEXC first (Render = Singapore, Binance geo-blocked).
        Fall back to Binance, then Gate.io.
        Returns (ohlcv_bars, exchange_name).
        """
        symbol_std  = asset.upper().replace("/", "")
        if not symbol_std.endswith("USDT"):
            symbol_std += "USDT"

        # Gate.io uses underscore format: BTC_USDT
        symbol_gate = symbol_std[:-4] + "_USDT"

        async with aiohttp.ClientSession() as session:

            # ── 1. MEXC (Binance-compatible format) ────────────────
            data = await self._try_binance_format(
                session, MEXC_KLINES,
                {"symbol": symbol_std, "interval": interval, "limit": limit}
            )
            if data:
                return data, "mexc"

            # ── 2. Binance ─────────────────────────────────────────
            data = await self._try_binance_format(
                session, BINANCE_KLINES,
                {"symbol": symbol_std, "interval": interval, "limit": limit}
            )
            if data:
                return data, "binance"

            # ── 3. Gate.io (different response format) ─────────────
            data = await self._try_gate(
                session, symbol_gate, interval, limit
            )
            if data:
                return data, "gate"

        return [], "none"

    async def _try_binance_format(
        self,
        session: aiohttp.ClientSession,
        url: str,
        params: dict,
    ) -> list:
        """
        Fetch klines from a Binance-compatible endpoint.
        Format: [ts, open, high, low, close, vol, ...]
        """
        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                if isinstance(data, list) and len(data) >= 30:
                    return data
        except Exception as e:
            self._warn(f"Binance-format fetch failed ({url}): {e}")
        return []

    async def _try_gate(
        self,
        session: aiohttp.ClientSession,
        currency_pair: str,
        interval: str,
        limit: int,
    ) -> list:
        """
        Fetch from Gate.io and normalise to Binance format.

        Gate.io kline response (array per bar):
          [timestamp_sec, vol, close, high, low, open, quote_vol]

        We return each bar as:
          [ts_ms, open, high, low, close, vol]
        so downstream consumers don't need to know the source.
        """
        # Gate.io interval strings differ slightly
        INTERVAL_MAP = {
            "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
            "1h": "1h", "2h": "2h", "4h": "4h", "8h": "8h",
            "1d": "1d", "3d": "3d", "1w": "7d",
        }
        gate_interval = INTERVAL_MAP.get(interval, interval)

        try:
            async with session.get(
                GATE_KLINES,
                params={
                    "currency_pair": currency_pair,
                    "interval":      gate_interval,
                    "limit":         limit,
                },
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return []
                raw = await resp.json()
                if not isinstance(raw, list) or len(raw) < 30:
                    return []

                # Normalise to [ts_ms, open, high, low, close, vol]
                normalised = []
                for bar in raw:
                    if len(bar) < 6:
                        continue
                    ts    = int(float(bar[GATE_IDX["ts"]])) * 1000  # → ms
                    open_ = float(bar[GATE_IDX["open"]])
                    high  = float(bar[GATE_IDX["high"]])
                    low   = float(bar[GATE_IDX["low"]])
                    close = float(bar[GATE_IDX["close"]])
                    vol   = float(bar[GATE_IDX["vol"]])
                    normalised.append([ts, open_, high, low, close, vol])

                return normalised if len(normalised) >= 30 else []

        except Exception as e:
            self._warn(f"Gate.io fetch failed ({currency_pair}): {e}")
        return []

    # ── Kalman filter ──────────────────────────────────────────────

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
