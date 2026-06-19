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
  1. KalmanAgent  → OHLCV + Kalman filter (MEXC→Binance→Gate)
  2. GARCHAgent   → vol regime (skips gracefully if < 20 bars)
  3. SentimentAgent → Fear & Greed global gate + funding for majors
  4. SignalAgent  → VPRT + ARIMA AR(1) confluence
  5. WhaleAgent   → tracked-wallet size + accumulation conviction
  6. Orchestrator → conviction >= 72 → fire Telegram signal

DEX SCAN (Option 2 — reuse main branch):
  Every 30 min, calls the main branch /dex-results endpoint
  to fetch cached DEX scan results (gems + vol_hits).
  Formats and fires DEX vol spike alerts to Telegram.

SCHEDULE:
  Pipeline:        every 5 minutes  (300s)
  Health checks:   every 15 minutes
  Outcome checker: every 30 minutes
  DEX scan:        every 30 minutes

ENV VARS REQUIRED:
  SUPABASE_URL, SUPABASE_KEY, TELEGRAM_BOT_TOKEN,
  TELEGRAM_TEST_CHANNEL or TELEGRAM_SIGNAL_CHANNEL

ENV VARS OPTIONAL:
  SWARM_ASSETS         Override universe (default: dynamic top 200)
  SWARM_THRESHOLD      Conviction threshold (default: 72)
  SWARM_TOP_N          Max coins to scan per cycle (default: 200)
  MAIN_BRANCH_API_URL  Main branch Render URL (default: https://crypto-sniper.onrender.com)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
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
from swarms.signal.agents.kalman_agent import KalmanAgent
from swarms.signal.agents.garch_agent  import GARCHAgent
from swarms.signal.agents.sentiment_agent import SentimentAgent
from swarms.signal.agents.signal_agent import SignalAgent
from swarms.signal.agents.whale_agent import WhaleAgent
from swarms.signal.orchestrator import run_orchestrator
from swarm.blackboard import blackboard as bb
from swarm.db import ping

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

# Main branch API for DEX results (Option 2)
MAIN_BRANCH_API = os.environ.get(
    "MAIN_BRANCH_API_URL",
    "https://crypto-sniper.onrender.com"
)

# Telegram config (shared with orchestrator but needed for DEX alerts)
TELEGRAM_BOT_TOKEN   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_TEST_CHANNEL = os.environ.get("TELEGRAM_TEST_CHANNEL", "")
TELEGRAM_PROD_CHANNEL = os.environ.get("TELEGRAM_SIGNAL_CHANNEL", "")

# ── Agent singletons ───────────────────────────────────────────────
AGENTS = {
    "kalman":    KalmanAgent(),
    "garch":     GARCHAgent(),
    "sentiment": SentimentAgent(),
    "vprt":      SignalAgent(),
}
WHALE_AGENT = WhaleAgent()  # separate stage-2 — see run_full_pipeline()

PIPELINE_ORDER = ["kalman", "garch", "sentiment", "vprt"]
WHALE_TOP_N = int(os.environ.get("SWARM_WHALE_TOP_N", "20"))

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

    mexc    = mexc    if isinstance(mexc, list)    else []
    binance = binance if isinstance(binance, list) else []
    gate    = gate    if isinstance(gate, list)    else []

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
                        return sym   # keep on fetch failure
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
    start = time.monotonic()

    for name in PIPELINE_ORDER:
        agent = AGENTS[name]
        try:
            result = await agent.run(asset, context)
            results[name] = {
                "success": result.success,
                "duration_ms": result.duration_ms,
                "error": result.error,
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

    return {"asset": asset, "elapsed": elapsed, "agents": results, "context": context}

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

    # ── Stage 2: WhaleAgent — top-20 by SignalAgent conviction only ────
    # Per DESIGN.md: whale flow tracking is expensive (multiple chain
    # APIs) and only meaningful for the assets already showing the
    # strongest VPRT conviction — not the full ~200-coin universe.
    ranked = sorted(
        (r for r in results if isinstance(r, dict)),
        key=lambda r: r.get("context", {}).get("conviction", 0),
        reverse=True,
    )
    whale_candidates = ranked[:WHALE_TOP_N]

    for r in whale_candidates:
        asset = r["asset"]
        context = r["context"]
        try:
            result = await WHALE_AGENT.run(asset, context)
            if result.success:
                bb.write(WHALE_AGENT.identity.name, asset, result.data)
                logger.debug(f"[{asset}] whale OK {result.duration_ms}ms")
            else:
                logger.warning(f"[{asset}] whale FAILED: {result.error}")
                WHALE_AGENT.log_health("FAILED", {"error": result.error, "asset": asset})
            for w in (result.warnings or []):
                logger.warning(f"[{asset}] whale WARN: {w}")
        except Exception as e:
            logger.error(f"[{asset}] whale EXCEPTION: {e}")

    logger.info(f"[Pipeline] WhaleAgent ran for top {len(whale_candidates)} assets by conviction")

    # Orchestrator
    fired = await run_orchestrator(asset_list=symbols, threshold=FIRE_THRESHOLD)
    if fired:
        logger.info(f"[Pipeline] Signals fired: {len(fired)}")
        for sig in fired:
            logger.info(
                f"  FIRED: {sig['asset']} {sig.get('direction','?')} "
                f"conviction={sig.get('conviction','?')} "
                f"exchange={sig.get('exchange','?')} "
                f"regime={sig.get('market_regime','?')}"
            )
    else:
        logger.info("[Pipeline] No signals fired this cycle")

# ── DEX Scan (Option 2 — reuse main branch) ───────────────────────

# Track last DEX scan results to avoid sending duplicates
_last_dex_scan_ts: int = 0

async def run_dex_scan() -> None:
    """
    Fetch cached DEX scan results from main branch /dex-results endpoint.
    Format and fire vol spike alerts to Telegram.
    Runs every 30 minutes.
    """
    global _last_dex_scan_ts

    url = f"{MAIN_BRANCH_API}/dex-results"
    logger.info(f"[DEX Scan] Fetching from {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                if r.status != 200:
                    logger.warning(f"[DEX Scan] /dex-results returned {r.status}")
                    return
                data = await r.json()
    except Exception as e:
        logger.error(f"[DEX Scan] Failed to fetch: {e}")
        return

    scan_ts = data.get("scan_ts", 0)
    fresh = data.get("fresh", False)

    # Skip if stale or already sent this scan
    if not fresh:
        logger.info(f"[DEX Scan] Results stale (age: {data.get('age_h', '?')}h) — skipping")
        return
    if scan_ts <= _last_dex_scan_ts:
        logger.debug("[DEX Scan] Already sent this scan — skipping")
        return

    gems = data.get("gems", [])
    vol_hits = data.get("vol_hits", [])
    scan_time = data.get("scan_time", "Unknown")

    if not gems and not vol_hits:
        logger.info("[DEX Scan] No DEX hits to report")
        _last_dex_scan_ts = scan_ts
        return

    # Format the DEX alert
    msg = _format_dex_alert(gems, vol_hits, scan_time)
    buttons = _build_dex_buttons(gems[:3])

    channel = TELEGRAM_TEST_CHANNEL or TELEGRAM_PROD_CHANNEL
    if channel and TELEGRAM_BOT_TOKEN:
        await _send_dex_telegram(msg, channel, reply_markup=buttons)
        _last_dex_scan_ts = scan_ts
        logger.info(f"[DEX Scan] Alert sent — {len(gems)} gems, {len(vol_hits)} vol hits")
    else:
        logger.warning("[DEX Scan] No Telegram channel — DEX alert logged only")
        logger.info(f"DEX alert:\n{msg}")
        _last_dex_scan_ts = scan_ts


def _format_dex_alert(
    gems: list[dict],
    vol_hits: list[dict],
    scan_time: str,
) -> str:
    """
    Format DEX vol spike alert matching DESIGN.md format.
    Uses plain text (no MarkdownV2) for cleaner formatting with monospace alignment.
    """
    total = len(gems) + len(vol_hits)

    lines = [
        f"⚡ CRYPTO SNIPER — DEX SCAN",
        f"{scan_time}",
        f"Hits: {len(gems)} gems  |  {len(vol_hits)} vol spikes",
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]

    if gems:
        lines.append("DEX GEMS")
        for hit in gems[:7]:
            signal = hit.get("signal", "BUY")
            sym = hit.get("symbol", "?")[:10]
            chain = hit.get("chain", "?").upper()[:5]
            rel_vol = hit.get("rel_vol", 0)
            pct_1h = hit.get("price_change_1h", hit.get("priceChange_1h", 0))
            liq = hit.get("liquidity", 0)

            # Signal emoji
            if signal == "STRONG BUY":
                sig_emoji = "🟢"
            elif signal == "BUY":
                sig_emoji = "🔵"
            else:
                sig_emoji = "⚪"

            # Vol label
            if rel_vol >= 4.0:
                vol_label = "Extreme"
            elif rel_vol >= 2.5:
                vol_label = "High"
            elif rel_vol >= 1.8:
                vol_label = "Elevated"
            else:
                vol_label = "Normal"

            # Liquidity formatting
            if liq >= 1_000_000:
                liq_str = f"${liq / 1_000_000:.1f}M"
            elif liq >= 1_000:
                liq_str = f"${liq / 1_000:.0f}K"
            else:
                liq_str = f"${liq:.0f}"

            pct_str = f"{pct_1h:+.1f}%" if isinstance(pct_1h, (int, float)) else str(pct_1h)

            lines.append(
                f"  {sig_emoji} {sym:<10} {chain:<5} "
                f"{vol_label} {rel_vol:.1f}×  ({pct_str} 1h)  "
                f"Liq {liq_str}  {signal}"
            )

    if vol_hits:
        if gems:
            lines.append("")
        lines.append("VOL BUILDING")
        for hit in vol_hits[:5]:
            sym = hit.get("symbol", "?")[:10]
            chain = hit.get("chain", "?").upper()[:5]
            rel_vol = hit.get("rel_vol", 0)
            pct_1h = hit.get("price_change_1h", hit.get("priceChange_1h", 0))
            pct_str = f"{pct_1h:+.1f}%" if isinstance(pct_1h, (int, float)) else str(pct_1h)

            lines.append(
                f"  ⚪ {sym:<10} {chain:<5} {rel_vol:.1f}×  ({pct_str} 1h)  WATCH"
            )

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("⚠️ Not financial advice. Market conditions only.")

    return "\n".join(lines)


def _build_dex_buttons(top_gems: list[dict]) -> dict:
    """Build inline keyboard with links to top DEX gems + scanner."""
    webapp_url = os.environ.get("WEBAPP_URL", "https://crypto-sniper.app")
    buttons = []

    # Top gem buttons (max 3)
    row = []
    for gem in top_gems:
        sym = gem.get("symbol", "?")
        address = gem.get("address", "")
        chain = gem.get("chain", "").lower()
        if address:
            url = f"https://dexscreener.com/{chain}/{address}"
        else:
            url = f"{webapp_url}/analyse/{sym.lower()}"
        row.append({"text": f"📊 {sym[:8]}", "url": url})
    if row:
        buttons.append(row)

    # Scanner + Ask AI row
    buttons.append([
        {"text": "🔍 Open Scanner", "url": f"{webapp_url}/scanner"},
        {"text": "💬 Ask AI", "url": "https://t.me/CryptoSniperBot?start=ask_dex"},
    ])

    return {"inline_keyboard": buttons}


async def _send_dex_telegram(
    message: str,
    channel: str,
    reply_markup: Optional[dict] = None,
) -> None:
    """Send DEX alert — plain text (no MarkdownV2) for cleaner monospace alignment."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": channel,
        "text": message,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    async with aiohttp.ClientSession() as s:
        async with s.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status != 200:
                body = await r.text()
                logger.error(f"[DEX Scan] Telegram send failed {r.status}: {body[:300]}")
            else:
                logger.info(f"[DEX Scan] Telegram alert sent to {channel}")


# ── Health checks ──────────────────────────────────────────────────

async def run_health_checks() -> None:
    for name, agent in {**AGENTS, "whale": WHALE_AGENT}.items():
        try:
            ok = await agent.health_check()
            status = "OK" if ok else "DEGRADED"
            agent.log_health(status)
            logger.debug(f"Health [{name}]: {status}")
        except Exception as e:
            agent.log_health("FAILED", {"error": str(e)})
            logger.error(f"Health check failed [{name}]: {e}")

# ── Outcome checker (Supabase-native) ─────────────────────────────

async def run_outcome_checker() -> None:
    """
    Resolve pending signals in Supabase.
    Uses swarms/signal/outcome_checker.py — no SQLite dependency.
    """
    try:
        from swarms.signal.outcome_checker import check_outcomes
        resolved = await check_outcomes()
        logger.info(
            f"[OutcomeChecker] Cycle complete — {resolved} resolved"
        )
    except Exception as e:
        logger.error(f"Outcome checker failed: {e}")

# ── Startup ────────────────────────────────────────────────────────

def startup_check() -> bool:
    logger.info("=" * 60)
    logger.info("CRYPTO SNIPER SIGNAL SWARM")
    logger.info(f"Mode: {'FIXED ' + str(FIXED_ASSETS) if FIXED_ASSETS else 'DYNAMIC TOP ' + str(TOP_N)}")
    logger.info(f"Threshold: {FIRE_THRESHOLD}")
    logger.info(f"Vol gate: {VOL_SPIKE_GATE}x")
    logger.info(f"DEX scan: {MAIN_BRANCH_API}/dex-results (every 30min)")
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

    PIPELINE_INTERVAL  = 300   # 5 min
    HEALTH_INTERVAL    = 900   # 15 min
    OUTCOME_INTERVAL   = 1800  # 30 min
    DEX_SCAN_INTERVAL  = 1800  # 30 min

    # Initialise to -infinity so first iteration runs immediately
    last_pipeline  = -PIPELINE_INTERVAL
    last_health    = -HEALTH_INTERVAL
    last_outcome   = -OUTCOME_INTERVAL
    last_dex_scan  = -DEX_SCAN_INTERVAL

    logger.info("Swarm scheduler running. First pipeline in 10 seconds.")
    await asyncio.sleep(10)

    while True:
        now = time.monotonic()  # FIX: was time.time()

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

        if now - last_dex_scan >= DEX_SCAN_INTERVAL:
            try:
                await run_dex_scan()
            except Exception as e:
                logger.error(f"DEX scan error: {e}")
            last_dex_scan = time.monotonic()

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
