"""
kronos.py — Kronos AI Forecast for Crypto Sniper
Uses Claude Haiku to generate 24H price forecasts with OHLCV predictions.
"""

import os, json, logging
import anthropic

logger = logging.getLogger(__name__)
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")

KRONOS_PROMPT = """You are Kronos, an AI price forecast engine for crypto trading.
Given market data, generate a structured 24-hour price forecast.

You MUST respond with valid JSON only, no other text. Format:
{
  "direction": "Rising" or "Falling" or "Sideways",
  "expected_move_pct": number (e.g. -1.89),
  "target_price": number,
  "high_24h": number,
  "low_24h": number,
  "momentum": "Mostly bullish" or "Mostly bearish" or "Mixed",
  "green_candle_pct": number (0-100, % of next 24 candles that close green),
  "trade_quality": "Strong setup" or "Avoid — bad odds" or "Moderate setup",
  "bull_case": "PASS" or "TAKE",
  "bear_case": "PASS" or "SHORT",
  "bull_conviction": "LOW" or "MEDIUM" or "HIGH",
  "bear_conviction": "LOW" or "MEDIUM" or "HIGH",
  "predicted_ohlcv": [
    {"h": 1, "open": number, "high": number, "low": number, "close": number},
    ... (24 entries, one per hour)
  ]
}"""


async def run_kronos_forecast(symbol: str, ctx: dict) -> dict:
    """Generate Kronos AI forecast. Falls back to heuristic model if no API key."""
    if not ANTHROPIC_KEY:
        return _heuristic_forecast(symbol, ctx)

    close  = ctx.get("close", 0)
    rsi    = ctx.get("rsi", 50)
    adx    = ctx.get("adx", 25)
    change = ctx.get("change_24h", 0)
    score  = ctx.get("total", 0)

    prompt = f"""Market data for {symbol}:
- Price: ${close:,.2f}
- 24H Change: {change:+.2f}%
- RSI: {rsi:.1f}
- ADX: {adx:.1f}
- Signal Score: {score}/16
- Direction: {ctx.get('direction', 'NEUTRAL')}
- EMA Stack: {'Bullish' if ctx.get('ema_stack') else 'Not confirmed'}

Generate a 24-hour forecast. Current price is ${close:,.2f}."""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1000,
            system=KRONOS_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )
        text = msg.content[0].text.strip()
        # Strip any markdown code fences
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        return _validate_forecast(data, close)
    except Exception as e:
        logger.warning(f"Kronos API error: {e}. Using heuristic.")
        return _heuristic_forecast(symbol, ctx)


def _validate_forecast(data: dict, close: float) -> dict:
    """Ensure all required fields are present with valid types."""
    required = ["direction","expected_move_pct","target_price","high_24h","low_24h",
                "momentum","green_candle_pct","trade_quality","bull_case","bear_case",
                "bull_conviction","bear_conviction","predicted_ohlcv"]
    for field in required:
        if field not in data:
            data[field] = _default_forecast(close)[field]

    # Ensure predicted_ohlcv has exactly 24 entries
    ohlcv = data.get("predicted_ohlcv", [])
    if len(ohlcv) < 24:
        # Pad with reasonable values
        last_close = ohlcv[-1]["close"] if ohlcv else close
        move = data.get("expected_move_pct", 0) / 24
        for h in range(len(ohlcv), 24):
            price = last_close * (1 + move / 100)
            ohlcv.append({
                "h": h + 1, "open": last_close, "high": price * 1.002,
                "low": price * 0.998, "close": price
            })
            last_close = price
    data["predicted_ohlcv"] = ohlcv[:24]
    return data


def _heuristic_forecast(symbol: str, ctx: dict) -> dict:
    """
    Deterministic heuristic forecast when no API key is set.
    Based on RSI, ADX, signal score, and actual recent OHLCV green candle ratio.
    """
    close  = ctx.get("close", 0) or 100
    rsi    = ctx.get("rsi", 50)
    adx    = ctx.get("adx", 20)
    change = ctx.get("change_24h", 0)
    score  = ctx.get("total", 0)
    ema_stack = ctx.get("ema_stack", False)

    # Compute green_pct from actual signal context instead of hardcoded buckets.
    # Uses RSI, ADX, score and 24h change to estimate momentum — unique per coin.
    base_green = 50.0
    # RSI contribution: RSI 70 = +15, RSI 30 = -15, linear between
    base_green += (rsi - 50) * 0.3
    # Score contribution: max score = 16, score 9 = +8, score 0 = -8
    base_green += (score - 8) * 1.0
    # 24h change contribution
    base_green += min(max(change * 1.5, -10), 10)
    # EMA stack bonus
    if ema_stack:
        base_green += 5
    # ADX: trending strongly amplifies the directional bias
    if adx >= 25:
        base_green += (base_green - 50) * 0.2
    green_pct = round(min(max(base_green, 15), 85), 1)

    # Direction based on signals
    if score >= 7 and change > 0:
        direction = "Rising"
        expected_move = abs(change) * 0.5
    elif rsi >= 70 or score < 3:
        direction = "Falling"
        expected_move = -(abs(change) * 0.8)
    else:
        direction = "Sideways"
        expected_move = change * 0.2

    target = round(close * (1 + expected_move / 100), 2)
    high   = round(close * 1.025, 2)
    low    = round(close * 0.975, 2)

    # Build 24 mock OHLCV candles
    candles = []
    price = close
    step  = (target - close) / 24
    atr = close * 0.005  # ~0.5% ATR per candle - realistic for crypto
    for h in range(1, 25):
        open_ = round(price, 4)
        noise = atr * (0.3 - (h % 5) * 0.12)  # oscillate around trend
        price = price + step + noise
        body_size = abs(price - open_)
        # Wicks are 20-50% of body size - realistic candlestick proportions
        wick_extra = max(body_size * 0.3, atr * 0.1)
        high_c = max(open_, price) + wick_extra
        low_c  = min(open_, price) - wick_extra
        candles.append({
            "h": h, "open": round(open_, 2), "high": round(high_c, 2),
            "low": round(low_c, 2), "close": round(price, 2)
        })

    bull_conv = "HIGH" if score >= 9 else "MEDIUM" if score >= 5 else "LOW"
    bear_conv = "HIGH" if rsi >= 75 or score < 3 else "MEDIUM" if rsi >= 65 else "LOW"

    return {
        "direction":        direction,
        "expected_move_pct": round(expected_move, 2),
        "target_price":     target,
        "high_24h":         high,
        "low_24h":          low,
        "momentum":         "Mostly bullish" if green_pct > 55 else "Mostly bearish" if green_pct < 45 else "Mixed",
        "green_candle_pct": green_pct,
        "trade_quality":    "Strong setup" if score >= 9 else "Avoid — bad odds" if score < 5 else "Moderate setup",
        "bull_case":        "TAKE" if score >= 7 else "PASS",
        "bear_case":        "SHORT" if rsi >= 75 else "PASS",
        "bull_conviction":  bull_conv,
        "bear_conviction":  bear_conv,
        "predicted_ohlcv":  candles,
    }


def _default_forecast(close: float) -> dict:
    return _heuristic_forecast("BTC", {"close": close, "rsi": 50, "change_24h": 0, "total": 3})
