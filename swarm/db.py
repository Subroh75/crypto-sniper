"""
swarm/db.py
───────────────────────────────────────────────
Supabase client singleton for the entire platform.

Every module imports from here:
    from swarm.db import db

Never instantiate supabase directly anywhere else.
This ensures one connection pool, one config point,
and easy mocking in tests.
"""

from __future__ import annotations
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client = None


def get_db():
    """
    Return the Supabase client singleton.
    Initialised once on first call, reused forever.
    Raises RuntimeError if env vars are missing.
    """
    global _client
    if _client is None:
        try:
            from supabase import create_client, Client
            url: str = os.environ["SUPABASE_URL"]
            key: str = os.environ["SUPABASE_KEY"]
            _client = create_client(url, key)
            logger.info("Supabase client initialised")
        except KeyError as e:
            raise RuntimeError(
                f"Missing env var: {e}. "
                f"Set SUPABASE_URL and SUPABASE_KEY in Render."
            ) from e
        except Exception as e:
            raise RuntimeError(
                f"Supabase init failed: {e}"
            ) from e
    return _client


# ── Convenience alias used everywhere ─────────────────
db = get_db


# ── Health check ───────────────────────────────────────
def ping() -> bool:
    """
    Verify Supabase is reachable.
    Called by agent health checks and /health endpoint.
    Returns True if OK, False if not.
    """
    try:
        get_db().table("agent_health").select("id").limit(1).execute()
        return True
    except Exception as e:
        logger.error(f"Supabase ping failed: {e}")
        return False


# ── Safe upsert helper ─────────────────────────────────
def upsert(table: str, payload: dict, conflict: str) -> Optional[dict]:
    """
    Upsert a single row. Returns data or None on error.
    conflict = comma-separated unique columns e.g. 'department,agent,namespace'
    """
    try:
        res = (
            get_db()
            .table(table)
            .upsert(payload, on_conflict=conflict)
            .execute()
        )
        return res.data
    except Exception as e:
        logger.error(f"upsert({table}) failed: {e}")
        return None


# ── Safe insert helper ─────────────────────────────────
def insert(table: str, payload: dict) -> Optional[dict]:
    """Insert a single row. Returns data or None on error."""
    try:
        res = get_db().table(table).insert(payload).execute()
        return res.data
    except Exception as e:
        logger.error(f"insert({table}) failed: {e}")
        return None


# ── Safe select helper ─────────────────────────────────
def select(
    table: str,
    filters: Optional[dict] = None,
    order_by: Optional[str] = None,
    desc: bool = False,
    limit: Optional[int] = None,
) -> list[dict]:
    """
    Select rows with optional filters, ordering, limit.
    Always returns a list (empty on error).

    Example:
        rows = select(
            'signals',
            filters={'symbol': 'BTC', 'outcome': None},
            order_by='fired_at',
            desc=True,
            limit=100
        )
    """
    try:
        q = get_db().table(table).select("*")
        if filters:
            for col, val in filters.items():
                if val is None:
                    q = q.is_(col, "null")
                else:
                    q = q.eq(col, val)
        if order_by:
            q = q.order(order_by, desc=desc)
        if limit:
            q = q.limit(limit)
        return q.execute().data or []
    except Exception as e:
        logger.error(f"select({table}) failed: {e}")
        return []


# ── Safe update helper ─────────────────────────────────
def update(
    table: str,
    payload: dict,
    match: dict,
) -> Optional[dict]:
    """
    Update rows matching all conditions in `match`.
    Returns data or None on error.

    Example:
        update('signals',
               payload={'outcome': 'WIN', 'resolved_pct': 8.3},
               match={'id': 42})
    """
    try:
        q = get_db().table(table).update(payload)
        for col, val in match.items():
            q = q.eq(col, val)
        return q.execute().data
    except Exception as e:
        logger.error(f"update({table}) failed: {e}")
        return None
