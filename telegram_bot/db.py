"""
Persistent SQLite store — maps Telegram user IDs to verified emails,
stores conversation history for escalation transcripts.
"""
import aiosqlite
import os

DB_PATH = os.environ.get("DB_PATH", "/data/bot.db")


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id   INTEGER PRIMARY KEY,
                first_name    TEXT,
                username      TEXT,
                email         TEXT,
                verified_at   TEXT,
                tier          TEXT DEFAULT 'free'
            )
        """)
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
