"""
kronos_real.py — Real Kronos-mini time-series forecast for Crypto Sniper.

Uses the actual open-source Kronos foundation model (NeoQuasar/Kronos-mini,
4.1M params, MIT licensed, arXiv:2508.02739, accepted AAAI 2026) rather than
an LLM asked to invent a forecast from five scalar numbers. Weights are
pulled from the Hugging Face Hub on first use and the predictor is cached
in memory for the life of the process.

IMPORTANT FIX vs. the abandoned backend/api.py prototype this was ported
from: Kronos-mini must be paired with Kronos-Tokenizer-2k (2048 context) —
NOT Kronos-Tokenizer-base (512 context), which is for Kronos-small/base
instead. The prototype used the wrong tokenizer for this model; using a
tokenizer trained for a different model would produce meaningless output.
Fixed here.

Falls back to returning None on ANY failure (missing deps, model load
failure, insufficient history, inference error) — kronos.py is responsible
for falling back to the LLM/heuristic path when this returns None. This
module never raises out to its caller.
"""

import logging

logger = logging.getLogger(__name__)

_predictor = None
_load_attempted = False

# Minimum bars of real history required before attempting a real-model
# forecast. Below this, the model's own forecast quality degrades sharply
# and it's more honest to fall back than to return a low-confidence guess
# dressed up as a real model output.
MIN_BARS_REQUIRED = 64

# Passed as max_context to KronosPredictor — a sliding-window cap on how
# much history informs each autoregressive step. The Kronos-Tokenizer-2k
# tokenizer supports up to 2048, but 512 keeps CPU inference latency lower;
# revisit once real latency is measured on the actual Render instance.
MAX_CONTEXT = 512


def _load_predictor():
    """Lazily load and cache the Kronos-mini model + tokenizer, once per
    process. Returns None (and logs why) if torch/model aren't importable
    or loading fails for any reason — this is the single point where the
    real-model path becomes unavailable and callers fall back."""
    global _predictor, _load_attempted
    if _load_attempted:
        return _predictor
    _load_attempted = True
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-2k")
        model     = Kronos.from_pretrained("NeoQuasar/Kronos-mini")
        _predictor = KronosPredictor(model, tokenizer, max_context=MAX_CONTEXT)
        logger.info("Kronos-mini model loaded — real forecast path active")
    except Exception as e:
        logger.warning(f"Kronos-mini model unavailable, will use LLM/heuristic fallback: {e}")
        _predictor = None
    return _predictor


def get_real_forecast(symbol: str, ohlcv_bars: list, pred_len: int = 24) -> dict | None:
    """
    Generate a forecast using the real Kronos-mini model against real
    historical OHLCV. Returns None (caller falls back to LLM/heuristic) if
    the model isn't available, there isn't enough history, or inference
    fails for any reason — never raises.

    ohlcv_bars: [[timestamp, open, high, low, close, volume], ...] oldest
    first — exactly what data.py's get_ohlcv() returns.
    """
    predictor = _load_predictor()
    if predictor is None:
        return None
    if not ohlcv_bars or len(ohlcv_bars) < MIN_BARS_REQUIRED:
        logger.info(
            f"Kronos-mini: insufficient history for {symbol} "
            f"({len(ohlcv_bars) if ohlcv_bars else 0} bars, need {MIN_BARS_REQUIRED}+) — falling back"
        )
        return None

    try:
        import pandas as pd

        lookback = min(len(ohlcv_bars), MAX_CONTEXT)
        recent = ohlcv_bars[-lookback:]

        raw_ts = [row[0] for row in recent]
        # Normalise to seconds if these look like millisecond timestamps
        if raw_ts[0] > 10**12:
            raw_ts = [t / 1000 for t in raw_ts]

        df = pd.DataFrame({
            "open":   [row[1] for row in recent],
            "high":   [row[2] for row in recent],
            "low":    [row[3] for row in recent],
            "close":  [row[4] for row in recent],
            "volume": [row[5] for row in recent],
        })
        x_timestamp = pd.to_datetime(raw_ts, unit="s")

        # Infer the actual bar interval from the data itself to build
        # correctly-spaced future timestamps, rather than assuming a fixed
        # interval that might not match what was actually requested.
        step_secs = raw_ts[-1] - raw_ts[-2] if len(raw_ts) >= 2 else 3600
        last_ts = raw_ts[-1]
        y_timestamp = pd.to_datetime(
            [last_ts + step_secs * (i + 1) for i in range(pred_len)], unit="s"
        )

        pred_df = predictor.predict(
            df=df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=pred_len,
            T=1.0,
            top_k=0,
            top_p=0.9,
            sample_count=1,   # single sample for CPU latency; raise once
                              # real-world timing on Render is measured
            verbose=False,
        )

        return _to_narrative_forecast(df, pred_df)

    except Exception as e:
        logger.warning(f"Kronos-mini inference failed for {symbol}: {e}")
        return None


def _to_narrative_forecast(hist_df, pred_df) -> dict:
    """
    Convert the model's raw predicted OHLCV into the same narrative JSON
    shape the LLM/heuristic paths produce. Critically, every field here is
    derived from the SAME predicted price path — direction, momentum, and
    green_candle_pct can't disagree with each other the way they could
    when computed by independent formulas (the exact bug class that
    prompted this whole investigation).
    """
    last_close  = float(hist_df["close"].iloc[-1])
    final_close = float(pred_df["close"].iloc[-1])
    expected_move_pct = (final_close - last_close) / last_close * 100 if last_close else 0.0

    # Small deadzone around zero avoids label flicker on negligible moves
    if expected_move_pct > 0.3:
        direction = "Rising"
    elif expected_move_pct < -0.3:
        direction = "Falling"
    else:
        direction = "Sideways"

    green_count = int((pred_df["close"] > pred_df["open"]).sum())
    green_candle_pct = round(green_count / len(pred_df) * 100, 1) if len(pred_df) else 50.0

    momentum = (
        "Mostly bullish" if green_candle_pct > 55
        else "Mostly bearish" if green_candle_pct < 45
        else "Mixed"
    )

    is_bullish = direction == "Rising"
    is_bearish = direction == "Falling"
    strong_move = abs(expected_move_pct) >= 1.5

    trade_quality = (
        "Strong setup" if (strong_move and ((is_bullish and green_candle_pct >= 55) or (is_bearish and green_candle_pct <= 45)))
        else "Avoid — bad odds" if abs(expected_move_pct) < 0.3
        else "Moderate setup"
    )

    bull_case = "TAKE" if (is_bullish and strong_move) else "PASS"
    bear_case = "SHORT" if (is_bearish and strong_move) else "PASS"

    bull_conviction = (
        "HIGH" if (is_bullish and green_candle_pct >= 65)
        else "MEDIUM" if (is_bullish and green_candle_pct >= 50)
        else "LOW"
    )
    bear_conviction = (
        "HIGH" if (is_bearish and green_candle_pct <= 35)
        else "MEDIUM" if (is_bearish and green_candle_pct <= 50)
        else "LOW"
    )

    predicted_ohlcv = [
        {
            "h": i + 1,
            "open":  round(float(row.open), 6),
            "high":  round(float(row.high), 6),
            "low":   round(float(row.low), 6),
            "close": round(float(row.close), 6),
        }
        for i, row in enumerate(pred_df.itertuples())
    ]

    return {
        "direction": direction,
        "expected_move_pct": round(expected_move_pct, 2),
        "target_price": round(final_close, 6),
        "high_24h": round(float(pred_df["high"].max()), 6),
        "low_24h": round(float(pred_df["low"].min()), 6),
        "momentum": momentum,
        "green_candle_pct": green_candle_pct,
        "trade_quality": trade_quality,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "bull_conviction": bull_conviction,
        "bear_conviction": bear_conviction,
        "predicted_ohlcv": predicted_ohlcv,
        # Lets the frontend/PDF optionally badge "real model" vs LLM/heuristic
        "model_source": "kronos-mini",
    }
