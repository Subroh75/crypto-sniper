"""
swarms/signal/scheduler.py
─────────────────────────────────────────────────────────────
Signal Swarm Scheduler — Pipeline Entry Point

This is the file that runs on Render as the background worker.
It wires all 5 agents together, runs them in sequence per asset,
and calls the orchestrator to score and fire signals.

PIPELINE (runs every 5 minutes per asset):
  1. KalmanAgent    → fetch OHLCV + filter price (writes to blackboard)
  2. GARCHAgent     → estimate vol regime (reads log_returns)
  3. SentimentAgent → fetch funding + fear/greed (independent)
  4. SignalAgent    → score V/P/R/T + compute R:R (reads OHLCV)
  5. Orchestrator   → score convergence → fire if >= threshold

SCHEDULE:
  Pipeline: every 5 minutes (300s)
  Health checks: every 15 minutes
  Outcome checker: every 30 minutes (resolve WIN/LOSS/EXPIRED)

RENDER DEPLOYMENT:
  Start command: python -m swarms.signal.scheduler
  Or:            python swarms/signal/scheduler.py

ENV VARS REQUIRED:
  SUPABASE_URL              Supabase project URL
  SUPABASE_KEY              Supabase service role key
  TELEGRAM_BOT_TOKEN        Telegram bot token
  TELEGRAM_TEST_CHANNEL     Private channel ID for testing
  TELEGRAM_SIGNAL_CHANNEL   Production channel ID (set when ready)

ENV VARS OPTIONAL:
  SWARM_ASSETS    Comma-separated assets (default: BTC,ETH,SOL,BNB)
  SWARM_THRESHOLD Conviction threshold (default: 65)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from datetime import datetime, timezone

# Ensure project root on path
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Logging setup ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("signal.scheduler")

# ── Agent imports ──────────────────────────────────────────────────
from swarms.signal.agents.kalman_agent    import KalmanAgent
from swarms.signal.agents.garch_agent     import GARCHAgent
from swarms.signal.agents.sentiment_agent import SentimentAgent
from swarms.signal.agents.signal_agent    import SignalAgent
from swarms.signal.orchestrator           import run_orchestrator, ASSET_LIST
from swarm.blackboard                     import blackboard as bb
from swarm.db                             import ping

# ── Agent instances (singletons per worker) ────────────────────────
AGENTS = {
    "kalman":    KalmanAgent(),
    "garch":     GARCHAgent(),
    "sentiment": SentimentAgent(),
    "vprt":      SignalAgent(),
}

# ── Pipeline ───────────────────────────────────────────────────────

async def run_pipeline_for_asset(asset: str) -> dict:
    """
    Run the full signal pipeline for one asset.
    Each agent reads from the blackboard and writes back.
    Agents run sequentially so each can read prior outputs.
    Returns summary dict.
    """
    context  = {}
    results  = {}
    start    = time.monotonic()

    # Sequential pipeline — order matters
    pipeline_order = ["kalman", "garch", "sentiment", "vprt"]

    for name in pipeline_order:
        agent = AGENTS[name]
        try:
            result = await agent.run(asset, context)
            results[name] = {
                "success":     result.success,
                "duration_ms": result.duration_ms,
                "error":       result.error,
            }

            if result.success:
                # Write to blackboard
                bb.write(agent.identity.department, asset, result.data)
                # Merge into local context for next agent
                context.update(result.data)
                logger.debug(
                    f"[{asset}] {name} OK in {result.duration_ms}ms"
                )
            else:
                logger.warning(
                    f"[{asset}] {name} FAILED: {result.error}"
                )
                # Write failure to health table
                agent.log_health("FAILED", {"error": result.error, "asset": asset})

            # Log warnings if any
            for w in (result.warnings or []):
                logger.warning(f"[{asset}] {name} WARN: {w}")

        except Exception as e:
            logger.error(f"[{asset}] {name} EXCEPTION: {e}")
            results[name] = {"success": False, "error": str(e)}

    elapsed = int((time.monotonic() - start) * 1000)
    logger.info(f"[{asset}] Pipeline complete in {elapsed}ms")

    return {
        "asset":   asset,
        "elapsed": elapsed,
        "agents":  results,
        "context_keys": list(context.keys()),
    }


async def run_full_pipeline() -> None:
    """
    Run pipeline for ALL assets, then call orchestrator.
    Assets run concurrently (separate OHLCV fetches).
    Orchestrator runs after all assets are done.
    """
    logger.info(
        f"Pipeline sweep starting | "
        f"assets={ASSET_LIST} | "
        f"threshold={os.environ.get('SWARM_THRESHOLD', 65)}"
    )

    # Run all assets concurrently
    tasks   = [run_pipeline_for_asset(asset) for asset in ASSET_LIST]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in results:
        if isinstance(r, Exception):
            logger.error(f"Pipeline task failed: {r}")

    # Orchestrator reads complete blackboard and fires signals
    fired = await run_orchestrator()
    if fired:
        logger.info(f"Signals fired this cycle: {len(fired)}")
        for sig in fired:
            logger.info(
                f"  FIRED: {sig['asset']} {sig['direction']} "
                f"conviction={sig['conviction']}"
            )
    else:
        logger.info("No signals fired this cycle")


async def run_health_checks() -> None:
    """Check all agent health endpoints and log to Supabase."""
    for name, agent in AGENTS.items():
        try:
            ok = await agent.health_check()
            status = "OK" if ok else "DEGRADED"
            agent.log_health(status)
            logger.debug(f"Health [{name}]: {status}")
        except Exception as e:
            agent.log_health("FAILED", {"error": str(e)})
            logger.error(f"Health check failed [{name}]: {e}")


async def run_outcome_checker() -> None:
    """Resolve WIN/LOSS/EXPIRED on open signals in Supabase."""
    try:
        from telegram_bot.signal_tracker import check_outcomes
        resolved = check_outcomes()
        if resolved:
            logger.info(f"Outcome checker: resolved {resolved} signals")
    except Exception as e:
        logger.error(f"Outcome checker failed: {e}")


# ── Startup checks ─────────────────────────────────────────────────

def startup_check() -> bool:
    """Verify all required services are reachable before starting."""
    logger.info("=" * 60)
    logger.info("CRYPTO SNIPER SIGNAL SWARM")
    logger.info(f"Assets:    {ASSET_LIST}")
    logger.info(f"Threshold: {os.environ.get('SWARM_THRESHOLD', 65)}")
    logger.info("=" * 60)

    # Check Supabase
    logger.info("Checking Supabase...")
    if not ping():
        logger.error("Supabase unreachable — check SUPABASE_URL and SUPABASE_KEY")
        return False
    logger.info("Supabase: OK")

    # Check Telegram token exists
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        logger.warning("TELEGRAM_BOT_TOKEN not set — signals will log only")
    else:
        logger.info("Telegram: token present")

    # Check channel
    channel = (
        os.environ.get("TELEGRAM_TEST_CHANNEL") or
        os.environ.get("TELEGRAM_SIGNAL_CHANNEL")
    )
    if not channel:
        logger.warning("No Telegram channel configured — signals will log only")
    else:
        logger.info(f"Telegram channel: {channel}")

    return True


# ── Main loop (APScheduler) ────────────────────────────────────────

async def main() -> None:
    """
    Main async loop.
    Uses simple time-based scheduling to avoid APScheduler dependency.
    Replace with APScheduler if you need more control.
    """
    if not startup_check():
        logger.error("Startup checks failed — exiting")
        sys.exit(1)

    PIPELINE_INTERVAL    = 300   # 5 minutes
    HEALTH_INTERVAL      = 900   # 15 minutes
    OUTCOME_INTERVAL     = 1800  # 30 minutes

    last_pipeline = 0
    last_health   = 0
    last_outcome  = 0

    logger.info("Swarm scheduler running. First pipeline in 10 seconds.")
    await asyncio.sleep(10)      # brief warmup

    while True:
        now = time.time()

        # Pipeline sweep
        if now - last_pipeline >= PIPELINE_INTERVAL:
            try:
                await run_full_pipeline()
            except Exception as e:
                logger.error(f"Pipeline sweep error: {e}")
            last_pipeline = time.time()

        # Health checks
        if now - last_health >= HEALTH_INTERVAL:
            try:
                await run_health_checks()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            last_health = time.time()

        # Outcome resolution
        if now - last_outcome >= OUTCOME_INTERVAL:
            try:
                await run_outcome_checker()
            except Exception as e:
                logger.error(f"Outcome checker error: {e}")
            last_outcome = time.time()

        # Sleep 30s between loop iterations
        await asyncio.sleep(30)


# ── Entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Swarm scheduler stopped by user")
    except Exception as e:
        logger.exception(f"Swarm scheduler crashed: {e}")
        sys.exit(1)
