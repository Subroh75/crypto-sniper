"""
history.py — Signal history, hit-rate tracking, scanner performance
SQLite DB: data.db (repo root — persists across Render deploys)

Tables:
  signals(id, symbol, interval, score, signal_label, close_price, ts, outcome_pct, outcome_checked)
  scanner_picks(id, symbol, score, signal_label, close_price, scan_date, outcome_pct, outcome_checked)
"""

import sqlite3, os, time, logging, requests
from datetime import datetime, timezone, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")


# ── DB setup ────────────────────────────────────────────────────────────────
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT    NOT NULL,
            interval        TEXT    NOT NULL DEFAULT '1H',
            score           INTEGER NOT NULL,
            signal_label    TEXT    NOT NULL,
            close_price     REAL    NOT NULL,
            ts              INTEGER NOT NULL,
            outcome_pct     REAL    DEFAULT NULL,
            outcome_checked INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_signals_sym ON signals(symbol, ts);

        CREATE TABLE IF NOT EXISTS scanner_picks (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol          TEXT    NOT NULL,
            score           INTEGER NOT NULL,
            signal_label    TEXT    NOT NULL,
            close_price     REAL    NOT NULL,
            scan_date       TEXT    NOT NULL,
            outcome_pct     REAL    DEFAULT NULL,
            outcome_checked INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_picks_date ON scanner_picks(scan_date);
        """)


_init_db()


# ── Signal recording ────────────────────────────────────────────────────────
def record_signal(symbol: str, interval: str, score: int, signal_label: str, close_price: float):
    """Record every /analyse call to history."""
    try:
        with _get_conn() as c:
            c.execute(
                "INSERT INTO signals (symbol, interval, score, signal_label, close_price, ts) VALUES (?,?,?,?,?,?)",
                (symbol.upper(), interval, score, signal_label, close_price, int(time.time())),
            )
    except Exception as e:
        logger.warning(f"record_signal failed: {e}")


def record_scan_result(symbol: str, score: int, signal_label: str, close_price: float, scan_date: Optional[str] = None):
    """Record a daily scanner pick."""
    date_str = scan_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        with _get_conn() as c:
            # Avoid dupes for same symbol same day
            existing = c.execute(
                "SELECT id FROM scanner_picks WHERE symbol=? AND scan_date=?",
                (symbol.upper(), date_str)
            ).fetchone()
            if not existing:
                c.execute(
                    "INSERT INTO scanner_picks (symbol, score, signal_label, close_price, scan_date) VALUES (?,?,?,?,?)",
                    (symbol.upper(), score, signal_label, close_price, date_str),
                )
    except Exception as e:
        logger.warning(f"record_scan_result failed: {e}")


# ── Outcome checking ─────────────────────────────────────────────────────────
def _get_current_price(symbol: str) -> Optional[float]:
    """Fetch current price from CoinGecko simple price."""
    try:
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": symbol.lower(), "vs_currencies": "usd"},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json()
            # Try direct symbol match first, then iterate
            for key, val in data.items():
                return float(val.get("usd", 0))
    except Exception:
        pass
    return None


def check_outcomes():
    """
    Background job: for signals older than 24H that haven't been checked,
    fetch the current price and compute outcome_pct.
    Call periodically (e.g., from daily cron or health check).
    """
    cutoff = int(time.time()) - 86_400  # 24H ago
    try:
        with _get_conn() as conn:
            rows = conn.execute(
                "SELECT id, symbol, close_price FROM signals WHERE ts <= ? AND outcome_checked = 0",
                (cutoff,)
            ).fetchall()
        for row in rows:
            price_now = _get_current_price(row["symbol"])
            if price_now and row["close_price"] > 0:
                pct = round((price_now - row["close_price"]) / row["close_price"] * 100, 2)
                with _get_conn() as conn:
                    conn.execute(
                        "UPDATE signals SET outcome_pct=?, outcome_checked=1 WHERE id=?",
                        (pct, row["id"]),
                    )
            time.sleep(0.5)  # gentle on rate limits
    except Exception as e:
        logger.warning(f"check_outcomes failed: {e}")


# ── Query: symbol history ────────────────────────────────────────────────────
def get_symbol_history(symbol: str, limit: int = 30) -> list:
    """Return last N signals for a symbol with outcome where available."""
    try:
        with _get_conn() as c:
            rows = c.execute(
                """SELECT symbol, interval, score, signal_label, close_price, ts, outcome_pct
                   FROM signals WHERE symbol=? ORDER BY ts DESC LIMIT ?""",
                (symbol.upper(), limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"get_symbol_history failed: {e}")
        return []


# ── Query: hit rate ──────────────────────────────────────────────────────────
def get_hit_rate(symbol: Optional[str] = None, days: int = 30) -> dict:
    """
    STRONG BUY hit rate: % of signals that went up ≥2% within 24H.
    Only counts signals with outcome already checked.
    """
    cutoff_ts = int(time.time()) - days * 86_400
    try:
        with _get_conn() as c:
            sym_filter = "AND symbol=?" if symbol else ""
            params: tuple = (cutoff_ts,) + ((symbol,) if symbol else ()) + ("STRONG BUY",)
            rows = c.execute(
                f"""SELECT outcome_pct FROM signals
                    WHERE ts >= ? {sym_filter}
                    AND signal_label = ?
                    AND outcome_checked = 1""",
                params,
            ).fetchall()

        total = len(rows)
        if total == 0:
            return {
                "hit_rate_pct": None,
                "total_signals": 0,
                "hits": 0,
                "threshold_pct": 2.0,
                "days": days,
                "symbol": symbol,
                "message": "Insufficient data — signals are still accumulating. Check back in 24H.",
            }

        hits = sum(1 for r in rows if r["outcome_pct"] is not None and r["outcome_pct"] >= 2.0)
        rate = round(hits / total * 100, 1)
        return {
            "hit_rate_pct": rate,
            "total_signals": total,
            "hits": hits,
            "threshold_pct": 2.0,
            "days": days,
            "symbol": symbol,
            "message": f"STRONG BUY signals were right {rate}% of the time in the last {days} days.",
        }
    except Exception as e:
        logger.warning(f"get_hit_rate failed: {e}")
        return {"hit_rate_pct": None, "total_signals": 0, "hits": 0, "days": days, "symbol": symbol, "message": "Error"}


# ── Query: scanner performance ───────────────────────────────────────────────
def get_scanner_performance(days: int = 7) -> dict:
    """
    Return the last N days of scanner picks with their % return.
    For unchecked picks > 24H old, tries to fill in outcome on the fly.
    """
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        with _get_conn() as c:
            rows = c.execute(
                """SELECT symbol, score, signal_label, close_price, scan_date, outcome_pct, outcome_checked
                   FROM scanner_picks WHERE scan_date >= ? ORDER BY scan_date DESC, score DESC""",
                (cutoff_date,),
            ).fetchall()

        picks = [dict(r) for r in rows]

        # Try to fill in outcomes for picks older than 24H
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        for pick in picks:
            if pick["outcome_checked"] == 0 and pick["scan_date"] < now_str:
                price_now = _get_current_price(pick["symbol"])
                if price_now and pick["close_price"] > 0:
                    pct = round((price_now - pick["close_price"]) / pick["close_price"] * 100, 2)
                    pick["outcome_pct"] = pct
                    with _get_conn() as c:
                        c.execute(
                            "UPDATE scanner_picks SET outcome_pct=?, outcome_checked=1 WHERE symbol=? AND scan_date=?",
                            (pct, pick["symbol"], pick["scan_date"]),
                        )

        # Summary stats
        checked = [p for p in picks if p["outcome_pct"] is not None]
        avg_return = round(sum(p["outcome_pct"] for p in checked) / len(checked), 2) if checked else None
        winners = [p for p in checked if p["outcome_pct"] >= 2.0]
        win_rate = round(len(winners) / len(checked) * 100, 1) if checked else None

        return {
            "picks": picks,
            "summary": {
                "total_picks": len(picks),
                "checked": len(checked),
                "avg_return_pct": avg_return,
                "win_rate_pct": win_rate,
                "days": days,
            },
        }
    except Exception as e:
        logger.warning(f"get_scanner_performance failed: {e}")
        return {"picks": [], "summary": {"total_picks": 0, "checked": 0, "avg_return_pct": None, "win_rate_pct": None, "days": days}}


# ── Backtest ─────────────────────────────────────────────────────────────────
def get_backtest(symbol: Optional[str] = None, days: int = 30) -> dict:
    """
    Simple backtest: for every STRONG BUY signal in the last N days,
    compute the % return from entry price to the latest recorded price/outcome.

    Returns:
      - trades: list of {symbol, ts, entry, exit_pct, outcome_pct}
      - summary: {total, wins, losses, avg_return, total_return, win_rate, days}
    """
    cutoff_ts = int(time.time()) - days * 86_400
    try:
        with _get_conn() as c:
            sym_filter = "AND symbol=?" if symbol else ""
            params: tuple = (cutoff_ts,) + ((symbol.upper(),) if symbol else ()) + ("STRONG BUY",)
            rows = c.execute(
                f"""SELECT symbol, interval, close_price, ts, outcome_pct, outcome_checked
                    FROM signals
                    WHERE ts >= ? {sym_filter}
                    AND signal_label = ?
                    ORDER BY ts ASC""",
                params,
            ).fetchall()

        trades = []
        for r in rows:
            row = dict(r)
            trades.append({
                "symbol":      row["symbol"],
                "interval":    row["interval"],
                "entry_price": row["close_price"],
                "ts":          row["ts"],
                "outcome_pct": row["outcome_pct"],    # None = not yet resolved
                "resolved":    bool(row["outcome_checked"]),
            })

        # Stats on resolved trades only
        resolved = [t for t in trades if t["outcome_pct"] is not None]
        wins     = [t for t in resolved if t["outcome_pct"] >= 2.0]
        losses   = [t for t in resolved if t["outcome_pct"] < 0]

        avg_return   = round(sum(t["outcome_pct"] for t in resolved) / len(resolved), 2) if resolved else None
        total_return = round(sum(t["outcome_pct"] for t in resolved), 2) if resolved else None
        win_rate     = round(len(wins) / len(resolved) * 100, 1) if resolved else None

        return {
            "trades": trades,
            "summary": {
                "total":        len(trades),
                "resolved":     len(resolved),
                "wins":         len(wins),
                "losses":       len(losses),
                "avg_return":   avg_return,
                "total_return": total_return,
                "win_rate":     win_rate,
                "threshold_pct": 2.0,
                "days":         days,
                "symbol":       symbol,
            },
        }
    except Exception as e:
        logger.warning(f"get_backtest failed: {e}")
        return {
            "trades": [],
            "summary": {"total": 0, "resolved": 0, "wins": 0, "losses": 0,
                        "avg_return": None, "total_return": None, "win_rate": None,
                        "threshold_pct": 2.0, "days": days, "symbol": symbol},
        }
