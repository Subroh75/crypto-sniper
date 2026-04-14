"""
backtest.py -- Kronos walk-forward backtester for Crypto Sniper

Single-asset: run_backtest(symbol, ...) -> dict
Multi-asset:  run_multi_backtest(symbols, ...) -> list[dict]  (parallel threads)

Metrics
-------
  direction_accuracy  -- % windows where Kronos called UP/DOWN correctly
  win_rate            -- % trade windows that were profitable
  sharpe              -- annualised Sharpe (5% risk-free)
  max_drawdown        -- peak-to-trough on equity curve (%)
  strategy_return     -- total compounded return (%)
  bh_return           -- buy-and-hold return over same period (%)
  avg_return_up/down  -- avg actual % return on UP / DOWN calls
  equity_curve        -- [{date, strategy, buy_hold}] for chart
  trades              -- last 50 [{date, direction, pred_pct, actual_pct, correct}]
"""

from __future__ import annotations

import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---- constants ---------------------------------------------------------------
LOOKBACK   = 200        # candles fed to Kronos as context
PRED_LEN   = 24         # candles Kronos forecasts ahead (24h on hourly)
STEP       = 24         # walk-forward step size (non-overlapping windows)
RISK_FREE  = 0.05       # annual risk-free rate for Sharpe
PERIODS_PA = 365 * 24   # hourly candles per year

# Top 10 most-traded crypto assets by volume / market cap
TOP_ASSETS = ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "AVAX", "LINK", "DOT"]


# ---- data --------------------------------------------------------------------

def _fetch_6m_hourly(symbol: str) -> Optional[pd.DataFrame]:
    """Pull ~6 months of hourly OHLCV from yfinance. Returns None on failure."""
    try:
        import yfinance as yf
    except ImportError:
        return None

    ticker = f"{symbol}-USD"
    try:
        raw = yf.download(ticker, period="6mo", interval="1h",
                          progress=False, auto_adjust=True)
        if raw is None or len(raw) < LOOKBACK + PRED_LEN * 4:
            return None

        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = [c[0].lower() for c in raw.columns]
        else:
            raw.columns = [c.lower() for c in raw.columns]

        raw = raw.reset_index()
        for cname in ("datetime", "date", "Datetime", "Date"):
            if cname in raw.columns:
                raw = raw.rename(columns={cname: "timestamp"})
                break
        if "timestamp" not in raw.columns:
            raw.columns = ["timestamp"] + list(raw.columns[1:])

        raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
        raw = raw[["timestamp", "open", "high", "low", "close", "volume"]].dropna()
        return raw.reset_index(drop=True)
    except Exception:
        return None


# ---- single-window Kronos call -----------------------------------------------

def _kronos_direction(predictor, ctx_df: pd.DataFrame, pred_len: int) -> Optional[str]:
    """Ask Kronos UP or DOWN. Returns None on inference failure."""
    try:
        x_ts  = ctx_df["timestamp"]
        delta = ctx_df["timestamp"].iloc[-1] - ctx_df["timestamp"].iloc[-2]
        y_ts  = pd.Series(pd.date_range(
            start=ctx_df["timestamp"].iloc[-1] + delta,
            periods=pred_len, freq=delta,
        ))
        cols = [c for c in ["open", "high", "low", "close", "volume"]
                if c in ctx_df.columns]
        pred = predictor.predict(
            df=ctx_df[cols], x_timestamp=x_ts, y_timestamp=y_ts,
            pred_len=pred_len, T=1.0, top_p=0.9, sample_count=1,
        )
        if pred is None or pred.empty:
            return None
        current_close  = float(ctx_df["close"].iloc[-1])
        forecast_close = float(pred["close"].iloc[-1])
        return "UP" if forecast_close > current_close else "DOWN"
    except Exception:
        return None


# ---- core walk-forward engine ------------------------------------------------

def run_backtest(
    symbol:    str = "BTC",
    pred_len:  int = PRED_LEN,
    lookback:  int = LOOKBACK,
    step:      int = STEP,
    predictor       = None,
) -> dict:
    """
    Walk-forward backtest over 6 months of hourly data for a single symbol.

    Strategy: long on UP signal, short on DOWN signal, held for pred_len candles.
    """
    df = _fetch_6m_hourly(symbol)
    if df is None or len(df) < lookback + pred_len + step:
        return {"error": f"Insufficient data for {symbol} -- need >= 6 months of hourly history."}

    if predictor is None:
        return {"error": "Kronos predictor not available."}

    n             = len(df)
    start_idx     = lookback
    end_idx       = n - pred_len

    trades        = []
    strategy_rets = []
    bh_rets       = []
    equity        = 1.0
    bh_start      = float(df["close"].iloc[start_idx])
    equity_curve  = []
    window_count  = 0

    for t in range(start_idx, end_idx, step):
        ctx    = df.iloc[t - lookback : t].reset_index(drop=True)
        future = df.iloc[t : t + pred_len]
        if len(future) < pred_len:
            break

        entry_price = float(df["close"].iloc[t - 1])
        exit_price  = float(future["close"].iloc[-1])
        actual_ret  = (exit_price - entry_price) / entry_price

        direction   = _kronos_direction(predictor, ctx, pred_len)
        if direction is None:
            continue

        strat_ret   = actual_ret if direction == "UP" else -actual_ret
        strategy_rets.append(strat_ret)
        bh_rets.append(actual_ret)

        is_correct = (direction == "UP" and actual_ret > 0) or \
                     (direction == "DOWN" and actual_ret < 0)

        trades.append({
            "date":       df["timestamp"].iloc[t].strftime("%Y-%m-%d %H:%M"),
            "direction":  direction,
            "pred_pct":   round(strat_ret * 100, 2),
            "actual_pct": round(actual_ret * 100, 2),
            "correct":    is_correct,
        })

        equity    *= (1 + strat_ret)
        bh_equity  = float(df["close"].iloc[t]) / bh_start

        equity_curve.append({
            "date":      df["timestamp"].iloc[t].strftime("%Y-%m-%d %H:%M"),
            "strategy":  round(equity, 6),
            "buy_hold":  round(bh_equity, 6),
        })
        window_count += 1

    if not strategy_rets:
        return {"error": f"No valid windows for {symbol}."}

    s_arr = np.array(strategy_rets)
    b_arr = np.array(bh_rets)

    direction_acc  = sum(t["correct"] for t in trades) / len(trades)
    win_rate       = sum(1 for r in strategy_rets if r > 0) / len(strategy_rets)

    windows_per_yr = PERIODS_PA / step
    std_ret        = s_arr.std(ddof=1) if len(s_arr) > 1 else 1e-9
    rf_per_win     = RISK_FREE / windows_per_yr
    sharpe         = (s_arr.mean() - rf_per_win) / std_ret * np.sqrt(windows_per_yr) \
                     if std_ret > 0 else 0.0

    eq_arr  = np.array([e["strategy"] for e in equity_curve])
    peaks   = np.maximum.accumulate(eq_arr)
    max_dd  = float(((eq_arr - peaks) / peaks).min()) if len(eq_arr) else 0.0

    up_trades   = [t for t in trades if t["direction"] == "UP"]
    down_trades = [t for t in trades if t["direction"] == "DOWN"]

    return {
        "symbol":             symbol,
        "total_windows":      window_count,
        "windows_up":         len(up_trades),
        "windows_down":       len(down_trades),
        "direction_accuracy": round(direction_acc * 100, 1),
        "win_rate":           round(win_rate * 100, 1),
        "strategy_return":    round((equity - 1.0) * 100, 2),
        "bh_return":          round((float(np.prod(b_arr + 1)) - 1) * 100, 2),
        "avg_return_up":      round(float(np.mean([t["actual_pct"] for t in up_trades])), 2)
                              if up_trades else 0.0,
        "avg_return_down":    round(float(np.mean([t["actual_pct"] for t in down_trades])), 2)
                              if down_trades else 0.0,
        "sharpe":             round(float(sharpe), 2),
        "max_drawdown":       round(max_dd * 100, 2),
        "equity_curve":       equity_curve,
        "trades":             trades[-50:],
    }


# ---- multi-asset parallel runner ---------------------------------------------

def run_multi_backtest(
    symbols:   list[str]  = None,
    pred_len:  int        = PRED_LEN,
    lookback:  int        = LOOKBACK,
    step:      int        = STEP,
    predictor             = None,
    max_workers: int      = 3,
) -> list[dict]:
    """
    Run walk-forward backtests for multiple symbols in parallel.

    Kronos inference is CPU-bound so we use threads (GIL releases during
    PyTorch forward pass).  max_workers=3 avoids OOM on Render Standard (2GB).

    Returns a list of result dicts (same schema as run_backtest), sorted by
    Sharpe ratio descending. Failed symbols are included with an 'error' key.
    """
    if symbols is None:
        symbols = TOP_ASSETS

    results = {}

    def _run_one(sym):
        return sym, run_backtest(
            symbol=sym, pred_len=pred_len, lookback=lookback,
            step=step, predictor=predictor,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_run_one, sym): sym for sym in symbols}
        for fut in as_completed(futures):
            sym, result = fut.result()
            results[sym] = result

    # Sort: successes by Sharpe desc, errors at the end
    ordered = []
    for sym in symbols:
        r = results.get(sym, {"symbol": sym, "error": "Did not complete."})
        ordered.append(r)

    ordered.sort(key=lambda r: (
        0 if "error" not in r else 1,
        -r.get("sharpe", -99),
    ))
    return ordered
