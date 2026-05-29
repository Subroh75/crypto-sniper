"""
swarms/signal/orchestrator.py
─────────────────────────────────────────────────────────────
Signal Swarm Orchestrator — Convergence Scorer and Telegram Delivery

Updated for dynamic universe (top 200) and ARIMA confluence.

CONVERGENCE SCORING WEIGHTS:
  VPRT score         30%  — directional signal quality
  GARCH vol regime   25%  — risk management gate
  Sentiment          20%  — market context
  Kalman velocity    15%  — momentum confirmation
  R:R ratio bonus    10%  — trade quality gate

ARIMA CONFLUENCE BONUS (additive, outside weights):
  HIGH_CONFLUENCE  → +5 pts  (ARIMA aligns with VPRT direction)
  BIAS_CONFLICT    → -5 pts  (ARIMA conflicts with VPRT direction)
  NO_CONFLUENCE    → 0 pts

SUPPRESSION GATES (any → conviction = 0):
  garch_signal_gate  == "SUPPRESS"
  sentiment_gate     == "AVOID"
  signal_direction   == "NEUTRAL"
  rr_ratio           <  1.5

DEFAULT FIRE THRESHOLD: 72/100
  Raised from 65 to reduce noise with 200-coin universe.
  Tunable via SWARM_THRESHOLD env var or threshold param.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from swarm.blackboard import blackboard as bb

logger = logging.getLogger("signal.orchestrator")

# ── Config ─────────────────────────────────────────────────────────
DEFAULT_THRESHOLD = int(os.environ.get("SWARM_THRESHOLD", "72"))

# Kept for backwards compat — scheduler now passes asset_list directly
ASSET_LIST = [
    a.strip().upper()
    for a in os.environ.get("SWARM_ASSETS", "BTC,ETH,SOL,BNB").split(",")
    if a.strip()
]

TELEGRAM_BOT_TOKEN    = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TEST_CHANNEL = os.environ.get("TELEGRAM_TEST_CHANNEL", "")
TELEGRAM_PROD_CHANNEL = os.environ.get("TELEGRAM_SIGNAL_CHANNEL", "")

# ── Scoring weights ────────────────────────────────────────────────
WEIGHTS = {
    "vprt":      0.30,
    "garch":     0.25,
    "sentiment": 0.20,
    "kalman":    0.15,
    "rr":        0.10,
}

ARIMA_BONUS = {
    "HIGH_CONFLUENCE": +5,
    "BIAS_CONFLICT":   -5,
    "NO_CONFLUENCE":    0,
    "INSUFFICIENT_DATA": 0,
}


# ── Main orchestrator ──────────────────────────────────────────────

async def run_orchestrator(
    asset_list: Optional[list[str]] = None,
    threshold:  int = DEFAULT_THRESHOLD,
) -> list[dict]:
    """
    Score convergence for each asset and fire Telegram signals.
    Returns list of fired signal dicts.
    """
    assets = asset_list or ASSET_LIST
    fired_signals = []

    for asset in assets:
        try:
            state = bb.read(asset)
            if not state:
                logger.debug(f"[{asset}] Blackboard empty — skipping")
                continue

            conviction, breakdown = _score_convergence(asset, state)

            logger.info(
                f"[{asset}] conviction={conviction} "
                f"direction={state.get('signal_direction','?')} "
                f"exchange={state.get('exchange','?')} "
                f"arima={state.get('arima_confluence','?')} "
                f"breakdown={breakdown}"
            )

            if conviction >= threshold:
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
    """Score convergence 0-100 with ARIMA bonus. Returns (score, breakdown)."""
    score     = 0.0
    breakdown = {}

    # ── Suppression gates ──────────────────────────────────────────
    if state.get("garch_signal_gate") == "SUPPRESS":
        return 0, {"suppressed": "GARCH_HIGH_VOL"}

    if state.get("sentiment_gate") == "AVOID":
        return 0, {"suppressed": "EXTREME_GREED"}

    if state.get("signal_direction", "NEUTRAL") == "NEUTRAL":
        return 0, {"suppressed": "NEUTRAL_DIRECTION"}

    rr = state.get("rr_ratio", 0)
    if rr < 1.5:
        return 0, {"suppressed": f"LOW_RR_{rr:.2f}"}

    # ── VPRT (0-30 pts) ────────────────────────────────────────────
    vprt_score = state.get("vprt_score", 0)
    vprt_pts   = (vprt_score / 13) * 100 * WEIGHTS["vprt"]
    score     += vprt_pts
    breakdown["vprt"] = round(vprt_pts, 1)

    # ── GARCH (0-25 pts) ───────────────────────────────────────────
    regime = state.get("garch_vol_regime", "HIGH")
    if regime == "LOW":
        garch_pts = 100 * WEIGHTS["garch"]
    elif regime == "MEDIUM":
        garch_pts = 60  * WEIGHTS["garch"]
    else:
        garch_pts = 0
    score     += garch_pts
    breakdown["garch"] = round(garch_pts, 1)

    # ── Sentiment (0-20 pts) ───────────────────────────────────────
    sentiment_score = state.get("sentiment_score", 50)
    if 40 <= sentiment_score <= 70:
        sent_pts = 100 * WEIGHTS["sentiment"]
    elif 25 <= sentiment_score < 40 or 70 < sentiment_score <= 80:
        sent_pts = 70  * WEIGHTS["sentiment"]
    else:
        sent_pts = 30  * WEIGHTS["sentiment"]
    score     += sent_pts
    breakdown["sentiment"] = round(sent_pts, 1)

    # ── Kalman velocity (0-15 pts) ─────────────────────────────────
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

    # ── R:R bonus (0-10 pts) ───────────────────────────────────────
    if rr >= 3.0:
        rr_pts = 100 * WEIGHTS["rr"]
    elif rr >= 2.0:
        rr_pts = 70  * WEIGHTS["rr"]
    else:
        rr_pts = 40  * WEIGHTS["rr"]
    score     += rr_pts
    breakdown["rr"] = round(rr_pts, 1)

    # ── ARIMA confluence bonus (additive) ─────────────────────────
    arima_conf  = state.get("arima_confluence", "NO_CONFLUENCE")
    arima_bonus = ARIMA_BONUS.get(arima_conf, 0)
    score      += arima_bonus
    breakdown["arima"] = arima_bonus

    final = max(0, min(100, int(score)))
    return final, breakdown


# ── Signal firing ──────────────────────────────────────────────────

async def _fire_signal(
    asset:      str,
    state:      dict[str, Any],
    conviction: int,
    breakdown:  dict,
) -> Optional[dict]:
    try:
        direction = state.get("signal_direction", "LONG")
        exchange  = state.get("exchange", "binance")
        msg       = _format_telegram(asset, state, conviction, direction, breakdown)

        channel = TELEGRAM_TEST_CHANNEL or TELEGRAM_PROD_CHANNEL
        if channel and TELEGRAM_BOT_TOKEN:
            await _send_telegram(msg, channel)
        else:
            logger.warning("No Telegram channel — signal logged only")
            logger.info(f"Signal message:\n{msg}")

        # Record to Supabase
        try:
            from telegram_bot.signal_tracker import record_signal
            record_signal(
                symbol       = asset,
                signal_label = state.get("signal_label", "BUY"),
                entry_price  = state.get("entry", 0),
                stop_price   = state.get("stop", 0),
                target_price = state.get("target", 0),
                score        = state.get("vprt_score", 0),
                source       = "cex",
                exchange     = exchange,
                conviction   = conviction,
                v_confirmed  = state.get("v_score", 0),
                t_confirmed  = state.get("t_score", 0),
                adx_confirmed= 0,
                p_confirmed  = state.get("p_score", 0),
                r_confirmed  = state.get("r_score", 0),
                rel_vol      = state.get("kalman_vol_ratio", 1.0),
            )
        except Exception as db_e:
            logger.error(f"record_signal failed: {db_e}")

        bb.write("orchestrator", asset, {
            "last_signal_conviction": conviction,
            "last_signal_direction":  direction,
            "last_signal_at":         datetime.now(timezone.utc).isoformat(),
            "signal_fired":           True,
        })

        logger.info(
            f"SIGNAL FIRED: {asset} {direction} "
            f"conviction={conviction} rr={rr:.1f} "
            f"exchange={exchange} arima={state.get('arima_confluence','?')}"
        )

        return {
            "asset":      asset,
            "direction":  direction,
            "conviction": conviction,
            "exchange":   exchange,
            "entry":      state.get("entry", 0),
            "stop":       state.get("stop", 0),
            "target":     state.get("target", 0),
            "rr_ratio":   state.get("rr_ratio", 0),
            "breakdown":  breakdown,
            "fired_at":   datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"_fire_signal failed for {asset}: {e}")
        return None


# ── Telegram formatter ─────────────────────────────────────────────

def _format_telegram(
    asset:      str,
    state:      dict[str, Any],
    conviction: int,
    direction:  str,
    breakdown:  dict,
) -> str:
    emoji     = "🟢" if direction == "LONG" else "🔴"
    vol_emoji = {"LOW": "✅", "MEDIUM": "⚠️", "HIGH": "🚫"}.get(
        state.get("garch_vol_regime", ""), "❓"
    )
    fg_val   = state.get("fear_greed_value", 50)
    fg_label = state.get("fear_greed_label", "Neutral")
    funding  = state.get("funding_rate", 0)
    regime   = state.get("garch_vol_regime", "MEDIUM")
    vol_pct  = state.get("garch_vol_current", 0)
    exchange = state.get("exchange", "binance").upper()

    modifier = state.get("position_modifier", 0.6)
    if modifier >= 1.0:
        size_label = "FULL"
    elif modifier >= 0.6:
        size_label = "HALF"
    else:
        size_label = "QUARTER"

    arima_bias = state.get("arima_bias", "")
    arima_conf = state.get("arima_confluence", "")
    arima_phi1 = state.get("arima_phi1", 0.0)

    arima_line = ""
    if arima_conf == "HIGH_CONFLUENCE":
        arima_line = f"└ ARIMA: {arima_bias} \\(φ={arima_phi1:+.2f}\\) ⚡ CONFLUENCE"
    elif arima_conf == "BIAS_CONFLICT":
        arima_line = f"└ ARIMA: {arima_bias} \\(φ={arima_phi1:+.2f}\\) ⚠️ CONFLICT"

    rr = state.get("rr_ratio", 0)

    lines = [
        f"{emoji} *CRYPTO SNIPER SIGNAL*",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"*{asset}/USDT* | {direction} | Conviction: {conviction}/100",
        f"Exchange: {exchange}",
        f"",
        f"📊 *Signal Stack*",
        f"├ Price \\(Kalman\\): ${state.get('kalman_price', 0):,.4f}",
        f"├ Momentum \\(V/P/R/T\\): {state.get('vprt_score', 0)}/13",
        f"├ Vol Regime \\(GARCH\\): {regime} {vol_emoji} \\({vol_pct:.0f}% ann\\)",
        f"├ Kalman Velocity: {state.get('kalman_velocity_pct', 0):+.2f}%/bar",
        f"├ Trend: {state.get('trend_label', 'N/A')}",
    ]
    if arima_line:
        lines.append(arima_line)
    else:
        lines.append(f"└ ARIMA: {arima_bias or 'N/A'}")

    lines += [
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
        f"├ R:R:    {rr:.1f}:1",
        f"└ Size:   {size_label} position",
        f"",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"⚠️ Not financial advice\\. Market conditions only\\.",
        f"🔫 @CryptoSniperSignals",
    ]
    return "\n".join(lines)


async def _send_telegram(message: str, channel: str) -> None:
    import aiohttp
    url     = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": channel, "text": message, "parse_mode": "MarkdownV2"}
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                body = await r.text()
                logger.error(f"Telegram send failed {r.status}: {body[:200]}")
            else:
                logger.info(f"Telegram message sent to {channel}")
