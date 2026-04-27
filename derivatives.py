"""
derivatives.py — Real-time perp derivatives data
Sources: Bybit (geo-friendly), OKX fallback
Data: Funding Rate, Open Interest, Long/Short Ratio
No API key required for public endpoints.
"""
import requests, time, logging
from functools import lru_cache

logger = logging.getLogger(__name__)

BYBIT  = "https://api.bybit.com"
OKX    = "https://www.okx.com"

# ── Symbol normalisation ──────────────────────────────────────────────────────
def _bybit_sym(symbol: str) -> str:
    """BTC → BTCUSDT for Bybit linear perps."""
    s = symbol.upper().strip()
    if not s.endswith("USDT"):
        s = s + "USDT"
    return s

def _okx_sym(symbol: str) -> str:
    """BTC → BTC-USDT-SWAP for OKX."""
    return f"{symbol.upper().strip()}-USDT-SWAP"

# ── Funding Rate ──────────────────────────────────────────────────────────────
def get_funding_rate(symbol: str) -> dict:
    """
    Returns current funding rate for the perp.
    Positive = longs pay shorts (overheated bulls, bearish signal)
    Negative = shorts pay longs (fearful market, bullish signal)
    """
    sym = _bybit_sym(symbol)
    try:
        r = requests.get(
            f"{BYBIT}/v5/market/tickers",
            params={"category": "linear", "symbol": sym},
            timeout=6,
        )
        r.raise_for_status()
        items = r.json().get("result", {}).get("list", [])
        if items:
            d = items[0]
            rate = float(d.get("fundingRate", 0))
            next_ts = int(d.get("nextFundingTime", 0)) // 1000
            return {
                "rate":        round(rate * 100, 4),   # convert to %
                "rate_8h":     round(rate * 100, 4),
                "rate_annualised": round(rate * 3 * 365 * 100, 1),  # 3x daily * 365
                "next_funding_ts": next_ts,
                "sentiment":   "bearish" if rate > 0.0005 else "bullish" if rate < -0.0001 else "neutral",
                "source":      "Bybit",
            }
    except Exception as e:
        logger.warning(f"Bybit funding rate failed for {symbol}: {e}")

    # OKX fallback
    try:
        r = requests.get(
            f"{OKX}/api/v5/public/funding-rate",
            params={"instId": _okx_sym(symbol)},
            timeout=6,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if data:
            rate = float(data[0].get("fundingRate", 0))
            return {
                "rate":        round(rate * 100, 4),
                "rate_8h":     round(rate * 100, 4),
                "rate_annualised": round(rate * 3 * 365 * 100, 1),
                "next_funding_ts": 0,
                "sentiment":   "bearish" if rate > 0.0005 else "bullish" if rate < -0.0001 else "neutral",
                "source":      "OKX",
            }
    except Exception as e:
        logger.warning(f"OKX funding rate failed for {symbol}: {e}")

    return {"rate": 0, "rate_8h": 0, "rate_annualised": 0, "next_funding_ts": 0, "sentiment": "neutral", "source": "unavailable"}


# ── Open Interest ─────────────────────────────────────────────────────────────
def get_open_interest(symbol: str) -> dict:
    """
    Returns current open interest (USD notional) and 24H change %.
    Rising OI + rising price = trend confirmed.
    Rising OI + falling price = trend exhaustion warning.
    """
    sym = _bybit_sym(symbol)
    try:
        # Current OI
        r = requests.get(
            f"{BYBIT}/v5/market/tickers",
            params={"category": "linear", "symbol": sym},
            timeout=6,
        )
        r.raise_for_status()
        items = r.json().get("result", {}).get("list", [])
        if items:
            d = items[0]
            oi_val  = float(d.get("openInterestValue", 0) or d.get("openInterest", 0))
            price   = float(d.get("lastPrice", 1) or 1)
            # If openInterestValue is in contracts, convert to USD
            if oi_val < 1_000_000 and price > 1:
                oi_usd = oi_val * price
            else:
                oi_usd = oi_val

            # 24H OI history for change % — use same USD conversion
            oi_24h_ago_raw = _get_oi_history(sym)
            # oi_24h_ago_raw is in contracts; multiply by same price to get USD
            oi_24h_ago = oi_24h_ago_raw * price if (oi_24h_ago_raw < 1_000_000 and price > 1) else oi_24h_ago_raw
            change_pct = round(((oi_usd - oi_24h_ago) / oi_24h_ago) * 100, 2) if oi_24h_ago and abs(oi_24h_ago) > 0 else 0
            # Sanity clamp — anything over 500% is a unit mismatch
            if abs(change_pct) > 500:
                change_pct = 0

            return {
                "oi_usd":      round(oi_usd),
                "oi_usd_fmt":  _fmt_large(oi_usd),
                "change_24h":  change_pct,
                "trend":       "rising" if change_pct > 2 else "falling" if change_pct < -2 else "flat",
                "source":      "Bybit",
            }
    except Exception as e:
        logger.warning(f"Bybit OI failed for {symbol}: {e}")

    return {"oi_usd": 0, "oi_usd_fmt": "N/A", "change_24h": 0, "trend": "flat", "source": "unavailable"}


def _get_oi_history(sym: str) -> float:
    """Get OI from ~24H ago using Bybit OI history endpoint."""
    try:
        end_ts   = int(time.time() * 1000)
        start_ts = end_ts - 86_400_000  # 24H ago
        r = requests.get(
            f"{BYBIT}/v5/market/open-interest",
            params={"category": "linear", "symbol": sym, "intervalTime": "1h",
                    "startTime": start_ts, "endTime": end_ts, "limit": 2},
            timeout=6,
        )
        r.raise_for_status()
        items = r.json().get("result", {}).get("list", [])
        if items:
            return float(items[-1].get("openInterest", 0))
    except Exception:
        pass
    return 0.0


# ── Long / Short Ratio ────────────────────────────────────────────────────────
def get_long_short_ratio(symbol: str) -> dict:
    """
    Returns % of accounts that are net long vs net short.
    Contrarian signal: >70% long = crowded trade, fade risk.
    <35% long = extreme fear, potential reversal.
    """
    sym = _bybit_sym(symbol)
    try:
        r = requests.get(
            f"{BYBIT}/v5/market/account-ratio",
            params={"category": "linear", "symbol": sym, "period": "1h", "limit": 1},
            timeout=6,
        )
        r.raise_for_status()
        items = r.json().get("result", {}).get("list", [])
        if items:
            buy_ratio  = float(items[0].get("buyRatio",  0.5))
            sell_ratio = float(items[0].get("sellRatio", 0.5))
            long_pct   = round(buy_ratio * 100, 1)
            short_pct  = round(sell_ratio * 100, 1)
            sentiment  = (
                "bearish" if long_pct > 60  else   # crowded longs = fade risk
                "bullish" if long_pct < 40  else   # short squeeze territory
                "neutral"
            )
            return {
                "long_pct":   long_pct,
                "short_pct":  short_pct,
                "sentiment":  sentiment,
                "note":       (
                    "Crowded longs — fade risk" if long_pct > 60 else
                    "Short squeeze risk — longs may be building" if long_pct < 40 else
                    "Balanced" if 48 <= long_pct <= 52 else
                    "Longs dominant" if long_pct > 52 else "Shorts dominant"
                ),
                "source": "Bybit",
            }
    except Exception as e:
        logger.warning(f"Bybit L/S ratio failed for {symbol}: {e}")

    return {"long_pct": 50, "short_pct": 50, "sentiment": "neutral", "note": "Balanced", "source": "unavailable"}


# ── Combined derivatives snapshot ─────────────────────────────────────────────
@lru_cache(maxsize=64)
def _deriv_cached(symbol: str, ts_bucket: int) -> dict:
    """Cached 5-min derivatives snapshot."""
    fr  = get_funding_rate(symbol)
    oi  = get_open_interest(symbol)
    ls  = get_long_short_ratio(symbol)
    # Check if symbol has perp data at all
    has_data = fr["source"] != "unavailable"
    return {"funding": fr, "open_interest": oi, "long_short": ls, "has_perp": has_data}

def get_derivatives(symbol: str) -> dict:
    ts_bucket = int(time.time() // 300)   # 5-min cache bucket
    return _deriv_cached(symbol.upper(), ts_bucket)


# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt_large(n: float) -> str:
    if n >= 1_000_000_000: return f"${n/1_000_000_000:.2f}B"
    if n >= 1_000_000:     return f"${n/1_000_000:.1f}M"
    if n >= 1_000:         return f"${n/1_000:.0f}K"
    return f"${n:.0f}"
