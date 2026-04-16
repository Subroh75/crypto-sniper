"""
main.py — Crypto Sniper FastAPI backend
Endpoints:
  GET  /                   health check
  POST /analyse            V/P/R/T scoring + indicators + agent debate
  POST /kronos             Kronos-mini AI forecast (loads once, cached)
  GET  /analyse/{symbol}   convenience GET variant (uses query params)
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from core import (
    clean_symbol,
    fetch_ohlcv,
    compute_indicators,
    compute_scores,
    generate_agent_debate,
    signal_label,
)

# ──────────────────────────────────────────────────────────────────────────────
# APP
# ──────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Crypto Sniper API",
    description="Real-time crypto signal intelligence — V/P/R/T scoring, AI agent debate, Kronos-mini forecast.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Allow all origins during development; tighten to crypto.guru in production
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────────────────────
# SCHEMAS
# ──────────────────────────────────────────────────────────────────────────────

class AnalyseRequest(BaseModel):
    symbol:   str = Field(..., example="BTC", description="Base asset ticker (BTC, ETH, SOL…)")
    interval: str = Field("1h",  example="1h",  description="1m 5m 15m 30m 1h 4h 1d")


class KronosRequest(BaseModel):
    symbol:   str = Field(..., example="BTC")
    interval: str = Field("1h")
    pred_len: int = Field(24, ge=4, le=96, description="Number of candles to forecast")


class AgentCard(BaseModel):
    text:    str
    verdict: str


class AnalyseResponse(BaseModel):
    symbol:    str
    interval:  str
    timestamp: str
    signal:    str
    score:     int
    score_max: int = 13
    components: dict   # V, P, R, T + sub-metrics
    market:     dict   # price, EMAs, VWAP, BB
    timing:     dict   # RSI, ADX, ATR, DI, RV, ATR move
    debate:     dict   # bull, bear, risk, cio


class KronosResponse(BaseModel):
    symbol:      str
    interval:    str
    direction:   str
    pct_change:  float
    final_close: float
    peak:        float
    trough:      float
    bull_pct:    float
    candles:     int
    forecast:    list[dict]   # [{open, high, low, close, volume}, …]
    available:   bool


class BacktestRequest(BaseModel):
    symbol:   str = Field("BTC", example="BTC")
    pred_len: int = Field(24, ge=4, le=96, description="Candles Kronos forecasts per window")
    lookback: int = Field(200, ge=50, le=500, description="Context candles fed to Kronos")
    step:     int = Field(24, ge=4, le=96, description="Candles between walk-forward steps")


class BacktestResponse(BaseModel):
    symbol:             str
    total_windows:      int
    windows_up:         int
    windows_down:       int
    direction_accuracy: float   # %
    win_rate:           float   # %
    strategy_return:    float   # %
    bh_return:          float   # %
    avg_return_up:      float   # % per window when Kronos said UP
    avg_return_down:    float   # % per window when Kronos said DOWN
    sharpe:             float
    max_drawdown:       float   # %
    equity_curve:       list[dict]
    trades:             list[dict]
    available:          bool
    error:              Optional[str] = None


# ──────────────────────────────────────────────────────────────────────────────
# KRONOS MODEL (loaded once per worker, reused across requests)
# ──────────────────────────────────────────────────────────────────────────────

_KRONOS_LOADED = False
_KRONOS_PREDICTOR = None

def _get_kronos_predictor():
    global _KRONOS_LOADED, _KRONOS_PREDICTOR
    if _KRONOS_LOADED:
        return _KRONOS_PREDICTOR
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
        tokenizer        = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model            = Kronos.from_pretrained("NeoQuasar/Kronos-mini")
        _KRONOS_PREDICTOR = KronosPredictor(model, tokenizer, max_context=512)
    except Exception:
        _KRONOS_PREDICTOR = None
    _KRONOS_LOADED = True
    return _KRONOS_PREDICTOR


def _run_kronos(df, pred_len: int = 24):
    """Run Kronos-mini on df. Returns forecast DataFrame or None."""
    import pandas as pd
    predictor = _get_kronos_predictor()
    if predictor is None:
        return None
    try:
        df       = df.sort_values("timestamp").reset_index(drop=True)
        lookback = min(256, len(df), 512)
        ctx      = df.tail(lookback).reset_index(drop=True)
        x_ts     = ctx["timestamp"]
        delta    = ctx["timestamp"].iloc[-1] - ctx["timestamp"].iloc[-2]
        y_ts     = pd.Series(pd.date_range(
            start=ctx["timestamp"].iloc[-1] + delta,
            periods=pred_len, freq=delta,
        ))
        cols = [c for c in ["open", "high", "low", "close", "volume"] if c in ctx.columns]
        return predictor.predict(
            df=ctx[cols], x_timestamp=x_ts, y_timestamp=y_ts,
            pred_len=pred_len, T=1.0, top_p=0.9, sample_count=1,
        )
    except Exception:
        return None


def _summarise_kronos(pred, current_close: float) -> dict:
    if pred is None or pred.empty:
        return {}
    closes    = pred["close"].values
    final     = float(closes[-1])
    peak      = float(pred["high"].max())
    trough    = float(pred["low"].min())
    pct       = (final - current_close) / current_close * 100
    bull_pct  = float((pred["close"] > pred["open"]).mean() * 100)
    direction = "UP" if final > current_close else "DOWN"

    # ── Confidence score (0–100) ──────────────────────────────────────────
    # Two components equally weighted:
    #
    # 1. Range tightness (50 pts): how narrow the predicted high–low range
    #    is relative to the current price. A tight range means the model
    #    is converging on a price path rather than spanning wide uncertainty.
    #    Normalised so a range of 0% → 50pts, ≥10% range → 0pts.
    #
    # 2. Directional consensus (50 pts): how far bull_pct deviates from
    #    the 50/50 coin-flip baseline. 100% bull or 0% bull = max consensus
    #    (50pts); 50% = no consensus (0pts).
    #
    # Result is clamped to [0, 100] and rounded to one decimal.

    range_pct   = (peak - trough) / current_close * 100 if current_close else 10.0
    tightness   = max(0.0, 50.0 * (1.0 - range_pct / 10.0))   # 0pts at >=10% spread
    consensus   = 50.0 * abs(bull_pct - 50.0) / 50.0           # 50pts at 100% or 0% bull
    confidence  = round(min(100.0, max(0.0, tightness + consensus)), 1)

    return {
        "final_close": round(final, 6),
        "pct_change":  round(pct, 2),
        "peak":        round(peak, 6),
        "trough":      round(trough, 6),
        "bull_pct":    round(bull_pct, 1),
        "direction":   direction,
        "candles":     len(pred),
        "confidence":  confidence,
    }


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def _fetch_and_score(symbol: str, interval: str):
    """Shared data pipeline: fetch → indicators → scores. Raises on failure."""
    base = clean_symbol(symbol)
    df   = fetch_ohlcv(base, interval)
    if df is None or len(df) < 60:
        raise HTTPException(
            status_code=422,
            detail=f"Could not fetch data for {base}. Check the symbol and try again."
        )
    df = compute_indicators(df)
    df = df.dropna(subset=["ema20", "ema50", "atr14", "adx14"]).reset_index(drop=True)
    if len(df) < 2:
        raise HTTPException(status_code=422, detail="Not enough data to compute indicators.")
    sc = compute_scores(df)
    if sc is None:
        raise HTTPException(status_code=422, detail="Scoring failed.")
    return base, df, sc


# ──────────────────────────────────────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def health():
    return {
        "status": "ok",
        "service": "Crypto Sniper API",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ping", tags=["Health"])
def ping():
    """
    Lightweight keep-alive endpoint.
    Returns a minimal payload — used by the GitHub Actions scheduled ping
    to prevent Render cold-starts. Also reports Kronos model load state
    so monitoring can detect if the model has been evicted from memory.
    """
    return {
        "ok": True,
        "kronos_loaded": _KRONOS_LOADED,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/warmup", tags=["Health"])
def warmup():
    """
    Runs a minimal Kronos inference on synthetic data so the model is
    JIT-compiled and hot before the first real /kronos request.
    Called by the keep-alive pinger after /ping confirms the container is up.
    Safe to call repeatedly — if the model is already warm it runs a tiny
    4-candle inference to keep weights paged in, then returns immediately.
    """
    import numpy as np
    import pandas as pd

    predictor = _get_kronos_predictor()
    if predictor is None:
        return {"ok": False, "kronos_loaded": False,
                "msg": "Kronos not available on this deployment."}

    try:
        n = 60
        price = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
        df_warm = pd.DataFrame({
            "open":   price,
            "high":   price * 1.001,
            "low":    price * 0.999,
            "close":  price,
            "volume": np.ones(n) * 1000.0,
        })
        df_warm["timestamp"] = pd.date_range("2024-01-01", periods=n, freq="1h")
        _run_kronos(df_warm, pred_len=4)   # shortest allowed forecast (pred_len min=4)
        warm = True
    except Exception as exc:
        warm = False
        print(f"[warmup] inference failed: {exc}")

    return {
        "ok": True,
        "kronos_loaded": _KRONOS_LOADED,
        "warm": warm,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/analyse", response_model=AnalyseResponse, tags=["Signal"])
def analyse(req: AnalyseRequest):
    """
    Run full V/P/R/T analysis on a symbol.
    Returns signal, score breakdown, market structure, timing metrics, and 4-agent debate.
    """
    base, df, sc = _fetch_and_score(req.symbol, req.interval)
    debate = generate_agent_debate(base, sc, req.interval)
    now    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return AnalyseResponse(
        symbol    = base,
        interval  = req.interval,
        timestamp = now,
        signal    = signal_label(sc["score"]),
        score     = sc["score"],
        components = {
            "V": {"score": sc["V"], "max": 5,  "rv": sc["rv"]},
            "P": {"score": sc["P"], "max": 3,  "atr_move": sc["atr_move"]},
            "R": {"score": sc["R"], "max": 2,  "range_pos": sc["range_pos"]},
            "T": {"score": sc["T"], "max": 3,  "adx": sc["adx14"],
                  "ema_stack": sc["ema20"] > sc["ema50"]},
        },
        market = {
            "close":     sc["close"],
            "open":      sc["open"],
            "high":      sc["high"],
            "low":       sc["low"],
            "pct":       sc["pct"],
            "ema20":     sc["ema20"],
            "ema50":     sc["ema50"],
            "ema200":    sc["ema200"],
            "vwap":      sc["vwap"],
            "bb_upper":  sc["bb_upper"],
            "bb_lower":  sc["bb_lower"],
            "above_ema20":  sc["close"] > sc["ema20"],
            "above_ema50":  sc["close"] > sc["ema50"],
            "above_ema200": sc["close"] > sc["ema200"],
            "above_vwap":   sc["close"] > sc["vwap"],
        },
        timing = {
            "rsi14":    sc["rsi14"],
            "adx14":    sc["adx14"],
            "plus_di":  sc["plus_di"],
            "minus_di": sc["minus_di"],
            "atr14":    sc["atr14"],
            "atr_pct":  round(sc["atr14"] / sc["close"] * 100, 4) if sc["close"] else 0,
            "rv":       sc["rv"],
            "atr_move": sc["atr_move"],
        },
        debate = debate,
    )


@app.get("/analyse/{symbol}", response_model=AnalyseResponse, tags=["Signal"])
def analyse_get(
    symbol:   str,
    interval: str = Query("1h", description="1m 5m 15m 30m 1h 4h 1d"),
):
    """GET convenience wrapper — useful for quick browser/curl testing."""
    return analyse(AnalyseRequest(symbol=symbol, interval=interval))


@app.post("/kronos", response_model=KronosResponse, tags=["Kronos"])
def kronos_forecast(req: KronosRequest):
    """
    Run Kronos-mini AI forecast for a symbol.
    Model is loaded once on first call and reused. First call may take 60-90s.
    Returns predicted OHLCV for the next pred_len candles.
    """
    base, df, sc = _fetch_and_score(req.symbol, req.interval)

    predictor = _get_kronos_predictor()
    if predictor is None:
        # Return a graceful unavailable response rather than a 500
        return KronosResponse(
            symbol=base, interval=req.interval,
            direction="N/A", pct_change=0.0, final_close=0.0,
            peak=0.0, trough=0.0, bull_pct=0.0, candles=0, confidence=0.0,
            forecast=[], available=False,
        )

    pred = _run_kronos(df, pred_len=req.pred_len)
    if pred is None or pred.empty:
        raise HTTPException(status_code=503, detail="Kronos forecast failed.")

    summary = _summarise_kronos(pred, sc["close"])

    # Serialise forecast rows — index is y_timestamp (DatetimeIndex)
    forecast_rows = []
    for ts, row in pred.iterrows():
        forecast_rows.append({
            "timestamp": pd.Timestamp(ts).isoformat(),
            "open":      round(float(row.get("open",   0)), 6),
            "high":      round(float(row.get("high",   0)), 6),
            "low":       round(float(row.get("low",    0)), 6),
            "close":     round(float(row.get("close",  0)), 6),
            "volume":    round(float(row.get("volume",  0)), 2),
        })

    return KronosResponse(
        symbol      = base,
        interval    = req.interval,
        direction   = summary["direction"],
        pct_change  = summary["pct_change"],
        final_close = summary["final_close"],
        peak        = summary["peak"],
        trough      = summary["trough"],
        bull_pct    = summary["bull_pct"],
        candles     = summary["candles"],
        confidence  = summary["confidence"],
        forecast    = forecast_rows,
        available   = True,
    )


@app.get("/kronos/{symbol}", response_model=KronosResponse, tags=["Kronos"])
def kronos_get(
    symbol:   str,
    interval: str = Query("1h"),
    pred_len: int = Query(24, ge=4, le=96),
):
    """GET convenience wrapper for Kronos forecast."""
    return kronos_forecast(KronosRequest(symbol=symbol, interval=interval, pred_len=pred_len))


# ──────────────────────────────────────────────────────────────────────────────
# BACKTEST
# ──────────────────────────────────────────────────────────────────────────────

@app.post("/backtest", response_model=BacktestResponse, tags=["Backtest"])
def backtest(req: BacktestRequest):
    """
    Walk-forward Kronos backtest over 6 months of hourly data.

    At each step the model is given `lookback` candles of context and asked
    to forecast the next `pred_len` candles.  The predicted direction (UP/DOWN)
    is compared to what actually happened.

    Warning: this is a slow endpoint — each window calls Kronos inference.
    Expect 2–5 minutes for BTC at default settings (~90 windows).
    Run it as a background / async job in production.
    """
    from backtest import run_backtest   # lazy import avoids load cost on startup

    base      = clean_symbol(req.symbol)
    predictor = _get_kronos_predictor()

    if predictor is None:
        return BacktestResponse(
            symbol=base, total_windows=0, windows_up=0, windows_down=0,
            direction_accuracy=0, win_rate=0, strategy_return=0, bh_return=0,
            avg_return_up=0, avg_return_down=0, sharpe=0, max_drawdown=0,
            equity_curve=[], trades=[], available=False,
            error="Kronos predictor not available — check /kronos first.",
        )

    result = run_backtest(
        symbol    = base,
        pred_len  = req.pred_len,
        lookback  = req.lookback,
        step      = req.step,
        predictor = predictor,
    )

    if "error" in result:
        return BacktestResponse(
            symbol=base, total_windows=0, windows_up=0, windows_down=0,
            direction_accuracy=0, win_rate=0, strategy_return=0, bh_return=0,
            avg_return_up=0, avg_return_down=0, sharpe=0, max_drawdown=0,
            equity_curve=[], trades=[], available=True,
            error=result["error"],
        )

    return BacktestResponse(
        symbol             = result["symbol"],
        total_windows      = result["total_windows"],
        windows_up         = result["windows_up"],
        windows_down       = result["windows_down"],
        direction_accuracy = result["direction_accuracy"],
        win_rate           = result["win_rate"],
        strategy_return    = result["strategy_return"],
        bh_return          = result["bh_return"],
        avg_return_up      = result["avg_return_up"],
        avg_return_down    = result["avg_return_down"],
        sharpe             = result["sharpe"],
        max_drawdown       = result["max_drawdown"],
        equity_curve       = result["equity_curve"],
        trades             = result["trades"],
        available          = True,
        error              = None,
    )




@app.post("/backtest/multi", tags=["Backtest"])
def backtest_multi(req: MultiBacktestRequest):
    """
    Run walk-forward Kronos backtests for multiple symbols in parallel.

    Symbols default to the top-10 most-traded crypto assets.
    Returns a list of result dicts sorted by Sharpe ratio (desc).
    Expect 5-15 minutes for all 10 assets at default settings.
    """
    from backtest import run_multi_backtest, TOP_ASSETS

    # Sanitise + deduplicate
    symbols   = list(dict.fromkeys(clean_symbol(s) for s in req.symbols)) or TOP_ASSETS
    predictor = _get_kronos_predictor()

    if predictor is None:
        return [{"symbol": s, "error": "Kronos not available.", "available": False}
                for s in symbols]

    results = run_multi_backtest(
        symbols     = symbols,
        pred_len    = req.pred_len,
        lookback    = req.lookback,
        step        = req.step,
        predictor   = predictor,
        max_workers = 3,
    )
    # Tag each result with available flag
    for r in results:
        r["available"] = "error" not in r
    return results


@app.get("/backtest/{symbol}", response_model=BacktestResponse, tags=["Backtest"])
def backtest_get(
    symbol:   str,
    pred_len: int = Query(24, ge=4, le=96),
    lookback: int = Query(200, ge=50, le=500),
    step:     int = Query(24, ge=4, le=96),
):
    """GET convenience wrapper for backtest (useful for testing)."""
    return backtest(BacktestRequest(symbol=symbol, pred_len=pred_len,
                                   lookback=lookback, step=step))


# ──────────────────────────────────────────────────────────────────────────────
# ON-CHAIN ANALYSIS
# ──────────────────────────────────────────────────────────────────────────────

import random
from datetime import timedelta

class OnChainRequest(BaseModel):
    address: str = Field(..., example="0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48")
    chain:   str = Field("ethereum", example="ethereum", description="'ethereum' or 'solana'")


def _demo_onchain(address: str, chain: str) -> dict:
    """
    Demo data generator — returns realistic holder data.
    Replace with live Etherscan / Helius calls (see README in cryptosniper-onchain repo).
    """
    known = {
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USD Coin",      "USDC",  46_000_000_000, 2_100_000),
        "0x6b175474e89094c44da98b954eedeac495271d0f": ("Dai Stablecoin", "DAI",    5_400_000_000,   510_000),
        "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": ("Uniswap",        "UNI",    1_000_000_000,   380_000),
    }
    name, symbol, supply, total_holders = known.get(
        address.lower(),
        ("DemoToken", "DEMO", 1_000_000_000, random.randint(5_000, 50_000))
    )

    labels = [
        "Binance Hot Wallet", "Coinbase Custody", "Kraken Exchange", "OKX Exchange",
        "Bybit Treasury", None, None, "Smart Contract",
        None, "DEX LP Pool", None, "Uniswap V3 Pool",
        None, None, None, None, None, None, None, None,
    ]
    is_contract = [True, True, False, False, False, False, False, True,
                   False, True, False, True, False, False, False, False,
                   False, False, False, False]
    raw_pcts    = [12.4, 8.7, 6.2, 5.1, 4.8, 4.2, 3.9, 3.5,
                   3.1, 2.8, 2.4, 2.1, 1.9, 1.7, 1.5, 1.3,
                   1.1, 0.9, 0.8, 0.7]

    chars = "abcdef0123456789"
    holders = []
    for i, pct in enumerate(raw_pcts):
        wallet_age = random.randint(1, 48)
        first_buy_days = random.randint(30, 730)
        last_active_days = random.randint(0, first_buy_days)
        first_buy = (datetime.now(timezone.utc) - timedelta(days=first_buy_days)).date().isoformat()
        last_active = (datetime.now(timezone.utc) - timedelta(days=last_active_days)).date().isoformat()
        prefix = "0x" if chain == "ethereum" else ""
        addr = prefix + "".join(random.choices(chars, k=40))
        holders.append({
            "rank":             i + 1,
            "address":          addr,
            "balance":          int((pct / 100) * supply),
            "percentage":       pct,
            "firstBuyDate":     first_buy,
            "lastActivityDate": last_active,
            "transactions":     random.randint(5, 200),
            "walletAgeMonths":  wallet_age,
            "isContract":       is_contract[i],
            "label":            labels[i],
        })

    top10_pct = sum(h["percentage"] for h in holders[:10])
    top20_pct = sum(h["percentage"] for h in holders)

    if top10_pct >= 70:   risk = "CRITICAL"
    elif top10_pct >= 50: risk = "HIGH"
    elif top10_pct >= 40: risk = "MEDIUM"
    else:                 risk = "LOW"

    age_buckets = [
        {"label": "< 3mo",  "count": sum(1 for h in holders if h["walletAgeMonths"] < 3)},
        {"label": "3–6mo",  "count": sum(1 for h in holders if 3 <= h["walletAgeMonths"] < 6)},
        {"label": "6–12mo", "count": sum(1 for h in holders if 6 <= h["walletAgeMonths"] < 12)},
        {"label": "1–2yr",  "count": sum(1 for h in holders if 12 <= h["walletAgeMonths"] < 24)},
        {"label": "> 2yr",  "count": sum(1 for h in holders if h["walletAgeMonths"] >= 24)},
    ]

    return {
        "tokenName":             name,
        "tokenSymbol":           symbol,
        "contractAddress":       address,
        "chain":                 chain,
        "totalHolders":          total_holders,
        "totalSupply":           supply,
        "top10Percentage":       round(top10_pct, 2),
        "top20Percentage":       round(top20_pct, 2),
        "riskLevel":             risk,
        "holders":               holders,
        "walletAgeDistribution": age_buckets,
        "concentrationScore":    round(100 - top10_pct, 1),
        "analysisTimestamp":     datetime.now(timezone.utc).isoformat(),
    }


@app.post("/analyze", tags=["On-Chain"])
def analyze_onchain(req: OnChainRequest):
    """
    On-chain holder analysis for an ERC-20 (Ethereum) or SPL (Solana) token.

    - Ethereum: live data via Etherscan when ETHERSCAN_API_KEY env var is set.
    - Solana:   live data via Helius when HELIUS_API_KEY env var is set.
    Both fall back to demo data if keys are absent or if the live fetch errors.
    """
    if req.chain not in ("ethereum", "solana"):
        raise HTTPException(status_code=400, detail="chain must be 'ethereum' or 'solana'")
    if not req.address.strip():
        raise HTTPException(status_code=400, detail="address is required")

    address = req.address.strip()

    if req.chain == "ethereum":
        etherscan_key = os.getenv("ETHERSCAN_API_KEY")
        if etherscan_key:
            try:
                from _etherscan import live_ethereum
                return live_ethereum(address, etherscan_key)
            except Exception as exc:
                print(f"[onchain] Etherscan live fetch failed: {exc} — falling back to demo")

    elif req.chain == "solana":
        helius_key = os.getenv("HELIUS_API_KEY")
        if helius_key:
            try:
                from _helius import live_solana
                return live_solana(address, helius_key)
            except Exception as exc:
                print(f"[onchain] Helius live fetch failed: {exc} — falling back to demo")

    # Fallback: demo data (no key set, or live fetch errored)
    return _demo_onchain(address, req.chain)
