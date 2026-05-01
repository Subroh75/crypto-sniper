"""
api.py - FastAPI backend for Crypto Sniper V2
Endpoints: /analyse /kronos /deep-research /market /trending /gainers /news /macro /watchlist /health
"""
import os, time, logging
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from data import (
    get_ohlcv, get_quote, get_indicators, get_trending,
    get_gainers_losers, get_market_overview, get_btc_onchain,
    get_news, get_macro, get_watchlist_scores, get_fear_greed, get_crypto_panic, health_check,
    get_social_delta, get_coinpaprika_meta,
    get_coindar_events, get_santiment_signals,
    get_binance_universe,
)
from signals import calculate_signals, get_key_levels
from agents import run_agent_council
from kronos import run_kronos_forecast
from perplexity_research import run_deep_research
from derivatives import get_derivatives
from history import (
    record_signal, get_symbol_history, get_hit_rate,
    get_scanner_performance, record_scan_result, get_backtest,
)
from watchlist_db import (
    get_watchlist, add_watchlist_symbol, remove_watchlist_symbol,
)
from auth import (
    send_magic_link, verify_magic_link, verify_session,
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
_SCAN_TTL  = 3600  # 1-hour cache (matches frontend auto-refresh interval)

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

@app.get("/health")
async def health():
    t = time.time()
    results = health_check()
    return {"status":"ok","version":"2.0.0","latency_ms":round((time.time()-t)*1000),"sources":results}

@app.get("/warmup")
async def warmup():
    return {"status":"ok"}

@app.post("/analyse")
async def analyse(req: AnalyseRequest):
    symbol = req.symbol.upper().strip()
    t_start = time.time()
    try:
        ohlcv        = get_ohlcv(symbol, req.interval)
        quote        = get_quote(symbol)
        indicators   = get_indicators(symbol, req.interval)
        fear_greed   = get_fear_greed()
        cp_news      = get_crypto_panic(symbol)
        social_delta    = get_social_delta(symbol)    # Santiment → CC → CryptoPanic proxy
        coindar_events  = get_coindar_events(symbol)   # upcoming HIGH/MED events
        san_signals     = get_santiment_signals(symbol) # dev_activity + active_addresses
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
    # Background: record signal + check price alerts
    import asyncio, threading
    threading.Thread(target=record_signal, args=(symbol, req.interval, sig.total, sig.signal_label, sig.close), daemon=True).start()
    threading.Thread(target=check_and_fire_alerts, args=(symbol, sig.close, sig.total), daemon=True).start()
    return {
        "symbol":symbol,"interval":req.interval,"timestamp":int(time.time()),
        "latency_ms":round((time.time()-t_start)*1000),
        "signal":{"label":sig.signal_label,"total":sig.total,"max":sig.max_score,"direction":sig.direction},
        "components":{
            "V":{"score":sig.v_score,"max":5,"label":"Volume","detail":f"RV={sig.rel_volume:.2f}x"},
            "P":{"score":sig.p_score,"max":3,"label":"Momentum","detail":f"chg={quote.get('change_24h',0):.1f}%"},
            "R":{"score":sig.r_score,"max":2,"label":"Range Pos","detail":f"{sig.range_pos:.0f}%"},
            "T":{"score":sig.t_score,"max":3,"label":"Trend","detail":f"ADX {sig.adx:.0f}"},
            "S":{"score":sig.s_score,"max":3,"label":"Social","detail":"LunarCrush"},
        },
        "structure":{"close":sig.close,"ema20":sig.ema20,"ema50":sig.ema50,"ema200":sig.ema200,"vwap":sig.vwap,"bb_upper":sig.bb_upper,"bb_lower":sig.bb_lower},
        "timing":{"rsi":sig.rsi,"adx":sig.adx,"atr":sig.atr,"rel_volume":sig.rel_volume},
        "quote":{"price":quote.get("price",sig.close),"change_24h":quote.get("change_24h",0),"volume_24h":quote.get("volume_24h",0),"high_24h":quote.get("high_24h",0),"low_24h":quote.get("low_24h",0)},
        "trade_setup":{"direction":sig.direction,"entry":sig.entry,"stop":sig.stop,"target":sig.target,"rr_ratio":sig.rr_ratio,"atr":sig.atr,"stop_dist_pct":round(((sig.close-sig.stop)/sig.close)*100,3) if sig.stop else None},
        "conviction":{"bull_pct":sig.bull_conviction,"bear_pct":sig.bear_conviction,"bull_signals":sig.bull_signals,"bear_signals":sig.bear_signals},
        "fear_greed":fear_greed,"cp_news":cp_news[:3],"key_levels":levels,
        "ohlcv":ohlcv[-48:],
        "derivatives": get_derivatives(symbol),
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
            indicators = get_indicators(symbol, req.interval)
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
    Scan the full Binance USDT universe (~400 coins), score each, return those >= min_score.

    Universe strategy (no CoinGecko dependency):
      1. All active Binance USDT pairs with 24h volume >= min_volume
      2. Sorted by 24h volume (most liquid first)
      3. Trending coins boosted to front (narrative momentum)
      4. Stablecoins / wrapped tokens excluded automatically

    This covers ~2x more coins than the old CoinGecko top-200 and is
    faster (1 Binance call vs 2 paginated CoinGecko calls).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    interval = interval.lower()
    now = int(time.time())
    cache_key = f"{interval}:{min_score}:{max_coins}:{int(min_volume)}"
    # Check in-memory cache first (fast)
    if _scan_cache.get("key") == cache_key and now - _scan_cache.get("ts", 0) < _SCAN_TTL:
        return {
            "signals":  _scan_cache["data"],
            "cached":   True,
            "universe": _scan_cache.get("universe", 0),
            "timestamp": _scan_cache["ts"],
        }
    # Fall back to SQLite (survives Render sleep/restart)
    db_cached = _scan_db_read(cache_key)
    if db_cached:
        _scan_cache.update({"key": cache_key, "ts": db_cached["ts"], "data": db_cached["data"], "universe": db_cached["universe"]})
        return {
            "signals":  db_cached["data"],
            "cached":   True,
            "universe": db_cached["universe"],
            "timestamp": db_cached["ts"],
        }

    # ── Step 1: Get full Binance universe ──────────────────────────────────────────
    universe = get_binance_universe(min_volume_usd=min_volume, max_coins=max_coins)
    if not universe:
        return {"signals": [], "error": "Binance unavailable", "timestamp": now}

    universe_size = len(universe)
    logger.info(f"/scan: universe={universe_size} coins, interval={interval}, min_score={min_score}")

    # ── Step 2: Score every coin in parallel ───────────────────────────────────
    def score_coin(coin: dict):
        sym = coin["symbol"]
        try:
            ohlcv = get_ohlcv(sym, interval)
            if not ohlcv or len(ohlcv) < 10:
                return None
            quote = {
                "price":      coin["price"],
                "change_24h": coin["change_24h"],
                "volume_24h": coin["volume_24h"],
                "high_24h":   coin["high_24h"],
                "low_24h":    coin["low_24h"],
            }
            indicators = get_indicators(sym, interval)
            sig = calculate_signals(ohlcv, quote, indicators)
            if sig.total < min_score:
                return None
            return {
                "symbol":    sym,
                "price":     quote["price"],
                "change":    quote["change_24h"],
                "volume_24h": quote["volume_24h"],
                "score":     sig.total,
                "max_score": 16,
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
            }
        except Exception:
            return None

    signals = []
    # 16 workers: Binance klines is the bottleneck, each call ~120ms
    # 500 coins / 16 workers ≈ 32 batches ≈ ~4s total
    with ThreadPoolExecutor(max_workers=16) as ex:
        futures = {ex.submit(score_coin, coin): coin for coin in universe}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                signals.append(result)

    signals.sort(key=lambda s: (s["score"], s["volume_24h"]), reverse=True)
    _scan_cache.update({"key": cache_key, "ts": now, "data": signals, "universe": universe_size})
    _scan_db_write(cache_key, signals, universe_size, now)  # persist across Render sleep
    return {
        "signals":   signals,
        "cached":    False,
        "universe":  universe_size,
        "timestamp": now,
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
            indicators = get_indicators(sym, interval)
            sig = calculate_signals(ohlcv, quote, indicators)
            if sig.total < min_score:
                return None
            return {
                "symbol":    sym,
                "price":     quote["price"],
                "change":    quote["change_24h"],
                "score":     sig.total,
                "max_score": 16,
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

    Groups results into score bands: 1-4, 5-6, 7-8, 9-10, 11-13, 14-16
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
        {"label": "14–16", "min": 14, "max": 16, "color": "#7c3aed"},
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
             11-13 (Strong+), 14-16 (Elite)
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
    """Return authenticated user email if session is valid."""
    email = verify_session(session_token)
    if not email:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return {"email": email, "timestamp": int(time.time())}


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
            indicators = get_indicators(sym, interval)
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
