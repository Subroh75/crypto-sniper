"""
signal_tracker.py
──────────────────
Records every BUY / STRONG BUY signal the bot posts, then tracks
price outcome at 4H, 24H, 48H, and 72H.

Schema
──────
signals(
    id            INTEGER PRIMARY KEY,
    fired_at      INTEGER,   -- Unix timestamp when signal posted
    source        TEXT,      -- "cex" | "dex"
    chain         TEXT,      -- "BSC" | "ETH" etc  (dex only, else "CEX")
    symbol        TEXT,      -- e.g. "BTC" or "UB/USDC"
    address       TEXT,      -- contract address (dex only)
    pool          TEXT,      -- pool address (dex only)
    dex_id        TEXT,      -- "pancakeswap" etc (dex only)
    interval      TEXT,      -- "1h" | "1d"
    signal_label  TEXT,      -- "BUY" | "STRONG BUY"
    score         INTEGER,   -- legacy 0-13 score
    entry_price   REAL,      -- price at time of signal
    stop_price    REAL,      -- -5% from entry
    target_price  REAL,      -- +10% from entry
    -- gate snapshots
    v_confirmed   INTEGER,
    t_confirmed   INTEGER,
    adx_confirmed INTEGER,
    p_confirmed   INTEGER,
    r_confirmed   INTEGER,
    rel_vol       REAL,
    -- outcome tracking
    price_4h      REAL,
    price_24h     REAL,
    price_48h     REAL,
    price_72h     REAL,
    pct_4h        REAL,
    pct_24h       REAL,
    pct_48h       REAL,
    pct_72h       REAL,
    outcome       TEXT,      -- "WIN" | "LOSS" | "INCONCLUSIVE" | NULL (pending)
    resolved_at   INTEGER,   -- when outcome was determined
    resolved_pct  REAL,      -- % gain/loss at resolution
    resolved_hrs  REAL,      -- hours from signal to resolution
    notes         TEXT       -- any extra context
)
"""

import os
import sqlite3
import logging
import time
from datetime import datetime, timezone
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# DB lives alongside the bot — persists across redeploys via Render disk
DB_PATH = os.environ.get("TRACKER_DB_PATH", "/opt/render/project/src/signal_tracker.db")

# Fallback for local dev
if not os.path.exists(os.path.dirname(DB_PATH)):
    DB_PATH = os.path.join(os.path.dirname(__file__), "signal_tracker.db")

# Price check schedule (hours after signal)
CHECK_HOURS = [4, 24, 48, 72]

# Win/loss thresholds — must hit target or stop within 72h
WIN_PCT  =  10.0   # +10% = WIN
LOSS_PCT =  -5.0   # -5%  = LOSS


# ── DB helpers ────────────────────────────────────────────────────────────────

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def init_tracker():
    """Create table if not exists. Call once at bot startup."""
    with _conn() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                fired_at      INTEGER NOT NULL,
                source        TEXT    NOT NULL,
                chain         TEXT    NOT NULL DEFAULT 'CEX',
                symbol        TEXT    NOT NULL,
                address       TEXT    DEFAULT '',
                pool          TEXT    DEFAULT '',
                dex_id        TEXT    DEFAULT '',
                interval      TEXT    DEFAULT '1h',
                signal_label  TEXT    NOT NULL,
                score         INTEGER DEFAULT 0,
                entry_price   REAL    NOT NULL,
                stop_price    REAL    NOT NULL,
                target_price  REAL    NOT NULL,
                v_confirmed   INTEGER DEFAULT 0,
                t_confirmed   INTEGER DEFAULT 0,
                adx_confirmed INTEGER DEFAULT 0,
                p_confirmed   INTEGER DEFAULT 0,
                r_confirmed   INTEGER DEFAULT 0,
                rel_vol       REAL    DEFAULT 0,
                price_4h      REAL,
                price_24h     REAL,
                price_48h     REAL,
                price_72h     REAL,
                pct_4h        REAL,
                pct_24h       REAL,
                pct_48h       REAL,
                pct_72h       REAL,
                outcome       TEXT,
                resolved_at   INTEGER,
                resolved_pct  REAL,
                resolved_hrs  REAL,
                notes         TEXT    DEFAULT ''
            )
        """)
        # Index for fast pending lookups
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_pending
            ON signals(outcome, fired_at)
            WHERE outcome IS NULL
        """)
    logger.info(f"[Tracker] DB initialised at {DB_PATH}")


# ── Record a new signal ───────────────────────────────────────────────────────

def record_signal(
    source: str,          # "cex" | "dex"
    symbol: str,
    entry_price: float,
    signal_label: str,
    score: int = 0,
    interval: str = "1h",
    chain: str = "CEX",
    address: str = "",
    pool: str = "",
    dex_id: str = "",
    v_confirmed: bool = False,
    t_confirmed: bool = False,
    adx_confirmed: bool = False,
    p_confirmed: bool = False,
    r_confirmed: bool = False,
    rel_vol: float = 0.0,
) -> int:
    """Insert a new signal. Returns row id."""
    stop_price   = round(entry_price * 0.95, 8)
    target_price = round(entry_price * 1.10, 8)

    with _conn() as con:
        cur = con.execute("""
            INSERT INTO signals (
                fired_at, source, chain, symbol, address, pool, dex_id,
                interval, signal_label, score, entry_price, stop_price, target_price,
                v_confirmed, t_confirmed, adx_confirmed, p_confirmed, r_confirmed, rel_vol
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            int(time.time()), source, chain, symbol, address, pool, dex_id,
            interval, signal_label, score, entry_price, stop_price, target_price,
            int(v_confirmed), int(t_confirmed), int(adx_confirmed),
            int(p_confirmed), int(r_confirmed), rel_vol,
        ))
        sig_id = cur.lastrowid

    logger.info(f"[Tracker] Recorded {source.upper()} signal #{sig_id}: {symbol} {signal_label} @ {entry_price}")
    return sig_id


# ── Get signals needing price checks ─────────────────────────────────────────

def get_pending_signals() -> list[dict]:
    """
    Returns all signals that:
    - Have no outcome yet (still within 72h window)
    - Were fired within the last 73h (give 1h grace)
    """
    cutoff = int(time.time()) - (73 * 3600)
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM signals
            WHERE outcome IS NULL
            AND fired_at > ?
            ORDER BY fired_at ASC
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


def get_expired_pending() -> list[dict]:
    """Signals older than 72h with no outcome — mark as INCONCLUSIVE."""
    cutoff = int(time.time()) - (72 * 3600)
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM signals
            WHERE outcome IS NULL
            AND fired_at <= ?
        """, (cutoff,)).fetchall()
    return [dict(r) for r in rows]


# ── Update price check ────────────────────────────────────────────────────────

def update_price_check(sig_id: int, hours: int, current_price: float, entry_price: float):
    """Store the price at a specific checkpoint (4h, 24h, 48h, 72h)."""
    pct = round((current_price - entry_price) / entry_price * 100, 2) if entry_price else 0
    col_price = f"price_{hours}h"
    col_pct   = f"pct_{hours}h"

    # Validate column name to prevent injection
    if col_price not in ("price_4h","price_24h","price_48h","price_72h"):
        return

    with _conn() as con:
        con.execute(
            f"UPDATE signals SET {col_price}=?, {col_pct}=? WHERE id=?",
            (current_price, pct, sig_id)
        )
    logger.debug(f"[Tracker] #{sig_id} {hours}H check: {current_price:.6g} ({pct:+.2f}%)")


def resolve_signal(sig_id: int, outcome: str, current_price: float, entry_price: float):
    """Mark a signal as WIN / LOSS / INCONCLUSIVE."""
    now  = int(time.time())
    pct  = round((current_price - entry_price) / entry_price * 100, 2) if entry_price else 0

    with _conn() as con:
        row = con.execute("SELECT fired_at FROM signals WHERE id=?", (sig_id,)).fetchone()
        hrs = round((now - row["fired_at"]) / 3600, 1) if row else 0
        con.execute("""
            UPDATE signals
            SET outcome=?, resolved_at=?, resolved_pct=?, resolved_hrs=?
            WHERE id=?
        """, (outcome, now, pct, hrs, sig_id))

    logger.info(f"[Tracker] #{sig_id} resolved: {outcome} @ {pct:+.2f}% in {hrs}h")


# ── Stats ─────────────────────────────────────────────────────────────────────

def get_track_record(source: str | None = None, days: int = 30) -> dict:
    """
    Returns cumulative stats for the track record.
    source: "cex" | "dex" | None (all)
    """
    cutoff = int(time.time()) - (days * 86400)
    source_filter = "AND source=?" if source else ""
    params = [cutoff] + ([source] if source else [])

    with _conn() as con:
        rows = con.execute(f"""
            SELECT * FROM signals
            WHERE fired_at > ?
            {source_filter}
            AND outcome IS NOT NULL
            ORDER BY fired_at DESC
        """, params).fetchall()

    records = [dict(r) for r in rows]

    wins   = [r for r in records if r["outcome"] == "WIN"]
    losses = [r for r in records if r["outcome"] == "LOSS"]
    incon  = [r for r in records if r["outcome"] == "INCONCLUSIVE"]
    total  = len(records)

    win_rate   = round(len(wins) / total * 100, 1) if total else 0
    avg_win    = round(sum(r["resolved_pct"] for r in wins)   / len(wins),   2) if wins   else 0
    avg_loss   = round(sum(r["resolved_pct"] for r in losses) / len(losses), 2) if losses else 0
    avg_win_h  = round(sum(r["resolved_hrs"] for r in wins)   / len(wins),   1) if wins   else 0
    best       = max(records, key=lambda r: r["resolved_pct"] or 0) if records else None
    worst      = min(records, key=lambda r: r["resolved_pct"] or 0) if records else None

    # Pending (not yet resolved)
    pending_rows = con if False else None  # re-query
    with _conn() as con2:
        pending = con2.execute("""
            SELECT COUNT(*) as n FROM signals
            WHERE outcome IS NULL AND fired_at > ?
        """, (cutoff,)).fetchone()["n"]

    return {
        "total":      total,
        "wins":       len(wins),
        "losses":     len(losses),
        "inconclusive": len(incon),
        "pending":    pending,
        "win_rate":   win_rate,
        "avg_win":    avg_win,
        "avg_loss":   avg_loss,
        "avg_win_hrs": avg_win_h,
        "best":       dict(best)  if best  else None,
        "worst":      dict(worst) if worst else None,
        "records":    records[:20],   # last 20 for display
    }


def get_recent_resolved(n: int = 5) -> list[dict]:
    """Last N resolved signals for the outcome poster."""
    with _conn() as con:
        rows = con.execute("""
            SELECT * FROM signals
            WHERE outcome IS NOT NULL
            ORDER BY resolved_at DESC
            LIMIT ?
        """, (n,)).fetchall()
    return [dict(r) for r in rows]
