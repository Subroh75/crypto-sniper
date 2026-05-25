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
from datetime import datetime, timezone, timedelta
from db import (
    save_trend_radar_signal,
    get_open_trend_radar_signals,
    update_trend_radar_outcome,
    get_trend_radar_stats,
)

logger = logging.getLogger(__name__)

# Render runs in Singapore — Binance geo-blocks Singapore IPs.
# MEXC is the primary source; Binance kept as silent fallback in case
# the bot ever moves off a geo-blocked region.
MEXC_KLINES = "https://api.mexc.com/api/v3/klines"
MEXC_TICKER = "https://api.mexc.com/api/v3/ticker/24hr"
MEXC_PRICE  = "https://api.mexc.com/api/v3/ticker/price"
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

    # ── P&D guards ────────────────────────────────────────────────────────
    # Guard 1: price vs filter cap — above 6% = already ran, likely pump
    # (was 5% — slightly relaxed to avoid killing slow-building trends)
    price_healthy = cur_price <= cur_filtered * 1.06

    # Guard 2: velocity consistency — must be positive for at least 3 of
    # the last 5 bars (not just the current bar after a flat/negative run).
    recent_vels  = velocities[-5:] if len(velocities) >= 5 else velocities
    vel_positive_bars = sum(1 for v in recent_vels if v > 0)
    vel_consistent = vel_positive_bars >= 3

    # Guard 3: no single-bar velocity explosion
    # If today's velocity is more than 6x yesterday's it's a spike, not a trend.
    # (relaxed from 4x — 4x was filtering out genuine breakout accelerations)
    vel_explosion = (prev_vel > 0 and cur_vel > prev_vel * 6)
    # ──────────────────────────────────────────────────────────────────────

    # Gate checks
    trend_up = cur_vel > 0

    # All-confirm signal
    # vol_ratio lowered from 1.5x to 1.2x — Kalman-smoothed baseline is
    # already conservative, 1.5x was rejecting genuine low-vol steady trends
    confirmed = (
        trend_up
        and accelerating
        and vol_ratio >= 1.2
        and price_healthy
        and vel_consistent
        and not vel_explosion
    )

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
        "label":           label,
        "confirmed":       confirmed,
        "velocity":        round(vel_pct, 3),       # % per bar
        "accelerating":    accelerating,
        "vel_consistent":  vel_consistent,          # 3/5 recent bars positive
        "vel_explosion":   vel_explosion,           # single-bar spike flag
        "vol_ratio":       round(vol_ratio, 2),
        "price":           cur_price,
        "filtered":        round(cur_filtered, 6),
        "price_vs_filter": round((cur_price / cur_filtered - 1) * 100, 2),
    }


# ─────────────────────────────────────────────
#  Data fetch — Binance 1D klines
# ─────────────────────────────────────────────

async def _fetch_klines(session: aiohttp.ClientSession,
                        symbol: str,
                        limit: int = 90) -> tuple[list[float], list[float]]:
    """
    Fetch 1D klines. Tries MEXC first (Render = Singapore, Binance geo-blocked).
    Falls back to Binance silently in case region changes.
    Returns (closes, vol_usd).
    """
    async def _try(url: str) -> tuple[list[float], list[float]]:
        try:
            params = {"symbol": f"{symbol}USDT", "interval": "1d", "limit": limit}
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return [], []
                data = await r.json()
            if not data or not isinstance(data, list) or len(data) < 5:
                return [], []
            closes  = [float(c[4]) for c in data]
            volumes = [float(c[5]) for c in data]
            vol_usd = [v * c for v, c in zip(volumes, closes)]
            return closes, vol_usd
        except Exception:
            return [], []

    # MEXC first
    closes, vol_usd = await _try(MEXC_KLINES)
    if closes:
        return closes, vol_usd
    # Binance fallback
    return await _try(BINANCE_KLINES)


async def _get_top_symbols(session: aiohttp.ClientSession,
                           n: int = 100) -> list[str]:
    """
    Top N USDT pairs by 24h quote volume.
    Tries MEXC first (Render = Singapore, Binance geo-blocked),
    falls back to Binance silently.
    """
    STABLECOINS = {
        "USDT","USDC","BUSD","DAI","TUSD","USDP","USDD","GUSD",
        "FRAX","LUSD","FDUSD","PYUSD","STETH","WBTC","WETH",
        "WBETH","EZETH","WEETH","SUSDE","USDE"
    }

    async def _parse_tickers(url: str, source: str) -> list[str]:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
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
            result = [sym for sym, _ in pairs[:n]]
            if result:
                logger.info(f"[TrendRadar] Universe: {len(result)} symbols from {source}")
            return result
        except Exception as e:
            logger.warning(f"[TrendRadar] {source} ticker failed: {e}")
            return []

    # MEXC first
    syms = await _parse_tickers(MEXC_TICKER, "MEXC")
    if syms:
        return syms
    # Binance fallback
    return await _parse_tickers(BINANCE_TICKER, "Binance")


# Keep old name as alias so nothing else breaks
_get_top_binance_symbols = _get_top_symbols


# ─────────────────────────────────────────────
#  Telegram message formatter
# ─────────────────────────────────────────────

def _trend_radar_msg(hits: list[dict], scan_time: str) -> str:
    lines = [
        "◎ CRYPTO SNIPER  --  TREND RADAR",
        f"Vol Filter scan \u00b7 {scan_time} \u00b7 1D \u00b7 top 100",
        "\u2501" * 32,
    ]
    for i, h in enumerate(hits[:8], 1):
        sym   = h["symbol"]
        label = h["label"]
        vel   = h["velocity"]
        vr    = h["vol_ratio"]
        diff  = h["price_vs_filter"]
        price = h["price"]

        diff_str = f"+{diff:.1f}%" if diff >= 0 else f"{diff:.1f}%"

        # Trade setup
        entry     = price
        stop      = entry * 0.90
        target_3d = entry * (1 + vel * 3 / 100)
        target_5d = entry * (1 + vel * 5 / 100)
        risk      = entry - stop          # always entry * 0.10
        reward_3d = target_3d - entry
        rr_3d     = reward_3d / risk if risk > 0 else 0

        # Format prices — use 6 sig-figs style
        def _fp(v):
            if v == 0:
                return "0"
            if v >= 1:
                return f"{v:,.4f}"
            return f"{v:.6g}"

        lines += [
            f"#{i}  {sym}/USDT",
            f"Trend:    {label}",
            f"Momentum: {vel:+.2f}% per day",
            f"Vol:      {vr:.1f}x above baseline",
            f"Price vs baseline: {diff_str}",
            "",
            f"Entry:    {_fp(entry)}",
            f"Stop:     {_fp(stop)}  (-10%)",
            f"Target 3D: {_fp(target_3d)}  (+{vel*3:.1f}%)",
            f"Target 5D: {_fp(target_5d)}  (+{vel*5:.1f}%)",
            f"R:R (3D): {rr_3d:.1f}:1",
            "",
        ]
    lines += [
        "\u2501" * 32,
        "Experimental \u00b7 Not financial advice",
        "https://crypto-sniper.app",
    ]
    return "\n".join(lines)


# ─────────────────────────────────────────────
#  Passive scan job — runs every 1 hour
# ─────────────────────────────────────────────

async def trend_radar_job(context) -> None:
    """
    Vol Filter-based Trend Radar passive scan.
    Fires every 1 hour. Alerts only new confirmed signals (8h cooldown).
    """
    import time
    now = time.time()
    now_utc = datetime.now(timezone.utc)
    scan_time = now_utc.strftime("%d %b %Y %H:%M UTC")

    # Clean expired cooldowns
    global _kalman_alerted
    _kalman_alerted = {k: v for k, v in _kalman_alerted.items()
                       if now - v < KALMAN_COOLDOWN}

    logger.info("[TrendRadar] Starting Vol Filter scan...")

    hits: list[dict] = []
    errors = 0

    async with aiohttp.ClientSession() as session:
        symbols = await _get_top_symbols(session, n=100)
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

    # Mark alerted + log to DB
    signal_date = now_utc.strftime("%Y-%m-%d")
    for h in hits:
        _kalman_alerted[f"KALMAN:{h['symbol']}"] = now
        try:
            await save_trend_radar_signal(
                symbol          = h["symbol"],
                signal_date     = signal_date,
                label           = h["label"],
                velocity        = h["velocity"],
                vol_ratio       = h["vol_ratio"],
                entry_price     = h["price"],
                filter_price    = h["filtered"],
                price_vs_filter = h["price_vs_filter"],
            )
        except Exception as e:
            logger.warning(f"[TrendRadar] DB save failed for {h['symbol']}: {e}")

    # Send Telegram message
    msg = _trend_radar_msg(hits, scan_time)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_CHAT,
            text=msg,
        )
        logger.info(f"[TrendRadar] Alert sent — {len(hits)} signals, logged to DB")
    except Exception as e:
        logger.warning(f"[TrendRadar] Telegram send failed: {e}")

# ─────────────────────────────────────────────
#  Outcome Checker — runs daily at 22:00 UTC
# ─────────────────────────────────────────────

async def _fetch_current_price(session: aiohttp.ClientSession, symbol: str) -> float:
    """
    Fetch latest price. Tries MEXC first, Binance fallback.
    MEXC /ticker/price returns {"symbol": ..., "price": ...} — identical to Binance.
    """
    async def _try(url: str) -> float:
        try:
            async with session.get(
                url,
                params={"symbol": f"{symbol}USDT"},
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status != 200:
                    return 0.0
                data = await r.json()
                return float(data.get("price", 0))
        except Exception:
            return 0.0

    price = await _try(MEXC_PRICE)
    if price > 0:
        return price
    return await _try("https://api.binance.com/api/v3/ticker/price")


async def trend_radar_outcome_checker(context) -> None:
    """
    Daily job: checks all OPEN Trend Radar signals.
    For each signal where 5 or 10 days have elapsed, fetches current price
    and marks WIN / LOSS / OPEN.

    WIN  = price >= target_price (entry * 1.20) at check date
    LOSS = price <= stop_price   (entry * 0.90) at check date
    OPEN = neither hit yet
    """
    now_utc     = datetime.now(timezone.utc)
    today       = now_utc.strftime("%Y-%m-%d")

    try:
        open_signals = await get_open_trend_radar_signals()
    except Exception as e:
        logger.warning(f"[TrendRadar] Outcome checker DB read failed: {e}")
        return

    if not open_signals:
        logger.info("[TrendRadar] Outcome checker: no open signals")
        return

    logger.info(f"[TrendRadar] Outcome checker: {len(open_signals)} open signals")

    updated: list[str] = []

    async with aiohttp.ClientSession() as session:
        for sig in open_signals:
            try:
                signal_date  = datetime.strptime(sig["signal_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days_elapsed = (now_utc - signal_date).days
                entry        = sig["entry_price"]
                stop         = sig["stop_price"]
                target       = sig["target_price"]
                symbol       = sig["symbol"]
                row_id       = sig["id"]

                if days_elapsed < 5:
                    continue  # too early

                price = await _fetch_current_price(session, symbol)
                if price <= 0:
                    continue

                pct = round((price - entry) / entry * 100, 2)

                # Determine outcome
                if price >= target:
                    outcome = "WIN"
                elif price <= stop:
                    outcome = "LOSS"
                else:
                    outcome = "OPEN"

                # Update 5D if not yet set
                if days_elapsed >= 5 and sig.get("outcome_5d") == "OPEN":
                    await update_trend_radar_outcome(row_id, 5, price, pct, outcome)
                    updated.append(f"{symbol} 5D: {outcome} ({pct:+.1f}%)")

                # Update 10D if not yet set
                if days_elapsed >= 10 and sig.get("outcome_10d") == "OPEN":
                    await update_trend_radar_outcome(row_id, 10, price, pct, outcome)
                    updated.append(f"{symbol} 10D: {outcome} ({pct:+.1f}%)")

            except Exception as e:
                logger.debug(f"[TrendRadar] Outcome check error for {sig.get('symbol','?')}: {e}")

    if not updated:
        logger.info("[TrendRadar] Outcome checker: nothing to update yet")
        return

    logger.info(f"[TrendRadar] Outcomes updated: {updated}")

    # Send summary to admin Telegram
    try:
        stats = await get_trend_radar_stats()
        win_rate = stats.get("win_rate")
        total    = stats.get("total", 0)
        wins     = stats.get("wins", 0) or 0
        losses   = stats.get("losses", 0) or 0
        open_ct  = stats.get("open", 0) or 0
        avg_10d  = stats.get("avg_pct_10d")

        lines = [
            "CRYPTO SNIPER  --  TREND RADAR",
            f"Performance update · {today}",
            "\u2501" * 32,
        ]
        for u in updated:
            lines.append(u)
        lines += [
            "\u2501" * 32,
            f"Total signals:  {total}",
            f"Wins:           {wins}",
            f"Losses:         {losses}",
            f"Open:           {open_ct}",
            f"Win rate:       {win_rate}%" if win_rate is not None else "Win rate:       N/A (need more data)",
            f"Avg return 10D: {avg_10d:+.1f}%" if avg_10d is not None else "Avg return 10D: N/A",
        ]

        await context.bot.send_message(
            chat_id=ADMIN_CHAT,
            text="\n".join(lines),
        )
    except Exception as e:
        logger.warning(f"[TrendRadar] Outcome Telegram notify failed: {e}")
