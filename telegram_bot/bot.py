"""
Crypto Sniper Telegram Bot
Full agent: CS + crypto Q&A + live /analyse commands + DEX scanner
"""
import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from db import (
    init_db, get_user, upsert_user, set_user_email,
    save_message, get_history, get_transcript, save_escalation,
    get_gem_scan_count, increment_gem_scan,
    add_watch, remove_watch, get_watches,
)
from agent import get_agent_response, extract_analyse_command, extract_escalation
from analyse import fetch_analysis
from escalation import escalate
from scanner import hourly_scan_job

# DEX scanner imports
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from dex_scanner.scanner import dex_scan_job, gem_lookup, get_last_sweep, SUPPORTED_CHAINS
from dex_scanner.blackboard import compose_rate_limited

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN     = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "5861457546"))

# DEX scanner constants
FREE_GEM_DAILY_LIMIT = 2   # free tier: 2 /gem scans per day
MAX_WATCHES          = 5   # free tier: up to 5 addresses watched

# ConversationHandler state
AWAITING_EMAIL = 1


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

async def _typing(update: Update):
    await update.effective_chat.send_action("typing")


def _is_valid_email(s: str) -> bool:
    return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", s.strip()))


def _is_address(s: str) -> bool:
    """Rough check: hex address (EVM) or base58 (Solana)."""
    s = s.strip()
    if re.match(r"^0x[0-9a-fA-F]{40}$", s):
        return True
    if re.match(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$", s):
        return True
    return False


def _get_tier(db_user: dict | None) -> str:
    if not db_user:
        return "free"
    return (db_user.get("tier") or "free").lower()


# ─────────────────────────────────────────────
#  /start
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id

    await upsert_user(user.id, user.first_name, user.username)
    db_user = await get_user(user.id)

    await _typing(update)

    if db_user and db_user.get("email"):
        await update.message.reply_text(
            f"Back online, {user.first_name}.\n\n"
            f"Account: {db_user['email']} | Tier: {db_user.get('tier','free').upper()}\n\n"
            "What do you need?\n"
            "/analyse BTC  — live signal\n"
            "/gem <addr>   — DEX gem scan\n"
            "/gems         — last sweep results\n"
            "/status       — your account\n"
            "/help         — all commands"
        )
        return ConversationHandler.END

    await update.message.reply_text(
        f"Crypto Sniper — support agent online.\n\n"
        f"Hey {user.first_name}. To link your account, send me your email address.\n"
        "Or type /skip to continue without linking."
    )
    return AWAITING_EMAIL


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not _is_valid_email(text):
        await update.message.reply_text(
            "That doesn't look like a valid email. Try again or /skip."
        )
        return AWAITING_EMAIL

    await set_user_email(update.effective_user.id, text.lower())
    await update.message.reply_text(
        f"Linked. Account email set to {text.lower()}.\n\n"
        "Ready. Try:\n"
        "/analyse BTC 1H  — live signal\n"
        "/gem <address>   — DEX gem scan\n"
        "/gems            — last sweep results\n"
        "/status          — account info\n"
        "/help            — all commands\n\n"
        "Or just ask me anything."
    )
    return ConversationHandler.END


async def skip_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "No problem. You can link your email anytime with /link.\n\n"
        "/analyse BTC — live signal\n"
        "/help        — all commands"
    )
    return ConversationHandler.END


# ─────────────────────────────────────────────
#  /help
# ─────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "CRYPTO SNIPER — COMMAND LIST\n"
        "─────────────────────────────\n"
        "/analyse [SYMBOL] [INTERVAL]\n"
        "  Live VPRT signal for any CEX coin\n"
        "  Example: /analyse BTC 4H\n"
        "  Intervals: 1m 5m 15m 30m 1H 4H 1D\n\n"
        "DEX SCANNER\n"
        "/gem <address or name>\n"
        "  On-demand DEX token scan (market + risk + signal)\n"
        "  Example: /gem 0xTokenAddress\n"
        "  Free: 2 scans/day  |  Pro: unlimited\n\n"
        "/gems\n"
        "  Latest hourly DEX sweep results\n\n"
        "/watch <address>\n"
        "  Add a token to your watchlist\n\n"
        "/unwatch <address>\n"
        "  Remove a token from watchlist\n\n"
        "/mywatches\n"
        "  View your watchlist\n\n"
        "/chains\n"
        "  List active scanner chains\n\n"
        "ACCOUNT\n"
        "/status  — Your account & tier\n"
        "/link    — Link your email\n"
        "/help    — This list\n\n"
        "Or just type your question.\n"
        "https://crypto-sniper.app"
    )


# ─────────────────────────────────────────────
#  /analyse
# ─────────────────────────────────────────────

async def analyse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args     = context.args
    symbol   = args[0].upper() if args else None
    interval = args[1].upper() if len(args) > 1 else "1H"

    if not symbol:
        await update.message.reply_text(
            "Which coin? Usage: /analyse BTC\n"
            "Optional interval: /analyse BTC 4H\n"
            "Intervals: 1m 5m 15m 30m 1H 4H 1D"
        )
        return

    await _typing(update)
    msg = await update.message.reply_text(f"Fetching {symbol}/{interval} signal...")

    result = await fetch_analysis(symbol, interval)
    await msg.edit_text(result)


# ─────────────────────────────────────────────
#  /status
# ─────────────────────────────────────────────

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = await get_user(update.effective_user.id)

    if not db_user:
        await update.message.reply_text(
            "No account found. Start with /start to link your email."
        )
        return

    email    = db_user.get("email") or "not linked"
    tier     = (db_user.get("tier") or "free").upper()
    verified = db_user.get("verified_at") or "—"

    # DEX scan usage
    scans_today, _ = await get_gem_scan_count(update.effective_user.id)
    scan_limit = "Unlimited" if tier.lower() != "free" else f"{scans_today}/{FREE_GEM_DAILY_LIMIT}"

    await update.message.reply_text(
        f"ACCOUNT STATUS\n"
        f"──────────────\n"
        f"Name:      {db_user.get('first_name','')}\n"
        f"Email:     {email}\n"
        f"Tier:      {tier}\n"
        f"Linked:    {verified[:10] if verified != '—' else '—'}\n"
        f"Gem scans: {scan_limit} today\n\n"
        f"Upgrade: https://crypto-sniper.app"
    )


# ─────────────────────────────────────────────
#  /link  (re-link email)
# ─────────────────────────────────────────────

async def link_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await upsert_user(
        update.effective_user.id,
        update.effective_user.first_name,
        update.effective_user.username
    )
    await update.message.reply_text(
        "Send me your Crypto Sniper account email to link it.\n"
        "Or /skip to cancel."
    )
    return AWAITING_EMAIL


# ─────────────────────────────────────────────
#  DEX SCANNER COMMANDS
# ─────────────────────────────────────────────

async def gem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /gem <contract_address_or_name>  [chain]
    On-demand single-token DEX scan with rate limiting.
    Free tier: FREE_GEM_DAILY_LIMIT scans/day.
    Pro tier: unlimited.
    """
    user    = update.effective_user
    chat_id = update.effective_chat.id

    if not context.args:
        await update.message.reply_text(
            "Usage: /gem <address or token name>\n"
            "Example: /gem 0xTokenAddress\n"
            "Example: /gem PEPE\n\n"
            "Optionally specify chain:\n"
            "/gem 0x... bsc\n"
            f"Supported: {', '.join(c.upper() for c in SUPPORTED_CHAINS)}"
        )
        return

    query          = context.args[0].strip()
    preferred_chain = context.args[1].lower() if len(context.args) > 1 else None

    # Ensure user exists in DB
    await upsert_user(user.id, user.first_name, user.username)
    db_user = await get_user(user.id)
    tier    = _get_tier(db_user)

    # Rate limiting — free tier only
    if tier == "free":
        scans_today, _ = await get_gem_scan_count(user.id)
        if scans_today >= FREE_GEM_DAILY_LIMIT:
            await update.message.reply_text(compose_rate_limited("midnight UTC"))
            return

    # Increment counter before scan
    await increment_gem_scan(user.id)

    # Run the scan (gem_lookup handles messaging directly)
    await gem_lookup(query, context.bot, chat_id, preferred_chain=preferred_chain)


async def gems_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /gems — Return the last hourly DEX sweep results from the blackboard.
    """
    await _typing(update)
    board, scan_time = get_last_sweep()

    if board is None:
        await update.message.reply_text(
            "No sweep has run yet.\n"
            "The DEX scanner runs every hour at the top of the hour.\n"
            "Check back shortly."
        )
        return

    msg = board.compose_sweep(top_n=10)
    chat_id = update.effective_chat.id

    try:
        if len(msg) <= 4096:
            await update.message.reply_text(msg)
        else:
            for chunk in _split_msg(msg):
                await context.bot.send_message(chat_id=chat_id, text=chunk)
    except Exception as e:
        logger.error(f"[/gems] Send failed: {e}")
        await update.message.reply_text("Failed to retrieve sweep results. Try again shortly.")


async def watch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /watch <contract_address>  — Add a token to watchlist.
    The bot will alert you when a gem scan picks it up.
    """
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "Usage: /watch <contract_address>\n"
            "Example: /watch 0xTokenAddress\n\n"
            "You'll be alerted when this token appears in a DEX sweep."
        )
        return

    address = context.args[0].strip().lower()

    if not _is_address(address) and len(address) < 10:
        await update.message.reply_text(
            "That doesn't look like a valid contract address.\n"
            "Please provide the full contract address.\n"
            "Example: /watch 0xTokenAddress"
        )
        return

    # Ensure user exists
    await upsert_user(user.id, user.first_name, user.username)

    # Check watch limit
    existing = await get_watches(user.id)
    if len(existing) >= MAX_WATCHES:
        await update.message.reply_text(
            f"Watch limit reached ({MAX_WATCHES} max on free tier).\n"
            "Use /unwatch <address> to remove one first.\n\n"
            "Upgrade to Pro for more watchlist slots:\n"
            "https://crypto-sniper.app"
        )
        return

    # Resolve symbol via DexScreener (best effort, non-blocking)
    symbol = "?"
    chain  = "unknown"
    try:
        import aiohttp, asyncio
        async with aiohttp.ClientSession() as session:
            url = f"https://api.dexscreener.com/latest/dex/search?q={address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    pairs = data.get("pairs") or []
                    if pairs:
                        p      = pairs[0]
                        symbol = p.get("baseToken", {}).get("symbol", "?")
                        chain  = p.get("chainId", "unknown")
    except Exception:
        pass

    added = await add_watch(user.id, address, symbol, chain)

    if added:
        short = f"{address[:8]}...{address[-6:]}" if len(address) > 16 else address
        await update.message.reply_text(
            f"Watching: {symbol} ({short})\n"
            f"Chain: {chain.upper()}\n\n"
            "You'll be notified when this token appears in a DEX sweep.\n"
            f"Watching {len(existing) + 1}/{MAX_WATCHES} addresses.\n\n"
            "/mywatches — view your full list"
        )
    else:
        await update.message.reply_text(
            "Already watching that address.\n"
            "/mywatches — view your list"
        )


async def unwatch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /unwatch <contract_address>  — Remove a token from watchlist.
    """
    if not context.args:
        await update.message.reply_text(
            "Usage: /unwatch <contract_address>\n"
            "/mywatches — see what you're watching"
        )
        return

    address = context.args[0].strip().lower()
    removed = await remove_watch(update.effective_user.id, address)

    if removed:
        short = f"{address[:8]}...{address[-6:]}" if len(address) > 16 else address
        await update.message.reply_text(
            f"Removed {short} from your watchlist.\n"
            "/mywatches — view remaining"
        )
    else:
        await update.message.reply_text(
            "That address isn't on your watchlist.\n"
            "/mywatches — see what you're watching"
        )


async def mywatches_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /mywatches — List all addresses the user is watching.
    """
    user    = update.effective_user
    watches = await get_watches(user.id)

    if not watches:
        await update.message.reply_text(
            "Your watchlist is empty.\n\n"
            "Add tokens with:\n"
            "/watch <contract_address>"
        )
        return

    lines = [f"YOUR WATCHLIST ({len(watches)}/{MAX_WATCHES})", "─" * 28]
    for i, w in enumerate(watches, 1):
        addr  = w["address"]
        short = f"{addr[:8]}...{addr[-6:]}" if len(addr) > 16 else addr
        sym   = w.get("symbol", "?")
        chain = (w.get("chain") or "?").upper()
        lines.append(f"#{i}  {sym}  {chain}\n    {short}")

    lines.append("\n/unwatch <address> — remove one")
    await update.message.reply_text("\n".join(lines))


async def chains_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /chains — List active DEX scanner chains with their config.
    """
    chain_info = {
        "bsc":      ("BNB Chain",  "🟡", "$50K liq  $100K vol"),
        "base":     ("Base",       "🔵", "$75K liq  $150K vol"),
        "ethereum": ("Ethereum",   "⬡",  "$150K liq $300K vol"),
        "solana":   ("Solana",     "🟣", "$50K liq  $100K vol  24h min age"),
        "arbitrum": ("Arbitrum",   "🔷", "$75K liq  $150K vol"),
    }

    lines = [
        "DEX SCANNER — ACTIVE CHAINS",
        "─" * 30,
    ]
    for chain_id in SUPPORTED_CHAINS:
        info = chain_info.get(chain_id, (chain_id.upper(), "🔗", ""))
        name, emoji, thresholds = info
        status = "✅ Active"
        lines.append(f"{emoji} {name}\n   {status}  ·  {thresholds}")

    lines.append(
        "\n─" + "─" * 29 + "\n"
        "Data: DexScreener · GoPlus · GeckoTerminal\n"
        "Sweep: every hour  ·  Score 9+/13 (VPRT)\n"
        "/gems — latest sweep results"
    )
    await update.message.reply_text("\n".join(lines))


# ─────────────────────────────────────────────
#  Free-text handler — main AI agent
# ─────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user     = update.effective_user
    text     = update.message.text.strip()
    db_user  = await get_user(user.id)

    if not db_user:
        await upsert_user(user.id, user.first_name, user.username)
        db_user = await get_user(user.id)

    await _typing(update)

    # Save user message
    await save_message(user.id, "user", text)

    # Get conversation history
    history = await get_history(user.id, limit=16)

    # Get agent response
    response = await get_agent_response(text, history[:-1], db_user)

    # Check for ANALYSE trigger
    analyse_params = extract_analyse_command(response)
    if analyse_params:
        symbol, interval = analyse_params
        await update.message.reply_text(f"Running analysis on {symbol}/{interval}...")
        result = await fetch_analysis(symbol, interval)
        await save_message(user.id, "assistant", result)
        await update.message.reply_text(result)
        return

    # Check for ESCALATE trigger
    esc_summary = extract_escalation(response)
    if esc_summary:
        transcript = await get_transcript(user.id, limit=20)
        await save_escalation(user.id, esc_summary, transcript)

        user_name  = db_user.get("first_name", str(user.id)) if db_user else str(user.id)
        user_email = (db_user.get("email") or "") if db_user else ""

        tg_ok, email_ok = await escalate(
            user.id, user_name, user_email, esc_summary, transcript,
            bot=context.bot
        )

        esc_msg = (
            "This has been escalated to the Crypto Sniper support team.\n"
            "Kai will follow up directly — usually within a few hours.\n\n"
            "Is there anything else I can help with in the meantime?"
        )
        await save_message(user.id, "assistant", esc_msg)
        await update.message.reply_text(esc_msg)
        return

    # Normal response
    await save_message(user.id, "assistant", response)
    await update.message.reply_text(response)


# ─────────────────────────────────────────────
#  Error handler
# ─────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _split_msg(msg: str, limit: int = 4096) -> list[str]:
    chunks = []
    while msg:
        chunks.append(msg[:limit])
        msg = msg[limit:]
    return chunks


def _seconds_to_next_hour() -> int:
    """
    Compute seconds until the next UTC hour boundary.
    Returns a value in [0, 3600).
    Clamps to a minimum of 30s so the job doesn't fire immediately on a
    near-boundary restart, giving the API a moment to warm up.
    If we're within 2 minutes past the hour, fire almost immediately (30s)
    so we don't skip this hour's scan.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    secs_past = now.minute * 60 + now.second
    secs_until_next = 3600 - secs_past
    # If we just crossed the hour (within 2 min past), fire quickly
    if secs_past <= 120:
        return 30
    # Otherwise fire at the top of the next hour, minus 2s buffer
    return max(30, secs_until_next - 2)


# ─────────────────────────────────────────────
#  Post-init: DB + JobQueue
# ─────────────────────────────────────────────

async def post_init(application: Application):
    await init_db()
    logger.info("DB initialised")

    job_queue = application.job_queue
    first_in  = _seconds_to_next_hour()

    # ── Existing: hourly CEX scanner ──────────────────────────────────────
    job_queue.run_repeating(
        hourly_scan_job,
        interval=3600,
        first=first_in,
        name="hourly_scanner",
    )
    logger.info(f"Hourly CEX scanner scheduled — first run in {first_in}s")

    # ── New: hourly DEX sweep ──────────────────────────────────────────────
    # Offset by 90s from CEX scan to avoid hammering APIs at the exact same time
    dex_first_in = first_in + 90
    job_queue.run_repeating(
        dex_scan_job,
        interval=3600,
        first=dex_first_in,
        name="dex_scanner",
        data={"chat_id": ADMIN_CHAT_ID},   # sends sweep to admin chat
    )
    logger.info(f"DEX scanner scheduled — first run in {dex_first_in}s")


# ─────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # Email linking conversation
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("link", link_cmd),
        ],
        states={
            AWAITING_EMAIL: [
                CommandHandler("skip", skip_email),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_email),
            ]
        },
        fallbacks=[CommandHandler("skip", skip_email)],
    )

    app.add_handler(conv)

    # Existing commands
    app.add_handler(CommandHandler("help",    help_cmd))
    app.add_handler(CommandHandler("analyse", analyse_cmd))
    app.add_handler(CommandHandler("analyze", analyse_cmd))
    app.add_handler(CommandHandler("status",  status_cmd))

    # DEX scanner commands
    app.add_handler(CommandHandler("gem",       gem_cmd))
    app.add_handler(CommandHandler("gems",      gems_cmd))
    app.add_handler(CommandHandler("watch",     watch_cmd))
    app.add_handler(CommandHandler("unwatch",   unwatch_cmd))
    app.add_handler(CommandHandler("mywatches", mywatches_cmd))
    app.add_handler(CommandHandler("chains",    chains_cmd))

    # Free-text fallback
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Crypto Sniper bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
