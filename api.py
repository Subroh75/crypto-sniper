"""
api.py - FastAPI backend for Crypto Sniper V2
Endpoints: /analyse /kronos /deep-research /market /trending /gainers /news /macro /watchlist /health
"""
import os, time, logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from data import (
    get_ohlcv, get_quote, get_indicators, get_trending,
    get_gainers_losers, get_market_overview, get_btc_onchain,
    get_news, get_macro, get_watchlist_scores, get_fear_greed, get_crypto_panic, health_check,
    get_social_delta, get_coinpaprika_meta,
    get_coindar_events, get_santiment_signals,
    get_binance_universe,
    get_mexc_universe,
    get_gate_universe,
    get_multi_exchange_universe,
    get_vol_prefilter,
)
from signals import calculate_signals, get_key_levels
from agents import run_agent_council
from kronos import run_kronos_forecast
from perplexity_research import run_deep_research
from derivatives import get_derivatives, get_market_microstructure
from history import (
    record_signal, get_symbol_history, get_hit_rate,
    get_scanner_performance, record_scan_result, get_backtest,
)
from watchlist_db import (
    get_watchlist, add_watchlist_symbol, remove_watchlist_symbol,
)
from auth import (
    send_magic_link, verify_magic_link, verify_session,
    validate_telegram_token, verify_session_with_tier,
)
from alerts import (
    AlertRequest, register_alert, get_alerts, delete_alert,
    check_and_fire_alerts, get_alert_history, get_unread_count,
)
from onchain import get_onchain
from backtest_internal import run_backtest as run_internal_backtest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Crypto Sniper API v2", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://crypto-sniper.app",
        "https://www.crypto-sniper.app",
        "http://localhost:5000",
        "http://localhost:3000",
        os.getenv("EXTRA_ORIGIN", ""),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AnalyseRequest(BaseModel):
    symbol: str = "BTC"
    interval: str = "1H"

class KronosRequest(BaseModel):
    symbol: str = "BTC"
    interval: str = "1H"
    signal_data: Optional[dict] = None

class ResearchRequest(BaseModel):
    symbol: str = "BTC"
    depth: str = "deep"
    context: Optional[dict] = None

class WatchlistRequest(BaseModel):
    symbols: list


# ── Scan cache ───────────────────────────────────────────────────────────────
_scan_cache: dict = {}
_SCAN_TTL  = 900   # 15-min cache - reduces how often a request hits the cold-scan path

# --- Per-key lock to coalesce concurrent identical /scan requests ---
# Without this, multiple simultaneous requests with the same params (e.g. the
# dashboard's TopSignals, VolRadar, and ScanAlertPoller components all calling
# /scan on page load) would each independently launch a full scan, overloading
# the backend. With this lock, only the first request runs the scan; the
# others wait and then read the freshly-populated cache.
import threading as _threading
_scan_locks: dict = {}
_scan_locks_guard = _threading.Lock()

def _get_scan_lock(key: str):
    with _scan_locks_guard:
        lock = _scan_locks.get(key)
        if lock is None:
            lock = _threading.Lock()
            _scan_locks[key] = lock
        return lock
# ── SQLite persistence for scan cache (survives Render sleep/restart) ─────────
_SCAN_DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")
import sqlite3 as _sqlite3, json as _json

def _scan_db_init():
    """Create scan_cache table if not exists."""
    try:
        with _sqlite3.connect(_SCAN_DB_PATH) as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS scan_cache_v2 (
                    cache_key TEXT PRIMARY KEY,
                    data_json TEXT NOT NULL,
                    universe  INTEGER NOT NULL DEFAULT 0,
                    ts        INTEGER NOT NULL
                )
            """)
    except Exception as _e:
        logger.warning(f"scan_db_init: {_e}")

def _scan_db_write(cache_key: str, data: list, universe: int, ts: int):
    """Persist scan result to SQLite."""
    try:
        with _sqlite3.connect(_SCAN_DB_PATH) as c:
            c.execute(
                "INSERT OR REPLACE INTO scan_cache_v2 (cache_key, data_json, universe, ts) VALUES (?,?,?,?)",
                (cache_key, _json.dumps(data), universe, ts)
            )
    except Exception as _e:
        logger.warning(f"scan_db_write: {_e}")

def _scan_db_read(cache_key: str) -> dict | None:
    """Read persisted scan result from SQLite. Returns None if missing or expired."""
    try:
        with _sqlite3.connect(_SCAN_DB_PATH) as c:
            row = c.execute(
                "SELECT data_json, universe, ts FROM scan_cache_v2 WHERE cache_key=?",
                (cache_key,)
            ).fetchone()
        if row and (int(time.time()) - row[2]) < _SCAN_TTL:
            return {"data": _json.loads(row[0]), "universe": row[1], "ts": row[2]}
    except Exception as _e:
        logger.warning(f"scan_db_read: {_e}")
    return None

# Init DB table on startup
_scan_db_init()

# Pre-warm in-memory cache from SQLite on startup (avoids cold scan on Render wake)
def _prewarm_scan_cache():
    try:
        with _sqlite3.connect(_SCAN_DB_PATH) as c:
            rows = c.execute(
                "SELECT cache_key, data_json, universe, ts FROM scan_cache_v2"
            ).fetchall()
        for row in rows:
            key, data_json, universe, ts = row
            if (int(time.time()) - ts) < _SCAN_TTL:
                _scan_cache.update({"key": key, "ts": ts, "data": _json.loads(data_json), "universe": universe})
                logger.info(f"Pre-warmed scan cache: key={key}, {universe} coins, age={int(time.time())-ts}s")
    except Exception as _e:
        logger.warning(f"_prewarm_scan_cache: {_e}")

_prewarm_scan_cache()

# ── Telegram notify helper (fire-and-forget, used by /analyse) ───────────────
_TG_BOT_TOKEN  = os.environ.get("BOT_TOKEN", "")
_TG_ADMIN_CHAT = os.environ.get("ADMIN_CHAT_ID", "5861457546")
_tg_signal_cooldown: dict = {}   # symbol -> last_alert_ts
_TG_SIGNAL_COOLDOWN = 4 * 3600  # don't re-alert same coin within 4h

def _tg_notify_signal(symbol: str, sig, quote: dict, interval: str) -> None:
    """Send a Telegram STRONG BUY alert from /analyse — runs in a background thread."""
    import requests as _req
    if not _TG_BOT_TOKEN:
        return
    now = time.time()
    key = f"{symbol}:{interval}"
    if now - _tg_signal_cooldown.get(key, 0) < _TG_SIGNAL_COOLDOWN:
        return   # already alerted this coin recently
    _tg_signal_cooldown[key] = now
    try:
        price   = quote.get("price", 0) or sig.close
        chg     = quote.get("change_24h", 0)
        rv      = round(sig.rel_volume, 1)
        adx     = round(sig.adx, 1)
        entry   = sig.entry or price
        stop    = sig.stop  or 0
        target  = sig.target or 0
        rr      = sig.rr_ratio or 0
        chg_str  = f"+{chg:.2f}%" if chg >= 0 else f"{chg:.2f}%"
        stop_pct = round(((price - stop) / price) * 100, 2) if stop else 0
        z_quality = getattr(sig, "z_quality", None) or "UNKNOWN"
        z_return  = getattr(sig, "z_return",  None)
        q_icon    = {"IDEAL": "[OK]", "GOOD": "[OK]", "CAUTION": "[!!]", "AVOID": "[X]"}.get(z_quality, "[ ]")
        z_line    = f"Entry:   {q_icon} {z_quality}"
        if z_return is not None and z_return > 2.5:
            z_line += "  -- price extended, consider sizing down"
        elif z_return is not None and z_return < -2.0:
            z_line += "  -- oversold zone, watch for reversal"
        msg = (
            f"CRYPTO SNIPER  --  STRONG BUY\n"
            f"(triggered via app analysis)\n"
            f"{'─' * 28}\n"
            f"{symbol}/USDT  |  {interval.upper()}\n\n"
            f"Score: {sig.total}/{sig.max_score}\n"
            f"Price: ${price:.6g}  ({chg_str})\n"
            f"Vol:   {rv}x  |  ADX: {adx}\n"
            f"{z_line}\n\n"
            f"TRADE SETUP\n"
            f"Entry:  ${entry:.6g}\n"
            f"Stop:   ${stop:.6g}  (-{stop_pct:.1f}%)\n"
            f"Target: ${target:.6g}  |  R:R {rr:.2f}\n"
            f"{'─' * 28}\n"
            f"https://crypto-sniper.app"
        )
        _req.post(
            f"https://api.telegram.org/bot{_TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": _TG_ADMIN_CHAT, "text": msg, "parse_mode": "HTML"},
            timeout=8,
        )
        logger.info(f"[TG] STRONG BUY alert sent for {symbol} ({interval})")
    except Exception as _e:
        logger.warning(f"[TG] notify failed for {symbol}: {_e}")

@app.get("/health")
async def health():
    import os as _os
    from data import _BINANCE_GEO_BLOCKED
    t = time.time()
    results = health_check()
    return {
        "status":         "ok",
        "version":        "2.0.0",
        "latency_ms":     round((time.time()-t)*1000),
        "skip_binance":   _BINANCE_GEO_BLOCKED,
        "skip_binance_env": _os.environ.get("SKIP_BINANCE", "NOT_SET"),
        "sources":        results,
    }

@app.get("/warmup")
async def warmup():
    return {"status":"ok"}

@app.post("/analyse")
async def analyse(req: AnalyseRequest):
    import asyncio
    symbol = req.symbol.upper().strip()
    t_start = time.time()
    try:
        # OHLCV, quote, derivatives, and microstructure are all independent —
        # derivatives/microstructure only need `symbol`, not ohlcv/indicators/sig,
        # so they run concurrently with ohlcv/quote instead of waiting for them.
        # (Confirmed: derivatives.py uses its own independent lru_cache, no
        # shared state with data.py's ohlcv/quote.)
        ohlcv, quote, derivatives, microstructure = await asyncio.gather(
            asyncio.to_thread(get_ohlcv, symbol, req.interval),
            asyncio.to_thread(get_quote, symbol),
            asyncio.to_thread(get_derivatives, symbol),
            asyncio.to_thread(get_market_microstructure, symbol),
        )
        indicators = get_indicators(symbol, req.interval, bars=ohlcv)
        # S score removed — social/sentiment calls skipped for speed
        fear_greed     = {}
        cp_news        = []
        social_delta   = 0.0
        coindar_events = []
        san_signals    = {}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not ohlcv:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    sig = calculate_signals(
        ohlcv, quote, indicators,
        fear_greed=fear_greed, cp_news=cp_news,
        social_delta=social_delta,
        coindar_events=coindar_events,
    )
    levels = get_key_levels(sig)
    # derivatives + microstructure already fetched above, in parallel with
    # ohlcv/quote — nothing left to do here.
    # Background: record signal + check price alerts + Telegram notify on STRONG BUY
    import threading
    threading.Thread(target=record_signal, args=(symbol, req.interval, sig.total, sig.signal_label, sig.close), daemon=True).start()
    threading.Thread(target=check_and_fire_alerts, args=(symbol, sig.close, sig.total), daemon=True).start()
    if sig.signal_label == "STRONG BUY":
        threading.Thread(target=_tg_notify_signal, args=(symbol, sig, quote, req.interval), daemon=True).start()
    return {
        "symbol":symbol,"interval":req.interval,"timestamp":int(time.time()),
        "latency_ms":round((time.time()-t_start)*1000),
        "signal":{"label":sig.signal_label,"total":sig.total,"max":sig.max_score,"direction":sig.direction,"gates":{"v":sig.v_confirmed,"t":sig.t_confirmed,"adx":sig.adx_confirmed}},
        "components":{
            "V":{"confirmed":sig.v_confirmed,"label":"Volume","detail":sig.v_detail,"score":sig.v_score,"max":5},
            "P":{"confirmed":sig.p_confirmed,"label":"Momentum","detail":sig.p_detail,"score":sig.p_score,"max":3},
            "R":{"confirmed":sig.r_confirmed,"label":"Range","detail":sig.r_detail,"score":sig.r_score,"max":2},
            "T":{"confirmed":sig.t_confirmed,"label":"Trend","detail":sig.t_detail,"score":sig.t_score,"max":3},
        },
        "structure":{"close":sig.close,"ema20":sig.ema20,"ema50":sig.ema50,"ema200":sig.ema200,"vwap":sig.vwap,"bb_upper":sig.bb_upper,"bb_lower":sig.bb_lower},
        "timing":{"rsi":sig.rsi,"adx":sig.adx,"atr":sig.atr,"rel_volume":sig.rel_volume,"z_price":sig.z_price,"z_vol":sig.z_vol,"z_return":sig.z_return,"z_quality":sig.z_quality,"vol_shield":sig.vol_shield,"vol_shield_sigma":sig.vol_shield_sigma,"vol_shield_sizing":sig.vol_shield_sizing,"arima_bias":sig.arima_bias,"arima_phi1":sig.arima_phi1,"arima_forecast":sig.arima_forecast,"arima_confluence":sig.arima_confluence},
        "quote":{"price":quote.get("price",0) or sig.close,"change_24h":quote.get("change_24h",0),"volume_24h":quote.get("volume_24h",0),"high_24h":quote.get("high_24h",0) or sig.close,"low_24h":quote.get("low_24h",0) or sig.close},
        "low_liquidity": quote.get("volume_24h", 0) < 1_000_000,  # <$1M 24h vol — scores may be unreliable
        "trade_setup":{"direction":sig.direction,"entry":sig.entry,"stop":sig.stop,"target":sig.target,"rr_ratio":sig.rr_ratio,"atr":sig.atr,"stop_dist_pct":round(((sig.close-sig.stop)/sig.close)*100,3) if sig.stop else None},
        "conviction":{"bull_pct":sig.bull_conviction,"bear_pct":sig.bear_conviction,"bull_signals":sig.bull_signals,"bear_signals":sig.bear_signals},
        "fear_greed":fear_greed,"cp_news":cp_news[:3],"key_levels":levels,
        "ohlcv":ohlcv[-220:],
        "derivatives": derivatives,
        "microstructure": microstructure,
        "social_delta":    social_delta,
        "santiment":       san_signals,
        "events":          coindar_events[:5] if coindar_events else [],
    }

@app.get("/events/{symbol}")
async def events(symbol: str):
    """Upcoming Coindar events for a symbol (next 30 days, HIGH/MED/LOW impact)."""
    sym = symbol.upper().strip()
    ev  = get_coindar_events(sym, days=30)
    return {"symbol": sym, "count": len(ev), "events": ev}

@app.get("/fundamentals/{symbol}")
async def fundamentals(symbol: str):
    """Richer coin fundamentals from Coinpaprika: ATH, rank, supply, tags, description."""
    sym  = symbol.upper().strip()
    meta = get_coinpaprika_meta(sym)
    if not meta:
        raise HTTPException(status_code=404, detail=f"No fundamentals data for {sym}")
    return meta

@app.post("/kronos")
async def kronos(req: KronosRequest):
    import asyncio
    symbol = req.symbol.upper().strip()
    try:
        if req.signal_data:
            signal_ctx = req.signal_data
        else:
            ohlcv = get_ohlcv(symbol, req.interval)
            quote = get_quote(symbol)
            indicators = get_indicators(symbol, req.interval, bars=ohlcv)
            sig = calculate_signals(ohlcv, quote, indicators)
            signal_ctx = {"symbol":symbol,"interval":req.interval,"close":sig.close,"rsi":sig.rsi,"adx":sig.adx,"ema_stack":sig.ema_stack,"signal":sig.signal_label,"total":sig.total,"direction":sig.direction,"change_24h":quote.get("change_24h",0)}

        # Run Kronos forecast and agent council in parallel (both are async)
        try:
            forecast, agents_raw = await asyncio.wait_for(
                asyncio.gather(
                    run_kronos_forecast(symbol, signal_ctx),
                    run_agent_council(symbol, signal_ctx),  # agents run without Kronos enrichment initially
                ),
                timeout=45,
            )
        except asyncio.TimeoutError:
            logger.warning(f"Kronos+agents timed out for {symbol}, falling back to heuristics")
            from kronos import _heuristic_forecast
            from agents import _fallback_agents
            forecast = _heuristic_forecast(symbol, signal_ctx)
            agents_raw = _fallback_agents(symbol, signal_ctx)

        # Post-enrich agent texts with Kronos data isn't possible after parallel run,
        # but agents already receive kron fields if signal_ctx has them pre-populated.
        return {"symbol":symbol,"timestamp":int(time.time()),"forecast":forecast,"agents":agents_raw}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/deep-research")
async def deep_research(req: ResearchRequest):
    try:
        report = await run_deep_research(req.symbol.upper(), req.depth, req.context or {})
        return {"symbol":req.symbol.upper(),"depth":req.depth,"report":report}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/market")
async def market_overview():
    overview = get_market_overview()
    btc = get_btc_onchain()
    return {**overview,"btc_mempool_fees":btc.get("fastest_fee",0),"btc_halfhour_fee":btc.get("halfhour_fee",0),"timestamp":int(time.time())}

@app.get("/trending")
async def trending():
    return {"coins":get_trending(),"timestamp":int(time.time())}

@app.get("/gainers")
async def gainers():
    data = get_gainers_losers()
    return {**data,"timestamp":int(time.time())}

@app.get("/news/{symbol}")
async def news(symbol: str):
    return {"symbol":symbol.upper(),"articles":get_news(symbol),"timestamp":int(time.time())}

@app.get("/macro")
async def macro():
    return {**get_macro(),"timestamp":int(time.time())}

@app.get("/scan", tags=["Signal"])
def scan_top_signals(
    interval: str = Query("1h", description="Candle interval e.g. 1h 4h 1d"),
    min_score: int = Query(9, ge=1, le=16),
    max_coins: int = Query(500, ge=50, le=500, description="Universe size (default 500)"),
    min_volume: float = Query(1_000_000, description="Min 24h volume USD to include"),
):
    """
    Trend-first scan: BUY only requires trend + ADX strength; STRONG BUY
    additionally requires confirmed volume, momentum, and range position.
    Volume is no longer a hard gate on which coins get scored — a coin can
    surface as BUY on trend alone (e.g. a steady multi-day move with no
    single-bar volume spike), and volume instead upgrades a BUY into a
    STRONG BUY inside calculate_signals().

    Pipeline:
      1. Fetch full Binance USDT universe (~400 coins, sorted by 24h vol)
      2. Compute rel_vol_pre for every coin (display/ranking only — no
         longer used to drop coins before scoring)
      3. Score remaining coins in parallel (OHLCV + VPRT gates)
      4. Return coins >= min_score, sorted by score then volume

    Falls back to full universe on cold start (no vol baseline in DB yet).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    interval = interval.lower()
    now = int(time.time())
    cache_key = f"{interval}:{min_score}:{max_coins}:{int(min_volume)}"
    # Check in-memory cache first (fast)
    if _scan_cache.get("key") == cache_key and now - _scan_cache.get("ts", 0) < _SCAN_TTL:
        age_mins = round((now - _scan_cache["ts"]) / 60, 1)
        return {
            "signals":       _scan_cache["data"],
            "cached":        True,
            "cached_age_mins": age_mins,
            "universe":      _scan_cache.get("universe", 0),
            "timestamp":     _scan_cache["ts"],
        }
    # Fall back to SQLite (survives Render sleep/restart)
    db_cached = _scan_db_read(cache_key)
    if db_cached:
        _scan_cache.update({"key": cache_key, "ts": db_cached["ts"], "data": db_cached["data"], "universe": db_cached["universe"]})
        age_mins = round((now - db_cached["ts"]) / 60, 1)
        return {
            "signals":       db_cached["data"],
            "cached":        True,
            "cached_age_mins": age_mins,
            "universe":      db_cached["universe"],
            "timestamp":     db_cached["ts"],
        }

    # --- Coalesce concurrent identical scans ---
    # If another request with the same cache_key is already running the
    # scan below, wait for it instead of launching a duplicate one.
    _lock = _get_scan_lock(cache_key)
    _lock.acquire()
    # Re-check caches now that we hold the lock - the in-flight request
    # we waited on may have just populated them.
    if _scan_cache.get("key") == cache_key and now - _scan_cache.get("ts", 0) < _SCAN_TTL:
        _lock.release()
        age_mins = round((now - _scan_cache["ts"]) / 60, 1)
        return {
            "signals":         _scan_cache["data"],
            "cached":          True,
            "cached_age_mins": age_mins,
            "universe":        _scan_cache.get("universe", 0),
            "timestamp":       _scan_cache["ts"],
        }
    db_cached = _scan_db_read(cache_key)
    if db_cached:
        _lock.release()
        _scan_cache.update({"key": cache_key, "ts": db_cached["ts"], "data": db_cached["data"], "universe": db_cached["universe"]})
        age_mins = round((now - db_cached["ts"]) / 60, 1)
        return {
            "signals":         db_cached["data"],
            "cached":          True,
            "cached_age_mins": age_mins,
            "universe":        db_cached["universe"],
            "timestamp":       db_cached["ts"],
        }

    # ── Step 1: Get multi-exchange universe (Binance + MEXC + Gate.io) ─────────
    universe = get_multi_exchange_universe(
        min_volume_usd_binance=min_volume,
        min_volume_usd_alt=500_000,
        max_coins_each=max_coins,
    )
    if not universe:
        # Fallback to Binance-only if multi fetch fails
        universe = get_binance_universe(min_volume_usd=min_volume, max_coins=max_coins)
    if not universe:
        _lock.release()
        return {"signals": [], "error": "All exchanges unavailable", "timestamp": now}

    universe_size = len(universe)
    logger.info(f"/scan: universe={universe_size} coins (multi-exchange), interval={interval}, min_score={min_score}")

    # ── Step 1b: Compute rel_vol_pre for every coin — no longer a hard filter ──
    # Volume used to gate which coins got scored at all (min_rvol=1.8 dropped
    # everything below that before scoring). Now that volume only upgrades a
    # BUY to a STRONG BUY inside calculate_signals(), gating on it here would
    # still hide trend-only movers (e.g. WPAY: 0.50 -> 1.00 over 5 days with
    # no single-bar volume spike) before they ever reach scoring. min_rvol=0.0
    # means this call effectively never excludes a coin, just tags rel_vol_pre.
    vol_universe = get_vol_prefilter(universe, interval=interval, min_rvol=0.0)
    scan_universe = vol_universe if vol_universe else universe
    scanned_size  = len(scan_universe)
    logger.info(f"/scan: scoring {scanned_size} coins (volume no longer a pre-scoring filter)")

    # ── Step 2: Score every coin in parallel ───────────────────────────────────
    def score_coin(coin: dict):
        sym = coin["symbol"]
        try:
            exch_for_hint = coin.get("exchange", "binance")
            # Pass exchange hint so get_ohlcv() tries the right source first
            ohlcv = get_ohlcv(sym, interval, exchange_hint=exch_for_hint)
            if not ohlcv or len(ohlcv) < 10:
                return None
            # Enforce 50-bar minimum for non-Binance coins (listing age filter)
            if not coin.get("binance_listed", True) and len(ohlcv) < 50:
                logger.debug(f"score_coin: {sym} skipped (<50 bars, new listing on {exch_for_hint})")
                return None
            quote = {
                "price":      coin["price"],
                "change_24h": coin["change_24h"],
                "volume_24h": coin["volume_24h"],
                "high_24h":   coin["high_24h"],
                "low_24h":    coin["low_24h"],
            }
            # Reuse already-fetched bars — eliminates second OHLCV HTTP call per coin
            indicators = get_indicators(sym, interval, bars=ohlcv)
            # skip_models=True: bulk scan doesn't need per-coin GARCH/ARIMA —
            # the model-fitting (not the network fetch) was the real
            # 3-minute bottleneck. Full stats still run in /analyse.
            sig = calculate_signals(ohlcv, quote, indicators, skip_models=True)
            if sig.total < min_score:
                return None
            exch      = coin.get("exchange", "binance")
            exchanges = coin.get("exchanges", [exch])
            on_bnc    = coin.get("binance_listed", exch == "binance")
            exch_label = (
                "MULTI"        if len(exchanges) > 1
                else "MEXC"    if exch == "mexc"
                else "GATE"    if exch == "gate"
                else "BINANCE"
            )
            return {
                "symbol":    sym,
                "price":     quote["price"],
                "change":    quote["change_24h"],
                "volume_24h": quote["volume_24h"],
                "score":     sig.total,
                "max_score": 13,
                "signal":    sig.signal_label,
                "direction": sig.direction,
                "rsi":       round(sig.rsi, 1),
                "adx":       round(sig.adx, 1),
                "rel_vol":   round(sig.rel_volume, 2),
                "v":         sig.v_score,
                "p":         sig.p_score,
                "r":         sig.r_score,
                "t":         sig.t_score,
                "s":         sig.s_score,
                "z_price":   sig.z_price,
                "z_vol":     sig.z_vol,
                "z_return":  sig.z_return,
                "z_quality": sig.z_quality,
                "vol_shield":        sig.vol_shield,
                "vol_shield_sigma":  sig.vol_shield_sigma,
                "vol_shield_sizing": sig.vol_shield_sizing,
                "arima_bias":        sig.arima_bias,
                "arima_phi1":        sig.arima_phi1,
                "arima_forecast":    sig.arima_forecast,
                "arima_confluence":  sig.arima_confluence,
                "scanned_at":     int(time.time()),
                "rel_vol_pre":    round(coin.get("rel_vol_pre") or sig.rel_volume, 2),
                "exchange":       exch,
                "exchange_label": exch_label,
                "exchanges":      exchanges,
                "binance_listed": on_bnc,
            }
        except Exception:
            return None

    signals = []
    # 16 workers: Binance klines is the bottleneck, each call ~120ms
    # 500 coins / 16 workers ≈ 32 batches ≈ ~4s total
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = {ex.submit(score_coin, coin): coin for coin in scan_universe}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                signals.append(result)

    signals.sort(key=lambda s: (s["score"], s["volume_24h"]), reverse=True)
    _scan_cache.update({"key": cache_key, "ts": now, "data": signals, "universe": universe_size})
    _scan_db_write(cache_key, signals, universe_size, now)  # persist across Render sleep
    _lock.release()
    return {
        "signals":        signals,
        "cached":         False,
        "universe":       universe_size,   # full multi-exchange universe count
        "scanned":        scanned_size,    # coins actually scored (volume no longer excludes coins here)
        "timestamp":      now,
    }


@app.post("/watchlist")
async def watchlist(req: WatchlistRequest):
    scores = get_watchlist_scores(req.symbols)
    return {"scores":scores,"timestamp":int(time.time())}


_dip_cache: dict = {}
_DIP_TTL = 300  # 5 minutes

@app.get("/dip-scan", tags=["Signal"])
def dip_scan(
    interval: str = Query("1h"),
    min_dip: float = Query(10.0, description="Min 24h drop % (absolute, e.g. 10 = down 10%+)"),
    min_score: int = Query(7, ge=1, le=16),
):
    """
    Contrarian dip scanner: coins down min_dip%+ in 24h that still score >= min_score.
    Pre-filters by 24h price change BEFORE scoring — only scores actual dip candidates.
    Cached 5 minutes.
    """
    import time, requests as _req
    from concurrent.futures import ThreadPoolExecutor, as_completed

    interval = interval.lower()
    now = int(time.time())
    cache_key = f"{interval}:{min_dip}:{min_score}"
    if _dip_cache.get("key") == cache_key and now - _dip_cache.get("ts", 0) < _DIP_TTL:
        return {"signals": _dip_cache["data"], "cached": True, "timestamp": _dip_cache["ts"]}

    # Step 1: Get Binance 24h tickers, pre-filter to dip candidates only
    try:
        resp = _req.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        tickers = resp.json()
    except Exception:
        return {"signals": [], "error": "Binance unavailable", "timestamp": now}

    dip_candidates = [
        t for t in tickers
        if t.get("symbol", "").endswith("USDT")
        and float(t.get("quoteVolume", 0)) > 500_000
        and float(t.get("priceChangePercent", 0)) <= -min_dip
    ]
    dip_candidates.sort(key=lambda t: float(t.get("priceChangePercent", 0)))  # most down first

    def score_dip(ticker):
        sym = ticker["symbol"].replace("USDT", "")
        try:
            ohlcv = get_ohlcv(sym, interval)
            if not ohlcv or len(ohlcv) < 10:
                return None
            quote = {
                "price":      float(ticker["lastPrice"]),
                "change_24h": float(ticker["priceChangePercent"]),
                "volume_24h": float(ticker["quoteVolume"]),
                "high_24h":   float(ticker["highPrice"]),
                "low_24h":    float(ticker["lowPrice"]),
            }
            indicators = get_indicators(sym, interval, bars=ohlcv)
            sig = calculate_signals(ohlcv, quote, indicators)
            if sig.total < min_score:
                return None
            return {
                "symbol":    sym,
                "price":     quote["price"],
                "change":    quote["change_24h"],
                "score":     sig.total,
                "max_score": 13,
                "signal":    sig.signal_label,
                "rsi":       round(sig.rsi, 1),
                "adx":       round(sig.adx, 1),
                "rel_vol":   round(sig.rel_volume, 2),
            }
        except Exception:
            return None

    signals = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(score_dip, t): t for t in dip_candidates}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                signals.append(result)

    signals.sort(key=lambda s: s["score"], reverse=True)
    _dip_cache.update({"key": cache_key, "ts": now, "data": signals})
    return {"signals": signals, "cached": False, "timestamp": now, "candidates": len(dip_candidates)}


# ── New endpoints ──────────────────────────────────────────────────────────────

@app.get("/derivatives/{symbol}")
async def derivatives_endpoint(symbol: str):
    """Real-time perp data: funding rate, OI, L/S ratio."""
    data = get_derivatives(symbol.upper().strip())
    return {"symbol": symbol.upper().strip(), "timestamp": int(time.time()), **data}


@app.get("/history/{symbol}")
async def signal_history(symbol: str, limit: int = 30):
    """Recent signal history for a symbol."""
    rows = get_symbol_history(symbol.upper().strip(), limit)
    return {"symbol": symbol.upper().strip(), "history": rows, "timestamp": int(time.time())}


@app.get("/hit-rate")
async def hit_rate(symbol: Optional[str] = None, days: int = 30):
    """STRONG BUY hit rate — % that achieved 2%+ gain within 24H."""
    data = get_hit_rate(symbol.upper() if symbol else None, days)
    return {**data, "timestamp": int(time.time())}


@app.get("/scanner-performance")
async def scanner_performance(days: int = 7):
    """Yesterday's scanner picks and their % return since signal."""
    data = get_scanner_performance(days)
    return {**data, "timestamp": int(time.time())}


@app.post("/alerts")
async def create_alert(req: AlertRequest):
    """Register a price alert for a symbol/score threshold."""
    result = register_alert(req)
    return result


@app.get("/alerts")
async def list_alerts(email: str):
    """List active alerts for an email address."""
    return {"alerts": get_alerts(email), "timestamp": int(time.time())}


@app.delete("/alerts/{alert_id}")
async def remove_alert(alert_id: int):
    """Delete an alert by ID."""
    ok = delete_alert(alert_id)
    return {"deleted": ok, "alert_id": alert_id}


@app.get("/alerts/history")
async def alert_history(email: str, limit: int = 50):
    """Return fired alert history for badge/bell dropdown."""
    rows = get_alert_history(email, limit)
    return {"history": rows, "count": len(rows), "timestamp": int(time.time())}


@app.get("/alerts/unread")
async def alert_unread(email: str, since_ts: int = 0):
    """Return count of alerts fired after since_ts (for badge polling)."""
    count = get_unread_count(email, since_ts)
    return {"unread": count, "since_ts": since_ts, "timestamp": int(time.time())}


# ── Backtest ─────────────────────────────────────────────────────────────────



@app.get("/dip-performance", tags=["Signal"])
def dip_performance(
    min_dip: float = Query(5.0, ge=1.0, le=50.0, description="Min 24h drop % (absolute)"),
    top_n:   int   = Query(20, ge=5, le=40, description="Number of dip coins to backtest"),
):
    """
    Dip score-band performance report.

    For each bar where a coin was down >= min_dip% AND scored in a given band,
    measures the next 1D / 3D / 7D recovery.

    Answers: "If I bought every coin that was down 10% AND scored 9/16, what happened?"

    Groups results into score bands: 1-4, 5-6, 7-8, 9-10, 11-13
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from backtest_internal import get_daily_ohlcv, _score_bar, _hold_return, MIN_BARS_CONTEXT

    # Step 1: Get dip coins — either from dip cache or current Binance snapshot
    dip_symbols: list[str] = []

    # Try dip cache first
    for key, val in _dip_cache.items():
        if key == "data" and isinstance(val, list):
            dip_symbols = [s["symbol"] for s in val[:top_n]]
            break

    # If no dip cache, use global Binance to find red coins right now
    if not dip_symbols:
        try:
            import requests as _req
            resp = _req.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
            tickers = resp.json()
            dips = [
                t["symbol"].replace("USDT", "")
                for t in tickers
                if t.get("symbol", "").endswith("USDT")
                and float(t.get("quoteVolume", 0)) > 1_000_000
                and float(t.get("priceChangePercent", 0)) <= -min_dip
            ]
            dips.sort(key=lambda s: s)
            dip_symbols = dips[:top_n]
        except Exception as e:
            logger.warning(f"dip_performance: Binance fetch failed: {e}")

    # Fallback to a broad set of mid-caps that dip regularly
    if not dip_symbols:
        dip_symbols = ["SOL","ADA","DOT","AVAX","LINK","ATOM","NEAR","FIL","ALGO",
                       "HBAR","XLM","ICP","ETC","DOGE","LTC","XRP","BCH","TRX",
                       "MATIC","UNI","AAVE","CRV","INJ","ARB","OP"][:top_n]

    # Step 2: Bar-by-bar backtest — only enter on bars where 24h change <= -min_dip
    all_pairs: list[dict] = []

    def backtest_dip_coin(symbol: str):
        try:
            ohlcv = get_daily_ohlcv(symbol)
            if not ohlcv or len(ohlcv) < MIN_BARS_CONTEXT + 2:
                return []
            pairs = []
            for i in range(MIN_BARS_CONTEXT, len(ohlcv) - 1):
                # 24h change proxy: (close[i] - close[i-1]) / close[i-1] * 100
                prev_close = ohlcv[i - 1][4]
                curr_close = ohlcv[i][4]
                if prev_close <= 0:
                    continue
                change_pct = (curr_close - prev_close) / prev_close * 100

                # Only consider bars that ARE a dip (down >= min_dip%)
                if change_pct > -min_dip:
                    continue

                sig = _score_bar(ohlcv, i)
                if sig.total < 1:
                    continue

                ret_1d = _hold_return(ohlcv, i, 1)
                ret_3d = _hold_return(ohlcv, i, 3)
                ret_7d = _hold_return(ohlcv, i, 7)

                if ret_1d is None:
                    continue

                pairs.append({
                    "symbol":     symbol,
                    "score":      sig.total,
                    "change_pct": round(change_pct, 2),
                    "ret_1d":     round(ret_1d, 3),
                    "ret_3d":     round(ret_3d, 3) if ret_3d is not None else None,
                    "ret_7d":     round(ret_7d, 3) if ret_7d is not None else None,
                })
            return pairs
        except Exception as e:
            logger.warning(f"dip_performance: {symbol} failed: {e}")
            return []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(backtest_dip_coin, sym): sym for sym in dip_symbols}
        for fut in as_completed(futures):
            all_pairs.extend(fut.result())

    if not all_pairs:
        return {
            "bands": [], "coins_used": dip_symbols,
            "total_bars": 0, "min_dip": min_dip,
            "error": "No backtest data — try lowering min_dip or run dip scan first"
        }

    # Step 3: Group by score band
    BANDS = [
        {"label": "1–4",   "min": 1,  "max": 4,  "color": "#64748b"},
        {"label": "5–6",   "min": 5,  "max": 6,  "color": "#f59e0b"},
        {"label": "7–8",   "min": 7,  "max": 8,  "color": "#f59e0b"},
        {"label": "9–10",  "min": 9,  "max": 10, "color": "#22c55e"},
        {"label": "11–13", "min": 11, "max": 13, "color": "#22c55e"},
    ]

    def band_stats(pairs):
        r1 = [p["ret_1d"] for p in pairs if p["ret_1d"] is not None]
        r3 = [p["ret_3d"] for p in pairs if p.get("ret_3d") is not None]
        r7 = [p["ret_7d"] for p in pairs if p.get("ret_7d") is not None]
        if not r1:
            return None
        avg_dip = sum(p["change_pct"] for p in pairs) / len(pairs)
        equity  = 100.0
        for r in r1:
            equity *= (1 + r / 100)
        return {
            "n":        len(r1),
            "avg_dip":  round(avg_dip, 2),
            "avg_1d":   round(sum(r1) / len(r1), 2),
            "avg_3d":   round(sum(r3) / len(r3), 2) if r3 else None,
            "avg_7d":   round(sum(r7) / len(r7), 2) if r7 else None,
            "win_rate": round(sum(1 for r in r1 if r >= 2) / len(r1) * 100, 1),
            "wins":     sum(1 for r in r1 if r >= 2),
            "equity":   round(equity, 2),
        }

    result_bands = []
    for band in BANDS:
        matches = [p for p in all_pairs if band["min"] <= p["score"] <= band["max"]]
        stats = band_stats(matches)
        if stats:
            result_bands.append({"label": band["label"], "color": band["color"],
                                  "min": band["min"], "max": band["max"], **stats})

    return {
        "bands":      result_bands,
        "coins_used": dip_symbols,
        "total_bars": len(all_pairs),
        "min_dip":    min_dip,
        "timestamp":  int(time.time()),
    }


@app.get("/score-performance", tags=["Signal"])
def score_performance(
    top_n: int = Query(15, ge=5, le=30, description="Number of top green coins to backtest"),
    interval: str = Query("1h", description="Interval for scan cache lookup"),
):
    """
    Score-band performance report.

    Takes the current top green coins from the /scan cache,
    runs bar-by-bar backtest on daily data for each,
    groups all (score → next-day return) pairs by score bucket,
    and returns avg return + win rate per bucket.

    Buckets: 1-4 (Weak), 5-6 (Moderate), 7-8 (Good), 9-10 (Strong Buy),
             11-13 (Elite)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from backtest_internal import get_daily_ohlcv, _score_bar, _hold_return, MIN_BARS_CONTEXT

    # ── Step 1: Get green coins from scan cache ───────────────────────────
    cache_key = f"1h:1:{500}:{int(1_000_000)}"  # matches default /scan params
    # Try in-memory first, then SQLite
    coins: list[str] = []
    if _scan_cache.get("key", "").startswith("1h:"):
        coins = [s["symbol"] for s in _scan_cache.get("data", [])[:top_n]]
    if not coins:
        db_row = _scan_db_read(cache_key)
        if db_row:
            coins = [s["symbol"] for s in db_row["data"][:top_n]]

    # If still nothing, use a small set of majors to give some data
    if not coins:
        coins = ["BTC","ETH","SOL","BNB","XRP","ADA","AVAX","LINK","DOGE","DOT"]

    # ── Step 2: Run daily backtest per coin in parallel ───────────────────
    # Collect all bar-score → next-bar-return pairs
    all_pairs: list[dict] = []   # {"score": int, "ret_1d": float, "symbol": str}

    def backtest_coin(symbol: str):
        try:
            ohlcv = get_daily_ohlcv(symbol)
            if not ohlcv or len(ohlcv) < MIN_BARS_CONTEXT + 2:
                return []
            pairs = []
            for i in range(MIN_BARS_CONTEXT, len(ohlcv) - 1):
                sig = _score_bar(ohlcv, i)
                if sig.total < 1:
                    continue
                close_entry = ohlcv[i][4]
                close_exit  = ohlcv[i + 1][4]
                if close_entry <= 0:
                    continue
                ret_1d = (close_exit - close_entry) / close_entry * 100
                ret_3d = _hold_return(ohlcv, i, 3)
                ret_7d = _hold_return(ohlcv, i, 7)
                pairs.append({
                    "symbol": symbol,
                    "score":  sig.total,
                    "ret_1d": round(ret_1d, 3),
                    "ret_3d": round(ret_3d, 3) if ret_3d is not None else None,
                    "ret_7d": round(ret_7d, 3) if ret_7d is not None else None,
                })
            return pairs
        except Exception as e:
            logger.warning(f"score_performance: backtest_coin {symbol} failed: {e}")
            return []

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(backtest_coin, sym): sym for sym in coins}
        for fut in as_completed(futures):
            all_pairs.extend(fut.result())

    if not all_pairs:
        return {"bands": [], "coins_used": coins, "total_bars": 0, "error": "No backtest data available"}

    # ── Step 3: Group by score bucket ────────────────────────────────────
    BANDS = [
        {"label": "1–4",  "min": 1,  "max": 4,  "color": "#64748b"},
        {"label": "5–6",  "min": 5,  "max": 6,  "color": "#f59e0b"},
        {"label": "7–8",  "min": 7,  "max": 8,  "color": "#f59e0b"},
        {"label": "9–10", "min": 9,  "max": 10, "color": "#22c55e"},
        {"label": "11–13","min": 11, "max": 13, "color": "#22c55e"},
        {"label": "14–16","min": 14, "max": 16, "color": "#7c3aed"},
    ]

    def band_stats(pairs):
        rets_1d = [p["ret_1d"] for p in pairs if p["ret_1d"] is not None]
        rets_3d = [p["ret_3d"] for p in pairs if p.get("ret_3d") is not None]
        rets_7d = [p["ret_7d"] for p in pairs if p.get("ret_7d") is not None]
        if not rets_1d:
            return None
        avg_1d   = round(sum(rets_1d) / len(rets_1d), 2)
        avg_3d   = round(sum(rets_3d) / len(rets_3d), 2) if rets_3d else None
        avg_7d   = round(sum(rets_7d) / len(rets_7d), 2) if rets_7d else None
        wins     = sum(1 for r in rets_1d if r >= 2)
        win_rate = round(wins / len(rets_1d) * 100, 1)
        # $100 invested in every bar at this score level (compounded)
        equity = 100.0
        for r in rets_1d:
            equity *= (1 + r / 100)
        return {
            "n":        len(rets_1d),
            "avg_1d":   avg_1d,
            "avg_3d":   avg_3d,
            "avg_7d":   avg_7d,
            "win_rate": win_rate,
            "wins":     wins,
            "equity":   round(equity, 2),   # compounded $100 start
        }

    result_bands = []
    for band in BANDS:
        matches = [p for p in all_pairs if band["min"] <= p["score"] <= band["max"]]
        stats = band_stats(matches)
        if stats:
            result_bands.append({
                "label":    band["label"],
                "color":    band["color"],
                "min":      band["min"],
                "max":      band["max"],
                **stats,
            })

    return {
        "bands":       result_bands,
        "coins_used":  coins,
        "total_bars":  len(all_pairs),
        "timestamp":   int(time.time()),
    }


@app.get("/backtest")
async def backtest(symbol: Optional[str] = None, days: int = 30):
    """Simple backtest of STRONG BUY signals from history DB."""
    data = get_backtest(symbol.upper() if symbol else None, days)
    return {**data, "timestamp": int(time.time())}


# ── Editable watchlist ───────────────────────────────────────────────────────

class WatchlistItemRequest(BaseModel):
    user_id: str = "anon"
    symbol: str


@app.get("/watchlist-items")
async def get_watchlist_items(user_id: str = "anon"):
    """Get persisted watchlist symbols for a user."""
    syms = get_watchlist(user_id)
    return {"user_id": user_id, "symbols": syms, "timestamp": int(time.time())}


@app.post("/watchlist-items")
async def add_watchlist_item(req: WatchlistItemRequest):
    """Add a symbol to the user's watchlist."""
    return add_watchlist_symbol(req.user_id, req.symbol)


@app.delete("/watchlist-items/{symbol}")
async def remove_watchlist_item(symbol: str, user_id: str = "anon"):
    """Remove a symbol from the user's watchlist."""
    return remove_watchlist_symbol(user_id, symbol)


# ── Auth ─────────────────────────────────────────────────────────────────────

class MagicLinkRequest(BaseModel):
    email: str


class VerifyRequest(BaseModel):
    token: str


@app.post("/auth/magic-link")
async def request_magic_link(req: MagicLinkRequest):
    """Send a magic-link login email."""
    return send_magic_link(req.email)


@app.get("/auth/verify")
async def verify_link(token: str):
    """Verify a magic-link token and return a session token."""
    return verify_magic_link(token)


@app.get("/auth/me")
async def me(session_token: str):
    """Return authenticated user email + tier if session is valid."""
    result = verify_session_with_tier(session_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return {**result, "timestamp": int(time.time())}


@app.post("/auth/telegram")
async def auth_telegram(request: Request):
    """
    Validate a short-lived token issued by the Telegram bot.
    Returns { email, tier, session_token, paid_until } on success.
    Called by the frontend after a user arrives via deep link:
      https://crypto-sniper.app?tg_token=XXX
    """
    body = await request.json()
    token = body.get("token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Missing token")
    result = validate_telegram_token(token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid or expired Telegram token")
    return {**result, "timestamp": int(time.time())}


# ── Internal Signal Backtest ────────────────────────────────────────────────

@app.get("/backtest-internal/{symbol}")
async def backtest_internal(symbol: str):
    """
    Replay the live scoring engine bar-by-bar over 1D OHLCV history.
    Returns trades, equity curve, bar scores, and summary stats.
    Fully self-contained — no external trade data needed.
    """
    import asyncio
    result = await asyncio.get_event_loop().run_in_executor(
        None, run_internal_backtest, symbol.upper().strip()
    )
    return result


# ── Multi-Symbol Scan Backtest ──────────────────────────────────────────────

@app.post("/backtest-multi")
async def backtest_multi(payload: dict):
    """
    Run backtest for a list of symbols (e.g. today's BUY signals) and return
    combined portfolio stats + per-symbol breakdown.
    Body: { symbols: ["TOMO","MEGA",...] }
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    import math

    raw_symbols = payload.get("symbols", [])
    symbols = [str(s).upper().strip() for s in raw_symbols if s][:20]  # cap at 20

    if not symbols:
        return {"error": "No symbols provided", "results": [], "portfolio": {}}

    def _run(sym: str) -> dict:
        try:
            r = run_internal_backtest(sym)
            r["symbol"] = sym
            return r
        except Exception as e:
            return {"symbol": sym, "error": str(e), "trades": [], "equity": [], "summary": {}}

    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=min(len(symbols), 8)) as ex:
        futures = [loop.run_in_executor(ex, _run, sym) for sym in symbols]
        results = await asyncio.gather(*futures)

    # ── Merge all trades into a portfolio view ───────────────────────────────
    all_trades = []
    for r in results:
        for t in (r.get("trades") or []):
            all_trades.append({**t, "symbol": r["symbol"]})

    # Sort chronologically
    all_trades.sort(key=lambda t: t.get("date", ""))

    # Portfolio equity: compound across all trades in time order
    equity = 100.0
    equity_curve = []
    wins_1d = losses_1d = 0
    sum_ret_1d = sum_ret_3d = sum_ret_5d = 0.0
    peak = 100.0
    max_dd = 0.0
    ret_list = []

    # Build daily equity curve
    dates_seen: dict = {}
    for t in all_trades:
        d = t.get("date", "")
        r1 = t.get("ret_1d", 0) or 0
        r3 = t.get("ret_3d", 0) or 0
        r5 = t.get("ret_5d", 0) or 0
        equity *= (1 + r1 / 100)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100
        max_dd = max(max_dd, dd)
        if r1 > 0: wins_1d += 1
        elif r1 < 0: losses_1d += 1
        sum_ret_1d += r1
        sum_ret_3d += r3
        sum_ret_5d += r5
        ret_list.append(r1)
        equity_curve.append({
            "date": d, "symbol": t["symbol"],
            "equity": round(equity, 2),
            "ret_1d": round(r1, 2),
            "signal": t.get("signal", ""),
        })

    n = len(all_trades)
    avg_ret_1d = round(sum_ret_1d / n, 2) if n else None
    avg_ret_3d = round(sum_ret_3d / n, 2) if n else None
    avg_ret_5d = round(sum_ret_5d / n, 2) if n else None
    total_trades_with_ret = wins_1d + losses_1d
    win_rate = round(wins_1d / total_trades_with_ret * 100, 1) if total_trades_with_ret else None
    total_return = round(equity - 100, 2) if n else None

    # Sharpe proxy
    if len(ret_list) > 1:
        mean_r = sum(ret_list) / len(ret_list)
        var_r  = sum((x - mean_r) ** 2 for x in ret_list) / len(ret_list)
        std_r  = math.sqrt(var_r)
        sharpe = round(mean_r / std_r * math.sqrt(252), 2) if std_r > 0 else None
    else:
        sharpe = None

    # Per-symbol summary
    per_symbol = []
    for r in results:
        s = r.get("summary") or {}
        per_symbol.append({
            "symbol":       r["symbol"],
            "total_trades": s.get("total_trades", 0),
            "win_rate_1d":  s.get("win_rate_1d"),
            "avg_ret_1d":   s.get("avg_ret_1d"),
            "avg_ret_3d":   s.get("avg_ret_3d"),
            "avg_ret_5d":   s.get("avg_ret_5d"),
            "total_return": s.get("total_return"),
            "max_drawdown": s.get("max_drawdown"),
            "error":        r.get("error"),
        })

    return {
        "symbols":  symbols,
        "results":  per_symbol,
        "trades":   all_trades[-30:],   # last 30 trades for display
        "equity":   equity_curve,
        "portfolio": {
            "total_trades":  n,
            "wins_1d":       wins_1d,
            "losses_1d":     losses_1d,
            "win_rate_1d":   win_rate,
            "avg_ret_1d":    avg_ret_1d,
            "avg_ret_3d":    avg_ret_3d,
            "avg_ret_5d":    avg_ret_5d,
            "total_return":  total_return,
            "max_drawdown":  round(max_dd, 2),
            "sharpe_proxy":  sharpe,
        },
    }


# ── On-Chain Intelligence ────────────────────────────────────────────────────

@app.get("/onchain/{symbol}")
async def onchain_intelligence(symbol: str):
    """
    On-chain intelligence for a symbol:
    supply metrics, MC/FDV ratio, NVT proxy, TVL, unlock schedule, risk signals.
    """
    sym = symbol.upper().strip()
    data = get_onchain(sym)
    return {**data, "timestamp": int(time.time())}


# ── Multi-timeframe confluence ────────────────────────────────────────────────

@app.get("/confluence/{symbol}")
async def confluence(symbol: str, intervals: str = "1H,4H,1D"):
    """
    Run /analyse for the same symbol across multiple timeframes.
    Returns a compact summary for each interval.
    """
    sym = symbol.upper().strip()
    interval_list = [i.strip() for i in intervals.split(",") if i.strip()]
    if not interval_list:
        interval_list = ["1H", "4H", "1D"]

    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    def analyse_tf(interval: str):
        try:
            ohlcv      = get_ohlcv(sym, interval)
            quote      = get_quote(sym)
            indicators = get_indicators(sym, interval, bars=ohlcv)
            if not ohlcv:
                return {"interval": interval, "error": "No data"}
            sig = calculate_signals(ohlcv, quote, indicators)
            return {
                "interval":  interval,
                "score":     sig.total,
                "max_score": sig.max_score,
                "signal":    sig.signal_label,
                "direction": sig.direction,
                "close":     sig.close,
                "rsi":       sig.rsi,
                "adx":       sig.adx,
                "ema_stack": sig.ema_stack,
                "rel_volume":sig.rel_volume,
                "components": {
                    "V": sig.v_score, "P": sig.p_score,
                    "R": sig.r_score, "T": sig.t_score, "S": sig.s_score,
                },
            }
        except Exception as e:
            return {"interval": interval, "error": str(e)}

    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(analyse_tf, interval_list))

    # Confluence score = avg of scores across timeframes
    valid = [r for r in results if "error" not in r]
    confluence_score = round(sum(r["score"] for r in valid) / len(valid), 1) if valid else 0
    all_bull = all(r.get("direction") == "LONG" for r in valid)
    any_strong = any(r.get("signal") == "STRONG BUY" for r in valid)

    return {
        "symbol":            sym,
        "timeframes":        results,
        "confluence_score":  confluence_score,
        "all_bullish":       all_bull,
        "any_strong_buy":    any_strong,
        "timestamp":         int(time.time()),
    }


# ── Signal Streak Heatmap ─────────────────────────────────────────────────────
@app.get("/streak")
async def signal_streak(days: int = 30, min_score: int = 7):
    """
    Return per-symbol, per-day max score for the last N days.
    Used to render the streak heatmap on the frontend.
    Response: { dates: [...], symbols: { SYM: [score_or_null, ...] } }
    """
    import sqlite3 as _sq
    from datetime import datetime, timezone, timedelta
    DB = os.path.join(os.path.dirname(__file__), "data.db")
    cutoff = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())

    try:
        conn = _sq.connect(DB)
        conn.row_factory = _sq.Row
        rows = conn.execute(
            """SELECT symbol,
                      date(ts, 'unixepoch') as day,
                      MAX(score) as max_score
               FROM signals
               WHERE ts >= ? AND score >= ?
               GROUP BY symbol, day
               ORDER BY day ASC""",
            (cutoff, min_score),
        ).fetchall()
        conn.close()
    except Exception as e:
        return {"error": str(e), "dates": [], "symbols": {}}

    # Build date list for last N days
    today = datetime.now(timezone.utc).date()
    date_list = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]

    # Aggregate by symbol
    sym_map: dict[str, dict[str, int]] = {}
    for r in rows:
        sym = r["symbol"]
        if sym not in sym_map:
            sym_map[sym] = {}
        sym_map[sym][r["day"]] = int(r["max_score"])

    # Only include symbols with at least 2 signal days (filter noise)
    result: dict[str, list] = {}
    for sym, day_scores in sym_map.items():
        if len(day_scores) >= 2:
            result[sym] = [day_scores.get(d) for d in date_list]

    # Sort by total signal days desc
    result = dict(sorted(result.items(), key=lambda x: sum(1 for v in x[1] if v), reverse=True))

    return {
        "dates":   date_list,
        "symbols": result,
        "min_score": min_score,
        "days":    days,
        "timestamp": int(time.time()),
    }


# ── Push Notification Subscriptions ──────────────────────────────────────────
from pydantic import BaseModel as _BM

class PushSubRequest(_BM):
    endpoint:   str
    p256dh:     str
    auth:       str
    user_id:    str = "anon"

def _init_push_db():
    import sqlite3 as _sq
    DB = os.path.join(os.path.dirname(__file__), "data.db")
    with _sq.connect(DB) as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   TEXT NOT NULL,
            endpoint  TEXT NOT NULL UNIQUE,
            p256dh    TEXT NOT NULL,
            auth      TEXT NOT NULL,
            created_ts INTEGER NOT NULL
        );
        """)

_init_push_db()

@app.post("/push/subscribe")
async def push_subscribe(req: PushSubRequest):
    """Save a Web Push subscription for this user."""
    import sqlite3 as _sq
    DB = os.path.join(os.path.dirname(__file__), "data.db")
    try:
        with _sq.connect(DB) as c:
            c.execute(
                """INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_ts)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth""",
                (req.user_id, req.endpoint, req.p256dh, req.auth, int(time.time())),
            )
        return {"ok": True, "message": "Push subscription saved"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

@app.delete("/push/subscribe")
async def push_unsubscribe(endpoint: str):
    """Remove a push subscription by endpoint URL."""
    import sqlite3 as _sq
    DB = os.path.join(os.path.dirname(__file__), "data.db")
    try:
        with _sq.connect(DB) as c:
            c.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Volume Surge ──────────────────────────────────────────────────────────────
from data import build_volume_baseline, get_volume_surge as _get_volume_surge

_VS_CACHE: dict = {}
_VS_TTL = 300  # 5 min cache for surge results
_VS_BASELINE_TS: dict = {"ts": 0}
_VS_BASELINE_TTL = 23 * 3600  # rebuild baseline once per ~day

def _maybe_build_baseline():
    """Trigger baseline build in background if >23h old or missing."""
    import threading, time as _t
    now = int(_t.time())
    if now - _VS_BASELINE_TS.get("ts", 0) < _VS_BASELINE_TTL:
        return
    _VS_BASELINE_TS["ts"] = now  # optimistic lock — prevent double-fire

    def _run():
        try:
            result = build_volume_baseline(max_coins=500, interval="1h")
            logger.info(f"Volume baseline rebuilt: {result}")
        except Exception as e:
            logger.error(f"Volume baseline build error: {e}")
            _VS_BASELINE_TS["ts"] = 0  # allow retry

    threading.Thread(target=_run, daemon=True).start()

# Kick off baseline build on startup
_maybe_build_baseline()


@app.get("/volume-surge")
def volume_surge(
    min_rvol:       float = Query(3.0,  description="Min relative volume (e.g. 3.0 = 3x baseline)"),
    max_price_chg:  float = Query(5.0,  description="Max abs price change % to include"),
    min_volume_usd: float = Query(50_000, description="Min 24h volume USD"),
    top_n:          int   = Query(20,   ge=1, le=100),
    interval:       str   = Query("1h"),
):
    """
    Return coins surging on volume vs their 20-bar baseline.
    Sorted by RVOL descending. PRE-BREAKOUT = high vol, muted price.
    """
    import time as _t
    now = int(_t.time())
    cache_key = f"{min_rvol}:{max_price_chg}:{min_volume_usd}:{top_n}:{interval}"

    # Maybe trigger background baseline rebuild
    _maybe_build_baseline()

    if _VS_CACHE.get("key") == cache_key and now - _VS_CACHE.get("ts", 0) < _VS_TTL:
        return {**_VS_CACHE["data"], "cached": True}

    results = _get_volume_surge(
        min_rvol=min_rvol,
        max_price_chg=max_price_chg,
        min_volume_usd=min_volume_usd,
        top_n=top_n,
        interval=interval,
    )

    payload = {
        "coins":      results,
        "count":      len(results),
        "min_rvol":   min_rvol,
        "interval":   interval,
        "timestamp":  now,
        "cached":     False,
    }
    _VS_CACHE.update({"key": cache_key, "ts": now, "data": payload})
    return payload


@app.post("/volume-baseline/rebuild")
async def rebuild_baseline(interval: str = "1h", max_coins: int = 500):
    """Manually trigger a volume baseline rebuild (runs in background)."""
    import threading
    def _run():
        try:
            result = build_volume_baseline(max_coins=max_coins, interval=interval)
            logger.info(f"Manual baseline rebuild: {result}")
        except Exception as e:
            logger.error(f"Manual baseline rebuild error: {e}")
    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": "Baseline rebuild started in background"}


# ── PDF Report Endpoint ────────────────────────────────────────────────────────
from fastapi.responses import Response as _FResponse




@app.post("/pdf-report")
async def pdf_report(payload: dict):
    """Dark-theme Crypto Sniper PDF — single/multi page, no blank pages."""
    import io
    from fpdf import FPDF
    from datetime import datetime, timezone

    def _p(text):
        text = str(text)
        for ch, rep in {
            "\u2014":"-","\u2013":"-","\u00d7":"x","\u00b7":".",
            "\u2019":"'","\u2018":"'","\u201c":'"',"\u201d":'"',
            "\u2022":"-","\u2026":"...","\u2192":"->",
            "\u2713":"OK","\u2717":"X","\u25b2":"^","\u25bc":"v",
            "\u2191":"^","\u2193":"v",
        }.items():
            text = text.replace(ch, rep)
        return text.encode("latin-1", errors="ignore").decode("latin-1")

    # ── Parse ────────────────────────────────────────────────────────────────────
    symbol    = payload.get("symbol", "?")
    interval  = payload.get("interval", "1D")
    now_str   = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    sig_obj   = payload.get("signal", {})
    score     = sig_obj.get("total", 0)
    score_max = sig_obj.get("max", 13)
    signal    = sig_obj.get("label", "NO SIGNAL")
    comp      = payload.get("components", {})
    mkt       = payload.get("structure", {})
    timing    = payload.get("timing", {})
    quote     = payload.get("quote", {})
    ts        = payload.get("trade_setup") or {}
    conv      = payload.get("conviction") or {}
    kron_fc   = payload.get("forecast") or {}

    agents_raw = payload.get("agents") or []
    if isinstance(agents_raw, dict):
        agents_list = [{"key":k,"name":k.upper(),"text":v.get("text",""),"verdict":v.get("verdict","")}
                       for k,v in agents_raw.items() if v]
    else:
        agents_list = list(agents_raw) if isinstance(agents_raw, list) else []

    # ── Stale-data guard: if close/price is 0, do a live re-fetch ─────────────
    # This happens when the frontend sends a cached sig object from before a
    # data-source fix was deployed (e.g. Gate-exclusive coins like SPCX).
    _close_check = mkt.get("close", 0) or quote.get("price", 0)
    if not _close_check and symbol and symbol != "?":
        try:
            logger.info(f"pdf-report: close=0 for {symbol}, doing live re-fetch")
            _ohlcv   = get_ohlcv(symbol, interval)
            _qt      = get_quote(symbol)
            _ind     = get_indicators(symbol, interval)
            _sig     = calculate_signals(_ohlcv, _qt, _ind)
            # Overwrite stale payload fields with fresh data
            mkt   = {"close":_sig.close,"ema20":_sig.ema20,"ema50":_sig.ema50,
                     "ema200":_sig.ema200,"vwap":_sig.vwap,
                     "bb_upper":_sig.bb_upper,"bb_lower":_sig.bb_lower}
            timing = {"rsi":_sig.rsi,"adx":_sig.adx,"atr":_sig.atr,
                      "rel_volume":_sig.rel_volume}
            quote  = {"price":_qt.get("price",0) or _sig.close,
                      "change_24h":_qt.get("change_24h",0),
                      "high_24h":_qt.get("high_24h",0) or _sig.close,
                      "low_24h":_qt.get("low_24h",0) or _sig.close}
            sig_obj  = {"total":_sig.total,"max":_sig.max_score,
                        "label":_sig.signal_label,"direction":_sig.direction}
            score    = _sig.total
            score_max= _sig.max_score
            signal   = _sig.signal_label
            comp     = {
                "V":{"score":_sig.v_score,"max":5,"detail":_sig.v_detail},
                "P":{"score":_sig.p_score,"max":3,"detail":_sig.p_detail},
                "R":{"score":_sig.r_score,"max":2,"detail":_sig.r_detail},
                "T":{"score":_sig.t_score,"max":3,"detail":_sig.t_detail},
            }
            if not ts.get("entry"):
                ts = {"entry":_sig.entry,"stop":_sig.stop,"target":_sig.target,
                      "rr_ratio":_sig.rr_ratio,"atr":_sig.atr,
                      "stop_dist_pct":round(((  _sig.close-_sig.stop)/_sig.close)*100,3) if _sig.stop else None}
        except Exception as _e:
            logger.warning(f"pdf-report live re-fetch failed for {symbol}: {_e}")

    close      = mkt.get("close", 0) or quote.get("price", 0)
    ema20      = mkt.get("ema20", 0); ema50 = mkt.get("ema50", 0)
    ema200     = mkt.get("ema200", 0); vwap  = mkt.get("vwap", 0)
    bb_u       = mkt.get("bb_upper", 0); bb_l = mkt.get("bb_lower", 0)
    rsi        = timing.get("rsi", 0);   adx  = timing.get("adx", 0)
    atr        = timing.get("atr", 0);   rv   = timing.get("rel_volume", 0)
    change_24h = quote.get("change_24h", 0)
    high_24h   = quote.get("high_24h", 0); low_24h = quote.get("low_24h", 0)
    bull_pct   = conv.get("bull_pct", 0); bear_pct = conv.get("bear_pct", 0)
    ts_entry   = ts.get("entry"); ts_stop = ts.get("stop")
    ts_target  = ts.get("target") or ts.get("target1")
    ts_rr      = ts.get("rr_ratio") or ts.get("rr")
    ts_stop_pct= ts.get("stop_dist_pct")
    fc_dir     = kron_fc.get("direction",""); fc_move = kron_fc.get("expected_move_pct",0)
    fc_quality = kron_fc.get("trade_quality",""); fc_target = kron_fc.get("target_price",0)
    fc_momentum= kron_fc.get("momentum",""); fc_green = kron_fc.get("green_candle_pct",0)
    fc_bull_case = kron_fc.get("bull_case",""); fc_bear_case = kron_fc.get("bear_case","")
    fc_bull_conv = kron_fc.get("bull_conviction",""); fc_bear_conv = kron_fc.get("bear_conviction","")

    def _comp(k):
        c = comp.get(k,{}); return c.get("score",0), c.get("max",0), c.get("detail","")
    v_sc,v_mx,v_det = _comp("V"); p_sc,p_mx,p_det = _comp("P")
    r_sc,r_mx,r_det = _comp("R"); t_sc,t_mx,t_det = _comp("T")

    # Colours
    BG=(6,9,18); SRF=(12,18,37); SRF2=(20,30,60); BDR=(30,45,80)
    TXT=(226,232,240); MUT=(100,116,139)
    GRN=(34,197,94); RED=(239,68,68); AMB=(245,158,11); PUR=(124,58,237); WHT=(241,245,249)
    SIG = GRN if score>=9 else AMB if score>=5 else MUT
    def pc(p,r): return GRN if p>r else RED

    # ── PDF ──────────────────────────────────────────────────────────────────────
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)   # we manage page breaks manually
    pdf.set_margins(0, 0, 0)

    MARGIN = 14
    PAGE_H = 297
    SAFE_BOTTOM = PAGE_H - 14   # last y we draw on

    def new_page():
        pdf.add_page()
        pdf.set_fill_color(*BG)
        pdf.rect(0, 0, pdf.w, PAGE_H, "F")
        pdf.set_y(12)

    def need(h):
        """Ensure h mm fits on current page; if not, start a new page."""
        if pdf.get_y() + h > SAFE_BOTTOM:
            new_page()

    new_page()
    PW = pdf.w

    # ── HEADER ───────────────────────────────────────────────────────────────────
    pdf.set_fill_color(20,5,45);  pdf.rect(0,0,PW,32,"F")
    pdf.set_fill_color(12,18,37); pdf.rect(0,22,PW,10,"F")
    pdf.set_font("Helvetica","B",15); pdf.set_text_color(*WHT)
    pdf.set_xy(MARGIN,8);  pdf.cell(80,8,"CRYPTO SNIPER")
    pdf.set_font("Helvetica","",7); pdf.set_text_color(*PUR)
    pdf.set_xy(MARGIN,17); pdf.cell(80,5,"DETECT EARLY. ACT SMART.")
    pdf.set_font("Helvetica","",7.5); pdf.set_text_color(*MUT)
    pdf.set_xy(PW-100,10); pdf.cell(86,5,_p(f"{symbol}/USDT  |  {interval}"),align="R")
    pdf.set_xy(PW-100,16); pdf.cell(86,5,_p(now_str),align="R")
    pdf.set_fill_color(*PUR); pdf.rect(0,32,PW,1.5,"F")
    pdf.set_y(38)

    # ── SIGNAL VERDICT ───────────────────────────────────────────────────────────
    need(38)
    y = pdf.get_y()
    pdf.set_fill_color(*SRF); pdf.set_draw_color(*BDR); pdf.set_line_width(0.3)
    pdf.rect(MARGIN,y,PW-2*MARGIN,32,"FD")
    pdf.set_font("Helvetica","B",26); pdf.set_text_color(*SIG)
    pdf.set_xy(MARGIN,y+4); pdf.cell(PW-2*MARGIN,12,_p(signal),align="C")
    bar_x=MARGIN+30; bar_w=PW-2*MARGIN-60; bar_y=y+18
    pdf.set_fill_color(*SRF2); pdf.rect(bar_x,bar_y,bar_w,4,"F")
    pdf.set_fill_color(*SIG);  pdf.rect(bar_x,bar_y,bar_w*(score/score_max if score_max else 0),4,"F")
    pdf.set_font("Helvetica","",8); pdf.set_text_color(*MUT)
    pdf.set_xy(MARGIN,bar_y+6); pdf.cell(PW-2*MARGIN,5,_p(f"Score  {score} / {score_max}"),align="C")
    pdf.set_y(y+34)

    # ── STATS ROW ────────────────────────────────────────────────────────────────
    need(18)
    stats = [
        ("CLOSE", f"${close:.6g}", TXT),
        ("24H",   f"{change_24h:+.2f}%", GRN if change_24h>=0 else RED),
        ("RSI",   f"{rsi:.0f}",    RED if rsi>=70 else GRN if rsi<=30 else AMB),
        ("ADX",   f"{adx:.0f}",    GRN if adx>=25 else AMB),
        ("VOL",   f"{rv:.1f}x",    GRN if rv>=2 else AMB if rv>=1.5 else MUT),
    ]
    if bull_pct:
        stats.append(("BULL", f"{bull_pct:.0f}%", GRN if bull_pct>=60 else AMB))
    cn = len(stats); cw = (PW-2*MARGIN)/cn; ys = pdf.get_y()+2
    for i in range(cn):
        x = MARGIN+i*cw
        pdf.set_fill_color(*SRF); pdf.set_draw_color(*BDR); pdf.set_line_width(0.2)
        pdf.rect(x,ys,cw-1,14,"FD")
    for i,(lbl,val,vc) in enumerate(stats):
        x = MARGIN+i*cw
        pdf.set_font("Helvetica","B",6.5); pdf.set_text_color(*MUT)
        pdf.set_xy(x,ys+1.5); pdf.cell(cw-1,4,_p(lbl),align="C")
        pdf.set_font("Helvetica","B",9); pdf.set_text_color(*vc)
        pdf.set_xy(x,ys+6);   pdf.cell(cw-1,5,_p(val),align="C")
    pdf.set_y(ys+17)

    # ── HELPERS ──────────────────────────────────────────────────────────────────
    def sec(title):
        need(10)
        y = pdf.get_y()+2
        sw = PW-2*MARGIN
        pdf.set_fill_color(*SRF2); pdf.set_draw_color(*BDR); pdf.set_line_width(0.2)
        pdf.rect(MARGIN,y,sw,7,"FD")
        pdf.set_fill_color(*PUR); pdf.rect(MARGIN,y,3,7,"F")
        pdf.set_font("Helvetica","B",8); pdf.set_text_color(*WHT)
        pdf.set_xy(MARGIN+6,y+1); pdf.cell(sw-6,5,_p(title.upper()))
        pdf.set_y(y+9)

    def sec_at(title, at_y, x, w):
        pdf.set_fill_color(*SRF2); pdf.set_draw_color(*BDR); pdf.set_line_width(0.2)
        pdf.rect(x,at_y,w,7,"FD")
        pdf.set_fill_color(*PUR); pdf.rect(x,at_y,3,7,"F")
        pdf.set_font("Helvetica","B",8); pdf.set_text_color(*WHT)
        pdf.set_xy(x+6,at_y+1); pdf.cell(w-6,5,_p(title.upper()))

    def kv(x, w, label, value, vc=None):
        pdf.set_x(x); pdf.set_font("Helvetica","B",7.5); pdf.set_text_color(*MUT)
        pdf.cell(38,5.5,_p(label))
        pdf.set_font("Helvetica","",8); pdf.set_text_color(*(vc or TXT))
        pdf.cell(w-38,5.5,_p(str(value)),ln=True)

    def card_4col(headers, values, colors, card_h=20):
        """Draw a 4-column info card at current y. Checks page fit first."""
        need(card_h+2)
        tc = (PW-2*MARGIN)/len(headers)
        y0 = pdf.get_y()
        pdf.set_fill_color(*SRF); pdf.set_draw_color(*BDR); pdf.set_line_width(0.2)
        pdf.rect(MARGIN,y0,PW-2*MARGIN,card_h,"FD")
        for i,(h,v,vc) in enumerate(zip(headers,values,colors)):
            x = MARGIN+i*tc
            if i>0:
                pdf.set_draw_color(*BDR); pdf.line(x,y0+1,x,y0+card_h-1)
            pdf.set_font("Helvetica","B",6.5); pdf.set_text_color(*MUT)
            pdf.set_xy(x,y0+2); pdf.cell(tc,5,_p(h),align="C")
            pdf.set_font("Helvetica","B",9 if card_h<=20 else 10)
            pdf.set_text_color(*vc); pdf.set_xy(x,y0+8); pdf.cell(tc,card_h-10,_p(v),align="C")
        pdf.set_y(y0+card_h+1)

    # ── VPRT PILLS ───────────────────────────────────────────────────────────────
    sec("Signal Components  V / P / R / T")
    need(22)
    pw2=43; ph=18; gap=2; tw=4*pw2+3*gap; px0=(PW-tw)/2; py0=pdf.get_y()
    for i,(lbl,sc,mx,det) in enumerate([("V",v_sc,v_mx,v_det),("P",p_sc,p_mx,p_det),("R",r_sc,r_mx,r_det),("T",t_sc,t_mx,t_det)]):
        ratio=sc/mx if mx else 0
        pc2=MUT if sc==0 else GRN if ratio>=0.67 else AMB if ratio>=0.34 else RED
        px=px0+i*(pw2+gap)
        pdf.set_fill_color(pc2[0]//6,pc2[1]//6,pc2[2]//6); pdf.set_draw_color(*pc2); pdf.set_line_width(0.4)
        pdf.rect(px,py0,pw2,ph,"FD")
        pdf.set_font("Helvetica","B",13); pdf.set_text_color(*pc2)
        pdf.set_xy(px+2,py0+1); pdf.cell(16,7,_p(lbl))
        pdf.set_font("Helvetica","B",9); pdf.set_xy(px+22,py0+1.5); pdf.cell(pw2-24,6,_p(f"{sc}/{mx}"),align="R")
        if det:
            pdf.set_font("Helvetica","",6); pdf.set_text_color(*MUT)
            # Strip markdown bold markers for clean output
            det_clean = str(det).replace("**","")
            # Fit detail text inside card: render up to 2 lines by clamping
            # the string to ~60 chars (card is 43mm wide at 6pt ~ 28 chars/line)
            words = det_clean.split()
            line1, line2 = [], []
            for w in words:
                if len(" ".join(line1 + [w])) <= 28:
                    line1.append(w)
                elif len(" ".join(line2 + [w])) <= 28:
                    line2.append(w)
                else:
                    break
            det_2lines = " ".join(line1)
            if line2:
                det_2lines += "\n" + " ".join(line2)
            pdf.set_xy(px+2,py0+9)
            pdf.set_left_margin(px+2); pdf.set_right_margin(PW-(px+pw2-2))
            pdf.multi_cell(pw2-4,3.5,_p(det_2lines))
            pdf.set_left_margin(0); pdf.set_right_margin(0)
    pdf.set_y(py0+ph+4)

    # ── 2-COL: MARKET + TIMING ───────────────────────────────────────────────────
    mkt_rows = [
        ("Close",    f"${close:.6g}",                              None),
        ("EMA 20",   f"{ema20:.6g}  {'above' if close>ema20 else 'below'}",   ema20),
        ("EMA 50",   f"{ema50:.6g}  {'above' if close>ema50 else 'below'}",   ema50),
        ("EMA 200",  f"{ema200:.6g}  {'above' if close>ema200 else 'below'}", ema200),
        ("VWAP",     f"{vwap:.6g}  {'above' if close>vwap else 'below'}",     vwap),
        ("BB Upper", f"{bb_u:.6g}" if bb_u else "n/a",             None),
        ("BB Lower", f"{bb_l:.6g}" if bb_l else "n/a",             None),
    ]
    if high_24h: mkt_rows.append(("24H High", f"${high_24h:.6g}", None))
    if low_24h:  mkt_rows.append(("24H Low",  f"${low_24h:.6g}",  None))

    tim_rows = [
        ("RSI 14",    f"{rsi:.1f}  {'OVERBOUGHT' if rsi>=70 else 'OVERSOLD' if rsi<=30 else 'NEUTRAL'}",
                      RED if rsi>=70 else GRN if rsi<=30 else AMB),
        ("ADX 14",    f"{adx:.1f}  {'Trending' if adx>=20 else 'Ranging'}",    GRN if adx>=25 else AMB),
        ("Rel Volume",f"{rv:.1f}x",  GRN if rv>=2 else AMB if rv>=1.5 else MUT),
    ]
    if atr and close: tim_rows.append(("ATR 14", f"{atr:.4g}  ({atr/close*100:.2f}%)", None))
    if bull_pct:
        tim_rows.append(("Conviction", f"{bull_pct:.0f}% bull / {bear_pct:.0f}% bear",
                         GRN if bull_pct>=60 else AMB if bull_pct>=40 else RED))

    col_h = max(len(mkt_rows), len(tim_rows))
    need(col_h * 5.5 + 16)
    ch = (PW-2*MARGIN-6)/2; lx=MARGIN; rx=MARGIN+ch+6; y2=pdf.get_y()

    sec_at("Market Structure",   y2, lx, ch)
    sec_at("Timing Quality",     y2, rx, ch)
    pdf.set_y(y2+9)

    # write left col
    y_l = pdf.get_y()
    for lbl,val,ref in mkt_rows:
        pdf.set_x(lx); kv(lx, ch, lbl, val, pc(close,ref) if ref else None)
    y_left = pdf.get_y()

    # write right col — reset y to y_l
    pdf.set_y(y_l)
    for lbl,val,vc in tim_rows:
        pdf.set_x(rx); kv(rx, ch, lbl, val, vc)
    y_right = pdf.get_y()

    pdf.set_y(max(y_left, y_right)+4)

    # ── TRADE SETUP ──────────────────────────────────────────────────────────────
    if ts_entry:
        sec("Trade Setup")
        card_4col(
            ["ENTRY","STOP","TARGET","R:R"],
            [f"${ts_entry:.6g}",f"${ts_stop:.6g}",f"${ts_target:.6g}",f"{ts_rr:.2f}" if ts_rr else "n/a"],
            [TXT, RED, GRN, GRN],
            card_h=22
        )
        if ts_stop_pct:
            need(6)
            pdf.set_font("Helvetica","",7); pdf.set_text_color(*MUT)
            pdf.cell(0,4,_p(f"Stop distance: {abs(ts_stop_pct):.2f}% from entry"),ln=True,align="C")
        pdf.ln(2)

    # ── AI FORECAST ──────────────────────────────────────────────────────────────
    if fc_dir:
        sec("AI Forecast  (Kronos)")
        card_4col(
            ["DIRECTION","EXPECTED MOVE","TRADE QUALITY"],
            [fc_dir, f"{'+' if fc_move>=0 else ''}{fc_move:.2f}%", fc_quality],
            [GRN if "Rising" in fc_dir else RED if "Falling" in fc_dir else AMB,
             GRN if fc_move>=0 else RED,
             RED if "Avoid" in fc_quality else AMB if "Moderate" in fc_quality else GRN],
        ) if False else None

        # 3-col row 1
        r1h = ["DIRECTION","EXPECTED MOVE","TRADE QUALITY"]
        r1v = [fc_dir, f"{'+' if fc_move>=0 else ''}{fc_move:.2f}%", fc_quality]
        r1c = [GRN if "Rising" in fc_dir else RED if "Falling" in fc_dir else AMB,
               GRN if fc_move>=0 else RED,
               RED if "Avoid" in fc_quality else AMB if "Moderate" in fc_quality else GRN]
        card_4col(r1h, r1v, r1c)

        # 3-col row 2 (target / momentum / green%)
        r2 = []
        if fc_target:   r2.append(("TARGET PRICE", f"${fc_target:.6g}", GRN))
        if fc_momentum: r2.append(("MOMENTUM", fc_momentum, GRN if "bull" in fc_momentum.lower() else RED if "bear" in fc_momentum.lower() else AMB))
        if fc_green:    r2.append(("GREEN CANDLE %", f"{fc_green:.0f}%", GRN if fc_green>=55 else RED if fc_green<=45 else AMB))
        if r2:
            card_4col([x[0] for x in r2],[x[1] for x in r2],[x[2] for x in r2])

        # Bull / Bear cases — only render if there's actual narrative text (not just "PASS" placeholders)
        _has_bull = fc_bull_case and fc_bull_case.upper() not in ("PASS", "FAIL", "N/A", "")
        _has_bear = fc_bear_case and fc_bear_case.upper() not in ("PASS", "FAIL", "N/A", "")
        if _has_bull or _has_bear:
            card_4col(
                ["BULL CASE","BEAR CASE"],
                [f"{fc_bull_case}  ({fc_bull_conv})" if _has_bull else "—",
                 f"{fc_bear_case}  ({fc_bear_conv})" if _has_bear else "—"],
                [GRN, RED]
            )
        pdf.ln(2)

    # ── AGENT DEBATE ─────────────────────────────────────────────────────────────
    if agents_list:
        sec("AI Lab  -  Agent Debate")
        agent_colors = {"bull":GRN,"bear":RED,"risk":AMB,"cio":PUR}
        for agent in agents_list:
            key     = agent.get("key","")
            name    = agent.get("name", key.upper())
            verdict = agent.get("verdict","")
            text    = agent.get("text","")
            ac      = agent_colors.get(key, MUT)
            lines   = [l.strip() for l in text.split("\n") if l.strip()]
            body    = "\n".join(l for l in lines if not l.upper().startswith("VERDICT:"))

            # Agent header — check fits
            need(10)
            y_ah = pdf.get_y()
            pdf.set_fill_color(ac[0]//8,ac[1]//8,ac[2]//8); pdf.set_draw_color(*ac); pdf.set_line_width(0.3)
            pdf.rect(MARGIN,y_ah,PW-2*MARGIN,7,"FD")
            pdf.set_fill_color(*ac); pdf.rect(MARGIN,y_ah,3,7,"F")
            pdf.set_font("Helvetica","B",8); pdf.set_text_color(*ac)
            pdf.set_xy(MARGIN+6,y_ah+1); pdf.cell(80,5,_p(name))
            pdf.set_font("Helvetica","B",7.5); pdf.set_text_color(*MUT)
            pdf.set_xy(MARGIN+90,y_ah+1); pdf.cell(0,5,_p(f"VERDICT:  {verdict}"))
            pdf.set_y(y_ah+8)

            if body:
                # Render full agent body — split into paragraphs so need() can
                # insert page breaks between them rather than mid-sentence.
                paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()] or [body]
                pdf.set_font("Helvetica","",7.5)
                pdf.set_text_color(180,195,215)
                pdf.set_left_margin(MARGIN+4); pdf.set_right_margin(MARGIN+4)
                for para in paragraphs:
                    # Strip markdown bold markers (**text**) for cleaner PDF output
                    clean = para.replace("**","")
                    need(10)
                    pdf.set_x(MARGIN+4)
                    pdf.multi_cell(PW-2*MARGIN-8, 4.5, _p(clean))
                    pdf.ln(1.5)
                pdf.set_left_margin(0); pdf.set_right_margin(0)
            need(5); pdf.ln(3)

    # ── FOOTER — pinned to bottom of last page, never creates a blank page ─────
    # Do NOT call need() here — it would push footer onto a new empty page.
    fy = PAGE_H - 12
    pdf.set_fill_color(*SRF2); pdf.rect(0,fy,PW,12,"F")
    pdf.set_font("Helvetica","",6.5); pdf.set_text_color(*MUT)
    pdf.set_xy(MARGIN,fy+4)
    pdf.cell(0,4,_p(f"Generated by Crypto Sniper  |  crypto-sniper.app  |  {now_str}  |  Not financial advice."),align="C")

    pdf_bytes = pdf.output()
    return _FResponse(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="crypto-sniper-{symbol}-{interval}.pdf"',
            "Access-Control-Expose-Headers": "Content-Disposition",
        }
    )


# ── DEX Analyse ───────────────────────────────────────────────────────────────
class DexAnalyseRequest(BaseModel):
    query: str          # contract address (0x...), Solana pubkey, or DexScreener pair URL
    chain: str = "auto" # "auto"|"eth"|"bsc"|"sol"|"base"|"arb"


# ─────────────────────────────────────────────────────────────────────────────
# DEX SCAN RESULTS — latest bot sweep, persisted to /tmp/dex_last_scan.json
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/dex-results", tags=["DEX"])
def dex_results():
    """
    Returns the last DEX scan results (gems + vol_hits) from the Telegram bot sweep.

    Read from Supabase (table: dex_scan_cache, single row id=1) rather than a
    local file — dex_scan_job runs in a separate Render service (the Telegram
    bot worker), which has its own separate filesystem. A local /tmp file
    written there was never visible to this API process.
    """
    import requests as _req
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    empty = {"gems": [], "vol_hits": [], "scan_time": None, "scan_ts": None, "fresh": False}
    if not supabase_url or not supabase_key:
        logger.warning("/dex-results: SUPABASE_URL/SUPABASE_SERVICE_KEY not set")
        return empty
    try:
        r = _req.get(
            f"{supabase_url}/rest/v1/dex_scan_cache",
            headers={
                "apikey": supabase_key,
                "Authorization": f"Bearer {supabase_key}",
            },
            params={"id": "eq.1", "select": "scan_time,scan_ts,gems,vol_hits"},
            timeout=10,
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            return empty
        data = rows[0]
        # Mark stale if older than 26h (daily scan, allow buffer)
        age_h = (time.time() - (data.get("scan_ts") or 0)) / 3600
        data["fresh"] = age_h < 26
        data["age_h"] = round(age_h, 1)
        return data
    except Exception as e:
        logger.warning(f"/dex-results Supabase read error: {e}")
        return empty

@app.post("/dex-analyse")
async def dex_analyse(req: DexAnalyseRequest):
    """
    Single-token DEX analysis via DexScreener + GoPlus.
    Accepts contract address, Solana pubkey, or DexScreener URL.
    Returns VPRT-style gate signal + risk scan + trade setup.
    """
    import aiohttp, re, sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "telegram_bot"))
    from dex_scanner.base_agent import ChainAgent, _score_market, _build_trade_setup, _unknown_risk

    t_start = time.time()
    query   = req.query.strip()

    # ── Extract address from DexScreener URL if pasted ───────────────────
    url_match = re.search(r"dexscreener\.com/[^/]+/([A-Za-z0-9]{32,})", query)
    if url_match:
        query = url_match.group(1)

    # ── Detect input type ─────────────────────────────────────────────────
    is_evm    = bool(re.match(r"^0x[0-9a-fA-F]{40}$", query))
    is_sol    = bool(re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", query)) and not is_evm
    is_symbol = not is_evm and not is_sol

    DEXSCREENER = "https://api.dexscreener.com"
    GOPLUS      = "https://api.gopluslabs.io/api/v1"

    # Chain → GoPlus chain ID map
    CHAIN_GOPLUS = {"eth": "1", "bsc": "56", "base": "8453", "arb": "42161", "sol": "solana", "auto": "1"}

    async def fetch_pairs(session, address: str, chain: str) -> list:
        """Search DexScreener for pairs matching address, optionally filtered by chain."""
        try:
            async with session.get(
                f"{DEXSCREENER}/latest/dex/search?q={address}",
                timeout=aiohttp.ClientTimeout(total=12)
            ) as r:
                if r.status != 200:
                    return []
                data  = await r.json()
                pairs = data.get("pairs") or []
                if chain != "auto":
                    chain_pairs = [p for p in pairs if p.get("chainId","").lower() == chain.lower()]
                    return chain_pairs or pairs  # fallback to all if none on requested chain
                return pairs
        except Exception as e:
            logger.warning(f"dex_analyse fetch_pairs: {e}")
            return []

    async def check_risk(session, address: str, chain: str) -> dict:
        if not address or is_sol:
            return _unknown_risk()
        goplus_chain = CHAIN_GOPLUS.get(chain, "1")
        try:
            url = f"{GOPLUS}/token_security/{goplus_chain}?contract_addresses={address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return _unknown_risk()
                data   = await r.json()
                result = (data.get("result") or {}).get(address.lower()) or \
                         (data.get("result") or {}).get(address) or {}
                if not result:
                    return _unknown_risk()

                honeypot     = result.get("is_honeypot",    "0") == "1"
                verified     = result.get("is_open_source", "0") == "1"
                mintable     = result.get("is_mintable",     "0") == "1"
                blacklist    = result.get("is_blacklisted",  "0") == "1"
                hidden_owner = result.get("hidden_owner",    "0") == "1"
                renounced    = result.get("owner_address", "x") in (
                    "", "0x0000000000000000000000000000000000000000"
                )
                buy_tax  = float(result.get("buy_tax",  0) or 0) * 100
                sell_tax = float(result.get("sell_tax", 0) or 0) * 100
                holders  = result.get("holders") or []
                top10_pct= sum(float(h.get("percent",0))*100 for h in holders[:10])

                flags = []
                if honeypot:        flags.append("HONEYPOT")
                if sell_tax > 10:   flags.append(f"HIGH SELL TAX {sell_tax:.0f}%")
                if buy_tax  > 10:   flags.append(f"HIGH BUY TAX {buy_tax:.0f}%")
                if mintable:        flags.append("MINTABLE")
                if hidden_owner:    flags.append("HIDDEN OWNER")
                if blacklist:       flags.append("BLACKLIST FUNCTION")
                if top10_pct > 80:  flags.append(f"TOP 10 HOLD {top10_pct:.0f}%")
                if not verified:    flags.append("UNVERIFIED CONTRACT")

                if honeypot or sell_tax > 20 or hidden_owner:
                    level = "CRITICAL"
                elif len(flags) >= 3 or top10_pct > 70 or sell_tax > 10:
                    level = "HIGH"
                elif len(flags) >= 1 or top10_pct > 50 or not renounced:
                    level = "MEDIUM"
                else:
                    level = "LOW"

                return {
                    "level": level, "honeypot": honeypot, "verified": verified,
                    "renounced": renounced, "mintable": mintable,
                    "buy_tax": round(buy_tax,1), "sell_tax": round(sell_tax,1),
                    "top10_pct": round(top10_pct,1), "flags": flags, "source": "GoPlus",
                }
        except Exception as e:
            logger.warning(f"GoPlus risk check failed: {e}")
            return _unknown_risk()

    def normalise_pair(p: dict) -> dict:
        base    = p.get("baseToken",  {})
        liq     = p.get("liquidity")  or {}
        vol     = p.get("volume")     or {}
        txns    = p.get("txns")       or {}
        chg     = p.get("priceChange") or {}
        txns_1h = txns.get("h1") or {}
        created_at = p.get("pairCreatedAt", 0) or 0
        import time as _time
        age_h = (_time.time() - created_at / 1000) / 3600 if created_at else 0
        symbol = f"{base.get('symbol','?')}/{(p.get('quoteToken') or {}).get('symbol','?')}"
        return {
            "symbol":       symbol,
            "base_symbol":  base.get("symbol", "?"),
            "base_address": base.get("address", ""),
            "pool_address": p.get("pairAddress", ""),
            "chain_id":     p.get("chainId", ""),
            "dex_id":       p.get("dexId", ""),
            "price":        float(p.get("priceUsd", 0) or 0),
            "change_5m":    float(chg.get("m5",  0) or 0),
            "change_1h":    float(chg.get("h1",  0) or 0),
            "change_6h":    float(chg.get("h6",  0) or 0),
            "change_24h":   float(chg.get("h24", 0) or 0),
            "volume_24h":   float(vol.get("h24", 0) or 0),
            "volume_6h":    float(vol.get("h6",  0) or 0),
            "vol_h1":       float(vol.get("h1",  0) or 0),
            "liquidity":    float(liq.get("usd",  0) or 0),
            "pair_age_h":   round(age_h, 1),
            "buys_1h":      int(txns_1h.get("buys",  0) or 0),
            "sells_1h":     int(txns_1h.get("sells", 0) or 0),
            "buys_24h":     int((txns.get("h24") or {}).get("buys",  0) or 0),
            "sells_24h":    int((txns.get("h24") or {}).get("sells", 0) or 0),
            "market_cap":   float(p.get("marketCap", 0) or 0),
            "fdv":          float(p.get("fdv", 0) or 0),
            "dex_url":      p.get("url", ""),
        }

    def build_summary(market: dict, signal: dict, risk: dict) -> str:
        """One plain-English sentence any retail trader can act on."""
        label    = signal.get("label", "NO SIGNAL")
        sym      = market.get("base_symbol", market.get("symbol","?").split("/")[0])
        rel_vol  = signal.get("rel_vol", 1.0)
        chg_24h  = market.get("change_24h", 0)
        liq      = market.get("liquidity", 0)
        risk_lvl = risk.get("level", "UNKNOWN")

        if label == "STRONG BUY":
            vol_txt = f"volume is surging {rel_vol:.1f}x above average"
            return (f"{sym} looks strong right now — {vol_txt}, "
                    f"price is up {chg_24h:+.1f}% in 24h with trend and momentum confirmed. "
                    f"Risk level: {risk_lvl}.")
        elif label == "BUY":
            return (f"{sym} has volume picking up ({rel_vol:.1f}x) and trend is aligned — "
                    f"conditions are building but not fully confirmed yet. "
                    f"Risk level: {risk_lvl}.")
        else:
            failed = []
            if not signal.get("v_confirmed"): failed.append("volume is low")
            if not signal.get("t_confirmed"): failed.append("trend is not aligned")
            if not signal.get("gates", {}).get("adx", False): failed.append("momentum is weak")
            reason = " and ".join(failed) if failed else "conditions are not met"
            return (f"No clear signal for {sym} right now — {reason}. "
                    f"Worth watching if conditions improve.")

    # ── Run analysis ──────────────────────────────────────────────────────
    chain = req.chain.lower()
    async with aiohttp.ClientSession() as session:
        pairs = await fetch_pairs(session, query, chain)
        if not pairs:
            raise HTTPException(status_code=404, detail=f"No pairs found for: {query}")

        # Best pair = highest liquidity
        best_raw = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0))
        market   = normalise_pair(best_raw)

        detected_chain = market.get("chain_id", chain)
        risk = await check_risk(session, market.get("base_address", ""), detected_chain)

    signal = _score_market(market)
    setup  = _build_trade_setup(market, signal)
    summary = build_summary(market, signal, risk)

    return {
        "query":       query,
        "symbol":      market["symbol"],
        "base_symbol": market["base_symbol"],
        "chain":       detected_chain,
        "dex":         market["dex_id"],
        "dex_url":     market["dex_url"],
        "address":     market["base_address"],
        "pool":        market["pool_address"],
        "timestamp":   int(time.time()),
        "latency_ms":  round((time.time() - t_start) * 1000),
        # Signal
        "signal": {
            "label":  signal["label"],
            "gates":  signal["gates"],
        },
        "components": {
            "V": {"confirmed": signal["v_confirmed"], "label": "Volume",    "detail": signal["v_detail"]},
            "P": {"confirmed": signal["p_confirmed"], "label": "Momentum",  "detail": signal["p_detail"]},
            "R": {"confirmed": signal["r_confirmed"], "label": "Range/Flow","detail": signal["r_detail"]},
            "T": {"confirmed": signal["t_confirmed"], "label": "Trend",     "detail": signal["t_detail"]},
        },
        # Market data
        "market": {
            "price":       market["price"],
            "change_5m":   market["change_5m"],
            "change_1h":   market["change_1h"],
            "change_6h":   market["change_6h"],
            "change_24h":  market["change_24h"],
            "volume_24h":  market["volume_24h"],
            "liquidity":   market["liquidity"],
            "pair_age_h":  market["pair_age_h"],
            "buys_1h":     market["buys_1h"],
            "sells_1h":    market["sells_1h"],
            "market_cap":  market["market_cap"],
        },
        "risk":        risk,
        "trade_setup": setup,
        "summary":     summary,
        "source":      "dex",
    }
