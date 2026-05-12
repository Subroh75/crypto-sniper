"""
signal_monitor.py
──────────────────
Hourly job that:
1. Fetches current prices for all pending signals
2. Checks if stop (-5%) or target (+10%) was hit
3. Resolves outcomes and posts results to Telegram
4. Posts weekly summary on Sundays at 22:00 UTC (8 AM AEST Monday)

Also exposes:
  format_record_message(source)  — for /record command
"""

import asyncio
import aiohttp
import logging
from datetime import datetime, timezone

from signal_tracker import (
    get_pending_signals, get_expired_pending,
    update_price_check, resolve_signal,
    get_track_record, get_recent_resolved,
    CHECK_HOURS, WIN_PCT, LOSS_PCT,
)

logger = logging.getLogger(__name__)

BINANCE_PRICE_URL = "https://data-api.binance.vision/api/v3/ticker/price?symbol={}USDT"
DEXSCREENER_URL   = "https://api.dexscreener.com/latest/dex/pairs/{}/{}"


# ── Price fetchers ────────────────────────────────────────────────────────────

async def _get_cex_price(session: aiohttp.ClientSession, symbol: str) -> float | None:
    """Fetch current price from Binance for a CEX symbol."""
    try:
        # symbol might be "BTC" → "BTCUSDT"
        sym = symbol.split("/")[0].upper()
        async with session.get(
            BINANCE_PRICE_URL.format(sym),
            timeout=aiohttp.ClientTimeout(total=8)
        ) as r:
            if r.status == 200:
                data = await r.json()
                return float(data.get("price", 0))
    except Exception as e:
        logger.debug(f"[Monitor] CEX price fetch failed {symbol}: {e}")
    return None


async def _get_dex_price(
    session: aiohttp.ClientSession,
    chain: str,
    pool: str,
    address: str,
) -> float | None:
    """Fetch current price from DexScreener for a DEX token."""
    # Try pool address first (more direct)
    if pool:
        try:
            url = DEXSCREENER_URL.format(chain.lower(), pool)
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as r:
                if r.status == 200:
                    data  = await r.json()
                    pairs = data.get("pairs") or []
                    if pairs:
                        return float(pairs[0].get("priceUsd", 0) or 0)
        except Exception as e:
            logger.debug(f"[Monitor] DEX pool price failed {pool}: {e}")

    # Fallback: search by contract address
    if address:
        try:
            async with session.get(
                f"https://api.dexscreener.com/latest/dex/search?q={address}",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 200:
                    data  = await r.json()
                    pairs = [
                        p for p in (data.get("pairs") or [])
                        if p.get("chainId", "").lower() == chain.lower()
                    ]
                    if pairs:
                        best = max(pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0))
                        return float(best.get("priceUsd", 0) or 0)
        except Exception as e:
            logger.debug(f"[Monitor] DEX address price failed {address}: {e}")

    return None


async def _fetch_price(session: aiohttp.ClientSession, sig: dict) -> float | None:
    """Route to correct price source based on signal source."""
    if sig["source"] == "cex":
        return await _get_cex_price(session, sig["symbol"])
    else:
        return await _get_dex_price(
            session,
            chain   = sig.get("chain", "bsc"),
            pool    = sig.get("pool", ""),
            address = sig.get("address", ""),
        )


# ── Outcome checker ───────────────────────────────────────────────────────────

def _hours_since(fired_at: int) -> float:
    return (datetime.now(timezone.utc).timestamp() - fired_at) / 3600


def _which_checkpoint(sig: dict) -> int | None:
    """Return the next checkpoint (hours) that needs a price fill, or None."""
    hrs = _hours_since(sig["fired_at"])
    for h in CHECK_HOURS:
        col = f"price_{h}h"
        if sig.get(col) is None and hrs >= h:
            return h
    return None


def _check_outcome(sig: dict, current_price: float) -> str | None:
    """
    Return "WIN", "LOSS", or None (still tracking).
    Checks if current price has crossed stop or target since signal.
    """
    entry  = sig["entry_price"]
    stop   = sig["stop_price"]
    target = sig["target_price"]

    if not entry or not current_price:
        return None

    pct = (current_price - entry) / entry * 100

    # First threshold crossed wins
    if current_price >= target:
        return "WIN"
    if current_price <= stop:
        return "LOSS"
    return None


# ── Telegram formatters ───────────────────────────────────────────────────────

def _fmt_price(p: float) -> str:
    if p == 0:       return "$0"
    if p < 0.000001: return f"${p:.2e}"
    if p < 0.0001:   return f"${p:.8f}"
    if p < 0.01:     return f"${p:.6f}"
    if p < 1:        return f"${p:.4f}"
    if p < 1000:     return f"${p:.2f}"
    return f"${p:,.0f}"


def _fmt_pct(p: float) -> str:
    return f"{p:+.2f}%"


def format_outcome_message(sig: dict) -> str:
    """Full outcome post — sent when a signal resolves."""
    outcome  = sig["outcome"]
    symbol   = sig["symbol"]
    source   = sig["source"].upper()
    chain    = sig.get("chain", "CEX")
    label    = sig["signal_label"]
    entry    = sig["entry_price"]
    stop     = sig["stop_price"]
    target   = sig["target_price"]
    fired_dt = datetime.fromtimestamp(sig["fired_at"], tz=timezone.utc)
    fired_str = fired_dt.strftime("%d %b %Y %H:%M UTC")
    pct      = sig.get("resolved_pct", 0) or 0
    hrs      = sig.get("resolved_hrs", 0) or 0

    result_icon = "WIN" if outcome == "WIN" else "LOSS" if outcome == "LOSS" else "INCONCLUSIVE"

    lines = [
        f"SIGNAL RESULT — {result_icon}",
        f"{'─' * 34}",
        f"Token:   {symbol}  ({source} · {chain})",
        f"Signal:  {label}  fired {fired_str}",
        f"Entry:   {_fmt_price(entry)}",
        f"Stop:    {_fmt_price(stop)} (-5%)",
        f"Target:  {_fmt_price(target)} (+10%)",
        f"{'─' * 34}",
    ]

    # Checkpoint prices
    for h in CHECK_HOURS:
        p = sig.get(f"price_{h}h")
        pct_h = sig.get(f"pct_{h}h")
        if p is not None:
            indicator = ""
            if pct_h is not None:
                if pct_h >= WIN_PCT:
                    indicator = " TARGET"
                elif pct_h <= LOSS_PCT:
                    indicator = " STOP"
            lines.append(
                f"{str(h)+'H':>4}:   {_fmt_price(p)}  ({_fmt_pct(pct_h)}){indicator}"
            )
        else:
            lines.append(f"{str(h)+'H':>4}:   —")

    lines.append(f"{'─' * 34}")

    if outcome == "WIN":
        lines.append(f"Result:  WIN  {_fmt_pct(pct)} in {hrs:.0f}h")
    elif outcome == "LOSS":
        lines.append(f"Result:  LOSS  {_fmt_pct(pct)} in {hrs:.0f}h")
    else:
        lines.append(f"Result:  INCONCLUSIVE  {_fmt_pct(pct)} after 72h")

    # Append running record
    stats = get_track_record()
    if stats["total"] > 0:
        lines.append(
            f"Record:  {stats['wins']}W / {stats['losses']}L  "
            f"({stats['win_rate']}% win rate)  "
            f"[{stats['total']} signals]"
        )

    lines.append("Not financial advice.")
    return "\n".join(lines)


def format_record_message(source: str | None = None) -> str:
    """For /record command — full track record."""
    stats = get_track_record(source=source, days=30)
    src_label = source.upper() if source else "ALL SIGNALS"

    lines = [
        f"SIGNAL TRACK RECORD — {src_label}",
        f"Last 30 days",
        f"{'─' * 34}",
        f"Total signals:   {stats['total'] + stats['pending']}",
        f"Resolved:        {stats['total']}  (pending: {stats['pending']})",
        f"Wins:            {stats['wins']}",
        f"Losses:          {stats['losses']}",
        f"Inconclusive:    {stats['inconclusive']}",
        f"Win rate:        {stats['win_rate']}%",
    ]

    if stats["avg_win"]:
        lines.append(f"Avg win:         {_fmt_pct(stats['avg_win'])} in {stats['avg_win_hrs']}h avg")
    if stats["avg_loss"]:
        lines.append(f"Avg loss:        {_fmt_pct(stats['avg_loss'])}")

    if stats["best"]:
        b = stats["best"]
        lines.append(f"Best:            {b['symbol']} {_fmt_pct(b['resolved_pct'])} in {b['resolved_hrs']:.0f}h")
    if stats["worst"]:
        w = stats["worst"]
        lines.append(f"Worst:           {w['symbol']} {_fmt_pct(w['resolved_pct'])}")

    lines.append(f"{'─' * 34}")

    # Last 5 resolved
    recent = get_recent_resolved(5)
    if recent:
        lines.append("Recent results:")
        for r in recent:
            icon = "W" if r["outcome"] == "WIN" else "L" if r["outcome"] == "LOSS" else "?"
            lines.append(
                f"  [{icon}] {r['symbol']} {_fmt_pct(r['resolved_pct'] or 0)} — {r['signal_label']} ({r['source'].upper()})"
            )

    lines.append(f"{'─' * 34}")
    lines.append("https://crypto-sniper.app")
    lines.append("Not financial advice.")
    return "\n".join(lines)


def format_weekly_summary() -> str:
    """Sunday weekly digest."""
    stats_all = get_track_record(source=None, days=7)
    stats_cex = get_track_record(source="cex", days=7)
    stats_dex = get_track_record(source="dex", days=7)

    lines = [
        "WEEKLY SIGNAL REPORT",
        f"{'─' * 34}",
        f"Signals fired:   {stats_all['total'] + stats_all['pending']}",
        f"Wins:            {stats_all['wins']}",
        f"Losses:          {stats_all['losses']}",
        f"Inconclusive:    {stats_all['inconclusive']}",
        f"Win rate:        {stats_all['win_rate']}%",
    ]

    if stats_all["avg_win"]:
        lines.append(f"Avg win:         {_fmt_pct(stats_all['avg_win'])} in {stats_all['avg_win_hrs']}h")
    if stats_all["avg_loss"]:
        lines.append(f"Avg loss:        {_fmt_pct(stats_all['avg_loss'])}")

    if stats_all["best"]:
        b = stats_all["best"]
        lines.append(f"Best signal:     {b['symbol']} {_fmt_pct(b['resolved_pct'])} in {b['resolved_hrs']:.0f}h ({b['signal_label']})")

    lines.append(f"{'─' * 34}")

    # CEX vs DEX split
    if stats_cex["total"] or stats_dex["total"]:
        lines.append("By source:")
        if stats_cex["total"]:
            lines.append(f"  CEX: {stats_cex['wins']}W/{stats_cex['losses']}L  {stats_cex['win_rate']}%  avg win {_fmt_pct(stats_cex['avg_win'])}")
        if stats_dex["total"]:
            lines.append(f"  DEX: {stats_dex['wins']}W/{stats_dex['losses']}L  {stats_dex['win_rate']}%  avg win {_fmt_pct(stats_dex['avg_win'])}")

    lines.append(f"{'─' * 34}")
    lines.append("https://crypto-sniper.app")
    lines.append("Not financial advice.")
    return "\n".join(lines)


# ── Main hourly job ───────────────────────────────────────────────────────────

async def signal_monitor_job(context) -> None:
    """
    JobQueue callback — fires every hour.
    - Fetches current prices for all pending signals
    - Fills checkpoint prices (4H, 24H, 48H, 72H)
    - Resolves outcomes and posts to Telegram
    - Marks expired signals as INCONCLUSIVE
    - Posts weekly summary on Monday 22:00 UTC (8 AM AEST Monday)
    """
    bot     = context.bot
    chat_id = context.job.data.get("chat_id")
    now_utc = datetime.now(timezone.utc)

    # ── 1. Expire stale pending signals ─────────────────────────────────
    expired = get_expired_pending()
    for sig in expired:
        # Try to get one final price before marking inconclusive
        try:
            async with aiohttp.ClientSession() as session:
                price = await _fetch_price(session, sig)
        except Exception:
            price = None

        final_price = price or sig["entry_price"]
        resolve_signal(sig["id"], "INCONCLUSIVE", final_price, sig["entry_price"])

        if chat_id:
            # Re-fetch to get all checkpoint data
            from signal_tracker import _conn
            with _conn() as con:
                updated = dict(con.execute("SELECT * FROM signals WHERE id=?", (sig["id"],)).fetchone())
            try:
                msg = format_outcome_message(updated)
                await bot.send_message(chat_id=chat_id, text=msg)
            except Exception as e:
                logger.error(f"[Monitor] Failed to post inconclusive outcome: {e}")

    # ── 2. Check pending signals ─────────────────────────────────────────
    pending = get_pending_signals()
    if not pending:
        logger.debug("[Monitor] No pending signals to check")

        # Still check for weekly summary
        if now_utc.weekday() == 6 and now_utc.hour == 22 and chat_id:  # Sunday 22:00 UTC
            summary = format_weekly_summary()
            try:
                await bot.send_message(chat_id=chat_id, text=summary)
            except Exception as e:
                logger.error(f"[Monitor] Weekly summary send failed: {e}")
        return

    logger.info(f"[Monitor] Checking {len(pending)} pending signals")

    async with aiohttp.ClientSession() as session:
        for sig in pending:
            try:
                current_price = await _fetch_price(session, sig)
                if not current_price:
                    logger.debug(f"[Monitor] No price for signal #{sig['id']} {sig['symbol']}")
                    continue

                entry = sig["entry_price"]

                # ── Fill checkpoint prices ───────────────────────────
                checkpoint = _which_checkpoint(sig)
                if checkpoint:
                    update_price_check(sig["id"], checkpoint, current_price, entry)

                # ── Check for stop/target hit ────────────────────────
                outcome = _check_outcome(sig, current_price)
                if outcome:
                    # Re-fetch updated sig with latest checkpoint data
                    from signal_tracker import _conn
                    with _conn() as con:
                        updated_sig = dict(
                            con.execute("SELECT * FROM signals WHERE id=?", (sig["id"],)).fetchone()
                        )
                    resolve_signal(sig["id"], outcome, current_price, entry)
                    updated_sig["outcome"]      = outcome
                    updated_sig["resolved_pct"] = round((current_price - entry) / entry * 100, 2)
                    updated_sig["resolved_hrs"] = round(_hours_since(sig["fired_at"]), 1)

                    if chat_id:
                        msg = format_outcome_message(updated_sig)
                        try:
                            await bot.send_message(chat_id=chat_id, text=msg)
                            logger.info(f"[Monitor] Posted outcome for #{sig['id']}: {outcome}")
                        except Exception as e:
                            logger.error(f"[Monitor] Outcome post failed: {e}")

                await asyncio.sleep(0.3)  # rate limit

            except Exception as e:
                logger.error(f"[Monitor] Error processing signal #{sig['id']}: {e}")

    # ── 3. Weekly summary ────────────────────────────────────────────────
    if now_utc.weekday() == 6 and now_utc.hour == 22 and chat_id:  # Sunday 22:00 UTC
        summary = format_weekly_summary()
        try:
            await bot.send_message(chat_id=chat_id, text=summary)
            logger.info("[Monitor] Weekly summary posted")
        except Exception as e:
            logger.error(f"[Monitor] Weekly summary failed: {e}")
