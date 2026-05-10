"""
dex_scanner/scanner.py
───────────────────────
Orchestrator — spawns all chain agents in parallel, collects results
onto the blackboard, and sends the Telegram sweep message.

Also exposes:
  gem_lookup(address, bot, chat_id)  — single-token /gem command handler
  get_last_sweep()                   — returns cached last sweep results
  SUPPORTED_CHAINS                   — list of active chain IDs

Wired into the Telegram bot's JobQueue for hourly sweeps.
"""

import asyncio
import logging
import aiohttp
from datetime import datetime, timezone

from dex_scanner.blackboard import Blackboard, compose_no_pair
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

# ── Last sweep cache — persists between JobQueue runs ─────────────────────────
_last_sweep_board: Blackboard | None = None
_last_sweep_time:  str               = "Never"


def get_last_sweep() -> tuple[Blackboard | None, str]:
    return _last_sweep_board, _last_sweep_time


# ────────────────────────────────────────────────────────────────────────────
# HOURLY SWEEP JOB — registered with python-telegram-bot JobQueue
# ────────────────────────────────────────────────────────────────────────────

async def dex_scan_job(context) -> None:
    """
    JobQueue callback — runs every hour.
    Spawns all chain agents in parallel, writes to blackboard,
    composes and sends sweep message.
    """
    global _last_sweep_board, _last_sweep_time

    bot       = context.bot
    chat_id   = context.job.data.get("chat_id")
    scan_time = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    logger.info(f"[DEX Scanner] Starting sweep — {scan_time}")

    board = Blackboard()
    for agent in AGENTS:
        board.register_chain(agent.chain_id)

    async with aiohttp.ClientSession() as session:
        tasks = [_run_agent(agent, session, board) for agent in AGENTS]
        await asyncio.gather(*tasks, return_exceptions=True)

    # Cache for /gems command
    _last_sweep_board = board
    _last_sweep_time  = scan_time

    msg = board.compose_sweep(top_n=10)
    s   = board.summary()
    logger.info(f"[DEX Scanner] Sweep done — {s['total_hits']} hits, {s['elapsed_s']}s")

    if not chat_id:
        logger.warning("[DEX Scanner] No chat_id in job data — skipping send")
        return

    try:
        # Telegram 4096 char limit
        if len(msg) <= 4096:
            await bot.send_message(chat_id=chat_id, text=msg)
        else:
            for chunk in _split_msg(msg):
                await bot.send_message(chat_id=chat_id, text=chunk)
    except Exception as e:
        logger.error(f"[DEX Scanner] Telegram send failed: {e}")


async def _run_agent(agent, session: aiohttp.ClientSession, board: Blackboard) -> None:
    """Run one chain agent with a hard 45s timeout, write results to board."""
    try:
        hits = await asyncio.wait_for(
            agent.scan(session, top_n=5),
            timeout=45
        )
        board.write(agent.chain_id, hits)
    except asyncio.TimeoutError:
        logger.warning(f"[{agent.chain_id.upper()}] Timed out after 45s")
        board.fail(agent.chain_id)
    except Exception as e:
        logger.error(f"[{agent.chain_id.upper()}] Agent error: {e}")
        board.fail(agent.chain_id)


# ────────────────────────────────────────────────────────────────────────────
# SINGLE TOKEN LOOKUP — /gem command
# ────────────────────────────────────────────────────────────────────────────

async def gem_lookup(
    address_or_name: str,
    bot,
    chat_id: int,
    preferred_chain: str | None = None
) -> None:
    """
    Resolve an address or token name, run all three checks (market + risk +
    signal) via the appropriate chain agent, and send the result.

    If preferred_chain is provided (e.g. "sol", "bsc"), try that agent first.
    Otherwise auto-detect via DexScreener cross-chain search.
    """
    query = address_or_name.strip()

    await bot.send_message(
        chat_id=chat_id,
        text=f"🔍 Scanning {query[:20]}{'...' if len(query) > 20 else ''}...\nRunning market · risk · signal checks"
    )

    async with aiohttp.ClientSession() as session:
        hit = None

        # If chain specified, try that agent first
        if preferred_chain:
            agent = _agent_by_chain(preferred_chain)
            if agent:
                hit = await asyncio.wait_for(
                    agent.analyse_address(session, query),
                    timeout=25
                )

        # Auto-detect: try all agents, take best result by liquidity
        if not hit:
            tasks = [
                asyncio.wait_for(agent.analyse_address(session, query), timeout=25)
                for agent in AGENTS
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            candidates = [r for r in results if isinstance(r, dict) and r is not None]
            if candidates:
                # Pick highest liquidity result
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
