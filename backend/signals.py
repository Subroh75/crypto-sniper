"""
signals.py — V/P/R/T/S scoring engine for Crypto Sniper

Signal Components:
  V — Volume     (0–5 pts)  : relative volume vs 20-bar avg
  P — Momentum   (0–3 pts)  : ATR-normalised price move
  R — Range Pos  (0–2 pts)  : close position in bar range
  T — Trend      (0–3 pts)  : EMA stack + ADX
  S — Social     (0–3 pts)  : LunarCrush score (free placeholder)

Total: 0–16 pts
  STRONG BUY : >= 9
  MODERATE   : >= 5
  NO SIGNAL  : < 5
"""

from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class SignalResult:
    # Scores
    v_score:   int = 0
    p_score:   int = 0
    r_score:   int = 0
    t_score:   int = 0
    s_score:   int = 0
    total:     int = 0
    max_score: int = 16

    # Raw values
    rel_volume: float = 0.0
    atr_move_sigma: float = 0.0
    range_pos: float = 0.0
    adx: float = 0.0
    rsi: float = 50.0
    ema_stack: bool = False
    social_delta: float = 0.0

    # Verdict
    signal: str = "NO SIGNAL"         # STRONG BUY / MODERATE / NO SIGNAL
    direction: str = "NEUTRAL"        # LONG / SHORT / NEUTRAL

    # Market structure
    close:    float = 0.0
    ema20:    float = 0.0
    ema50:    float = 0.0
    ema200:   float = 0.0
    vwap:     float = 0.0
    bb_upper: float = 0.0
    bb_lower: float = 0.0
    atr:      float = 0.0

    # Trade setup (auto-calculated)
    entry:     Optional[float] = None
    stop:      Optional[float] = None
    target:    Optional[float] = None
    rr_ratio:  Optional[float] = None

    # Conviction
    bull_signals: list = field(default_factory=list)
    bear_signals: list = field(default_factory=list)

    @property
    def pct_score(self) -> float:
        return (self.total / self.max_score) * 100

    @property
    def signal_label(self) -> str:
        if self.total >= 9:
            return "STRONG BUY"
        elif self.total >= 5:
            return "MODERATE"
        else:
            return "NO SIGNAL"

    @property
    def bull_conviction(self) -> int:
        """0-100 percentage of signals bullish."""
        total_sigs = len(self.bull_signals) + len(self.bear_signals)
        if total_sigs == 0:
            return 50
        return int((len(self.bull_signals) / total_sigs) * 100)

    @property
    def bear_conviction(self) -> int:
        return 100 - self.bull_conviction


def calculate_signals(
    ohlcv: list[list],
    quote: dict,
    indicators: dict,
    social_delta: float = 0.0,  # % change in social score (LunarCrush)
) -> SignalResult:
    """
    Main signal calculation entry point.

    Args:
        ohlcv:        [[ts, o, h, l, c], ...] newest last
        quote:        {price, change_24h, volume_24h, high_24h, low_24h, ...}
        indicators:   {rsi, adx, atr, ema20, ema50, ema200, bb_upper, bb_lower, macd, macd_hist}
        social_delta: % change in social engagement score over 6H

    Returns:
        SignalResult with all fields populated
    """
    result = SignalResult()

    if not ohlcv or len(ohlcv) < 21:
        result.signal = "NO SIGNAL"
        return result

    # ── Extract prices ─────────────────────────────────────────────────────
    closes  = [bar[4] for bar in ohlcv]
    highs   = [bar[2] for bar in ohlcv]
    lows    = [bar[3] for bar in ohlcv]
    volumes = []  # CoinGecko OHLC doesn't include volume; use quote vol

    close  = closes[-1]
    high   = highs[-1]
    low    = lows[-1]
    open_  = ohlcv[-1][1]

    # ── Indicators (prefer Twelve Data, fallback to manual calc) ───────────
    rsi       = indicators.get("rsi") or _calc_rsi(closes, 14)
    adx       = indicators.get("adx") or 25.0
    atr       = indicators.get("atr") or _calc_atr(highs, lows, closes, 14)
    ema20     = indicators.get("ema20") or _calc_ema(closes, 20)
    ema50     = indicators.get("ema50") or _calc_ema(closes, 50)
    ema200    = indicators.get("ema200") or _calc_ema(closes, 200)
    bb_upper  = indicators.get("bb_upper") or (ema20 * 1.02 if ema20 else close * 1.02)
    bb_lower  = indicators.get("bb_lower") or (ema20 * 0.98 if ema20 else close * 0.98)
    macd_hist = indicators.get("macd_hist") or 0

    # ── VWAP ───────────────────────────────────────────────────────────────
    vwap = _calc_vwap_approx(ohlcv[-24:])

    # ── Relative Volume ────────────────────────────────────────────────────
    # Use actual candle volumes when available (ohlcv col 5); fall back to
    # price-change proxy only when volume data is absent.
    volumes = [bar[5] for bar in ohlcv if len(bar) > 5]
    if volumes and len(volumes) >= 20:
        avg_vol = sum(volumes[-21:-1]) / 20
        cur_vol = volumes[-1]
        rel_vol = round(cur_vol / avg_vol, 2) if avg_vol > 0 else 1.0
        rel_vol = max(0.5, min(rel_vol, 15.0))
    else:
        price_chg_abs = abs(quote.get("change_24h", 0))
        rel_vol = 1.0 + (price_chg_abs / 10)
        rel_vol = max(0.5, min(rel_vol, 8.0))

    chg = quote.get("change_24h", 0)

    # ── ATR move ───────────────────────────────────────────────────────────
    if atr > 0:
        price_move     = close - open_
        atr_move_sigma = price_move / atr
    else:
        atr_move_sigma = 0.0

    # ── Range position ─────────────────────────────────────────────────────
    bar_range = high - low
    range_pos = (close - low) / bar_range if bar_range > 0 else 0.5

    # ══════════════════════════════════════════════════════════════════════
    # GATE LOGIC  — identical to telegram_bot/signals.py
    # ══════════════════════════════════════════════════════════════════════

    # ── V gate: flat — any rel_vol >= 1.2x is confirmed ────────────────
    v_confirmed = rel_vol >= 1.2

    # ── T gate: close > EMA20 > EMA50 > EMA200 (all three MAs) ─────────
    ema_stack   = False
    t_confirmed = False
    if ema20 and ema50 and ema200 and close:
        t_confirmed = close > ema20 > ema50 > ema200
        ema_stack   = t_confirmed

    # ── ADX gate: >= 25 ────────────────────────────────────────────────
    adx_confirmed = adx >= 25

    # ── P confirmation: positive change AND positive ATR move ──────────
    p_confirmed = chg > 0 and atr_move_sigma > 0

    # ── R confirmation: close in upper 50% of bar range ───────────────
    r_confirmed = range_pos >= 0.5

    # ── Signal tier ────────────────────────────────────────────────────
    buy_gates_met = v_confirmed and t_confirmed and adx_confirmed

    if buy_gates_met and p_confirmed and r_confirmed:
        signal = "STRONG BUY"
    elif buy_gates_met:
        signal = "BUY"
    else:
        signal = "NO SIGNAL"

    # ── Scores (V max 3, P max 2, R max 1, T max 3 = 9 total for STRONG BUY)
    # S score REMOVED — pure VPRT only
    v_score = 3 if rel_vol >= 2.0 else (2 if rel_vol >= 1.5 else (1 if v_confirmed else 0))
    p_score = 2 if p_confirmed and chg >= 3 else (1 if p_confirmed else 0)
    r_score = 1 if r_confirmed else 0
    t_score = 3 if t_confirmed and adx_confirmed else (2 if t_confirmed else (1 if adx_confirmed else 0))
    s_score = 0  # removed
    total   = v_score + p_score + r_score + t_score

    # ── Direction ──────────────────────────────────────────────────────
    direction = "NEUTRAL"
    if signal in ("BUY", "STRONG BUY") and chg > 0:
        direction = "LONG"
    elif rsi >= 75 or (chg < -3 and ema20 and close < ema20):
        direction = "SHORT"

    # ── Trade Setup ────────────────────────────────────────────────────
    entry = stop = target = rr = None
    if signal in ("BUY", "STRONG BUY") and direction == "LONG" and atr:
        entry  = close
        stop   = round(close - (1.5 * atr), 2)
        target = round(close + (2.5 * atr), 2)
        risk   = entry - stop
        reward = target - entry
        rr     = round(reward / risk, 2) if risk > 0 else None

    # ── Bull / Bear Signal Lists ────────────────────────────────────────
    bull_signals = []
    bear_signals = []

    if ema_stack:                  bull_signals.append("EMA20 > EMA50 > EMA200 — full bullish stack")
    if ema50 and close > ema50:    bull_signals.append("Price above EMA50 — medium trend bullish")
    if ema200 and close > ema200:  bull_signals.append("Price above EMA200 — macro trend intact")
    if chg > 2:                    bull_signals.append(f"24H change +{chg:.1f}% — momentum")
    if macd_hist > 0:              bull_signals.append("MACD histogram positive")
    if adx_confirmed and chg > 0:  bull_signals.append(f"ADX {adx:.0f} — trend has strength")
    if social_delta > 5:           bull_signals.append(f"Social +{social_delta:.0f}% — retail accumulating")
    if rel_vol >= 2:               bull_signals.append(f"Volume {rel_vol:.1f}x above average")
    if rsi <= 30:                  bull_signals.append(f"RSI {rsi:.0f} — oversold, bounce potential")

    if rsi >= 70:                  bear_signals.append(f"RSI {rsi:.0f} — overbought, fade risk")
    if ema200 and close < ema200:  bear_signals.append("Price below EMA200 — macro trend bearish")
    if ema50 and close < ema50:    bear_signals.append("Price below EMA50 — medium trend bearish")
    if adx_confirmed and chg < 0:  bear_signals.append(f"ADX {adx:.0f} — bearish trend has strength")
    if chg < -3:                   bear_signals.append(f"24H change {chg:.1f}% — selling pressure")
    if macd_hist < 0:              bear_signals.append("MACD histogram negative — momentum fading")
    if rel_vol >= 2 and chg < 0:   bear_signals.append(f"Volume {rel_vol:.1f}x — heavy distribution")

    # ── Populate result ─────────────────────────────────────────────────
    result.v_score   = v_score
    result.p_score   = p_score
    result.r_score   = r_score
    result.t_score   = t_score
    result.s_score   = 0
    result.total     = total
    result.signal    = signal
    result.direction = direction

    result.rel_volume     = round(rel_vol, 2)
    result.atr_move_sigma = round(atr_move_sigma, 3)
    result.range_pos      = round(range_pos * 100, 1)
    result.adx            = round(adx, 1)
    result.rsi            = round(rsi, 1)
    result.ema_stack      = ema_stack
    result.social_delta   = social_delta

    result.close    = round(close, 2)
    result.ema20    = round(ema20, 2) if ema20 else 0
    result.ema50    = round(ema50, 2) if ema50 else 0
    result.ema200   = round(ema200, 2) if ema200 else 0
    result.vwap     = round(vwap, 2) if vwap else 0
    result.bb_upper = round(bb_upper, 2) if bb_upper else 0
    result.bb_lower = round(bb_lower, 2) if bb_lower else 0
    result.atr      = round(atr, 2) if atr else 0

    result.entry    = entry
    result.stop     = stop
    result.target   = target
    result.rr_ratio = rr

    result.bull_signals = bull_signals
    result.bear_signals = bear_signals

    return result


# ════════════════════════════════════════════════════════════════════════════
# MANUAL INDICATOR CALCULATIONS (fallback when no Twelve Data key)
# ════════════════════════════════════════════════════════════════════════════

def _calc_ema(prices: list[float], period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return ema

def _calc_rsi(closes: list[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(d, 0) for d in deltas[-period:]]
    losses = [abs(min(d, 0)) for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def _calc_atr(highs, lows, closes, period=14) -> float:
    if len(closes) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period

def _calc_vwap_approx(ohlcv: list[list]) -> float:
    """Approximate VWAP using typical price average."""
    if not ohlcv:
        return 0.0
    typical_prices = [(bar[2] + bar[3] + bar[4]) / 3 for bar in ohlcv]
    return sum(typical_prices) / len(typical_prices)


# ════════════════════════════════════════════════════════════════════════════
# KEY PRICE LEVELS
# ════════════════════════════════════════════════════════════════════════════

def get_key_levels(result: SignalResult) -> list[dict]:
    """
    Returns sorted list of key price levels for the Key Levels sidebar panel.
    """
    close = result.close
    levels = []

    def add(label, price, kind):
        if price and price > 0:
            dist = round(((price - close) / close) * 100, 2) if close else 0
            levels.append({"label": label, "price": price, "kind": kind, "dist_pct": dist})

    add("BB Upper",   result.bb_upper, "resistance")
    add("EMA 20",     result.ema20,    "dynamic")
    add("EMA 50",     result.ema50,    "dynamic")
    add("VWAP",       result.vwap,     "dynamic")
    add("EMA 200",    result.ema200,   "dynamic")
    add("BB Lower",   result.bb_lower, "support")
    if result.stop:
        add("Stop Loss",  result.stop,  "stop")
    if result.target:
        add("AI Target",  result.target, "target")

    # Sort: resistances above close, supports below
    above = sorted([l for l in levels if l["price"] > close],
                   key=lambda x: x["price"])
    now   = [{"label": "NOW", "price": close, "kind": "current", "dist_pct": 0}]
    below = sorted([l for l in levels if l["price"] <= close],
                   key=lambda x: x["price"], reverse=True)

    return above + now + below
