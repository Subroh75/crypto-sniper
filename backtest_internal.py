"""
backtest_internal.py — Internal Signal Backtest Engine

Replays the live scoring engine (signals.py) bar-by-bar over daily OHLCV
history fetched from CoinGecko. No external trade data. Fully self-contained.

Strategy:
  - Look-back window : each bar uses the preceding N bars as history context
  - Entry            : when score >= STRONG_BUY_THRESHOLD (9/16) on close of bar i
  - Exit             : close of bar i+1 (next-day close) — simple 1-bar hold
  - Also tracks 3-bar and 5-bar hold variants for comparison
  - Computes equity curve, win rate, avg return, max drawdown, Sharpe proxy
"""

import time, logging, requests
from functools import lru_cache
from typing import Optional
from signals import calculate_signals, SignalResult, _calc_rsi, _calc_atr, _calc_adx, _calc_ema

logger = logging.getLogger(__name__)

STRONG_BUY_THRESHOLD = 9
MIN_BARS_CONTEXT     = 50    # need this many bars before first signal is valid
HOLD_PERIODS         = [1, 3, 5]   # days to hold after entry

# CoinGecko OHLC endpoint — free, no key, CORS-open
CG_OHLC_URL = "https://api.coingecko.com/api/v3/coins/{cg_id}/ohlc"

CG_ID: dict[str, str] = {
    "BTC":"bitcoin",            "ETH":"ethereum",
    "SOL":"solana",             "BNB":"binancecoin",
    "XRP":"ripple",             "ADA":"cardano",
    "DOGE":"dogecoin",          "DOT":"polkadot",
    "AVAX":"avalanche-2",       "LINK":"chainlink",
    "UNI":"uniswap",            "ATOM":"cosmos",
    "LTC":"litecoin",           "MATIC":"matic-network",
    "PEPE":"pepe",              "WIF":"dogwifhat",
    "HYPE":"hyperliquid",       "RENDER":"render-token",
    "KAVA":"kava",              "SEI":"sei-network",
    "SUI":"sui",                "APT":"aptos",
    "ARB":"arbitrum",           "OP":"optimism",
    "INJ":"injective-protocol", "TIA":"celestia",
    "BONK":"bonk",              "FET":"fetch-ai",
    "NEAR":"near",              "ALGO":"algorand",
    "ICP":"internet-computer",  "FIL":"filecoin",
    "HBAR":"hedera-hashgraph",  "PENGU":"pudgy-penguins",
    "TON":"the-open-network",   "SHIB":"shiba-inu",
    "NOT":"notcoin",            "STRK":"starknet",
    "LDO":"lido-dao",           "MKR":"maker",
    "AAVE":"aave",              "CRV":"curve-dao-token",
    "GMX":"gmx",                "JUP":"jupiter-exchange-solana",
    "PYTH":"pyth-network",      "WLD":"worldcoin-wld",
    "TAO":"bittensor",          "ENA":"ethena",
    "COMP":"compound-governance-token",
    "XMR":"monero",             "ETC":"ethereum-classic",
    "BCH":"bitcoin-cash",       "TRX":"tron",
}


# ── Data fetch ────────────────────────────────────────────────────────────────
@lru_cache(maxsize=64)
def _fetch_daily_ohlcv(cg_id: str, ts_bucket: int) -> list[list]:
    """
    Fetch daily OHLCV from CoinGecko /ohlc.
    days=365 returns ~90 daily candles (free tier max).
    Returns list of [ts_ms, open, high, low, close] newest last.
    ts_bucket makes the cache refresh every 30 min.
    """
    try:
        r = requests.get(
            CG_OHLC_URL.format(cg_id=cg_id),
            params={"vs_currency": "usd", "days": "365"},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list) and data:
            # CoinGecko returns [ts_ms, open, high, low, close]
            # Add dummy volume=0 at index 5 to match signals.py expected format
            return [[c[0], c[1], c[2], c[3], c[4], 0.0] for c in data]
    except Exception as e:
        logger.warning(f"fetch_daily_ohlcv {cg_id}: {e}")
    return []


def get_daily_ohlcv(symbol: str) -> list[list]:
    cg_id = CG_ID.get(symbol.upper())
    if not cg_id:
        return []
    ts_bucket = int(time.time() // 1800)   # 30-min cache
    return _fetch_daily_ohlcv(cg_id, ts_bucket)


# ── Signal replay ─────────────────────────────────────────────────────────────
def _score_bar(ohlcv_window: list[list], bar_idx: int) -> SignalResult:
    """
    Score bar at bar_idx using all bars up to and including bar_idx as history.
    The window is the full candle list (oldest first).
    """
    history = ohlcv_window[: bar_idx + 1]
    if len(history) < MIN_BARS_CONTEXT:
        return SignalResult()   # insufficient history — default 0 score

    bar   = history[-1]
    close = bar[4]
    high  = bar[2]
    low   = bar[3]
    prev_close = history[-2][4] if len(history) >= 2 else close

    # Synthesise quote from this bar
    change_24h = ((close - prev_close) / prev_close * 100) if prev_close else 0
    quote = {
        "price":      close,
        "change_24h": change_24h,
        "volume_24h": 0,   # daily OHLCV from CG has no volume in free tier
        "high_24h":   high,
        "low_24h":    low,
    }

    # Compute indicators from this window
    closes = [b[4] for b in history]
    highs  = [b[2] for b in history]
    lows   = [b[3] for b in history]

    indicators = {
        "rsi":      _calc_rsi(closes, 14),
        "adx":      _calc_adx(highs, lows, closes, 14),
        "atr":      _calc_atr(highs, lows, closes, 14),
        "ema20":    _calc_ema(closes, 20),
        "ema50":    _calc_ema(closes, 50),
        "ema200":   _calc_ema(closes, min(200, len(closes) - 1)),
        "bb_upper": None,
        "bb_lower": None,
        "macd_hist": 0,
    }

    # BB from 20-period SMA ± 2 std
    if len(closes) >= 20:
        window20  = closes[-20:]
        sma20     = sum(window20) / 20
        std20     = (sum((x - sma20) ** 2 for x in window20) / 20) ** 0.5
        indicators["bb_upper"] = sma20 + 2 * std20
        indicators["bb_lower"] = sma20 - 2 * std20

    return calculate_signals(history, quote, indicators)


# ── Main backtest ─────────────────────────────────────────────────────────────
def run_backtest(symbol: str) -> dict:
    """
    Full internal backtest for a symbol on 1D bars.
    Returns trades, equity curve, summary stats.
    """
    symbol  = symbol.upper()
    ohlcv   = get_daily_ohlcv(symbol)

    if not ohlcv:
        return {
            "symbol":  symbol,
            "error":   f"No daily OHLCV available for {symbol}",
            "trades":  [],
            "equity":  [],
            "summary": {},
            "bars_scanned": 0,
        }

    n = len(ohlcv)

    # ── Replay every bar ────────────────────────────────────────────────────
    bar_scores: list[dict] = []

    for i in range(MIN_BARS_CONTEXT, n):
        res   = _score_bar(ohlcv, i)
        ts_ms = ohlcv[i][0]
        close = ohlcv[i][4]
        bar_scores.append({
            "bar_idx": i,
            "ts_ms":   ts_ms,
            "date":    _ms_to_date(ts_ms),
            "close":   close,
            "score":   res.total,
            "signal":  res.signal,
            "v": res.v_score, "p": res.p_score,
            "r": res.r_score, "t": res.t_score, "s": res.s_score,
            "rsi":     res.rsi,
            "adx":     res.adx,
            "ema_stack": res.ema_stack,
        })

    # ── Extract trades (1-bar hold) ─────────────────────────────────────────
    trades: list[dict] = []
    in_trade = False
    entry_bar = None

    for i, bar in enumerate(bar_scores):
        if in_trade:
            # Exit at close of this bar (1-day hold)
            entry_close = entry_bar["close"]
            exit_close  = bar["close"]
            ret_pct     = round((exit_close - entry_close) / entry_close * 100, 2) if entry_close else 0

            # Also compute 3-bar and 5-bar hold returns
            entry_idx = entry_bar["bar_idx"]
            ret3 = _hold_return(ohlcv, entry_idx, 3)
            ret5 = _hold_return(ohlcv, entry_idx, 5)

            trades.append({
                "date":        entry_bar["date"],
                "entry_price": entry_close,
                "exit_price":  exit_close,
                "score":       entry_bar["score"],
                "signal":      entry_bar["signal"],
                "rsi":         entry_bar["rsi"],
                "adx":         entry_bar["adx"],
                "ret_1d":      ret_pct,
                "ret_3d":      ret3,
                "ret_5d":      ret5,
                "win_1d":      ret_pct >= 2.0,
                "win_3d":      ret3 >= 2.0 if ret3 is not None else None,
                "win_5d":      ret5 >= 2.0 if ret5 is not None else None,
            })
            in_trade = False
            entry_bar = None

        if bar["score"] >= STRONG_BUY_THRESHOLD and not in_trade:
            in_trade  = True
            entry_bar = bar

    # ── Equity curve (1-bar hold, compounding) ──────────────────────────────
    equity = 100.0
    equity_curve: list[dict] = []
    for bar in bar_scores:
        equity_curve.append({
            "date":   bar["date"],
            "score":  bar["score"],
            "signal": bar["signal"],
            "equity": round(equity, 2),
            "close":  bar["close"],
        })
        # Apply trade return if this bar had a signal entry
        # (equity updates at exit = next bar, handled in trade list above)

    # Rebuild equity as running compounded P&L from trades
    equity = 100.0
    trade_dates = {t["date"] for t in trades}
    eq_out: list[dict] = []
    for pt in equity_curve:
        # Find trade that entered on this date
        for t in trades:
            if t["date"] == pt["date"]:
                equity *= (1 + t["ret_1d"] / 100)
                break
        eq_out.append({**pt, "equity": round(equity, 2)})

    # ── Summary stats ────────────────────────────────────────────────────────
    resolved = [t for t in trades]
    wins_1d  = [t for t in resolved if t["win_1d"]]
    losses_1d= [t for t in resolved if not t["win_1d"]]

    avg_ret_1d   = _safe_avg([t["ret_1d"] for t in resolved])
    avg_ret_3d   = _safe_avg([t["ret_3d"] for t in resolved if t["ret_3d"] is not None])
    avg_ret_5d   = _safe_avg([t["ret_5d"] for t in resolved if t["ret_5d"] is not None])
    win_rate_1d  = round(len(wins_1d) / len(resolved) * 100, 1) if resolved else None
    total_ret    = round(eq_out[-1]["equity"] - 100, 2) if eq_out else None
    max_dd       = _max_drawdown([e["equity"] for e in eq_out])

    # Sharpe proxy: avg_return / std_return (annualised naively)
    rets = [t["ret_1d"] for t in resolved]
    sharpe = None
    if len(rets) >= 3:
        avg_r = sum(rets) / len(rets)
        std_r = (sum((r - avg_r) ** 2 for r in rets) / len(rets)) ** 0.5
        if std_r > 0:
            sharpe = round(avg_r / std_r * (252 ** 0.5), 2)

    # Bar-level score distribution
    score_dist = {str(k): 0 for k in range(17)}
    for b in bar_scores:
        score_dist[str(b["score"])] = score_dist.get(str(b["score"]), 0) + 1

    summary = {
        "symbol":          symbol,
        "bars_scanned":    len(bar_scores),
        "total_trades":    len(resolved),
        "wins_1d":         len(wins_1d),
        "losses_1d":       len(losses_1d),
        "win_rate_1d":     win_rate_1d,
        "avg_ret_1d":      avg_ret_1d,
        "avg_ret_3d":      avg_ret_3d,
        "avg_ret_5d":      avg_ret_5d,
        "total_return":    total_ret,         # compounded, 1-bar hold
        "max_drawdown":    max_dd,
        "sharpe_proxy":    sharpe,
        "threshold":       STRONG_BUY_THRESHOLD,
        "hold_days":       1,
        "score_dist":      score_dist,
        "first_date":      bar_scores[0]["date"]  if bar_scores else None,
        "last_date":       bar_scores[-1]["date"] if bar_scores else None,
    }

    return {
        "symbol":       symbol,
        "trades":       trades[-30:],     # last 30 trades max
        "equity":       eq_out,           # full equity curve
        "bar_scores":   bar_scores,       # all bars with score
        "summary":      summary,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────
def _ms_to_date(ts_ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _hold_return(ohlcv: list, entry_idx: int, hold: int) -> Optional[float]:
    exit_idx = entry_idx + hold
    if exit_idx >= len(ohlcv):
        return None
    entry_close = ohlcv[entry_idx][4]
    exit_close  = ohlcv[exit_idx][4]
    if entry_close <= 0:
        return None
    return round((exit_close - entry_close) / entry_close * 100, 2)


def _safe_avg(values: list) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _max_drawdown(equity_series: list[float]) -> Optional[float]:
    if len(equity_series) < 2:
        return None
    peak = equity_series[0]
    max_dd = 0.0
    for v in equity_series:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)
