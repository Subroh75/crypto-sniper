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
    return {
        "final_close": round(final, 6),
        "pct_change":  round(pct, 2),
        "peak":        round(peak, 6),
        "trough":      round(trough, 6),
        "bull_pct":    round(bull_pct, 1),
        "direction":   direction,
        "candles":     len(pred),
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
            peak=0.0, trough=0.0, bull_pct=0.0, candles=0,
            forecast=[], available=False,
        )

    pred = _run_kronos(df, pred_len=req.pred_len)
    if pred is None or pred.empty:
        raise HTTPException(status_code=503, detail="Kronos forecast failed.")

    summary = _summarise_kronos(pred, sc["close"])

    # Serialise forecast rows
    forecast_rows = []
    for _, row in pred.iterrows():
        forecast_rows.append({
            "open":   round(float(row.get("open",  0)), 6),
            "high":   round(float(row.get("high",  0)), 6),
            "low":    round(float(row.get("low",   0)), 6),
            "close":  round(float(row.get("close", 0)), 6),
            "volume": round(float(row.get("volume", 0)), 2),
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
