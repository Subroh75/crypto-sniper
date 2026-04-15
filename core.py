"""
core.py — Shared indicator, scoring, and agent logic for Crypto Sniper.
Imported by both main.py (FastAPI) and the legacy Streamlit app.
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# DATA
# ──────────────────────────────────────────────────────────────────────────────

INTERVAL_MAP: dict[str, tuple[str, str]] = {
    "1m":  ("1m",  "1d"),
    "5m":  ("5m",  "5d"),
    "15m": ("15m", "5d"),
    "30m": ("30m", "30d"),
    "1h":  ("1h",  "60d"),
    "4h":  ("1h",  "60d"),   # resampled
    "1d":  ("1d",  "1y"),
}


def clean_symbol(raw: str) -> str:
    """Strip pair notation — return base asset only (BTC, ETH, SOL…)."""
    s = raw.strip().upper().replace(" ", "")
    for quote in ["USDT", "BUSD", "USDC", "USD", "BTC", "ETH", "BNB"]:
        if s.endswith(quote) and len(s) > len(quote):
            s = s[:-len(quote)]
            break
    if "/" in s:
        s = s.split("/")[0]
    return s


def fetch_ohlcv(base: str, interval: str, limit: int = 500) -> Optional[pd.DataFrame]:
    """Fetch OHLCV from Yahoo Finance. Returns DataFrame or None."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    yf_interval, period = INTERVAL_MAP.get(interval, ("1h", "60d"))
    ticker = f"{base}-USD"
    try:
        raw = yf.download(ticker, period=period, interval=yf_interval,
                          progress=False, auto_adjust=True)
        if raw is None or len(raw) == 0:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0].lower() for c in raw.columns]
        else:
            raw.columns = [c.lower() for c in raw.columns]
        raw = raw.reset_index()
        # Normalise timestamp column name
        for cname in ("datetime", "date", "Datetime", "Date", "index"):
            if cname in raw.columns:
                raw = raw.rename(columns={cname: "timestamp"})
                break
        if "timestamp" not in raw.columns:
            raw.columns = ["timestamp"] + list(raw.columns[1:])
        raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
        raw = raw[["timestamp", "open", "high", "low", "close", "volume"]].dropna()
        if interval == "4h":
            raw = raw.set_index("timestamp")
            raw = raw.resample("4h").agg(
                {"open": "first", "high": "max", "low": "min",
                 "close": "last", "volume": "sum"}
            ).dropna().reset_index()
        return raw.tail(limit).reset_index(drop=True)
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# INDICATORS
# ──────────────────────────────────────────────────────────────────────────────

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().sort_values("timestamp").reset_index(drop=True)

    # EMAs
    df["ema20"]  = df["close"].ewm(span=20,  adjust=False).mean()
    df["ema50"]  = df["close"].ewm(span=50,  adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()

    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift(1)).abs()
    lc = (df["low"]  - df["close"].shift(1)).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr14"] = tr.ewm(span=14, adjust=False).mean()

    # ADX + DI
    up  = df["high"].diff()
    dn  = -df["low"].diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), index=df.index)
    mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), index=df.index)
    atr = df["atr14"].replace(0, np.nan)
    pdi = 100 * pdm.ewm(span=14, adjust=False).mean() / atr
    mdi = 100 * mdm.ewm(span=14, adjust=False).mean() / atr
    dx  = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    df["adx14"]    = dx.ewm(span=14, adjust=False).mean()
    df["plus_di"]  = pdi
    df["minus_di"] = mdi

    # RSI
    delta = df["close"].diff()
    gain  = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
    df["rsi14"] = 100 - (100 / (1 + gain / loss.replace(0, np.nan)))

    # Volume MA
    df["vol_ma20"] = df["volume"].rolling(20).mean()

    # VWAP (session approximation)
    df["vwap"] = (df["close"] * df["volume"]).cumsum() / df["volume"].cumsum()

    # Bollinger Bands
    df["bb_mid"]   = df["close"].rolling(20).mean()
    df["bb_std"]   = df["close"].rolling(20).std()
    df["bb_upper"] = df["bb_mid"] + 2 * df["bb_std"]
    df["bb_lower"] = df["bb_mid"] - 2 * df["bb_std"]

    return df


# ──────────────────────────────────────────────────────────────────────────────
# SCORING  (V / P / R / T — max 13)
# ──────────────────────────────────────────────────────────────────────────────

def _score_v(rv: float) -> int:
    if rv < 2:   return 0
    elif rv < 4: return 2
    elif rv < 8: return 3
    return 5

def _score_p(close_now: float, close_prev: float, atr_move: float) -> int:
    if close_now <= close_prev: return 0
    if atr_move < 1.5:          return 0
    elif atr_move < 2.5:        return 1
    elif atr_move < 4.0:        return 2
    return 3

def _score_r(range_pos: float) -> int:
    if range_pos < 0.70:   return 0
    elif range_pos < 0.85: return 1
    return 2

def _score_t(close: float, ema20: float, ema50: float, adx14: float) -> int:
    t = 0
    if close > ema20:  t += 1
    if ema20  > ema50: t += 1
    if adx14  >= 20:   t += 1
    return t


def compute_scores(df: pd.DataFrame) -> Optional[dict]:
    if len(df) < 2:
        return None
    row  = df.iloc[-1]
    prev = df.iloc[-2]

    rv       = float(row["volume"]) / float(row["vol_ma20"]) if float(row["vol_ma20"]) > 0 else 0.0
    atr_move = (float(row["close"]) - float(prev["close"])) / float(row["atr14"]) if float(row["atr14"]) > 0 else 0.0
    hl       = float(row["high"]) - float(row["low"])
    range_pos = (float(row["close"]) - float(row["low"])) / hl if hl > 0 else 0.5

    v = _score_v(rv)
    p = _score_p(float(row["close"]), float(prev["close"]), atr_move)
    r = _score_r(range_pos)
    t = _score_t(float(row["close"]), float(row["ema20"]), float(row["ema50"]), float(row["adx14"]))
    pct = (float(row["close"]) - float(prev["close"])) / float(prev["close"]) * 100

    return {
        "close":    float(row["close"]),  "open":  float(row["open"]),
        "high":     float(row["high"]),   "low":   float(row["low"]),
        "volume":   float(row["volume"]),
        "ema20":    float(row["ema20"]),   "ema50":    float(row["ema50"]),
        "ema200":   float(row["ema200"]),  "atr14":    float(row["atr14"]),
        "adx14":    float(row["adx14"]),   "rsi14":    float(row["rsi14"]),
        "plus_di":  float(row["plus_di"]), "minus_di": float(row["minus_di"]),
        "vwap":     float(row["vwap"]),
        "bb_upper": float(row["bb_upper"]), "bb_lower": float(row["bb_lower"]),
        "vol_ma20": float(row["vol_ma20"]),
        "rv":        round(rv, 2),
        "atr_move":  round(atr_move, 2),
        "range_pos": round(range_pos, 3),
        "pct":       round(pct, 2),
        "V": v, "P": p, "R": r, "T": t,
        "score": v + p + r + t,
        "timestamp": str(row["timestamp"])[:16],
    }


# ──────────────────────────────────────────────────────────────────────────────
# AGENT DEBATE
# ──────────────────────────────────────────────────────────────────────────────

def generate_agent_debate(
    symbol: str,
    sc: dict,
    interval: str,
    kronos_summary: Optional[dict] = None,
) -> dict:
    score     = sc["score"]
    rsi       = sc["rsi14"]
    adx       = sc["adx14"]
    rv        = sc["rv"]
    pct       = sc["pct"]
    trend_up  = sc["ema20"] > sc["ema50"]
    above_200 = sc["close"] > sc["ema200"]
    bb_pos    = (
        (sc["close"] - sc["bb_lower"]) / (sc["bb_upper"] - sc["bb_lower"])
        if (sc["bb_upper"] - sc["bb_lower"]) > 0 else 0.5
    )
    has_kronos = bool(kronos_summary)

    # ── Bull ──────────────────────────────────────────────────────────────────
    bull_points: list[str] = []
    if has_kronos and kronos_summary.get("direction") == "UP":
        bull_points.append(
            f"Kronos-mini forecasts +{kronos_summary['pct_change']:.1f}% over next "
            f"{kronos_summary['candles']} candles — model aligns with the bull case"
        )
    if trend_up:
        bull_points.append("EMA20 > EMA50 confirms bullish structure")
    if above_200:
        bull_points.append("Price above EMA200 — macro trend intact")
    if rv >= 2:
        bull_points.append(f"Volume spike at {rv:.1f}x average signals conviction")
    if rsi > 50 and rsi < 70:
        bull_points.append(f"RSI {rsi:.0f} — momentum building without being overbought")
    if sc["atr_move"] >= 1.5:
        bull_points.append(f"ATR move of {sc['atr_move']:.1f}x sigma shows real directional force")
    if not bull_points:
        bull_points.append("Watching for volume confirmation before entry")
        bull_points.append("Accumulation zone — patient longs could be rewarded")
    bull_text    = ". ".join(bull_points[:3]) + "."
    bull_verdict = "BUY" if score >= 7 else "HOLD"

    # ── Bear ──────────────────────────────────────────────────────────────────
    bear_points: list[str] = []
    if has_kronos and kronos_summary.get("direction") == "DOWN":
        bear_points.append(
            f"Kronos-mini model predicts {kronos_summary['pct_change']:.1f}% move "
            f"lower — AI forecast supports the bear thesis"
        )
    elif has_kronos and kronos_summary.get("direction") == "UP":
        bear_points.append(
            f"Kronos shows upside to {kronos_summary['final_close']:.6g} "
            f"but bull% only {kronos_summary['bull_pct']:.0f}% — fragile conviction"
        )
    if rsi >= 70:
        bear_points.append(f"RSI {rsi:.0f} is overbought — fade the rally")
    if not trend_up:
        bear_points.append("EMA20 below EMA50 signals bearish crossover")
    if not above_200:
        bear_points.append("Price under EMA200 — macro trend remains down")
    if bb_pos > 0.9:
        bear_points.append("Price pressing upper Bollinger Band — mean reversion likely")
    if pct > 5:
        bear_points.append(f"Already up {pct:.1f}% this candle — late entry risk is real")
    if sc["atr_move"] < 1:
        bear_points.append("Weak ATR move — no real momentum behind this move")
    if not bear_points:
        bear_points.append("Low volatility environment limits upside conviction")
        bear_points.append("Macro headwinds remain — any rally should be sold")
    bear_text    = ". ".join(bear_points[:3]) + "."
    bear_verdict = "SELL" if score <= 4 else "HOLD"

    # ── Risk Manager ──────────────────────────────────────────────────────────
    atr_pct = sc["atr14"] / sc["close"] * 100 if sc["close"] > 0 else 0
    risk_points = [
        f"ATR at {atr_pct:.2f}% of price — size positions accordingly",
        f"Suggested stop: {sc['close'] - 1.5 * sc['atr14']:.6g} (1.5x ATR below close)",
        f"ADX {adx:.0f} — "
        f"{'trending market, trend-following rules apply' if adx >= 20 else 'ranging market, reduce size and widen stops'}",
    ]
    if has_kronos:
        risk_points.append(
            f"Kronos model peak: {kronos_summary['peak']:.6g}, "
            f"trough: {kronos_summary['trough']:.6g} — use trough as hard floor for stop placement"
        )
    if rv >= 4:
        risk_points.append(f"Volume {rv:.1f}x above average — watch for exhaustion spike")
    risk_text    = ". ".join(risk_points[:3]) + "."
    risk_verdict = "HOLD" if score < 5 else ("BUY" if score >= 8 else "HOLD")

    # ── CIO ───────────────────────────────────────────────────────────────────
    kronos_lead = ""
    if has_kronos:
        kronos_lead = (
            f"Kronos-mini AI forecasts {kronos_summary['direction']} "
            f"({kronos_summary['pct_change']:+.1f}%) over {kronos_summary['candles']} candles. "
        )
    if score >= 9:
        cio_text = (
            kronos_lead +
            f"Score {score}/13 with {rv:.1f}x volume, ADX {adx:.0f}, and "
            f"bullish EMA stack. This is a textbook high-conviction setup. "
            f"Allocate with defined risk. "
            f"{'Macro trend is supportive.' if above_200 else 'Be mindful this is counter-trend.'}"
        )
        cio_verdict = "BUY"
    elif score >= 5:
        cio_text = (
            kronos_lead +
            f"Mixed signals at score {score}/13. "
            f"{'Trend is constructive but' if trend_up else 'Trend is bearish and'} "
            f"volume {'confirms' if rv >= 2 else 'does not confirm'} the move. "
            f"Reduce size and wait for cleaner confirmation before committing capital."
        )
        cio_verdict = "WATCHLIST"
    else:
        cio_text = (
            kronos_lead +
            f"Score {score}/13 — setup does not meet minimum thresholds. "
            f"RSI {rsi:.0f}, ADX {adx:.0f}, volume {rv:.1f}x average. "
            f"No edge present. Preserve capital and wait for a proper signal."
        )
        cio_verdict = "HOLD"

    return {
        "bull": {"text": bull_text,  "verdict": bull_verdict},
        "bear": {"text": bear_text,  "verdict": bear_verdict},
        "risk": {"text": risk_text,  "verdict": risk_verdict},
        "cio":  {"text": cio_text,   "verdict": cio_verdict},
    }


# ──────────────────────────────────────────────────────────────────────────────
# SIGNAL LABEL
# ──────────────────────────────────────────────────────────────────────────────

def signal_label(score: int) -> str:
    if score >= 9: return "STRONG BUY"
    if score >= 5: return "MODERATE"
    return "NO SIGNAL"
