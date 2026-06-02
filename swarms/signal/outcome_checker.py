"""
swarms/signal/outcome_checker.py
─────────────────────────────────────────────────────────────
Supabase-native outcome checker for the Crypto-Swarm.

Replaces the SQLite-based telegram_bot.signal_tracker.check_outcomes()
with a direct Supabase implementation. Only touches signals written
by the swarm (department='signal', source='cex').

RESOLUTION LOGIC:
  WIN           → current price >= target_price within 72h
  LOSS          → current price <= stop_price within 72h
  INCONCLUSIVE  → neither hit after 72h window expires

PRICE CHECKPOINTS:
  pct_4h, pct_24h, pct_48h, pct_72h written as each window passes.

PRICE SOURCE:
  MEXC → Binance fallback (same chain as signal engine).
  No API key required for simple price checks.

CALLED BY:
  swarms/signal/scheduler.py → run_outcome_checker() every 30 min.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import aiohttp

from swarm.db import get_db, server_now

logger = logging.getLogger("signal.outcome_checker")

# Hours at which we snapshot price (for track record charts)
CHECK_HOURS = [4, 24, 48, 72]

# ── Price fetch ────────────────────────────────────────────────────

async def _fetch_price(
    symbol: str,
    session: aiohttp.ClientSession,
) -> Optional[float]:
    """
    Fetch current USDT price for a symbol.
    MEXC first, Binance fallback — matches signal engine data sources.
    """
    endpoints = [
        f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}USDT",
        f"https://data-api.binance.vision/api/v3/ticker/price?symbol={symbol}USDT",
    ]
    for url in endpoints:
        try:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    price = float(data.get("price", 0))
                    if price > 0:
                        return price
        except Exception:
            continue
    return None


async def _fetch_prices_batch(symbols: list[str]) -> dict[str, float]:
    """Fetch prices for all unique symbols concurrently."""
    sem = asyncio.Semaphore(10)

    async def fetch_one(sym: str, session: aiohttp.ClientSession) -> tuple[str, Optional[float]]:
        async with sem:
            price = await _fetch_price(sym, session)
            return sym, price

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *[fetch_one(sym, session) for sym in symbols],
            return_exceptions=True,
        )

    prices = {}
    for r in results:
        if isinstance(r, tuple):
            sym, price = r
            if price:
                prices[sym] = price
    return prices


# ── Core checker ───────────────────────────────────────────────────

async def check_outcomes() -> int:
    """
    Resolve pending signals in Supabase signals table.
    Returns count of newly resolved signals.

    Only processes signals with:
      - department = 'signal'  (written by swarm orchestrator)
      - source     = 'cex'
      - outcome    IS NULL
    """
    now = server_now()
    window_73h = now - (73 * 3600)   # 73h = 72h window + 1h grace
    window_72h = now - (72 * 3600)
    resolved_count = 0

    try:
        db = get_db()

        # ── Pending signals (within 72h window) ───────────────────
        pending = (
            db.table("signals")
            .select("*")
            .is_("outcome", "null")
            .eq("source", "cex")
            .eq("department", "signal")
            .gt("fired_at", window_73h)
            .execute()
        ).data or []

        # ── Expired signals (>72h, still unresolved) ──────────────
        expired = (
            db.table("signals")
            .select("id, symbol, entry_price, fired_at")
            .is_("outcome", "null")
            .eq("source", "cex")
            .eq("department", "signal")
            .lte("fired_at", window_72h)
            .execute()
        ).data or []

        logger.info(
            f"[OutcomeChecker] {len(pending)} pending  "
            f"{len(expired)} expired"
        )

        # ── Mark expired as INCONCLUSIVE ──────────────────────────
        for row in expired:
            try:
                db.table("signals").update({
                    "outcome":     "INCONCLUSIVE",
                    "resolved_at": now,
                    "resolved_pct": 0.0,
                }).eq("id", row["id"]).execute()
                resolved_count += 1
                logger.info(
                    f"[OutcomeChecker] #{row['id']} {row['symbol']} "
                    f"→ INCONCLUSIVE (72h expired)"
                )
            except Exception as e:
                logger.error(f"[OutcomeChecker] Failed to mark INCONCLUSIVE #{row['id']}: {e}")

        if not pending:
            return resolved_count

        # ── Fetch current prices for all pending symbols ──────────
        symbols = list({r["symbol"] for r in pending})
        prices  = await _fetch_prices_batch(symbols)

        logger.info(
            f"[OutcomeChecker] Prices fetched: "
            f"{len(prices)}/{len(symbols)} symbols"
        )

        # ── Evaluate each pending signal ──────────────────────────
        for row in pending:
            sym          = row["symbol"]
            current_price = prices.get(sym)

            if not current_price:
                logger.debug(f"[OutcomeChecker] #{row['id']} {sym}: no price — skipping")
                continue

            entry  = float(row.get("entry_price") or 0)
            stop   = float(row.get("stop_price")  or 0)
            target = float(row.get("target_price") or 0)
            fired  = int(row.get("fired_at") or 0)

            if not entry:
                continue

            pct           = round((current_price - entry) / entry * 100, 2)
            hours_elapsed = (now - fired) / 3600

            # ── Update price checkpoint columns as windows pass ───
            checkpoint_updates = {}
            for h in CHECK_HOURS:
                pct_col   = f"pct_{h}h"
                price_col = f"price_{h}h"
                if hours_elapsed >= h and row.get(pct_col) is None:
                    checkpoint_updates[pct_col]   = pct
                    # price_Xh may not exist in schema — safe to skip
                    try:
                        checkpoint_updates[price_col] = current_price
                    except Exception:
                        pass

            if checkpoint_updates:
                try:
                    db.table("signals").update(
                        checkpoint_updates
                    ).eq("id", row["id"]).execute()
                except Exception as e:
                    logger.debug(f"[OutcomeChecker] Checkpoint update failed #{row['id']}: {e}")

            # ── WIN: price reached target ─────────────────────────
            if target and current_price >= target:
                try:
                    db.table("signals").update({
                        "outcome":      "WIN",
                        "resolved_at":  now,
                        "resolved_pct": pct,
                    }).eq("id", row["id"]).execute()
                    resolved_count += 1
                    logger.info(
                        f"[OutcomeChecker] #{row['id']} {sym} "
                        f"→ WIN {pct:+.2f}% "
                        f"(target ${target:.4f} hit)"
                    )
                except Exception as e:
                    logger.error(f"[OutcomeChecker] WIN update failed #{row['id']}: {e}")
                continue

            # ── LOSS: price hit stop ──────────────────────────────
            if stop and current_price <= stop:
                try:
                    db.table("signals").update({
                        "outcome":      "LOSS",
                        "resolved_at":  now,
                        "resolved_pct": pct,
                    }).eq("id", row["id"]).execute()
                    resolved_count += 1
                    logger.info(
                        f"[OutcomeChecker] #{row['id']} {sym} "
                        f"→ LOSS {pct:+.2f}% "
                        f"(stop ${stop:.4f} hit)"
                    )
                except Exception as e:
                    logger.error(f"[OutcomeChecker] LOSS update failed #{row['id']}: {e}")
                continue

            logger.debug(
                f"[OutcomeChecker] #{row['id']} {sym} "
                f"OPEN  price=${current_price:.4f}  "
                f"pct={pct:+.2f}%  "
                f"elapsed={hours_elapsed:.1f}h"
            )

        return resolved_count

    except Exception as e:
        logger.error(f"[OutcomeChecker] Fatal error: {e}")
        return 0
