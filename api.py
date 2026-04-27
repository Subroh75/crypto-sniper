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
    }

@app.post("/kronos")
async def kronos(req: KronosRequest):
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
        forecast = await run_kronos_forecast(symbol, signal_ctx)
        agents = await run_agent_council(symbol, signal_ctx)
        return {"symbol":symbol,"timestamp":int(time.time()),"forecast":forecast,"agents":agents}
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
    min_score: int = Query(5, ge=1, le=16),
):
    """
    Scan top coins by volume from Binance, score each, return those >= min_score.
    Cached 5 minutes.
    """
    import time, requests as _req
    from concurrent.futures import ThreadPoolExecutor, as_completed

    interval = interval.lower()
    now = int(time.time())
    cache_key = f"{interval}:{min_score}"
    if _scan_cache.get("key") == cache_key and now - _scan_cache.get("ts", 0) < _SCAN_TTL:
        return {"signals": _scan_cache["data"], "cached": True, "timestamp": _scan_cache["ts"]}

    # Get top coins by quote volume from Binance 24hr ticker
    try:
        resp = _req.get("https://api.binance.com/api/v3/ticker/24hr", timeout=10)
        tickers = resp.json()
    except Exception:
        return {"signals": [], "error": "Binance unavailable", "timestamp": now}

    # Filter USDT pairs, sort by quote volume, take top 50
    usdt = [t for t in tickers if t.get("symbol","").endswith("USDT") and float(t.get("quoteVolume",0)) > 1_000_000]
    usdt.sort(key=lambda t: float(t.get("quoteVolume", 0)), reverse=True)
    top50 = usdt[:50]

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
                "max_score": sig.max_score,
                "signal":    sig.signal,
                "direction": sig.direction,
                "components": {
                    "V": sig.v_score, "P": sig.p_score,
                    "R": sig.r_score, "T": sig.t_score, "S": sig.s_score,
                },
            }
        except Exception:
            return None

    signals = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(score_coin, t): t for t in top50}
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
