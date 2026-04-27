"""
watchlist_db.py — User-editable watchlist persisted to SQLite (data.db)

Table: watchlist(id, user_id, symbol, added_ts)
  user_id = "anon" for unauthenticated users (stored in frontend as a stable UUID)
  Authenticated users use their email as user_id.

Endpoints exposed via api.py:
  GET  /watchlist-items?user_id=…
  POST /watchlist-items  { user_id, symbol }
  DELETE /watchlist-items/{symbol}?user_id=…
"""

import sqlite3, os, time, logging
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")

DEFAULT_SYMS = ["BTC", "ETH", "SOL", "BNB", "DOGE"]


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_watchlist_db():
    with _get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS watchlist (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id  TEXT NOT NULL DEFAULT 'anon',
            symbol   TEXT NOT NULL,
            added_ts INTEGER NOT NULL,
            UNIQUE(user_id, symbol)
        );
        CREATE INDEX IF NOT EXISTS idx_watchlist_user ON watchlist(user_id);
        """)


_init_watchlist_db()


def get_watchlist(user_id: str = "anon") -> list:
    """Return symbols for a user, in insertion order."""
    try:
        with _get_conn() as c:
            rows = c.execute(
                "SELECT symbol FROM watchlist WHERE user_id=? ORDER BY added_ts ASC",
                (user_id,)
            ).fetchall()
        syms = [r["symbol"] for r in rows]
        # Seed defaults for new users
        if not syms:
            for sym in DEFAULT_SYMS:
                _add_symbol(user_id, sym)
            return list(DEFAULT_SYMS)
        return syms
    except Exception as e:
        logger.warning(f"get_watchlist failed: {e}")
        return list(DEFAULT_SYMS)


def _add_symbol(user_id: str, symbol: str) -> bool:
    try:
        with _get_conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO watchlist (user_id, symbol, added_ts) VALUES (?,?,?)",
                (user_id, symbol.upper().strip(), int(time.time())),
            )
        return True
    except Exception as e:
        logger.warning(f"add_symbol failed: {e}")
        return False


def add_watchlist_symbol(user_id: str, symbol: str) -> dict:
    sym = symbol.upper().strip()
    ok = _add_symbol(user_id, sym)
    return {"added": ok, "symbol": sym, "user_id": user_id,
            "message": f"{sym} added to watchlist" if ok else "Already in watchlist or error"}


def remove_watchlist_symbol(user_id: str, symbol: str) -> dict:
    sym = symbol.upper().strip()
    try:
        with _get_conn() as c:
            result = c.execute(
                "DELETE FROM watchlist WHERE user_id=? AND symbol=?",
                (user_id, sym)
            )
        deleted = result.rowcount > 0
        return {"deleted": deleted, "symbol": sym, "user_id": user_id}
    except Exception as e:
        logger.warning(f"remove_watchlist_symbol failed: {e}")
        return {"deleted": False, "symbol": sym, "user_id": user_id}
