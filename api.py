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
_SCAN_TTL  = 300  # 5-minute cache

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
        ohlcv      = get_ohlcv(symbol, req.interval)
        quote      = get_quote(symbol)
        indicators = get_indicators(symbol, req.interval)
        fear_greed = get_fear_greed()
        cp_news    = get_crypto_panic(symbol)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    if not ohlcv:
        raise HTTPException(status_code=404, detail=f"No data for {symbol}")
    sig = calculate_signals(ohlcv, quote, indicators, fear_greed=fear_greed, cp_news=cp_news)
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
    }

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
):
    """
    Scan top 200 coins by market cap, score each, return those >= min_score.
    Universe: CoinGecko top-200 by market cap (symbols intersected with Binance USDT pairs).
    Cached 5 minutes.
    """
    import time, requests as _req
    from concurrent.futures import ThreadPoolExecutor, as_completed

    interval = interval.lower()
    now = int(time.time())
    cache_key = f"{interval}:{min_score}"
    if _scan_cache.get("key") == cache_key and now - _scan_cache.get("ts", 0) < _SCAN_TTL:
        return {"signals": _scan_cache["data"], "cached": True, "timestamp": _scan_cache["ts"]}

    # ── Step 1: Get top-200 symbols by market cap from CoinGecko ──────────────
    top200_syms: list[str] = []
    try:
        for page in range(1, 3):
            cg = _req.get(
                "https://api.coingecko.com/api/v3/coins/markets"
                "?vs_currency=usd&order=market_cap_desc"
                f"&per_page=100&page={page}&sparkline=false",
                timeout=12,
            )
            if cg.status_code == 200:
                for coin in cg.json():
                    sym = coin.get("symbol", "").upper().strip()
                    if sym and sym not in top200_syms:
                        top200_syms.append(sym)
            time.sleep(0.3)
    except Exception:
        pass  # fall back to Binance volume ordering if CoinGecko fails

    # ── Step 2: Get Binance 24h tickers for price/volume data ─────────────────
    try:
        resp = _req.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        tickers = resp.json()
    except Exception:
        return {"signals": [], "error": "Binance unavailable", "timestamp": now}

    # Build symbol→ticker map from all USDT pairs with meaningful volume
    ticker_map: dict[str, dict] = {}
    for t in tickers:
        s = t.get("symbol", "")
        if s.endswith("USDT") and float(t.get("quoteVolume", 0)) > 500_000:
            sym = s.replace("USDT", "")
            ticker_map[sym] = t

    # ── Step 3: Build scan list — top-200 market cap ∩ Binance USDT pairs ─────
    if top200_syms:
        # Preserve market-cap order, only include symbols tradeable on Binance
        scan_list = [ticker_map[s] for s in top200_syms if s in ticker_map]
    else:
        # CoinGecko unavailable — fall back to top-100 by Binance volume
        all_usdt = list(ticker_map.values())
        all_usdt.sort(key=lambda t: float(t.get("quoteVolume", 0)), reverse=True)
        scan_list = all_usdt[:100]

    def score_coin(ticker):
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
                "signal":    sig.signal,
                "direction": sig.direction,
                "rsi":       sig.rsi,
                "adx":       sig.adx,
                "v":         sig.v_score,
                "p":         sig.p_score,
                "r":         sig.r_score,
                "t":         sig.t_score,
                "s":         sig.s_score,
            }
        except Exception:
            return None

    signals = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(score_coin, t): t for t in scan_list}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                signals.append(result)

    signals.sort(key=lambda s: s["score"], reverse=True)
    _scan_cache.update({"key": cache_key, "ts": now, "data": signals})
    return {"signals": signals, "cached": False, "timestamp": now}


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
                "signal":    sig.signal,
                "rsi":       sig.rsi,
                "adx":       sig.adx,
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
