"""
kalman_scanner.py — Trend Radar passive scan (Kalman Filter, experimental)

Runs every 6 hours. Scans top 100 coins by volume (Binance 1D klines).
Outputs a Telegram message tagged [TREND RADAR] — completely separate from VPRT.

Kalman model
------------
State vector:  [price, velocity]
Transition:    price_t   = price_{t-1} + velocity_{t-1}
               velocity_t = velocity_{t-1}   (constant velocity model)
Observation:   price only (close)

After convergence (~20 bars) the filter gives:
  - filtered_price  : smoothed price estimate (less lag than EMA)
  - velocity        : rate of change per bar (positive = accelerating up)

Volume baseline uses a separate 1D Kalman on raw volume — more robust than
simple 20-bar average because it down-weights outlier candles.

Signal logic (all must confirm):
  1. velocity  > 0          (trend moving up)
  2. velocity  > prev_vel   (acceleration — trend gaining strength)
  3. vol_ratio > 1.5        (current vol > 1.5x Kalman vol baseline)
  4. price     > filtered   (close above smoothed trend — not extended)

Output label:
  velocity >  1.5% / bar   → STRONG MOMENTUM
  velocity >  0.5% / bar   → BUILDING MOMENTUM
  velocity >= 0.0% / bar   → EARLY TREND
"""

import asyncio
import logging
import aiohttp
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

BINANCE_KLINES = "https://api.binance.com/api/v3/klines"
BINANCE_TICKER = "https://api.binance.com/api/v3/ticker/24hr"
ADMIN_CHAT     = int(os.environ.get("ADMIN_CHAT_ID", "5861457546"))
KALMAN_COOLDOWN = 8 * 3600   # 8h cooldown per coin — fires less than vol spikes

# Module-level cooldown dict
_kalman_alerted: dict[str, float] = {}


# ─────────────────────────────────────────────
#  Kalman Filter (pure Python, no scipy needed)
# ─────────────────────────────────────────────

def _kalman_filter(observations: list[float],
                   process_noise: float = 1e-4,
                   obs_noise: float = 1e-2) -> tuple[list[float], list[float]]:
    """
    1D Kalman filter with constant-velocity model.

    Returns:
        filtered  : smoothed values (same length as observations)
        velocity  : velocity estimate at each step
    """
    n = len(observations)
    if n < 10:
        return observations[:], [0.0] * n

    # State: [x, v] — position and velocity
    x = observations[0]
    v = 0.0

    # Covariance matrix (2x2 flattened as [p00, p01, p10, p11])
    p00, p01, p10, p11 = 1.0, 0.0, 0.0, 1.0

    # Noise
    q = process_noise   # process noise (how much the true state can change)
    r = obs_noise       # observation noise (how noisy the measurement is)

    filtered  = []
    velocities = []

    for z in observations:
        # ── Predict ─────────────────────────────────────────────────
        x_pred = x + v
        v_pred = v

        # Predicted covariance
        p00_pred = p00 + p01 + p10 + p11 + q
        p01_pred = p01 + p11
        p10_pred = p10 + p11
        p11_pred = p11 + q

        # ── Update ──────────────────────────────────────────────────
        # Kalman gain (for position observation only)
        s = p00_pred + r                        # innovation covariance
        k0 = p00_pred / s                       # gain for position
        k1 = p10_pred / s                       # gain for velocity

        # Innovation
        innov = z - x_pred

        # Updated state
        x = x_pred + k0 * innov
        v = v_pred + k1 * innov

        # Updated covariance
        p00 = (1 - k0) * p00_pred
        p01 = (1 - k0) * p01_pred
        p10 = p10_pred - k1 * p00_pred
        p11 = p11_pred - k1 * p01_pred

        filtered.append(x)
        velocities.append(v)

    return filtered, velocities


def _kalman_signal(closes: list[float],
                   volumes: list[float]) -> dict:
    """
    Run Kalman on price and volume series.
    Returns signal dict with label, velocity, vol_ratio, quality.
    """
    if len(closes) < 30:
        return {"label": "INSUFFICIENT_DATA", "velocity": 0.0, "vol_ratio": 0.0}

    # Normalise closes to avoid float precision issues
    base = closes[0]
    norm = [c / base for c in closes]

    filtered, velocities = _kalman_filter(norm, process_noise=1e-4, obs_noise=5e-3)

    # Current state (last bar)
    cur_price    = closes[-1]
    cur_filtered = filtered[-1] * base
    cur_vel      = velocities[-1] * base      # absolute $/bar
    prev_vel     = velocities[-2] * base if len(velocities) >= 2 else 0.0
    vel_pct      = (cur_vel / cur_price) * 100 if cur_price > 0 else 0.0
    accelerating = cur_vel > prev_vel

    # Volume Kalman baseline
    vol_filtered, _ = _kalman_filter(volumes, process_noise=1e-3, obs_noise=1e-1)
    vol_baseline  = vol_filtered[-1]
    vol_ratio     = volumes[-1] / vol_baseline if vol_baseline > 0 else 1.0

    # Gate checks
    trend_up      = cur_vel > 0
    price_healthy = cur_price <= cur_filtered * 1.08    # not more than 8% above filter

    # All-confirm signal
    confirmed = trend_up and accelerating and vol_ratio >= 1.5 and price_healthy

    # Label
    if not confirmed:
        if trend_up and vol_ratio >= 1.5:
            label = "VOL_WITHOUT_TREND"
        elif trend_up and accelerating:
            label = "TREND_WITHOUT_VOL"
        else:
            label = "NO_SIGNAL"
    else:
        if vel_pct >= 1.5:
            label = "STRONG MOMENTUM"
        elif vel_pct >= 0.5:
            label = "BUILDING MOMENTUM"
        else:
            label = "EARLY TREND"

    return {
        "label":       label,
        "confirmed":   confirmed,
        "velocity":    round(vel_pct, 3),       # % per bar
        "accelerating": accelerating,
        "vol_ratio":   round(vol_ratio, 2),
        "price":       cur_price,
        "filtered":    round(cur_filtered, 6),
        "price_vs_filter": round((cur_price / cur_filtered - 1) * 100, 2),  # % above/below
    }


# ─────────────────────────────────────────────
#  Data fetch — Binance 1D klines
# ─────────────────────────────────────────────

async def _fetch_klines(session: aiohttp.ClientSession,
                        symbol: str,
                        limit: int = 90) -> tuple[list[float], list[float]]:
    """
    Fetch 1D klines from Binance. Returns (closes, volumes).
    """
    try:
        params = {"symbol": f"{symbol}USDT", "interval": "1d", "limit": limit}
        async with session.get(
            BINANCE_KLINES,
            params=params,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as r:
            if r.status != 200:
                return [], []
            data = await r.json()
        closes  = [float(c[4]) for c in data]   # index 4 = close
        volumes = [float(c[5]) for c in data]    # index 5 = volume (base)
        # Convert volume to quote (USD) using close price
        vol_usd = [v * c for v, c in zip(volumes, closes)]
        return closes, vol_usd
    except Exception:
        return [], []


async def _get_top_binance_symbols(session: aiohttp.ClientSession,
                                   n: int = 100) -> list[str]:
    """Top N Binance USDT pairs by 24h quote volume."""
    STABLECOINS = {
        "USDT","USDC","BUSD","DAI","TUSD","USDP","USDD","GUSD",
        "FRAX","LUSD","FDUSD","PYUSD","STETH","WBTC","WETH",
        "WBETH","EZETH","WEETH","SUSDE","USDE"
    }
    try:
        async with session.get(
            BINANCE_TICKER,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            if r.status != 200:
                return []
            tickers = await r.json()
        pairs = [
            (t["symbol"][:-4], float(t.get("quoteVolume", 0)))
            for t in tickers
            if t["symbol"].endswith("USDT")
            and t["symbol"][:-4] not in STABLECOINS
            and float(t.get("quoteVolume", 0)) > 500_000
        ]
        pairs.sort(key=lambda x: x[1], reverse=True)
        return [sym for sym, _ in pairs[:n]]
    except Exception as e:
        logger.warning(f"[TrendRadar] Binance ticker failed: {e}")
        return []


# ─────────────────────────────────────────────
#  Telegram message formatter
# ─────────────────────────────────────────────

def _trend_radar_msg(hits: list[dict], scan_time: str) -> str:
    lines = [
        "CRYPTO SNIPER  --  TREND RADAR",
        f"Kalman scan · {scan_time} · 1D · top 100",
        "\u2501" * 32,
    ]
    for i, h in enumerate(hits[:8], 1):
        sym   = h["symbol"]
        label = h["label"]
        vel   = h["velocity"]
        vr    = h["vol_ratio"]
        diff  = h["price_vs_filter"]
        diff_str = f"+{diff:.1f}%" if diff >= 0 else f"{diff:.1f}%"
        lines += [
            f"#{i}  {sym}/USDT",
            f"Trend:    {label}",
            f"Velocity: {vel:+.2f}% per day",
            f"Vol:      {vr:.1f}x above baseline",
            f"Price vs filter: {diff_str}",
            "",
        ]
    lines += [
        "\u2501" * 32,
        "Experimental · Not financial advice",
        "https://crypto-sniper.app",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  Passive scan job — runs every 6 hours
# ─────────────────────────────────────────────

async def trend_radar_job(context) -> None:
    """
    Kalman-based Trend Radar passive scan.
    Fires every 6 hours. Alerts only new confirmed signals (8h cooldown).
    """
    import time
    now = time.time()
    now_utc = datetime.now(timezone.utc)
    scan_time = now_utc.strftime("%d %b %Y %H:%M UTC")

    # Clean expired cooldowns
    global _kalman_alerted
    _kalman_alerted = {k: v for k, v in _kalman_alerted.items()
                       if now - v < KALMAN_COOLDOWN}

    logger.info("[TrendRadar] Starting Kalman scan...")

    hits: list[dict] = []
    errors = 0

    async with aiohttp.ClientSession() as session:
        symbols = await _get_top_binance_symbols(session, n=100)
        if not symbols:
            logger.warning("[TrendRadar] No symbols returned — aborting")
            return

        logger.info(f"[TrendRadar] Scanning {len(symbols)} symbols")

        # Fetch klines in batches to avoid hammering Binance
        tasks = [_fetch_klines(session, sym) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sym, result in zip(symbols, results):
            if isinstance(result, Exception) or not result or not result[0]:
                errors += 1
                continue
            closes, volumes = result
            if len(closes) < 30:
                errors += 1
                continue
            try:
                sig = _kalman_signal(closes, volumes)
                if sig["confirmed"] and f"KALMAN:{sym}" not in _kalman_alerted:
                    hits.append({"symbol": sym, **sig})
            except Exception as e:
                logger.debug(f"[TrendRadar] {sym} error: {e}")
                errors += 1

    # Sort by velocity desc
    hits.sort(key=lambda x: x["velocity"], reverse=True)

    logger.info(f"[TrendRadar] Done — {len(hits)} confirmed signals, {errors} errors")

    if not hits:
        logger.info("[TrendRadar] No new Trend Radar signals this cycle")
        return

    # Mark alerted
    for h in hits:
        _kalman_alerted[f"KALMAN:{h['symbol']}"] = now

    # Send Telegram message
    msg = _trend_radar_msg(hits, scan_time)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT,
            text=msg,
        )
        logger.info(f"[TrendRadar] Alert sent — {len(hits)} signals")
    except Exception as e:
        logger.warning(f"[TrendRadar] Telegram send failed: {e}")
