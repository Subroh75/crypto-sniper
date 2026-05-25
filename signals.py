"""
signals.py — V/P/R/T gate-based signal engine for Crypto Sniper

Signal Logic:
  V — Volume gate  : rel_vol >= 1.8x  → confirmed (unusual volume)
  T — Trend gate   : close > EMA20 > EMA50 > EMA200 (all 3 MAs below price)
  ADX gate         : ADX >= 25 → trending

Signal Tiers:
  BUY         = V confirmed + T confirmed + ADX >= 25
  STRONG BUY  = BUY + P confirmed + R confirmed
                  P = change_24h > 0 AND atr_move > 0
                  R = close in upper 50% of bar range
  NO SIGNAL   = any gate fails

Display: plain English, no raw scores
"""

from dataclasses import dataclass, field
from typing import Optional
import math


@dataclass
class SignalResult:
    # Gate confirmations
    v_confirmed: bool = False
    t_confirmed: bool = False
    adx_confirmed: bool = False
    p_confirmed: bool = False
    r_confirmed: bool = False

    # Legacy score fields (kept for API compat / trade setup logic)
    v_score:   int = 0
    p_score:   int = 0
    r_score:   int = 0
    t_score:   int = 0
    s_score:   int = 0   # always 0
    total:     int = 0
    max_score: int = 13

    # Plain English detail strings
    v_detail: str = ""
    p_detail: str = ""
    r_detail: str = ""
    t_detail: str = ""

    # Raw values
    rel_volume: float = 0.0
    atr_move_sigma: float = 0.0
    range_pos: float = 0.0
    adx: float = 0.0
    rsi: float = 50.0
    ema_stack: bool = False
    social_delta: float = 0.0

    # Verdict
    signal: str = "NO SIGNAL"         # STRONG BUY / BUY / NO SIGNAL
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
    # Z-score Phase 1 — entry quality (display only, not blocking signals)
    z_price:   float = 0.0
    z_vol:     float = 0.0
    z_return:  float = 0.0
    z_quality: str   = "UNKNOWN"

    # Vol Shield — GARCH volatility regime
    vol_shield:       str   = ""      # CALM / ELEVATED / STORM
    vol_shield_sigma: float = 0.0     # forecast daily σ %
    vol_shield_sizing: float = 1.0    # suggested position size multiplier

    @property
    def pct_score(self) -> float:
        return (self.total / self.max_score) * 100

    @property
    def signal_label(self) -> str:
        return self.signal

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


# ─────────────────────────────────────────────
#  Vol Shield — GARCH(1,1) volatility regime
# ─────────────────────────────────────────────

def _garch_vol_shield(closes: list[float]) -> dict:
    """
    Fit GARCH(1,1) on log returns and forecast next-bar conditional volatility.
    Returns vol_shield regime + sigma + sizing multiplier.
    Falls back gracefully if arch not installed or insufficient data.
    """
    MIN_BARS = 30
    if len(closes) < MIN_BARS:
        return {"vol_shield": "", "sigma": 0.0, "sizing": 1.0}

    try:
        import numpy as np
        from arch import arch_model

        # Log returns in percent (arch expects percent scale)
        px    = np.array(closes, dtype=float)
        rets  = np.diff(np.log(px)) * 100          # % log returns
        rets  = rets[-120:]                          # cap at 120 bars

        # Demean
        rets  = rets - rets.mean()

        # Fit GARCH(1,1)
        gm    = arch_model(rets, vol="Garch", p=1, q=1, dist="normal", rescale=False)
        res   = gm.fit(disp="off", show_warning=False)

        # One-step-ahead variance forecast
        fc    = res.forecast(horizon=1, reindex=False)
        var   = float(fc.variance.iloc[-1, 0])
        sigma = float(var ** 0.5)                   # daily σ in %

        # Regime classification
        if sigma < 2.5:
            regime = "CALM"
            sizing = 1.0
        elif sigma < 5.0:
            regime = "ELEVATED"
            sizing = 0.6
        else:
            regime = "STORM"
            sizing = 0.4

        return {"vol_shield": regime, "sigma": round(sigma, 2), "sizing": sizing}

    except Exception:
        # arch not installed or numerical failure — silent fallback
        return {"vol_shield": "", "sigma": 0.0, "sizing": 1.0}


def calculate_signals(
    ohlcv: list[list],
    quote: dict,
    indicators: dict,
    fear_greed: dict = None,
    cp_news: list = None,
    social_delta: float = 0.0,
    coindar_events: list = None,
) -> SignalResult:
    """
    Gate-based signal engine.

    Args:
        ohlcv:        [[ts, o, h, l, c, vol], ...] newest last
        quote:        {price, change_24h, volume_24h, high_24h, low_24h, ...}
        indicators:   {rsi, adx, atr, ema20, ema50, ema200, bb_upper, bb_lower, macd_hist}
        social_delta: % change in social engagement score over 6H

    Returns:
        SignalResult with all fields populated
    """
    result = SignalResult()

    if not ohlcv or len(ohlcv) < 50:
        result.signal = "NO SIGNAL"
        result.v_detail = "Vol: insufficient history (new listing?)"
        result.t_detail = "Trend: insufficient history — need 50+ bars"
        result.p_detail = "Momentum: insufficient data"
        result.r_detail = "Range: insufficient data"
        return result

    # ── Extract prices ─────────────────────────────────────────────────────
    closes  = [bar[4] for bar in ohlcv]
    highs   = [bar[2] for bar in ohlcv]
    lows    = [bar[3] for bar in ohlcv]
    volumes = [bar[5] for bar in ohlcv if len(bar) > 5]

    close  = closes[-1]
    high   = highs[-1]
    low    = lows[-1]
    open_  = ohlcv[-1][1]

    # ── Indicators ─────────────────────────────────────────────────────────
    rsi       = indicators.get("rsi") or _calc_rsi(closes, 14)
    adx       = indicators.get("adx") or _calc_adx(highs, lows, closes, 14)
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
        price_move = close - open_
        atr_move_sigma = price_move / atr
    else:
        atr_move_sigma = 0.0

    # ── Range position ─────────────────────────────────────────────────────
    bar_range = high - low
    range_pos = (close - low) / bar_range if bar_range > 0 else 0.5

    # ══════════════════════════════════════════════════════════════════════
    # GATE LOGIC
    # ══════════════════════════════════════════════════════════════════════

    # ── V gate: unusual volume — rel_vol >= 1.8x required ────────────────
    v_confirmed = rel_vol >= 1.8
    if v_confirmed:
        v_detail = f"Vol: {rel_vol:.1f}x — unusual volume confirmed"
    else:
        v_detail = f"Vol: {rel_vol:.1f}x — below 1.8x threshold"

    # ── T gate: close > EMA20 > EMA50 > EMA200 ─────────────────────────
    ema_stack = False
    if ema20 and ema50 and ema200 and close:
        t_confirmed = close > ema20 > ema50 > ema200
        ema_stack   = t_confirmed
        # Build plain English MA breakdown
        above_mas = []
        below_mas = []
        for label, val in [("EMA20", ema20), ("EMA50", ema50), ("EMA200", ema200)]:
            if val and close > val:
                above_mas.append(label)
            elif val:
                below_mas.append(label)
        if t_confirmed:
            t_detail = "Trend: above EMA20 · EMA50 · EMA200"
        elif above_mas and below_mas:
            t_detail = f"Trend: above {' · '.join(above_mas)} — below {' · '.join(below_mas)}"
        elif below_mas:
            t_detail = f"Trend: below {' · '.join(below_mas)}"
        else:
            # above all MAs individually but EMA stack not ordered (e.g. EMA20 < EMA50)
            ma_order = []
            if ema20 and ema50 and ema20 < ema50:
                ma_order.append("EMA20 < EMA50")
            if ema50 and ema200 and ema50 < ema200:
                ma_order.append("EMA50 < EMA200")
            if ma_order:
                t_detail = f"Trend: above all MAs but {' · '.join(ma_order)} — stack not aligned"
            else:
                t_detail = "Trend: above all MAs"
    else:
        t_confirmed = False
        t_detail = "Trend: EMA data unavailable"

    # ── ADX gate: >= 25 ────────────────────────────────────────────────
    adx_confirmed = adx >= 25
    if adx_confirmed:
        adx_label = f"ADX: {adx:.0f} — trending"
    else:
        adx_label = f"ADX: {adx:.0f} — sideways"

    # ── P confirmation: change_24h > 0 AND atr_move > 0 ───────────────
    p_confirmed = chg > 0 and atr_move_sigma > 0
    p_detail = f"Momentum: {chg:+.2f}% · RSI {rsi:.0f}"

    # ── R confirmation: close in upper 50% of bar range ───────────────
    r_confirmed = range_pos >= 0.5
    if range_pos >= 0.75:
        r_detail = "Range: upper quarter of bar"
    elif range_pos >= 0.5:
        r_detail = "Range: upper half of bar"
    else:
        r_detail = f"Range: lower half of bar ({range_pos*100:.0f}%)"

    # ══════════════════════════════════════════════════════════════════════
    # SIGNAL TIER
    # ══════════════════════════════════════════════════════════════════════
    buy_gates_met = v_confirmed and t_confirmed and adx_confirmed

    if buy_gates_met and p_confirmed and r_confirmed:
        signal = "STRONG BUY"
    elif buy_gates_met:
        signal = "BUY"
    else:
        signal = "NO SIGNAL"

    # ── Legacy score fields (kept for trade setup + API compat) ────────
    v_score = 3 if rel_vol >= 3.5 else (2 if rel_vol >= 2.5 else (1 if v_confirmed else 0))
    p_score = 2 if p_confirmed and chg >= 3 else (1 if p_confirmed else 0)
    r_score = 1 if r_confirmed else 0
    t_score = 3 if t_confirmed and adx_confirmed else (2 if t_confirmed else (1 if adx_confirmed else 0))
    total   = v_score + p_score + r_score + t_score

    # ── Direction ──────────────────────────────────────────────────────
    direction = "NEUTRAL"
    if signal in ("BUY", "STRONG BUY") and chg > 0:
        direction = "LONG"
    elif rsi >= 75 or (chg < -3 and ema20 and close < ema20):
        direction = "SHORT"

    # ── Trade Setup ────────────────────────────────────────────────────
    entry = stop = target = rr = None
    if signal in ("BUY", "STRONG BUY") and direction == "LONG":
        entry  = close
        # Fixed 10% stop on 1D signals — ATR on daily candles averages 3-5%
        # so 1.5x ATR was consistently too tight. 10% gives the trade room.
        stop   = round(close * 0.90, 8)
        # Target: 2.5x ATR but minimum 20% above entry to maintain R:R >= 2
        atr_target = close + (2.5 * atr) if atr else 0
        target = round(max(atr_target, close * 1.20), 8)
        risk   = entry - stop
        reward = target - entry
        rr     = round(reward / risk, 2) if risk > 0 else None

    # ── Bull / Bear Signal Lists ────────────────────────────────────────
    bull_signals = []
    bear_signals = []

    fg = fear_greed or {}
    fg_val = fg.get("value", 50)
    news   = cp_news or []
    bull_n = sum(1 for n in news if n.get("sentiment") == "bullish")
    bear_n = sum(1 for n in news if n.get("sentiment") == "bearish")

    if fg_val <= 25:   bull_signals.append(f"Fear&Greed {fg_val} - extreme fear, potential reversal")
    elif fg_val >= 75: bear_signals.append(f"Fear&Greed {fg_val} - extreme greed, fade risk")
    if bull_n > bear_n: bull_signals.append(f"News {bull_n} bullish vs {bear_n} bearish")
    elif bear_n > bull_n: bear_signals.append(f"News {bear_n} bearish vs {bull_n} bullish")

    if ema_stack:
        bull_signals.append("EMA20 > EMA50 > EMA200 - full bullish stack")
    if ema50 and close > ema50:
        bull_signals.append("Price above EMA50 - medium trend bullish")
    if ema200 and close > ema200:
        bull_signals.append("Price above EMA200 - macro trend intact")
    if chg > 2:
        bull_signals.append(f"24H change +{chg:.1f}% - momentum")
    if macd_hist > 0:
        bull_signals.append("MACD histogram positive")
    if adx_confirmed and chg > 0:
        bull_signals.append(f"ADX {adx:.0f} - trend has strength")
    if social_delta > 5:
        bull_signals.append(f"Social +{social_delta:.0f}% - retail accumulating")
    if rel_vol >= 2:
        bull_signals.append(f"Volume {rel_vol:.1f}x above average")
    if rsi <= 30:
        bull_signals.append(f"RSI {rsi:.0f} - oversold, bounce potential")

    if rsi >= 70:
        bear_signals.append(f"RSI {rsi:.0f} - overbought, fade risk")
    if ema200 and close < ema200:
        bear_signals.append("Price below EMA200 - macro trend bearish")
    if ema50 and close < ema50:
        bear_signals.append("Price below EMA50 - medium trend bearish")
    if adx_confirmed and chg < 0:
        bear_signals.append(f"ADX {adx:.0f} - bearish trend has strength")
    if chg < -3:
        bear_signals.append(f"24H change {chg:.1f}% - selling pressure")
    if macd_hist < 0:
        bear_signals.append("MACD histogram negative")
    if rel_vol >= 2 and chg < 0:
        bear_signals.append(f"Volume {rel_vol:.1f}x - heavy distribution")

    # ── Populate result ─────────────────────────────────────────────────
    result.v_confirmed   = v_confirmed
    result.t_confirmed   = t_confirmed
    result.adx_confirmed = adx_confirmed
    result.p_confirmed   = p_confirmed
    result.r_confirmed   = r_confirmed

    result.v_detail = v_detail
    result.p_detail = p_detail
    result.r_detail = r_detail
    result.t_detail = f"{t_detail} · {adx_label}"

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

    # ── Z-score suite (Phase 1 — display + tracker storage) ────────────
    def _zscore(series):
        if len(series) < 5:
            return 0.0, 0.0, 0.0
        n    = len(series)
        mean = sum(series) / n
        var  = sum((x - mean) ** 2 for x in series) / n
        std  = var ** 0.5
        if std == 0:
            return 0.0, mean, 0.0
        return (series[-1] - mean) / std, mean, std

    closes_list = [bar[4] for bar in ohlcv]
    volumes_list = [bar[5] for bar in ohlcv if len(bar) > 5]

    z_price, _, _ = _zscore(closes_list[-20:])

    if volumes_list and len(volumes_list) >= 5:
        z_vol, _, _ = _zscore(volumes_list[-20:])
    else:
        z_vol = 0.0

    if len(closes_list) >= 21:
        returns = [(closes_list[i] - closes_list[i-1]) / closes_list[i-1] * 100
                   for i in range(len(closes_list)-20, len(closes_list))]
        z_return, _, _ = _zscore(returns)
    else:
        z_return = 0.0

    good_z_price  = z_price  <  2.0
    good_z_vol    = z_vol    >= 0.5
    good_z_return = z_return <  2.5
    quality_pts   = sum([good_z_price, good_z_vol, good_z_return])
    if quality_pts == 3:   z_quality = "IDEAL"
    elif quality_pts == 2: z_quality = "GOOD"
    elif quality_pts == 1: z_quality = "CAUTION"
    else:                  z_quality = "AVOID"

    result.z_price   = round(z_price,   2)
    result.z_vol     = round(z_vol,     2)
    result.z_return  = round(z_return,  2)
    result.z_quality = z_quality

    # ── Vol Shield — GARCH(1,1) on closes (runs on every signal, fast fallback if arch missing)
    shield = _garch_vol_shield(closes_list)
    result.vol_shield        = shield["vol_shield"]
    result.vol_shield_sigma  = shield["sigma"]
    result.vol_shield_sizing = shield["sizing"]

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


def _calc_adx(highs: list, lows: list, closes: list, period: int = 14) -> float:
    """Calculate ADX (Average Directional Index) from OHLCV data."""
    if len(highs) < period * 2 + 1:
        return 0.0
    try:
        tr_list, pdm_list, ndm_list = [], [], []
        for i in range(1, len(highs)):
            h, l, pc = highs[i], lows[i], closes[i-1]
            tr  = max(h - l, abs(h - pc), abs(l - pc))
            pdm = max(highs[i] - highs[i-1], 0) if highs[i] - highs[i-1] > lows[i-1] - lows[i] else 0
            ndm = max(lows[i-1] - lows[i], 0) if lows[i-1] - lows[i] > highs[i] - highs[i-1] else 0
            tr_list.append(tr); pdm_list.append(pdm); ndm_list.append(ndm)

        def smooth(data, p):
            s = sum(data[:p])
            result = [s]
            for v in data[p:]:
                s = s - s/p + v
                result.append(s)
            return result

        atr_s  = smooth(tr_list, period)
        pdm_s  = smooth(pdm_list, period)
        ndm_s  = smooth(ndm_list, period)

        dx_list = []
        for a, p, n in zip(atr_s, pdm_s, ndm_s):
            if a == 0: continue
            pdi = 100 * p / a
            ndi = 100 * n / a
            dx  = 100 * abs(pdi - ndi) / (pdi + ndi) if (pdi + ndi) > 0 else 0
            dx_list.append(dx)

        if len(dx_list) < period:
            return 0.0
        adx = sum(dx_list[:period]) / period
        for dx in dx_list[period:]:
            adx = (adx * (period - 1) + dx) / period
        return round(adx, 1)
    except Exception:
        return 0.0

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

    above = sorted([l for l in levels if l["price"] > close],
                   key=lambda x: x["price"])
    now   = [{"label": "NOW", "price": close, "kind": "current", "dist_pct": 0}]
    below = sorted([l for l in levels if l["price"] <= close],
                   key=lambda x: x["price"], reverse=True)

    return above + now + below
