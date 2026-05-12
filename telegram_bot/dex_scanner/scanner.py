"""
dex_scanner/scanner.py
───────────────────────
Orchestrator — spawns all chain agents in parallel, writes to blackboard,
sends the Telegram sweep message.

  22:00 UTC (8 AM AEST)  →  daily sweep only — tighter filters, top 5 per chain
  Hourly DEX removed     →  too noisy, pump & dump false positives on short TFs

Also exposes:
  gem_lookup(address, bot, chat_id)  — single-token /gem command handler
  get_last_sweep()                   — cached last sweep board + time
  SUPPORTED_CHAINS                   — list of active chain IDs
"""

import asyncio
import logging
import aiohttp
from datetime import datetime, timezone
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dex_scanner.blackboard import Blackboard, compose_no_pair
from signal_tracker import record_signal
from dex_scanner.chains.agent_bsc  import BSCAgent
from dex_scanner.chains.agent_base import BASEAgent
from dex_scanner.chains.agent_eth  import ETHAgent
from dex_scanner.chains.agent_sol  import SOLAgent
from dex_scanner.chains.agent_arb  import ARBAgent

logger = logging.getLogger(__name__)

# ── Active chain agents ───────────────────────────────────────────────────────
AGENTS = [
    BSCAgent(),
    BASEAgent(),
    ETHAgent(),
    SOLAgent(),
    ARBAgent(),
]

SUPPORTED_CHAINS = [a.chain_id for a in AGENTS]

# ── Scan mode config ──────────────────────────────────────────────────────────
DAILY_HOUR_UTC = 22   # 8 AM AEST — use tighter daily filters at this UTC hour

# Daily mode: stricter filters — only the clearest setups
DAILY_TOP_N    = 5    # top N per chain
DAILY_MIN_LIQ_MULT  = 2.0   # 2× the chain's base min_liq
DAILY_MIN_VOL_MULT  = 2.0   # 2× the chain's base min_vol
DAILY_MIN_AGE_H     = 72    # older pairs only (3 days+)
DAILY_MIN_TXNS      = 100   # higher activity threshold

# Hourly mode: standard filters — fresher, more coins
HOURLY_TOP_N   = 5    # top N per chain
# (uses each agent's default min_liq, min_vol, min_age_h, min_txns_1h)

# ── Last sweep cache — persists between JobQueue runs ─────────────────────────
_last_sweep_board: Blackboard | None = None
_last_sweep_time:  str               = "Never"


def get_last_sweep() -> tuple[Blackboard | None, str]:
    return _last_sweep_board, _last_sweep_time


# ────────────────────────────────────────────────────────────────────────────
# HOURLY/DAILY SWEEP JOB — registered with python-telegram-bot JobQueue
# ────────────────────────────────────────────────────────────────────────────

async def dex_scan_job(context) -> None:
    """
    JobQueue callback — fires once per day at 22:00 UTC (8 AM AEST).

    Daily-only: tighter filters, cleaner signals, no intraday noise.
    Hourly DEX scans removed — too many pump & dump false positives on short TFs.
    """
    global _last_sweep_board, _last_sweep_time

    bot       = context.bot
    chat_id   = context.job.data.get("chat_id")
    now_utc   = datetime.now(timezone.utc)
    scan_time = now_utc.strftime("%d %b %Y %H:%M UTC")

    is_daily = True   # always daily mode now
    mode     = "DAILY"
    top_n    = DAILY_TOP_N

    logger.info(f"[DEX Scanner] Starting DAILY sweep — {scan_time}")

    board = Blackboard()
    for agent in AGENTS:
        board.register_chain(agent.chain_id)

    async with aiohttp.ClientSession() as session:
        tasks = [
            _run_agent(agent, session, board, is_daily=is_daily, top_n=top_n)
            for agent in AGENTS
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    # Cache for /gems command
    _last_sweep_board = board
    _last_sweep_time  = scan_time

    s   = board.summary()
    msg = board.compose_sweep(top_n=top_n * len(AGENTS), mode=mode)

    logger.info(
        f"[DEX Scanner] {mode} sweep done — "
        f"{s['total_hits']} hits, {s['elapsed_s']}s"
    )

    if not chat_id:
        logger.warning("[DEX Scanner] No chat_id in job data — skipping send")
        return

    try:
        if len(msg) <= 4096:
            await bot.send_message(chat_id=chat_id, text=msg)
        else:
            for chunk in _split_msg(msg):
                await bot.send_message(chat_id=chat_id, text=chunk)
    except Exception as e:
        logger.error(f"[DEX Scanner] Telegram send failed: {e}")

    # Record BUY / STRONG BUY hits for signal quality tracking
    hits = board.all_hits(top_n=top_n * len(AGENTS))
    for hit in hits:
        if hit.get("signal") not in ("BUY", "STRONG BUY"):
            continue
        try:
            price = hit.get("price", 0)
            if price <= 0:
                continue
            gates = hit.get("gates") or {}
            # ATR from trade_setup (DEX uses 24h range / 4 as proxy)
            trade_s = hit.get("trade_setup") or {}
            atr_dex = float(trade_s.get("atr") or 0)
            record_signal(
                source        = "dex",
                symbol        = hit.get("symbol", "?"),
                entry_price   = price,
                signal_label  = hit.get("signal", "BUY"),
                score         = hit.get("score", 0),
                interval      = "1d" if is_daily else "1h",
                chain         = hit.get("chain", "bsc").upper(),
                address       = hit.get("address", ""),
                pool          = hit.get("pool_address", ""),
                dex_id        = hit.get("dex", ""),
                v_confirmed   = bool(gates.get("v", False)),
                t_confirmed   = bool(gates.get("t", False)),
                adx_confirmed = bool(gates.get("adx", False)),
                p_confirmed   = False,  # not tracked at sweep level
                r_confirmed   = False,
                rel_vol       = float(hit.get("rel_vol", 0)),
                atr           = atr_dex,
                z_price       = float(hit.get("z_price", 0)),
            )
        except Exception as e:
            logger.warning(f"[DEX Scanner] Tracker record failed for {hit.get('symbol','?')}: {e}")


async def _run_agent(
    agent,
    session: aiohttp.ClientSession,
    board: Blackboard,
    is_daily: bool = False,
    top_n: int = 5,
) -> None:
    """
    Run one chain agent with a hard 45s timeout.
    Daily mode: temporarily tighten the agent's filters before scanning.
    """
    # Stash originals
    orig_liq   = agent.min_liq
    orig_vol   = agent.min_vol
    orig_age   = agent.min_age_h
    orig_txns  = agent.min_txns_1h

    if is_daily:
        agent.min_liq     = orig_liq  * DAILY_MIN_LIQ_MULT
        agent.min_vol     = orig_vol  * DAILY_MIN_VOL_MULT
        agent.min_age_h   = max(orig_age, DAILY_MIN_AGE_H)
        agent.min_txns_1h = max(orig_txns, DAILY_MIN_TXNS)

    try:
        hits = await asyncio.wait_for(
            agent.scan(session, top_n=top_n),
            timeout=45
        )
        board.write(agent.chain_id, hits)
    except asyncio.TimeoutError:
        logger.warning(f"[{agent.chain_id.upper()}] Timed out after 45s")
        board.fail(agent.chain_id)
    except Exception as e:
        logger.error(f"[{agent.chain_id.upper()}] Agent error: {e}")
        board.fail(agent.chain_id)
    finally:
        # Always restore original filters
        agent.min_liq     = orig_liq
        agent.min_vol     = orig_vol
        agent.min_age_h   = orig_age
        agent.min_txns_1h = orig_txns


# ────────────────────────────────────────────────────────────────────────────
# SINGLE TOKEN LOOKUP — /gem command
# ────────────────────────────────────────────────────────────────────────────

async def gem_lookup(
    address_or_name: str,
    bot,
    chat_id: int,
    preferred_chain: str | None = None,
) -> None:
    """
    Resolve an address or token name, run all checks via the appropriate
    chain agent, and send the result.
    """
    query = address_or_name.strip()

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🔍 Scanning {query[:20]}{'...' if len(query) > 20 else ''}...\n"
            "Running market · risk · signal checks"
        )
    )

    async with aiohttp.ClientSession() as session:
        hit = None

        if preferred_chain:
            agent = _agent_by_chain(preferred_chain)
            if agent:
                try:
                    hit = await asyncio.wait_for(
                        agent.analyse_address(session, query),
                        timeout=25
                    )
                except Exception:
                    pass

        if not hit:
            tasks = [
                asyncio.wait_for(agent.analyse_address(session, query), timeout=25)
                for agent in AGENTS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            candidates = [r for r in results if isinstance(r, dict) and r is not None]
            if candidates:
                hit = max(candidates, key=lambda x: x.get("liquidity", 0))

    if not hit:
        msg = compose_no_pair(query, SUPPORTED_CHAINS)
    else:
        board = Blackboard()
        msg   = board.compose_single(hit)

    try:
        if len(msg) <= 4096:
            await bot.send_message(chat_id=chat_id, text=msg)
        else:
            for chunk in _split_msg(msg):
                await bot.send_message(chat_id=chat_id, text=chunk)
    except Exception as e:
        logger.error(f"[DEX Scanner] gem_lookup send failed: {e}")


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _agent_by_chain(chain_id: str):
    for a in AGENTS:
        if a.chain_id.lower() == chain_id.lower():
            return a
    return None


def _split_msg(msg: str, limit: int = 4096) -> list[str]:
    chunks = []
    while msg:
        chunks.append(msg[:limit])
        msg = msg[limit:]
    return chunks
