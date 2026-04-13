"""
Crypto Sniper App
=================
Combines a multi-factor scoring engine (V, P, R, T) with the Kronos
time-series foundation model for forward OHLCV prediction.

Usage
-----
    # Live scan (default: top USDT pairs on Binance)
    python app.py

    # Single symbol with Kronos forecast
    python app.py --symbol BTCUSDT --interval 1h --kronos

    # Scan with custom watchlist + Kronos
    python app.py --watchlist BTC ETH SOL BNB --interval 15m --kronos

    # Top-N ranked output only
    python app.py --top 10

Requirements
------------
    pip install ccxt pandas numpy pandas-ta rich torch huggingface_hub
    pip install git+https://github.com/shiyu-coder/Kronos.git   # or local clone
"""

import argparse
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ──────────────────────────────────────────────────────────────────────────────
# Optional imports — graceful degradation when not installed
# ──────────────────────────────────────────────────────────────────────────────
try:
    import ccxt
    HAS_CCXT = True
except ImportError:
    HAS_CCXT = False
    print("[WARN] ccxt not installed — live data unavailable. Use --csv to load local data.")

try:
    import pandas_ta as ta
    HAS_TA = True
except ImportError:
    HAS_TA = False
    print("[WARN] pandas_ta not installed — falling back to manual indicator calculations.")

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    console = None

try:
    import torch
    from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore
    HAS_KRONOS = True
except ImportError:
    HAS_KRONOS = False


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — INDICATOR ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute all indicators required by the scoring system.

    Expected input columns: open, high, low, close, volume
    Added columns: ema20, ema50, atr14, adx14, rsi14
    """
    df = df.copy()
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)

    if HAS_TA:
        # EMA
        df["ema20"] = ta.ema(df["close"], length=20)
        df["ema50"] = ta.ema(df["close"], length=50)

        # ATR (14-period)
        atr = ta.atr(df["high"], df["low"], df["close"], length=14)
        df["atr14"] = atr

        # ADX (14-period)
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
        df["adx14"] = adx_df[f"ADX_14"] if adx_df is not None else np.nan

        # RSI (14-period) — used for relative volume baseline context
        df["rsi14"] = ta.rsi(df["close"], length=14)

        # Rolling volume (20-period mean)
        df["vol_ma20"] = ta.sma(df["volume"], length=20)

    else:
        # ── Manual EMA ──────────────────────────────────────────────────────
        df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
        df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()

        # ── Manual ATR ──────────────────────────────────────────────────────
        hl = df["high"] - df["low"]
        hc = (df["high"] - df["close"].shift(1)).abs()
        lc = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        df["atr14"] = tr.ewm(span=14, adjust=False).mean()

        # ── Manual ADX ──────────────────────────────────────────────────────
        up_move = df["high"].diff()
        down_move = -df["low"].diff()
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
        plus_dm_s = pd.Series(plus_dm).ewm(span=14, adjust=False).mean()
        minus_dm_s = pd.Series(minus_dm).ewm(span=14, adjust=False).mean()
        plus_di = 100 * plus_dm_s / df["atr14"]
        minus_di = 100 * minus_dm_s / df["atr14"]
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
        df["adx14"] = dx.ewm(span=14, adjust=False).mean()

        # ── Manual RSI ──────────────────────────────────────────────────────
        delta = df["close"].diff()
        gain = delta.clip(lower=0).ewm(span=14, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(span=14, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi14"] = 100 - (100 / (1 + rs))

        # ── Rolling volume ────────────────────────────────────────────────
        df["vol_ma20"] = df["volume"].rolling(20).mean()

    return df


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — SCORING ENGINE  (V, P, R, T)
# ══════════════════════════════════════════════════════════════════════════════

def score_V(rv: float) -> int:
    """
    Volume Score (V)
    RV = relative volume = current_volume / rolling_vol_ma20
    """
    if rv < 2:
        return 0
    elif rv < 4:
        return 2
    elif rv < 8:
        return 3
    else:
        return 5


def score_P(close_now: float, close_prev: float, atr_move: float) -> int:
    """
    Price Momentum Score (P)
    atr_move = (close_now - close_prev) / atr14
    """
    if close_now <= close_prev:
        return 0
    if atr_move < 1.5:
        return 0
    elif atr_move < 2.5:
        return 1
    elif atr_move < 4.0:
        return 2
    else:
        return 3


def score_R(range_pos: float) -> int:
    """
    Range Position Score (R)
    range_pos = (close - low) / (high - low)   [0..1]
    """
    if range_pos < 0.70:
        return 0
    elif range_pos < 0.85:
        return 1
    else:
        return 2


def score_T(close_now: float, ema20: float, ema50: float, adx14: float) -> int:
    """
    Trend Alignment Score (T)
    +1 if close > EMA20
    +1 if EMA20 > EMA50
    +1 if ADX14 >= 20
    """
    t = 0
    if close_now > ema20:
        t += 1
    if ema20 > ema50:
        t += 1
    if adx14 >= 20:
        t += 1
    return t


def compute_scores(df: pd.DataFrame) -> dict:
    """
    Compute all four scores for the last completed candle.
    Returns a dict with individual scores and the composite VPRT score.
    """
    if len(df) < 2:
        raise ValueError("Need at least 2 candles to compute scores.")

    row = df.iloc[-1]
    prev = df.iloc[-2]

    # ── Derived quantities ────────────────────────────────────────────────
    rv = row["volume"] / row["vol_ma20"] if row["vol_ma20"] > 0 else 0.0
    atr_move = (row["close"] - prev["close"]) / row["atr14"] if row["atr14"] > 0 else 0.0
    hl = row["high"] - row["low"]
    range_pos = (row["close"] - row["low"]) / hl if hl > 0 else 0.5

    v = score_V(rv)
    p = score_P(row["close"], prev["close"], atr_move)
    r = score_R(range_pos)
    t = score_T(row["close"], row["ema20"], row["ema50"], row["adx14"])
    composite = v + p + r + t

    return {
        "close": row["close"],
        "ema20": row["ema20"],
        "ema50": row["ema50"],
        "atr14": row["atr14"],
        "adx14": row["adx14"],
        "rsi14": row["rsi14"],
        "rv": round(rv, 2),
        "atr_move": round(atr_move, 2),
        "range_pos": round(range_pos, 3),
        "V": v,
        "P": p,
        "R": r,
        "T": t,
        "score": composite,
        "timestamp": row["timestamp"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — DATA FETCHER
# ══════════════════════════════════════════════════════════════════════════════

def fetch_ohlcv(
    symbol: str,
    interval: str = "1h",
    limit: int = 600,
    exchange_id: str = "binance",
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV data from a ccxt-compatible exchange.
    Returns a DataFrame with columns: timestamp, open, high, low, close, volume
    """
    if not HAS_CCXT:
        return None

    try:
        exchange_cls = getattr(ccxt, exchange_id)
        exchange = exchange_cls({"enableRateLimit": True})
        raw = exchange.fetch_ohlcv(symbol, timeframe=interval, limit=limit)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.dropna()
    except Exception as e:
        print(f"[ERROR] Failed to fetch {symbol}: {e}")
        return None


def load_csv(path: str) -> pd.DataFrame:
    """Load OHLCV data from a local CSV file."""
    df = pd.read_csv(path)
    # Normalise column names
    df.columns = [c.lower().strip() for c in df.columns]
    # Accept 'date', 'time', 'datetime', 'ts' as timestamp aliases
    for alias in ["date", "time", "datetime", "ts"]:
        if alias in df.columns and "timestamp" not in df.columns:
            df.rename(columns={alias: "timestamp"}, inplace=True)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"CSV missing columns: {missing}")
    return df.dropna(subset=["timestamp", "close"]).reset_index(drop=True)


def get_top_usdt_pairs(n: int = 30, exchange_id: str = "binance") -> list[str]:
    """Return the top-N USDT pairs by 24h quote volume."""
    if not HAS_CCXT:
        return []
    try:
        exchange_cls = getattr(ccxt, exchange_id)
        exchange = exchange_cls({"enableRateLimit": True})
        tickers = exchange.fetch_tickers()
        usdt = {
            k: v for k, v in tickers.items()
            if k.endswith("/USDT") and v.get("quoteVolume")
        }
        ranked = sorted(usdt.items(), key=lambda x: x[1]["quoteVolume"] or 0, reverse=True)
        return [s for s, _ in ranked[:n]]
    except Exception as e:
        print(f"[ERROR] Could not fetch ticker list: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — KRONOS INTEGRATION
# ══════════════════════════════════════════════════════════════════════════════

_kronos_predictor: Optional[object] = None  # singleton cache


def load_kronos(model_variant: str = "NeoQuasar/Kronos-small") -> Optional[object]:
    """
    Load the Kronos model + tokenizer from HuggingFace (cached after first call).
    """
    global _kronos_predictor
    if _kronos_predictor is not None:
        return _kronos_predictor

    if not HAS_KRONOS:
        print("[WARN] Kronos not available. Run: pip install git+https://github.com/shiyu-coder/Kronos.git")
        return None

    try:
        _print("Loading Kronos model from HuggingFace…")
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
        model = Kronos.from_pretrained(model_variant)
        _kronos_predictor = KronosPredictor(model, tokenizer, max_context=512)
        _print(f"Kronos loaded ({model_variant})", style="green")
        return _kronos_predictor
    except Exception as e:
        print(f"[ERROR] Kronos load failed: {e}")
        return None


def run_kronos_forecast(
    df: pd.DataFrame,
    pred_len: int = 24,
    lookback: int = 400,
    temperature: float = 1.0,
    top_p: float = 0.9,
    model_variant: str = "NeoQuasar/Kronos-small",
) -> Optional[pd.DataFrame]:
    """
    Run a Kronos forecast on the given OHLCV DataFrame.

    Parameters
    ----------
    df        : Full OHLCV dataframe (at least `lookback` rows)
    pred_len  : Number of candles to predict ahead
    lookback  : Number of historical candles to use as context (≤ 512)
    temperature : Sampling temperature
    top_p     : Nucleus sampling threshold

    Returns
    -------
    Forecast DataFrame with columns: open, high, low, close, volume
    indexed by predicted timestamps.
    """
    predictor = load_kronos(model_variant)
    if predictor is None:
        return None

    df = df.sort_values("timestamp").reset_index(drop=True)
    lookback = min(lookback, len(df), 512)

    context_df = df.tail(lookback).reset_index(drop=True)
    x_ts = context_df["timestamp"]

    # Generate future timestamps based on the inferred candle frequency
    last_ts = context_df["timestamp"].iloc[-1]
    freq = pd.infer_freq(context_df["timestamp"])
    if freq is None:
        # Estimate from the last two candles
        delta = context_df["timestamp"].iloc[-1] - context_df["timestamp"].iloc[-2]
        future_ts = pd.date_range(start=last_ts + delta, periods=pred_len, freq=delta)
    else:
        future_ts = pd.date_range(start=last_ts, periods=pred_len + 1, freq=freq)[1:]

    y_ts = pd.Series(future_ts)

    # Kronos expects: open, high, low, close, volume  (amount is optional)
    ohlcv_cols = [c for c in ["open", "high", "low", "close", "volume", "amount"] if c in context_df.columns]
    try:
        pred_df = predictor.predict(
            df=context_df[ohlcv_cols],
            x_timestamp=x_ts,
            y_timestamp=y_ts,
            pred_len=pred_len,
            T=temperature,
            top_p=top_p,
            sample_count=1,
        )
        return pred_df
    except Exception as e:
        print(f"[ERROR] Kronos prediction failed: {e}")
        return None


def summarise_forecast(pred_df: pd.DataFrame, current_close: float) -> dict:
    """Derive high-level forecast summary from Kronos output."""
    if pred_df is None or pred_df.empty:
        return {}

    forecast_close = pred_df["close"].values
    high_target = pred_df["high"].max()
    low_target = pred_df["low"].min()
    final_close = forecast_close[-1]
    pct_change = (final_close - current_close) / current_close * 100

    # Simple directional confidence: fraction of candles where close > open
    bullish_candles = (pred_df["close"] > pred_df["open"]).sum()
    bullish_pct = bullish_candles / len(pred_df) * 100

    return {
        "forecast_close": round(final_close, 6),
        "pct_change": round(pct_change, 2),
        "high_target": round(high_target, 6),
        "low_target": round(low_target, 6),
        "bullish_pct": round(bullish_pct, 1),
        "candles_ahead": len(pred_df),
    }


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — OUTPUT HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _print(msg: str, style: str = ""):
    if HAS_RICH:
        console.print(f"[{style}]{msg}[/{style}]" if style else msg)
    else:
        print(msg)


def _score_color(score: int) -> str:
    if score >= 10:
        return "bold magenta"
    elif score >= 7:
        return "bold green"
    elif score >= 4:
        return "yellow"
    else:
        return "dim"


def print_rich_table(results: list[dict]):
    if not HAS_RICH:
        _print_plain_table(results)
        return

    table = Table(
        title="🎯  Crypto Sniper — Signal Scanner",
        box=box.ROUNDED,
        show_lines=True,
        highlight=True,
    )

    cols = [
        ("Symbol", "cyan", "left"),
        ("Close", "white", "right"),
        ("RV", "white", "right"),
        ("ATR Move", "white", "right"),
        ("ADX", "white", "right"),
        ("RSI", "white", "right"),
        ("V", "blue", "center"),
        ("P", "blue", "center"),
        ("R", "blue", "center"),
        ("T", "blue", "center"),
        ("Score", "green", "center"),
    ]

    for name, style, justify in cols:
        table.add_column(name, style=style, justify=justify)

    for r in results:
        score_str = f"[{_score_color(r['score'])}]{r['score']}[/{_score_color(r['score'])}]"
        table.add_row(
            r["symbol"],
            f"{r['close']:.4g}",
            f"{r['rv']:.2f}x",
            f"{r['atr_move']:.2f}",
            f"{r['adx14']:.1f}",
            f"{r['rsi14']:.1f}",
            str(r["V"]),
            str(r["P"]),
            str(r["R"]),
            str(r["T"]),
            score_str,
        )

    console.print(table)


def print_kronos_panel(symbol: str, summary: dict):
    if not HAS_RICH or not summary:
        if summary:
            print(f"\n[Kronos Forecast — {symbol}]")
            print(f"  Forecast close  : {summary['forecast_close']}")
            print(f"  Expected change : {summary['pct_change']:+.2f}%")
            print(f"  High target     : {summary['high_target']}")
            print(f"  Low target      : {summary['low_target']}")
            print(f"  Bullish candles : {summary['bullish_pct']}%")
            print(f"  Candles ahead   : {summary['candles_ahead']}")
        return

    direction = "▲ BULLISH" if summary["pct_change"] > 0 else "▼ BEARISH"
    color = "green" if summary["pct_change"] > 0 else "red"

    content = (
        f"[bold]Direction:[/bold]  [{color}]{direction}[/{color}]\n"
        f"[bold]Forecast close:[/bold]  {summary['forecast_close']}\n"
        f"[bold]Expected change:[/bold]  [{color}]{summary['pct_change']:+.2f}%[/{color}]\n"
        f"[bold]High target:[/bold]  {summary['high_target']}\n"
        f"[bold]Low target:[/bold]  {summary['low_target']}\n"
        f"[bold]Bullish candles:[/bold]  {summary['bullish_pct']}%\n"
        f"[bold]Candles ahead:[/bold]  {summary['candles_ahead']}"
    )
    console.print(Panel(content, title=f"[bold cyan]Kronos Forecast — {symbol}[/bold cyan]", expand=False))


def _print_plain_table(results: list[dict]):
    header = f"{'Symbol':<12} {'Close':>10} {'RV':>6} {'ATRMv':>6} {'ADX':>6} {'RSI':>6}  V  P  R  T  Score"
    print("\n" + header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['symbol']:<12} {r['close']:>10.4g} {r['rv']:>6.2f} {r['atr_move']:>6.2f}"
            f" {r['adx14']:>6.1f} {r['rsi14']:>6.1f}"
            f"  {r['V']}  {r['P']}  {r['R']}  {r['T']}  {r['score']}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════

def analyse_symbol(
    symbol: str,
    interval: str = "1h",
    limit: int = 600,
    exchange: str = "binance",
    csv_path: Optional[str] = None,
) -> Optional[dict]:
    """
    Full pipeline for a single symbol:
    1. Fetch OHLCV data
    2. Compute indicators
    3. Compute V/P/R/T scores
    Returns a score dict or None on failure.
    """
    if csv_path:
        df = load_csv(csv_path)
    else:
        df = fetch_ohlcv(symbol, interval=interval, limit=limit, exchange_id=exchange)

    if df is None or len(df) < 60:
        return None

    df = compute_indicators(df)
    df = df.dropna(subset=["ema20", "ema50", "atr14", "adx14"]).reset_index(drop=True)

    if len(df) < 2:
        return None

    scores = compute_scores(df)
    scores["symbol"] = symbol
    scores["df"] = df          # carry the full df for Kronos use
    scores["interval"] = interval
    return scores


def run_scanner(
    symbols: list[str],
    interval: str = "1h",
    limit: int = 600,
    exchange: str = "binance",
    top_n: int = 0,
    use_kronos: bool = False,
    pred_len: int = 24,
    lookback: int = 400,
    min_score: int = 0,
    kronos_model: str = "NeoQuasar/Kronos-small",
) -> list[dict]:
    """
    Scan a list of symbols and return ranked results.
    """
    results = []

    for sym in symbols:
        _print(f"Analysing {sym}…", style="dim")
        res = analyse_symbol(sym, interval=interval, limit=limit, exchange=exchange)
        if res is None:
            continue
        results.append(res)

    # Sort by composite score descending
    results.sort(key=lambda x: x["score"], reverse=True)

    # Apply score filter
    results = [r for r in results if r["score"] >= min_score]

    if top_n > 0:
        results = results[:top_n]

    # Run Kronos on each qualifying result
    if use_kronos:
        if not HAS_KRONOS:
            _print("[WARN] Kronos not installed — skipping forecasts.", style="yellow")
        else:
            for r in results:
                _print(f"Running Kronos forecast for {r['symbol']}…", style="dim")
                forecast = run_kronos_forecast(
                    r["df"],
                    pred_len=pred_len,
                    lookback=lookback,
                    model_variant=kronos_model,
                )
                r["kronos_forecast"] = summarise_forecast(forecast, r["close"])
                r["kronos_raw"] = forecast

    # Strip df from output (not needed downstream)
    for r in results:
        r.pop("df", None)

    return results


# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    parser = argparse.ArgumentParser(
        description="Crypto Sniper — V/P/R/T scoring + Kronos forecast",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Data source
    src = parser.add_mutually_exclusive_group()
    src.add_argument("--symbol", type=str, help="Single symbol to analyse (e.g. BTCUSDT or BTC/USDT)")
    src.add_argument("--watchlist", nargs="+", help="Space-separated list of base assets, e.g. BTC ETH SOL")
    src.add_argument("--csv", type=str, help="Path to local CSV file (single symbol analysis)")

    parser.add_argument("--interval", default="1h", help="Candle interval (default: 1h)")
    parser.add_argument("--limit", type=int, default=600, help="Max candles to fetch (default: 600)")
    parser.add_argument("--exchange", default="binance", help="ccxt exchange ID (default: binance)")
    parser.add_argument("--top", type=int, default=0, help="Show only top-N results")
    parser.add_argument("--min-score", type=int, default=0, help="Minimum composite score filter")
    parser.add_argument("--scan-top", type=int, default=30, help="Auto-scan top-N USDT pairs (default: 30)")

    # Kronos options
    parser.add_argument("--kronos", action="store_true", help="Enable Kronos AI forecast")
    parser.add_argument("--pred-len", type=int, default=24, help="Kronos: candles to predict (default: 24)")
    parser.add_argument("--lookback", type=int, default=400, help="Kronos: context candles (default: 400)")
    parser.add_argument("--kronos-model", default="NeoQuasar/Kronos-small",
                        help="Kronos HuggingFace model variant (default: NeoQuasar/Kronos-small)")

    return parser.parse_args()


def main():
    args = parse_args()

    _print(Panel.renderable if HAS_RICH else "")
    if HAS_RICH:
        console.rule("[bold cyan]Crypto Sniper[/bold cyan]")
        console.print(f"[dim]{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}[/dim]\n")
    else:
        print("=" * 60)
        print("Crypto Sniper")
        print(datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
        print("=" * 60)

    # ── Build symbol list ─────────────────────────────────────────────────
    if args.csv:
        # Single CSV analysis
        _print(f"Loading CSV: {args.csv}")
        res = analyse_symbol("CSV", csv_path=args.csv)
        if res is None:
            _print("[ERROR] Could not analyse CSV data.", style="red")
            sys.exit(1)
        results = [res]
        results[0]["symbol"] = Path(args.csv).stem

    elif args.symbol:
        sym = args.symbol if "/" in args.symbol else args.symbol.upper().replace("USDT", "") + "/USDT"
        results = run_scanner(
            [sym], interval=args.interval, limit=args.limit,
            exchange=args.exchange, use_kronos=args.kronos,
            pred_len=args.pred_len, lookback=args.lookback,
            kronos_model=args.kronos_model,
        )

    elif args.watchlist:
        symbols = [s.upper() + "/USDT" for s in args.watchlist]
        results = run_scanner(
            symbols, interval=args.interval, limit=args.limit,
            exchange=args.exchange, top_n=args.top,
            use_kronos=args.kronos, pred_len=args.pred_len,
            lookback=args.lookback, min_score=args.min_score,
            kronos_model=args.kronos_model,
        )

    else:
        # Default: auto-scan top USDT pairs
        _print(f"Fetching top-{args.scan_top} USDT pairs by volume…")
        symbols = get_top_usdt_pairs(n=args.scan_top, exchange_id=args.exchange)
        if not symbols:
            _print("[ERROR] No symbols fetched. Install ccxt or provide --watchlist.", style="red")
            sys.exit(1)
        results = run_scanner(
            symbols, interval=args.interval, limit=args.limit,
            exchange=args.exchange, top_n=args.top,
            use_kronos=args.kronos, pred_len=args.pred_len,
            lookback=args.lookback, min_score=args.min_score,
            kronos_model=args.kronos_model,
        )

    # ── Display results ───────────────────────────────────────────────────
    if not results:
        _print("No results matched the criteria.", style="yellow")
        sys.exit(0)

    print_rich_table(results)

    # Kronos panels (if enabled)
    if args.kronos:
        for r in results:
            if r.get("kronos_forecast"):
                print_kronos_panel(r["symbol"], r["kronos_forecast"])

    # Summary
    if HAS_RICH:
        console.print(f"\n[dim]Scanned {len(results)} symbols  ·  "
                      f"Interval: {args.interval}  ·  Exchange: {args.exchange}[/dim]")


if __name__ == "__main__":
    main()
