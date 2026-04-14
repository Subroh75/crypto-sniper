"""
backtest.py — Kronos walk-forward backtester for Crypto Sniper
==============================================================
Walks 6 months of hourly OHLCV data for any symbol using a sliding window.
At each step it asks Kronos: "which way will price move over the next N candles?"
Then it compares that prediction to what actually happened.

Metrics returned
----------------
  direction_accuracy   — % of windows where Kronos called UP/DOWN correctly
  win_rate             — % of trades that were profitable (Kronos UP → long)
  sharpe               — annualised Sharpe of the signal-driven strategy
  avg_return_up        — avg % return when Kronos said UP
  avg_return_down      — avg % return when Kronos said DOWN
  bh_return            — total return of buy-and-hold over the same period
  strategy_return      — total return of the Kronos-driven strategy
  total_windows        — number of walk-forward windows evaluated
  windows_up / windows_down — breakdown of signal counts
  equity_curve         — [{date, strategy, buy_hold}] for charting
  trades               — [{date, direction, pred_pct, actual_pct, correct}]
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ─── constants ────────────────────────────────────────────────────────────────
LOOKBACK   = 200   # candles fed into Kronos as context
PRED_LEN   = 24    # candles Kronos forecasts ahead (24h on hourly data)
STEP       = 24    # walk forward by 24 candles per window (non-overlapping)
RISK_FREE  = 0.05  # annual risk-free rate for Sharpe (5%)
PERIODS_PA = 365 * 24  # hourly candles per year


# ─── data ─────────────────────────────────────────────────────────────────────

def _fetch_6m_hourly(symbol: str) -> Optional[pd.DataFrame]:
    """
    Pull ~6 months of hourly BTC-USD data from yfinance.
    yfinance caps 1h at 730 days but returns ~4380 rows for 6 months.
    We request period='6mo' explicitly.
    """
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


# ─── single-window Kronos call ─────────────────────────────────────────────────

def _kronos_direction(predictor, ctx_df: pd.DataFrame, pred_len: int) -> Optional[str]:
    """
    Ask Kronos which direction price will move over the next pred_len candles.
    Returns 'UP', 'DOWN', or None on failure.
    """
    try:
        import pandas as pd

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


# ─── main backtester ─────────────────────────────────────────────────────────

def run_backtest(
    symbol:     str   = "BTC",
    pred_len:   int   = PRED_LEN,
    lookback:   int   = LOOKBACK,
    step:       int   = STEP,
    predictor         = None,   # KronosPredictor — injected from main.py
) -> dict:
    """
    Walk-forward backtest over 6 months of hourly data.

    Strategy
    --------
    At each step t:
      - Feed candles [t-lookback : t] to Kronos
      - If Kronos says UP  → long the next `pred_len` candles
      - If Kronos says DOWN → short the next `pred_len` candles
      - Record actual % return over [t : t+pred_len]

    Returns a result dict with all metrics + equity curve + trade log.
    """

    # ── 1. fetch data ─────────────────────────────────────────────────────────
    df = _fetch_6m_hourly(symbol)
    if df is None or len(df) < lookback + pred_len + step:
        return {"error": "Insufficient data — need at least 6 months of hourly history."}

    if predictor is None:
        return {"error": "Kronos predictor not available — cannot run backtest."}

    # ── 2. walk-forward loop ──────────────────────────────────────────────────
    n          = len(df)
    start_idx  = lookback
    end_idx    = n - pred_len      # last valid window start

    trades          = []
    strategy_rets   = []           # per-window return
    bh_rets         = []           # buy-and-hold return over same window

    # Running equity (starts at 1.0)
    equity          = 1.0
    bh_equity       = 1.0
    bh_start_price  = float(df["close"].iloc[start_idx])
    equity_curve    = []

    window_count = 0

    for t in range(start_idx, end_idx, step):
        ctx    = df.iloc[t - lookback : t].reset_index(drop=True)
        future = df.iloc[t : t + pred_len]

        if len(future) < pred_len:
            break   # not enough future data

        entry_price  = float(df["close"].iloc[t - 1])
        exit_price   = float(future["close"].iloc[-1])

        # Actual return over the window
        actual_ret   = (exit_price - entry_price) / entry_price

        # Kronos direction call
        direction    = _kronos_direction(predictor, ctx, pred_len)
        if direction is None:
            continue   # skip failed windows

        # Strategy return: long on UP, short on DOWN
        strat_ret    = actual_ret if direction == "UP" else -actual_ret

        strategy_rets.append(strat_ret)
        bh_rets.append(actual_ret)

        # Predicted % change (from Kronos forecast close vs entry)
        pred_pct     = strat_ret * 100   # sign already applied

        trades.append({
            "date":       df["timestamp"].iloc[t].strftime("%Y-%m-%d %H:%M"),
            "direction":  direction,
            "pred_pct":   round(pred_pct, 2),
            "actual_pct": round(actual_ret * 100, 2),
            "correct":    (direction == "UP" and actual_ret > 0)
                          or (direction == "DOWN" and actual_ret < 0),
        })

        # Compound equity
        equity    *= (1 + strat_ret)
        bh_price   = float(df["close"].iloc[t])
        bh_equity  = bh_price / bh_start_price

        equity_curve.append({
            "date":       df["timestamp"].iloc[t].strftime("%Y-%m-%d %H:%M"),
            "strategy":   round(equity, 6),
            "buy_hold":   round(bh_equity, 6),
        })

        window_count += 1

    # ── 3. metrics ────────────────────────────────────────────────────────────
    if not strategy_rets:
        return {"error": "No valid windows completed — Kronos may have failed on all windows."}

    s_arr = np.array(strategy_rets)
    b_arr = np.array(bh_rets)

    direction_correct = sum(t["correct"] for t in trades)
    direction_acc     = direction_correct / len(trades) if trades else 0.0

    profitable_trades = [r for r in strategy_rets if r > 0]
    win_rate          = len(profitable_trades) / len(strategy_rets) if strategy_rets else 0.0

    # Annualised Sharpe (windows are `step` candles apart on hourly data)
    windows_per_year  = PERIODS_PA / step
    mean_ret          = s_arr.mean()
    std_ret           = s_arr.std(ddof=1) if len(s_arr) > 1 else 1e-9
    rf_per_window     = RISK_FREE / windows_per_year
    sharpe            = (mean_ret - rf_per_window) / std_ret * np.sqrt(windows_per_year) \
                        if std_ret > 0 else 0.0

    # Max drawdown on equity curve
    eq_series = np.array([e["strategy"] for e in equity_curve])
    peaks     = np.maximum.accumulate(eq_series)
    drawdowns = (eq_series - peaks) / peaks
    max_dd    = float(drawdowns.min()) if len(drawdowns) else 0.0

    up_trades   = [t for t in trades if t["direction"] == "UP"]
    down_trades = [t for t in trades if t["direction"] == "DOWN"]

    avg_ret_up   = float(np.mean([t["actual_pct"] for t in up_trades]))   if up_trades   else 0.0
    avg_ret_down = float(np.mean([t["actual_pct"] for t in down_trades]))  if down_trades else 0.0

    bh_total  = float(np.prod(b_arr + 1)) - 1 if len(b_arr) else 0.0
    strat_total = equity - 1.0

    return {
        # summary
        "symbol":             symbol,
        "total_windows":      window_count,
        "windows_up":         len(up_trades),
        "windows_down":       len(down_trades),
        # accuracy
        "direction_accuracy": round(direction_acc * 100, 1),
        "win_rate":           round(win_rate * 100, 1),
        # returns
        "strategy_return":    round(strat_total * 100, 2),
        "bh_return":          round(bh_total * 100, 2),
        "avg_return_up":      round(avg_ret_up, 2),
        "avg_return_down":    round(avg_ret_down, 2),
        # risk
        "sharpe":             round(float(sharpe), 2),
        "max_drawdown":       round(max_dd * 100, 2),
        # detail
        "equity_curve":       equity_curve,
        "trades":             trades[-50:],   # last 50 for payload size
    }
