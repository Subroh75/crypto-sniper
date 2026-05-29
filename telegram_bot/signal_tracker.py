"""
telegram_bot/signal_tracker.py
───────────────────────────────────────────────
Migrated from SQLite (data.db) to Supabase.
Same schema, same logic, same function signatures.
Only the connection layer changed: SQLite to swarm.db.

Benefits:
  Signal history survives every Render deploy
  4H/24H/48H/72H outcome tracking persists
  Markov agent has history to fit on in Week 3
  Partner referral codes attached to every signal
"""

from __future__ import annotations
import logging
import os
import sys
import time
from typing import Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from swarm.db import insert, update, ping

logger = logging.getLogger(__name__)
TABLE = "signals"

# Signal expires after 72 hours with no resolution
EXPIRY_SECONDS = 72 * 3600


def init_db() -> bool:
    ok = ping()
    if ok:
        logger.info("signal_tracker: Supabase OK")
    else:
        logger.error("signal_tracker: Supabase FAILED")
    return ok


def record_signal(
    symbol: str,
    signal_label: str,
    entry_price: float,
    stop_price: float,
    target_price: float,
    score: int = 0,
    source: str = "cex",
    interval: str = "1h",
    exchange: str = "binance",
    chain: Optional[str] = None,
    address: Optional[str] = None,
    pool: Optional[str] = None,
    dex_id: Optional[str] = None,
    v_confirmed: int = 0,
    t_confirmed: int = 0,
    adx_confirmed: int = 0,
    p_confirmed: int = 0,
    r_confirmed: int = 0,
    rel_vol: float = 0.0,
    z_price: float = 0.0,
    conviction: int = 0,
    referral_code: Optional[str] = None,
    partner_id: Optional[int] = None,
) -> Optional[int]:
    payload = {
        "fired_at":      int(time.time()),
        "source":        source,
        "chain":         chain,
        "symbol":        symbol.upper(),
        "address":       address,
        "pool":          pool,
        "dex_id":        dex_id,
        "interval":      interval,
        "signal_label":  signal_label,
        "score":         score,
        "entry_price":   entry_price,
        "stop_price":    stop_price,
        "target_price":  target_price,
        "v_confirmed":   v_confirmed,
        "t_confirmed":   t_confirmed,
        "adx_confirmed": adx_confirmed,
        "p_confirmed":   p_confirmed,
        "r_confirmed":   r_confirmed,
        "rel_vol":       rel_vol,
        "z_price":       z_price,
        "conviction":    conviction,
        "referral_code": referral_code,
        "partner_id":    partner_id,
        "exchange":      exchange,
        "department":    "signal",
    }
    result = insert(TABLE, payload)
    if result:
        new_id = result[0].get("id")
        logger.info(f"Signal recorded: {symbol} {signal_label} id={new_id}")
        return new_id
    return None


def get_pending_signals(max_age_hours: int = 120) -> list[dict]:
    cutoff = int(time.time()) - (max_age_hours * 3600)
    try:
        from swarm.db import get_db
        rows = (
            get_db().table(TABLE).select("*")
            .is_("outcome", "null")
            .gte("fired_at", cutoff)
            .order("fired_at", desc=False)
            .execute()
        )
        return rows.data or []
    except Exception as e:
        logger.error(f"get_pending_signals failed: {e}")
        return []


def update_price_snapshot(
    signal_id: int,
    window: str,
    current_price: float,
) -> None:
    try:
        from swarm.db import get_db
        row = (
            get_db().table(TABLE).select("entry_price")
            .eq("id", signal_id).single().execute()
        )
        if not row.data:
            return
        entry = row.data["entry_price"]
        pct = round((current_price - entry) / entry * 100, 2) if entry else 0
        update(TABLE,
               payload={f"pct_{window}": pct},
               match={"id": signal_id})
    except Exception as e:
        logger.error(f"update_price_snapshot({signal_id}, {window}) failed: {e}")


def resolve_signal(
    signal_id: int,
    outcome: str,
    resolved_pct: float,
    resolved_at: Optional[int] = None,
) -> None:
    update(TABLE,
           payload={
               "outcome":      outcome,
               "resolved_pct": resolved_pct,
               "resolved_at":  resolved_at or int(time.time()),
           },
           match={"id": signal_id})
    logger.info(f"Signal {signal_id} resolved: {outcome} ({resolved_pct}%)")


def _get_current_price(symbol: str) -> Optional[float]:
    """Fetch latest price from CoinGecko (no key required for basic price)."""
    try:
        import requests
        slug = symbol.lower()
        CG_IDS = {
            "btc": "bitcoin", "eth": "ethereum",
            "sol": "solana",  "bnb": "binancecoin",
        }
        cg_id = CG_IDS.get(slug, slug)
        r = requests.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={"ids": cg_id, "vs_currencies": "usd"},
            timeout=10,
        )
        r.raise_for_status()
        return r.json().get(cg_id, {}).get("usd")
    except Exception as e:
        logger.warning(f"_get_current_price({symbol}) failed: {e}")
        return None


def check_outcomes() -> int:
    """
    Resolve WIN / LOSS / EXPIRED on all open signals.
    Called by the scheduler every 30 minutes.
    Returns the number of signals resolved this run.
    """
    pending = get_pending_signals(max_age_hours=120)
    if not pending:
        return 0

    resolved = 0
    now = int(time.time())

    for sig in pending:
        signal_id    = sig.get("id")
        symbol       = sig.get("symbol", "")
        entry_price  = sig.get("entry_price") or 0
        target_price = sig.get("target_price") or 0
        stop_price   = sig.get("stop_price") or 0
        fired_at     = sig.get("fired_at") or 0

        # Expire signals older than EXPIRY_SECONDS
        if now - fired_at >= EXPIRY_SECONDS:
            resolve_signal(signal_id, "EXPIRED", 0.0, resolved_at=now)
            resolved += 1
            continue

        # Skip if prices not set
        if not entry_price or not target_price or not stop_price:
            continue

        current = _get_current_price(symbol)
        if current is None:
            continue

        pct = round((current - entry_price) / entry_price * 100, 2)

        if current >= target_price:
            resolve_signal(signal_id, "WIN", pct, resolved_at=now)
            resolved += 1
        elif current <= stop_price:
            resolve_signal(signal_id, "LOSS", pct, resolved_at=now)
            resolved += 1
        else:
            # Still open — update price snapshots at each window
            age_hours = (now - fired_at) // 3600
            for window in ["4h", "24h", "48h", "72h"]:
                window_h = int(window.replace("h", ""))
                if age_hours >= window_h:
                    update_price_snapshot(signal_id, window, current)

    logger.info(f"check_outcomes: {resolved} resolved out of {len(pending)} pending")
    return resolved
