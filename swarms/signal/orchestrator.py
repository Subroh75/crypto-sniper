"""
swarms/signal/orchestrator.py
─────────────────────────────────────────────────────────────
Signal Swarm Orchestrator — Convergence Scorer and Telegram Delivery

RESPONSIBILITY:
  Reads the complete blackboard state for each asset.
  Scores convergence across all agent outputs (0-100).
  Fires a Telegram signal when convergence >= FIRE_THRESHOLD.
  Records every fired signal to Supabase via signal_tracker.

CONVERGENCE SCORING WEIGHTS:
  VPRT score         30%  — directional signal quality
  GARCH vol regime   25%  — risk management gate
  Sentiment          20%  — market context
  Kalman velocity    15%  — momentum confirmation
  R:R ratio bonus    10%  — trade quality gate

SUPPRESSION LOGIC:
  Any of these → conviction = 0, no fire:
    garch_signal_gate  == "SUPPRESS"
    sentiment_gate     == "AVOID"
    signal_direction   == "NEUTRAL"
    rr_ratio           <  1.5

FIRE THRESHOLD: 65/100 (tunable via env var SWARM_THRESHOLD)

TELEGRAM FORMAT:
  Private test channel during development.
  Production channel when merged to main.

ASSET UNIVERSE (default):
  BTC, ETH, SOL, BNB
  Extend via env var SWARM_ASSETS="BTC,ETH,SOL,BNB,MATIC"
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from swarm.blackboard import blackboard as bb

logger = logging.getLogger("signal.orchestrator")

# ── Configuration ──────────────────────────────────────────────────

FIRE_THRESHOLD = int(os.environ.get("SWARM_THRESHOLD", "65"))
ASSET_LIST     = [
    a.strip().upper()
    for a in os.environ.get("SWARM_ASSETS", "BTC,ETH,SOL,BNB").split(",")
    if a.strip()
]

TELEGRAM_BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TEST_CHANNEL = os.environ.get("TELEGRAM_TEST_CHANNEL", "")    # private
TELEGRAM_PROD_CHANNEL = os.environ.get("TELEGRAM_SIGNAL_CHANNEL", "")  # subscribers

# ── Scoring weights ────────────────────────────────────────────────

WEIGHTS = {
    "vprt":      0.30,
    "garch":     0.25,
    "sentiment": 0.20,
    "kalman":    0.15,
    "rr":        0.10,
}


# ── Main orchestrator function ─────────────────────────────────────

async def run_orchestrator() -> list[dict]:
    """
    Run one full orchestration cycle across all assets.
    Returns list of signals fired this cycle.
    """
    fired_signals = []

    for asset in ASSET_LIST:
        try:
            state = bb.read(asset)
            if not state:
                logger.debug(f"[{asset}] Blackboard empty — skipping")
                continue

            conviction, breakdown = _score_convergence(asset, state)

            logger.info(
                f"[{asset}] conviction={conviction} "
                f"direction={state.get('signal_direction','?')} "
                f"breakdown={breakdown}"
            )

            if conviction >= FIRE_THRESHOLD:
                signal = await _fire_signal(asset, state, conviction, breakdown)
                if signal:
                    fired_signals.append(signal)

        except Exception as e:
            logger.error(f"[{asset}] Orchestrator error: {e}")

    return fired_signals


def _score_convergence(
    asset: str,
    state: dict[str, Any],
) -> tuple[int, dict]:
    """
    Score convergence from 0 to 100.
    Returns (score, breakdown_dict).
    """
    score     = 0.0
    breakdown = {}

    # ── Suppression gates (any = instant 0) ─────────────────
    if state.get("garch_signal_gate") == "SUPPRESS":
        logger.debug(f"[{asset}] Suppressed: GARCH HIGH vol")
        return 0, {"suppressed": "GARCH_HIGH_VOL"}

    if state.get("sentiment_gate") == "AVOID":
        logger.debug(f"[{asset}] Suppressed: extreme greed")
        return 0, {"suppressed": "EXTREME_GREED"}

    if state.get("signal_direction", "NEUTRAL") == "NEUTRAL":
        logger.debug(f"[{asset}] Suppressed: NEUTRAL direction")
        return 0, {"suppressed": "NEUTRAL_DIRECTION"}

    rr = state.get("rr_ratio", 0)
    if rr < 1.5:
        logger.debug(f"[{asset}] Suppressed: R:R={rr:.2f} < 1.5")
        return 0, {"suppressed": f"LOW_RR_{rr:.2f}"}

    # ── VPRT component (0-30 pts) ─────────────────────────
    vprt_score = state.get("vprt_score", 0)
    vprt_max   = 13
    vprt_pts   = (vprt_score / vprt_max) * 100 * WEIGHTS["vprt"]
    score     += vprt_pts
    breakdown["vprt"] = round(vprt_pts, 1)

    # ── GARCH component (0-25 pts) ───────────────────────
    regime = state.get("garch_vol_regime", "HIGH")
    if regime == "LOW":
        garch_pts = 100 * WEIGHTS["garch"]       # full
    elif regime == "MEDIUM":
        garch_pts = 60  * WEIGHTS["garch"]       # partial
    else:
        garch_pts = 0                             # already suppressed above
    score     += garch_pts
    breakdown["garch"] = round(garch_pts, 1)

    # ── Sentiment component (0-20 pts) ───────────────────
    sentiment_score = state.get("sentiment_score", 50)
    # Normalise 0-100 sentiment → contribution
    # Sweet spot 40-70: full marks. Below 20 or above 80: reduced.
    if 40 <= sentiment_score <= 70:
        sent_pts = 100 * WEIGHTS["sentiment"]
    elif 25 <= sentiment_score < 40 or 70 < sentiment_score <= 80:
        sent_pts = 70  * WEIGHTS["sentiment"]
    else:
        sent_pts = 30  * WEIGHTS["sentiment"]
    score     += sent_pts
    breakdown["sentiment"] = round(sent_pts, 1)

    # ── Kalman velocity component (0-15 pts) ─────────────
    vel_pct = abs(state.get("kalman_velocity_pct", 0))
    if vel_pct >= 1.5:
        vel_pts = 100 * WEIGHTS["kalman"]
    elif vel_pct >= 0.5:
        vel_pts = 70  * WEIGHTS["kalman"]
    elif vel_pct >= 0.1:
        vel_pts = 40  * WEIGHTS["kalman"]
    else:
        vel_pts = 0
    score     += vel_pts
    breakdown["kalman"] = round(vel_pts, 1)

    # ── R:R bonus component (0-10 pts) ───────────────────
    if rr >= 3.0:
        rr_pts = 100 * WEIGHTS["rr"]
    elif rr >= 2.0:
        rr_pts = 70  * WEIGHTS["rr"]
    else:
        rr_pts = 40  * WEIGHTS["rr"]    # already passed 1.5 gate above
    score     += rr_pts
    breakdown["rr"] = round(rr_pts, 1)

    return int(score), breakdown


async def _fire_signal(
    asset:     str,
    state:     dict[str, Any],
    conviction: int,
    breakdown: dict,
) -> dict | None:
    """
    Format and send the Telegram signal.
    Record to Supabase via signal_tracker.
    Returns signal dict if successful, None if failed.
    """
    try:
        direction = state.get("signal_direction", "LONG")
        msg       = _format_telegram(asset, state, conviction, direction, breakdown)

        # Send to test channel during Crypto-Swarm branch
        channel = TELEGRAM_TEST_CHANNEL or TELEGRAM_PROD_CHANNEL
        if channel and TELEGRAM_BOT_TOKEN:
            await _send_telegram(msg, channel)
        else:
            logger.warning("No Telegram channel configured — signal not sent")
            logger.info(f"Signal message:\n{msg}")

        # Record to Supabase
        signal_record = {
            "asset":      asset,
            "direction":  direction,
            "conviction": conviction,
            "entry":      state.get("entry", 0),
            "stop":       state.get("stop",  0),
            "target":     state.get("target", 0),
            "rr_ratio":   state.get("rr_ratio", 0),
            "vprt_score": state.get("vprt_score", 0),
            "garch_regime": state.get("garch_vol_regime", ""),
            "sentiment":  state.get("sentiment_score", 0),
            "breakdown":  breakdown,
            "fired_at":   datetime.now(timezone.utc).isoformat(),
        }

        try:
            from telegram_bot.signal_tracker import record_signal
            record_signal(
                symbol=asset,
                signal_label=state.get("signal_label", "BUY"),
                entry_price=state.get("entry", 0),
                stop_price=state.get("stop", 0),
                target_price=state.get("target", 0),
                score=state.get("vprt_score", 0),
                source="cex",
                exchange="binance",
                conviction=conviction,
                v_confirmed=state.get("v_score", 0),
                t_confirmed=state.get("t_score", 0),
                adx_confirmed=0,
                p_confirmed=state.get("p_score", 0),
                r_confirmed=state.get("r_score", 0),
                rel_vol=state.get("kalman_vol_ratio", 1.0),
            )
        except Exception as db_e:
            logger.error(f"signal_tracker.record_signal failed: {db_e}")

        # Write fired state to blackboard
        bb.write("orchestrator", asset, {
            "last_signal_conviction": conviction,
            "last_signal_direction":  direction,
            "last_signal_at":         datetime.now(timezone.utc).isoformat(),
            "signal_fired":           True,
        })

        logger.info(
            f"SIGNAL FIRED: {asset} {direction} "
            f"conviction={conviction} rr={state.get('rr_ratio',0):.1f}"
        )
        return signal_record

    except Exception as e:
        logger.error(f"_fire_signal failed for {asset}: {e}")
        return None


def _format_telegram(
    asset:      str,
    state:      dict[str, Any],
    conviction: int,
    direction:  str,
    breakdown:  dict,
) -> str:
    """
    Format the Telegram signal message.
    Designed for readability on mobile.
    """
    emoji     = "🟢" if direction == "LONG" else "🔴"
    vol_emoji = {"LOW": "✅", "MEDIUM": "⚠️", "HIGH": "🚫"}.get(
        state.get("garch_vol_regime", ""), "❓"
    )
    fg_val   = state.get("fear_greed_value", 50)
    fg_label = state.get("fear_greed_label", "Neutral")
    funding  = state.get("funding_rate", 0)

    regime   = state.get("garch_vol_regime", "MEDIUM")
    vol_pct  = state.get("garch_vol_current", 0)

    # Position size guidance
    modifier = state.get("position_modifier", 0.6)
    if modifier >= 1.0:
        size_label = "FULL"
    elif modifier >= 0.6:
        size_label = "HALF"
    else:
        size_label = "QUARTER"

    lines = [
        f"{emoji} *CRYPTO SNIPER SIGNAL*",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"*{asset}/USDT* | {direction} | Conviction: {conviction}/100",
        f"",
        f"📊 *Signal Stack*",
        f"├ Price \\(Kalman\\): ${state.get('kalman_price', 0):,.4f}",
        f"├ Momentum \\(V/P/R/T\\): {state.get('vprt_score', 0)}/13",
        f"├ Vol Regime \\(GARCH\\): {regime} {vol_emoji} \\({vol_pct:.0f}% ann\\)",
        f"├ Kalman Velocity: {state.get('kalman_velocity_pct', 0):+.2f}%/bar",
        f"└ Trend: {state.get('trend_label', 'N/A')}",
        f"",
        f"📈 *Sentiment*",
        f"├ Fear & Greed: {fg_val}/100 \\({fg_label}\\)",
        f"├ Funding Rate: {funding*100:+.4f}%",
        f"└ Bias: {state.get('funding_bias', 'NEUTRAL')}",
        f"",
        f"⚙️ *Trade Setup*",
        f"├ Entry:  ${state.get('entry', 0):,.4f}",
        f"├ Stop:   ${state.get('stop', 0):,.4f} \\(1\\.5x ATR\\)",
        f"├ Target: ${state.get('target', 0):,.4f}",
        f"├ R:R:    {state.get('rr_ratio', 0):.1f}:1",
        f"└ Size:   {size_label} position",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"⚠️ Not financial advice\\. Market conditions only\\.",
        f"🔫 @CryptoSniperSignals",
    ]
    return "\n".join(lines)


async def _send_telegram(message: str, channel: str) -> None:
    """Send message to Telegram channel via Bot API."""
    import aiohttp
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    channel,
        "text":       message,
        "parse_mode": "MarkdownV2",
    }
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                body = await r.text()
                logger.error(f"Telegram send failed {r.status}: {body[:200]}")
            else:
                logger.info(f"Telegram message sent to {channel}")
