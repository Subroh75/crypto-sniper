"""
Persistent SQLite store — maps Telegram user IDs to verified emails,
stores conversation history for escalation transcripts.

DEX Scanner additions:
  - users.gem_scans_today     — daily /gem scan counter (free tier = 2/day)
  - users.gem_scans_reset_at  — unix timestamp of last midnight-UTC reset
  - dex_watches               — per-user watchlist of contract addresses
"""
import aiosqlite
import os

DB_PATH = os.environ.get("DB_PATH", "/data/bot.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id        INTEGER PRIMARY KEY,
                first_name         TEXT,
                username           TEXT,
                email              TEXT,
                verified_at        TEXT,
                tier               TEXT DEFAULT 'free',
                gem_scans_today    INTEGER DEFAULT 0,
                gem_scans_reset_at INTEGER DEFAULT 0
            )
        """)
        # ── Migrate existing tables that might be missing the new columns ──
        for col, default in [
            ("gem_scans_today",    "INTEGER DEFAULT 0"),
            ("gem_scans_reset_at", "INTEGER DEFAULT 0"),
            ("lang",               "TEXT DEFAULT 'en'"),
        ]:
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {default}")
            except Exception:
                pass  # column already exists — safe to ignore

        await db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id   INTEGER,
                role          TEXT,   -- 'user' | 'assistant'
                content       TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS escalations (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id   INTEGER,
                summary       TEXT,
                transcript    TEXT,
                resolved      INTEGER DEFAULT 0,
                created_at    TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS dex_watches (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id   INTEGER NOT NULL,
                address       TEXT    NOT NULL,
                symbol        TEXT,
                chain         TEXT,
                added_at      INTEGER DEFAULT (strftime('%s','now')),
                UNIQUE(telegram_id, address)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trend_radar_signals (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol           TEXT    NOT NULL,
                signal_date      TEXT    NOT NULL,  -- YYYY-MM-DD UTC
                label            TEXT,              -- STRONG MOMENTUM / BUILDING MOMENTUM / EARLY TREND
                velocity         REAL,              -- % per day
                vol_ratio        REAL,              -- x above Kalman vol baseline
                entry_price      REAL,
                filter_price     REAL,              -- Kalman filtered price at signal
                price_vs_filter  REAL,              -- % above/below filter
                stop_price       REAL,              -- entry * 0.90
                target_price     REAL,              -- entry * 1.20
                price_5d         REAL    DEFAULT NULL,
                price_10d        REAL    DEFAULT NULL,
                pct_5d           REAL    DEFAULT NULL,
                pct_10d          REAL    DEFAULT NULL,
                outcome_5d       TEXT    DEFAULT 'OPEN',
                outcome_10d      TEXT    DEFAULT 'OPEN',
                created_at       TEXT    DEFAULT (datetime('now'))
            )
        """)
        await db.commit()


async def get_user(telegram_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def upsert_user(telegram_id: int, first_name: str, username: str | None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (telegram_id, first_name, username)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                first_name = excluded.first_name,
                username   = excluded.username
        """, (telegram_id, first_name, username or ""))
        await db.commit()


async def set_user_lang(telegram_id: int, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET lang = ? WHERE telegram_id = ?",
            (lang, telegram_id)
        )
        await db.commit()


async def set_user_email(telegram_id: int, email: str):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users SET email = ?, verified_at = ? WHERE telegram_id = ?
        """, (email, now, telegram_id))
        await db.commit()


async def save_message(telegram_id: int, role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO messages (telegram_id, role, content)
            VALUES (?, ?, ?)
        """, (telegram_id, role, content))
        await db.commit()


async def get_history(telegram_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT role, content FROM messages
            WHERE telegram_id = ?
            ORDER BY created_at DESC LIMIT ?
        """, (telegram_id, limit)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in reversed(rows)]


async def get_transcript(telegram_id: int, limit: int = 30) -> str:
    history = await get_history(telegram_id, limit)
    lines = []
    for m in history:
        role = "User" if m["role"] == "user" else "Bot"
        lines.append(f"{role}: {m['content']}")
    return "\n".join(lines) if lines else "(no prior messages)"


async def save_escalation(telegram_id: int, summary: str, transcript: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO escalations (telegram_id, summary, transcript)
            VALUES (?, ?, ?)
        """, (telegram_id, summary, transcript))
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
#  DEX Scanner — rate limiting helpers
# ─────────────────────────────────────────────────────────────────────────────

async def get_gem_scan_count(telegram_id: int) -> tuple[int, int]:
    """
    Returns (scans_today, reset_at).
    Automatically resets the counter if reset_at is before today's midnight UTC.
    """
    import time
    from datetime import datetime, timezone

    # Midnight UTC today (unix ts)
    now_utc   = datetime.now(timezone.utc)
    midnight  = int(datetime(now_utc.year, now_utc.month, now_utc.day,
                             tzinfo=timezone.utc).timestamp())

    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT gem_scans_today, gem_scans_reset_at FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            return 0, midnight

        scans    = row["gem_scans_today"]    or 0
        reset_at = row["gem_scans_reset_at"] or 0

        # If stored reset_at is before today's midnight → new day, reset counter
        if reset_at < midnight:
            await db.execute("""
                UPDATE users
                SET gem_scans_today = 0, gem_scans_reset_at = ?
                WHERE telegram_id = ?
            """, (midnight, telegram_id))
            await db.commit()
            return 0, midnight

        return scans, reset_at


async def increment_gem_scan(telegram_id: int):
    """Increment today's gem scan counter."""
    from datetime import datetime, timezone
    now_utc  = datetime.now(timezone.utc)
    midnight = int(datetime(now_utc.year, now_utc.month, now_utc.day,
                            tzinfo=timezone.utc).timestamp())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE users
            SET gem_scans_today    = COALESCE(gem_scans_today, 0) + 1,
                gem_scans_reset_at = CASE
                    WHEN COALESCE(gem_scans_reset_at, 0) < ?
                    THEN ?
                    ELSE gem_scans_reset_at
                END
            WHERE telegram_id = ?
        """, (midnight, midnight, telegram_id))
        await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
#  DEX Scanner — watchlist helpers
# ─────────────────────────────────────────────────────────────────────────────

async def add_watch(telegram_id: int, address: str, symbol: str, chain: str) -> bool:
    """
    Add an address to a user's DEX watchlist.
    Returns True if added, False if already watching.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute("""
                INSERT INTO dex_watches (telegram_id, address, symbol, chain)
                VALUES (?, ?, ?, ?)
            """, (telegram_id, address.lower(), symbol.upper(), chain.lower()))
            await db.commit()
            return True
        except Exception:
            return False  # UNIQUE constraint — already watching


async def remove_watch(telegram_id: int, address: str) -> bool:
    """
    Remove an address from a user's watchlist.
    Returns True if removed, False if wasn't watching.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            DELETE FROM dex_watches
            WHERE telegram_id = ? AND address = ?
        """, (telegram_id, address.lower()))
        await db.commit()
        return cur.rowcount > 0


async def get_watches(telegram_id: int) -> list[dict]:
    """Return all watchlist entries for a user, newest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT address, symbol, chain, added_at
            FROM dex_watches
            WHERE telegram_id = ?
            ORDER BY added_at DESC
        """, (telegram_id,)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  Trend Radar — Signal Performance Tracker
# ─────────────────────────────────────────────

async def save_trend_radar_signal(
    symbol: str,
    signal_date: str,
    label: str,
    velocity: float,
    vol_ratio: float,
    entry_price: float,
    filter_price: float,
    price_vs_filter: float,
) -> int:
    """Log a new Trend Radar signal. Returns the new row id."""
    stop_price   = round(entry_price * 0.90, 8)
    target_price = round(entry_price * 1.20, 8)
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO trend_radar_signals
                (symbol, signal_date, label, velocity, vol_ratio,
                 entry_price, filter_price, price_vs_filter,
                 stop_price, target_price)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (symbol, signal_date, label, velocity, vol_ratio,
              entry_price, filter_price, price_vs_filter,
              stop_price, target_price))
        await db.commit()
        return cur.lastrowid


async def get_open_trend_radar_signals() -> list[dict]:
    """Return all signals where either outcome is still OPEN."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM trend_radar_signals
            WHERE outcome_5d = 'OPEN' OR outcome_10d = 'OPEN'
            ORDER BY signal_date DESC
        """) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def update_trend_radar_outcome(
    row_id: int,
    days: int,
    price: float,
    pct: float,
    outcome: str,
) -> None:
    """Update the 5D or 10D outcome for a signal row."""
    col_price   = f"price_{days}d"
    col_pct     = f"pct_{days}d"
    col_outcome = f"outcome_{days}d"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"""
            UPDATE trend_radar_signals
            SET {col_price} = ?, {col_pct} = ?, {col_outcome} = ?
            WHERE id = ?
        """, (price, pct, outcome, row_id))
        await db.commit()


async def get_trend_radar_stats() -> dict:
    """Return aggregated win/loss stats for completed signals."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT
                COUNT(*)                                          AS total,
                SUM(CASE WHEN outcome_10d = 'WIN'  THEN 1 END)   AS wins,
                SUM(CASE WHEN outcome_10d = 'LOSS' THEN 1 END)   AS losses,
                SUM(CASE WHEN outcome_10d = 'OPEN' THEN 1 END)   AS open,
                ROUND(AVG(CASE WHEN outcome_10d != 'OPEN' THEN pct_10d END), 2) AS avg_pct_10d,
                ROUND(AVG(CASE WHEN outcome_5d  != 'OPEN' THEN pct_5d  END), 2) AS avg_pct_5d
            FROM trend_radar_signals
        """) as cur:
            row = await cur.fetchone()
            if not row:
                return {}
            d = dict(row)
            total    = d.get("total", 0) or 0
            wins     = d.get("wins",  0) or 0
            losses   = d.get("losses",0) or 0
            completed = wins + losses
            d["win_rate"] = round(wins / completed * 100, 1) if completed > 0 else None
            return d


async def get_trend_radar_history(limit: int = 30) -> list[dict]:
    """Return last N signals with outcomes, newest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT symbol, signal_date, label, velocity, vol_ratio,
                   entry_price, stop_price, target_price,
                   pct_5d, pct_10d, outcome_5d, outcome_10d
            FROM trend_radar_signals
            ORDER BY signal_date DESC
            LIMIT ?
        """, (limit,)) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
