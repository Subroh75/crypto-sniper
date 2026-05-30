"""
swarms/signal/scheduler.py
─────────────────────────────────────────────────────────────
Signal Swarm Scheduler — Pipeline Entry Point

Ported from main branch telegram_bot/scanner.py to the swarm
architecture. Now scans top 200 coins by volume across
Binance + MEXC + Gate.io instead of 4 fixed assets.

UNIVERSE FETCH (every cycle):
  1. Fetch top 200 USDT pairs by 24h volume from all 3 exchanges
  2. Pre-filter: rel_vol >= 1.5x (1h vs 6h hourly avg)
  3. Run full pipeline for each survivor (semaphore=5 concurrency)

PIPELINE (per asset):
  1. KalmanAgent    → OHLCV + Kalman filter (MEXC→Binance→Gate)
  2. GARCHAgent     → vol regime (skips gracefully if < 20 bars)
  3. SentimentAgent → Fear & Greed global gate + funding for majors
  4. SignalAgent    → VPRT + ARIMA AR(1) confluence
  5. Orchestrator   → conviction >= 72 → fire Telegram signal

SCHEDULE:
  Pipeline: every 5 minutes (300s)
  Health checks: every 15 minutes
  Outcome checker: every 30 minutes

ENV VARS REQUIRED:
  SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN,
  TELEGRAM_TEST_CHANNEL or TELEGRAM_SIGNAL_CHANNEL

ENV VARS OPTIONAL:
  SWARM_ASSETS     Override universe (default: dynamic top 200)
  SWARM_THRESHOLD  Conviction threshold (default: 72)
  SWARM_TOP_N      Max coins to scan per cycle (default: 200)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from typing import Optional

import aiohttp

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)
)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Logging ────────────────────────────────────────────────────────
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
from swarms.signal.orchestrator           import run_orchestrator
from swarm.blackboard                     import blackboard as bb
from swarm.db                             import ping

# ── Config ─────────────────────────────────────────────────────────
FIRE_THRESHOLD = int(os.environ.get("SWARM_THRESHOLD", "72"))
TOP_N          = int(os.environ.get("SWARM_TOP_N", "200"))
CONCURRENCY    = 5
VOL_SPIKE_GATE = 1.5   # min 1h/6h-avg ratio to enter pipeline

# If SWARM_ASSETS is set, skip universe fetch and use fixed list
FIXED_ASSETS = [
    a.strip().upper()
    for a in os.environ.get("SWARM_ASSETS", "").split(",")
    if a.strip()
]

# Exchange endpoints
MEXC_TICKER    = "https://api.mexc.com/api/v3/ticker/24hr"
BINANCE_TICKER = "https://data-api.binance.vision/api/v3/ticker/24hr"
GATE_TICKER    = "https://api.gateio.ws/api/v4/spot/tickers"

STABLECOINS = {
    "USDT","USDC","BUSD","DAI","TUSD","USDP","USDD","GUSD","FRAX","LUSD",
    "FDUSD","PYUSD","STETH","WBTC","WETH","WBETH","EZETH","WEETH","SUSDE","USDE"
}
LEVERAGED_SUFFIXES = {"3L","3S","5L","5S","2L","2S","UP","DOWN","BULL","BEAR"}
MIN_VOLUME_USD = 500_000

# ── Agent singletons ───────────────────────────────────────────────
AGENTS = {
    "kalman":    KalmanAgent(),
    "garch":     GARCHAgent(),
    "sentiment": SentimentAgent(),
    "vprt":      SignalAgent(),
}

PIPELINE_ORDER = ["kalman", "garch", "sentiment", "vprt"]

# ── Universe fetch ─────────────────────────────────────────────────

async def _fetch_mexc(session: aiohttp.ClientSession) -> list[tuple[str, float, float, float]]:
    """Returns [(symbol, vol_24h, vol_1h, vol_6h), ...] from MEXC."""
    try:
        async with session.get(MEXC_TICKER, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            tickers = await r.json()
            coins = []
            for t in tickers:
                pair = t.get("symbol", "")
                if not pair.endswith("USDT"):
                    continue
                sym = pair[:-4]
                if sym in STABLECOINS or any(sym.endswith(s) for s in LEVERAGED_SUFFIXES):
                    continue
                vol = float(t.get("quoteVolume", 0) or 0)
                if vol < MIN_VOLUME_USD:
                    continue
                coins.append((sym, vol, 0.0, 0.0))
            return coins
    except Exception as e:
        logger.warning(f"[Universe] MEXC ticker failed: {e}")
        return []


async def _fetch_binance(session: aiohttp.ClientSession) -> list[tuple[str, float, float, float]]:
    """Returns [(symbol, vol_24h, vol_1h, vol_6h), ...] from Binance."""
    try:
        async with session.get(BINANCE_TICKER, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            tickers = await r.json()
            coins = []
            for t in tickers:
                pair = t.get("symbol", "")
                if not pair.endswith("USDT"):
                    continue
                sym = pair[:-4]
                if sym in STABLECOINS:
                    continue
                vol = float(t.get("quoteVolume", 0) or 0)
                if vol < MIN_VOLUME_USD:
                    continue
                coins.append((sym, vol, 0.0, 0.0))
            return coins
    except Exception as e:
        logger.warning(f"[Universe] Binance ticker failed: {e}")
        return []


async def _fetch_gate(session: aiohttp.ClientSession) -> list[tuple[str, float, float, float]]:
    """Returns [(symbol, vol_24h, vol_1h, vol_6h), ...] from Gate.io."""
    try:
        async with session.get(GATE_TICKER, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            tickers = await r.json()
            coins = []
            for t in tickers:
                pair = t.get("currency_pair", "")
                if not pair.endswith("_USDT"):
                    continue
                sym = pair[:-5]
                if sym in STABLECOINS or any(sym.endswith(s) for s in LEVERAGED_SUFFIXES):
                    continue
                vol = float(t.get("quote_volume", 0) or 0)
                if vol < MIN_VOLUME_USD:
                    continue
                coins.append((sym, vol, 0.0, 0.0))
            return coins
    except Exception as e:
        logger.warning(f"[Universe] Gate.io ticker failed: {e}")
        return []


async def fetch_universe(top_n: int = TOP_N) -> list[str]:
    """
    Fetch multi-exchange universe.
    Deduplicates by highest 24h volume across all 3 exchanges.
    Returns sorted list of symbols (highest vol first), capped at top_n.
    """
    async with aiohttp.ClientSession() as session:
        mexc, binance, gate = await asyncio.gather(
            _fetch_mexc(session),
            _fetch_binance(session),
            _fetch_gate(session),
            return_exceptions=True,
        )

    mexc    = mexc    if isinstance(mexc,    list) else []
    binance = binance if isinstance(binance, list) else []
    gate    = gate    if isinstance(gate,    list) else []

    # Dedup: highest vol wins
    seen: dict[str, float] = {}
    for sym, vol, _, __ in mexc:
        seen[sym] = max(seen.get(sym, 0), vol)
    for sym, vol, _, __ in binance:
        seen[sym] = max(seen.get(sym, 0), vol)
    for sym, vol, _, __ in gate:
        seen[sym] = max(seen.get(sym, 0), vol)

    sorted_syms = sorted(seen.items(), key=lambda x: x[1], reverse=True)
    symbols = [sym for sym, _ in sorted_syms[:top_n]]

    mexc_n    = sum(1 for s, _ in sorted_syms[:top_n] if any(s == sym for sym, *_ in mexc))
    binance_n = sum(1 for s, _ in sorted_syms[:top_n] if any(s == sym for sym, *_ in binance))
    gate_n    = sum(1 for s, _ in sorted_syms[:top_n] if any(s == sym for sym, *_ in gate))

    logger.info(
        f"[Universe] {len(symbols)} symbols "
        f"(MEXC≈{mexc_n} Binance≈{binance_n} Gate≈{gate_n})"
    )
    return symbols


# ── Vol pre-filter ─────────────────────────────────────────────────

async def _vol_prefilter(symbols: list[str]) -> list[str]:
    """
    Quick vol spike screen using MEXC 1h klines.
    Keeps only coins where 1h vol >= VOL_SPIKE_GATE × (6h vol / 6).
    Falls back to keeping all symbols if the screen fails.
    """
    MEXC_KLINES = "https://api.mexc.com/api/v3/klines"
    sem = asyncio.Semaphore(10)
    survivors = []

    async def check(session: aiohttp.ClientSession, sym: str) -> Optional[str]:
        async with sem:
            try:
                params = {"symbol": f"{sym}USDT", "interval": "1h", "limit": 7}
                async with session.get(
                    MEXC_KLINES, params=params,
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as r:
                    if r.status != 200:
                        return sym  # keep on fetch failure
                    bars = await r.json()
                    if not bars or len(bars) < 7:
                        return sym
                    # vol_1h = last closed bar (index -2), vol_6h = sum of prior 6
                    vols = [float(b[5]) for b in bars]
                    vol_1h = vols[-2]
                    vol_6h = sum(vols[-7:-1])
                    avg_hourly = vol_6h / 6 if vol_6h > 0 else 0
                    if avg_hourly <= 0:
                        return sym
                    rel = vol_1h / avg_hourly
                    return sym if rel >= VOL_SPIKE_GATE else None
            except Exception:
                return sym  # keep on error

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[check(session, sym) for sym in symbols],
            return_exceptions=True
        )

    for r in results:
        if isinstance(r, str):
            survivors.append(r)

    logger.info(
        f"[PreFilter] Vol gate: {len(symbols)} → {len(survivors)} "
        f"survivors (>= {VOL_SPIKE_GATE}x)"
    )
    return survivors


# ── Per-asset pipeline ─────────────────────────────────────────────

async def run_pipeline_for_asset(asset: str) -> dict:
    """Run full agent pipeline for one asset. Returns summary dict."""
    context = {}
    results = {}
    start   = time.monotonic()

    for name in PIPELINE_ORDER:
        agent = AGENTS[name]
        try:
            result = await agent.run(asset, context)
            results[name] = {
                "success":     result.success,
                "duration_ms": result.duration_ms,
                "error":       result.error,
            }
            if result.success:
                bb.write(agent.identity.name, asset, result.data)
                context.update(result.data)
                logger.debug(f"[{asset}] {name} OK {result.duration_ms}ms")
            else:
                logger.warning(f"[{asset}] {name} FAILED: {result.error}")
                agent.log_health("FAILED", {"error": result.error, "asset": asset})

            for w in (result.warnings or []):
                logger.warning(f"[{asset}] {name} WARN: {w}")

        except Exception as e:
            logger.error(f"[{asset}] {name} EXCEPTION: {e}")
            results[name] = {"success": False, "error": str(e)}

    elapsed = int((time.monotonic() - start) * 1000)
    logger.debug(f"[{asset}] Pipeline complete in {elapsed}ms")

    return {"asset": asset, "elapsed": elapsed, "agents": results}


# ── Full pipeline sweep ────────────────────────────────────────────

async def run_full_pipeline() -> None:
    """
    1. Fetch universe (or use FIXED_ASSETS)
    2. Vol pre-filter
    3. Run pipeline for all survivors concurrently (semaphore=5)
    4. Orchestrator scores and fires signals
    """
    # Universe
    if FIXED_ASSETS:
        symbols = FIXED_ASSETS
        logger.info(f"[Pipeline] Fixed assets mode: {symbols}")
    else:
        symbols = await fetch_universe(TOP_N)
        if not symbols:
            logger.error("[Pipeline] Universe fetch returned nothing — aborting")
            return
        symbols = await _vol_prefilter(symbols)
        if not symbols:
            logger.info("[Pipeline] No survivors after vol pre-filter")
            return

    logger.info(
        f"[Pipeline] Sweep starting | "
        f"{len(symbols)} assets | threshold={FIRE_THRESHOLD}"
    )

    sem = asyncio.Semaphore(CONCURRENCY)

    async def bounded(asset: str):
        async with sem:
            return await run_pipeline_for_asset(asset)

    results = await asyncio.gather(
        *[bounded(sym) for sym in symbols],
        return_exceptions=True
    )

    errors = sum(1 for r in results if isinstance(r, Exception))
    if errors:
        logger.warning(f"[Pipeline] {errors} asset pipelines raised exceptions")

    # Orchestrator
    fired = await run_orchestrator(asset_list=symbols, threshold=FIRE_THRESHOLD)
    if fired:
        logger.info(f"[Pipeline] Signals fired: {len(fired)}")
        for sig in fired:
            logger.info(
                f"  FIRED: {sig['asset']} {sig.get('direction','?')} "
                f"conviction={sig.get('conviction','?')} "
                f"exchange={sig.get('exchange','?')}"
            )
    else:
        logger.info("[Pipeline] No signals fired this cycle")


# ── Health checks ──────────────────────────────────────────────────

async def run_health_checks() -> None:
    for name, agent in AGENTS.items():
        try:
            ok = await agent.health_check()
            status = "OK" if ok else "DEGRADED"
            agent.log_health(status)
            logger.debug(f"Health [{name}]: {status}")
        except Exception as e:
            agent.log_health("FAILED", {"error": str(e)})
            logger.error(f"Health check failed [{name}]: {e}")


# ── Outcome checker ────────────────────────────────────────────────

async def run_outcome_checker() -> None:
    try:
        from telegram_bot.signal_tracker import check_outcomes
        resolved = check_outcomes()
        if resolved:
            logger.info(f"Outcome checker: resolved {resolved} signals")
    except Exception as e:
        logger.error(f"Outcome checker failed: {e}")


# ── Startup ────────────────────────────────────────────────────────

def startup_check() -> bool:
    logger.info("=" * 60)
    logger.info("CRYPTO SNIPER SIGNAL SWARM")
    logger.info(f"Mode:      {'FIXED ' + str(FIXED_ASSETS) if FIXED_ASSETS else 'DYNAMIC TOP ' + str(TOP_N)}")
    logger.info(f"Threshold: {FIRE_THRESHOLD}")
    logger.info(f"Vol gate:  {VOL_SPIKE_GATE}x")
    logger.info("=" * 60)

    logger.info("Checking Supabase...")
    if not ping():
        logger.error("Supabase unreachable — check SUPABASE_URL and SUPABASE_KEY")
        return False
    logger.info("Supabase: OK")

    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        logger.warning("TELEGRAM_BOT_TOKEN not set — signals will log only")
    else:
        logger.info("Telegram: token present")

    channel = (
        os.environ.get("TELEGRAM_TEST_CHANNEL") or
        os.environ.get("TELEGRAM_SIGNAL_CHANNEL")
    )
    if not channel:
        logger.warning("No Telegram channel configured — signals will log only")
    else:
        logger.info(f"Telegram channel: {channel}")

    return True


# ── Main loop ──────────────────────────────────────────────────────

async def main() -> None:
    if not startup_check():
        logger.error("Startup checks failed — exiting")
        import sys; sys.exit(1)

    # FIX: Use time.monotonic() for all interval tracking.
    # time.time() on Render returns a value ~1 year behind Supabase,
    # causing all intervals to appear expired on every 30s tick.
    # monotonic() measures elapsed time since process start — immune
    # to system clock skew.

    PIPELINE_INTERVAL = 300    # 5 min
    HEALTH_INTERVAL   = 900    # 15 min
    OUTCOME_INTERVAL  = 1800   # 30 min

    # Initialise to -infinity so first iteration runs immediately
    last_pipeline = -PIPELINE_INTERVAL
    last_health   = -HEALTH_INTERVAL
    last_outcome  = -OUTCOME_INTERVAL

    logger.info("Swarm scheduler running. First pipeline in 10 seconds.")
    await asyncio.sleep(10)

    while True:
        now = time.monotonic()   # FIX: was time.time()

        if now - last_pipeline >= PIPELINE_INTERVAL:
            try:
                await run_full_pipeline()
            except Exception as e:
                logger.error(f"Pipeline sweep error: {e}")
            last_pipeline = time.monotonic()

        if now - last_health >= HEALTH_INTERVAL:
            try:
                await run_health_checks()
            except Exception as e:
                logger.error(f"Health check error: {e}")
            last_health = time.monotonic()

        if now - last_outcome >= OUTCOME_INTERVAL:
            try:
                await run_outcome_checker()
            except Exception as e:
                logger.error(f"Outcome checker error: {e}")
            last_outcome = time.monotonic()

        await asyncio.sleep(30)


if __name__ == "__main__":
    import sys
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Swarm scheduler stopped by user")
    except Exception as e:
        logger.exception(f"Swarm scheduler crashed: {e}")
        sys.exit(1)
