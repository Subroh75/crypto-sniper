"""
Crypto Sniper Telegram Bot — UX Redesign
Full agent: CS + crypto Q&A + live /analyse + DEX scanner + signal tracker
- Persistent reply keyboard (tap menu)
- Language detection (EN/ES/VI/ID/HI/ZH/AR)
- Inline buttons on all result messages
- Callback query handler for all button actions
- Onboarding flow for new users
"""
import os
import re
import logging
from dotenv import load_dotenv

load_dotenv()

from telegram import Update, ReplyKeyboardRemove, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from db import (
    init_db, get_user, upsert_user, set_user_email, set_user_lang,
    save_message, get_history, get_transcript, save_escalation,
    get_gem_scan_count, increment_gem_scan,
    add_watch, remove_watch, get_watches,
)
from agent import get_agent_response, extract_analyse_command, extract_escalation
from analyse import fetch_analysis
from escalation import escalate
from scanner import hourly_scan_job, vol_spike_job, _vol_scan, _format_vol_report, _get_top_symbols
from kalman_scanner import trend_radar_job, trend_radar_outcome_checker
from dex_scanner.scanner import dex_scan_job, gem_lookup, get_last_sweep, SUPPORTED_CHAINS
from dex_scanner.blackboard import compose_rate_limited
from signal_tracker import init_tracker
from signal_monitor import signal_monitor_job, format_record_message
from keyboards import (
    main_menu_keyboard, onboarding_keyboard,
    signal_inline_keyboard, gem_inline_keyboard,
    record_inline_keyboard, sweep_inline_keyboard,
    account_inline_keyboard,
)
from i18n import t, resolve_lang

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN     = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "5861457546"))

FREE_GEM_DAILY_LIMIT = 2
MAX_WATCHES          = 5

# ConversationHandler states
AWAITING_EMAIL  = 1
AWAITING_SYMBOL = 2
AWAITING_DEX    = 3

# Menu button labels (must match keyboards.py exactly)
MENU_SIGNAL  = "📡 Live Signal"
MENU_DEX     = "💎 DEX Gem Scan"
MENU_SWEEP   = "📊 Last Sweep"
MENU_RECORD  = "📈 Track Record"
MENU_ACCOUNT = "⚙️ My Account"
MENU_HELP    = "❓ Help"


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

async def _typing(update: Update):
    await update.effective_chat.send_action("typing")


def _is_valid_email(s: str) -> bool:
    return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", s.strip()))


def _is_address(s: str) -> bool:
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


def _get_lang(db_user: dict | None, tg_user=None) -> str:
    """Resolve language: DB preference > Telegram locale > English."""
    if db_user and db_user.get("lang"):
        return resolve_lang(db_user["lang"])
    if tg_user and tg_user.language_code:
        return resolve_lang(tg_user.language_code)
    return "en"


def _split_msg(msg: str, limit: int = 4096) -> list[str]:
    chunks = []
    while msg:
        chunks.append(msg[:limit])
        msg = msg[limit:]
    return chunks


# ─────────────────────────────────────────────
#  /start — onboarding
# ─────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id

    await upsert_user(user.id, user.first_name, user.username)
    db_user = await get_user(user.id)

    # Detect and save language on first visit
    lang = _get_lang(db_user, user)
    if db_user and not db_user.get("lang"):
        await set_user_lang(user.id, lang)

    await _typing(update)

    if db_user and db_user.get("email"):
        # Returning user — show menu immediately
        tier  = (db_user.get("tier") or "free").upper()
        email = db_user["email"]
        msg = t("welcome_back", lang, name=user.first_name, email=email, tier=tier)
        await update.message.reply_text(
            msg,
            reply_markup=main_menu_keyboard()
        )
        return ConversationHandler.END

    # New user — onboarding with language-detected welcome
    msg = t("welcome_new", lang, name=user.first_name)
    await update.message.reply_text(
        msg,
        reply_markup=onboarding_keyboard()
    )
    return ConversationHandler.END


async def receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text    = update.message.text.strip()
    db_user = await get_user(update.effective_user.id)
    lang    = _get_lang(db_user, update.effective_user)

    if not _is_valid_email(text):
        await update.message.reply_text(
            "That doesn't look like a valid email — try again or /skip."
        )
        return AWAITING_EMAIL

    await set_user_email(update.effective_user.id, text.lower())
    await update.message.reply_text(
        f"Linked. Account set to {text.lower()}.\n\n"
        + t("help", lang),
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END


async def skip_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = await get_user(update.effective_user.id)
    lang    = _get_lang(db_user, update.effective_user)
    await update.message.reply_text(
        t("help", lang),
        reply_markup=main_menu_keyboard()
    )
    return ConversationHandler.END


# ─────────────────────────────────────────────
#  /help
# ─────────────────────────────────────────────

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = await get_user(update.effective_user.id)
    lang    = _get_lang(db_user, update.effective_user)
    await update.message.reply_text(
        t("help", lang),
        reply_markup=main_menu_keyboard()
    )


# ─────────────────────────────────────────────
#  /analyse — CEX signal
# ─────────────────────────────────────────────

async def analyse_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user  = await get_user(update.effective_user.id)
    lang     = _get_lang(db_user, update.effective_user)
    args     = context.args
    symbol   = args[0].upper() if args else None
    interval = args[1].upper() if len(args) > 1 else "1H"

    if not symbol:
        await update.message.reply_text(
            t("enter_symbol", lang),
            reply_markup=main_menu_keyboard()
        )
        return

    await _typing(update)
    msg = await update.message.reply_text(f"Scanning {symbol}/{interval}...")
    result = await fetch_analysis(symbol, interval)
    await msg.edit_text(
        result,
        reply_markup=signal_inline_keyboard(symbol, interval)
    )


# ─────────────────────────────────────────────
#  /status
# ─────────────────────────────────────────────

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_user = await get_user(update.effective_user.id)

    if not db_user:
        await update.message.reply_text(
            "No account found. Use /start to set up.",
            reply_markup=main_menu_keyboard()
        )
        return

    lang          = _get_lang(db_user, update.effective_user)
    email         = db_user.get("email") or "not linked"
    tier          = (db_user.get("tier") or "free").upper()
    verified      = db_user.get("verified_at") or "—"
    scans_today, _ = await get_gem_scan_count(update.effective_user.id)
    scan_limit    = "Unlimited" if tier.lower() != "free" else f"{scans_today}/{FREE_GEM_DAILY_LIMIT}"

    has_email = bool(db_user.get("email"))
    await update.message.reply_text(
        f"ACCOUNT\n"
        f"──────────────────────\n"
        f"Name:       {db_user.get('first_name','')}\n"
        f"Email:      {email}\n"
        f"Tier:       {tier}\n"
        f"Linked:     {verified[:10] if verified != '—' else '—'}\n"
        f"DEX scans:  {scan_limit} today\n\n"
        f"Upgrade: https://crypto-sniper.app",
        reply_markup=account_inline_keyboard(has_email)
    )


# ─────────────────────────────────────────────
#  /link
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
#  /gems — last DEX sweep
# ─────────────────────────────────────────────

async def gems_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _typing(update)
    board, scan_time = get_last_sweep()
    chat_id = update.effective_chat.id

    if board is None:
        await update.message.reply_text(
            "No sweep has run yet.\n"
            "The DEX scanner runs once daily at 8 AM AEST (22:00 UTC).\n"
            "Check back shortly.",
            reply_markup=main_menu_keyboard()
        )
        return

    msg = board.compose_sweep(top_n=10)
    try:
        if len(msg) <= 4096:
            await update.message.reply_text(msg, reply_markup=sweep_inline_keyboard())
        else:
            chunks = _split_msg(msg)
            for i, chunk in enumerate(chunks):
                kb = sweep_inline_keyboard() if i == len(chunks) - 1 else None
                await context.bot.send_message(chat_id=chat_id, text=chunk, reply_markup=kb)
    except Exception as e:
        logger.error(f"[/gems] Send failed: {e}")
        await update.message.reply_text("Failed to retrieve results. Try again shortly.")


# ─────────────────────────────────────────────
#  /gem — on-demand DEX scan
# ─────────────────────────────────────────────

async def gem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    chat_id = update.effective_chat.id
    db_user = await get_user(user.id)
    lang    = _get_lang(db_user, user)

    if not context.args:
        await update.message.reply_text(
            t("enter_dex_address", lang),
            reply_markup=main_menu_keyboard()
        )
        return

    query           = context.args[0].strip()
    preferred_chain = context.args[1].lower() if len(context.args) > 1 else None

    await upsert_user(user.id, user.first_name, user.username)
    db_user = await get_user(user.id)
    tier    = _get_tier(db_user)

    if tier == "free":
        scans_today, _ = await get_gem_scan_count(user.id)
        if scans_today >= FREE_GEM_DAILY_LIMIT:
            await update.message.reply_text(
                t("rate_limit", lang, limit=FREE_GEM_DAILY_LIMIT),
                reply_markup=main_menu_keyboard()
            )
            return

    await increment_gem_scan(user.id)
    await gem_lookup(query, context.bot, chat_id, preferred_chain=preferred_chain)


# ─────────────────────────────────────────────
#  /record — signal track record
# ─────────────────────────────────────────────

async def record_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _typing(update)
    arg = (context.args[0].lower() if context.args else None)
    if arg not in ("cex", "dex", None):
        arg = None
    msg = format_record_message(source=arg)
    await update.message.reply_text(
        msg,
        reply_markup=record_inline_keyboard(current=arg or "all")
    )


# ─────────────────────────────────────────────
#  Watchlist commands
# ─────────────────────────────────────────────

async def watch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not context.args:
        await update.message.reply_text(
            "Usage: /watch <contract_address>\n"
            "Example: /watch 0xTokenAddress\n\n"
            "You'll be alerted when this token appears in a DEX sweep.",
            reply_markup=main_menu_keyboard()
        )
        return

    address = context.args[0].strip().lower()
    if not _is_address(address) and len(address) < 10:
        await update.message.reply_text(
            "That doesn't look like a valid contract address.\n"
            "Provide the full address. Example: /watch 0xTokenAddress"
        )
        return

    await upsert_user(user.id, user.first_name, user.username)
    existing = await get_watches(user.id)
    if len(existing) >= MAX_WATCHES:
        await update.message.reply_text(
            f"Watch limit reached ({MAX_WATCHES} max on free tier).\n"
            "Use /unwatch <address> to remove one first.\n\n"
            "Upgrade for more slots: https://crypto-sniper.app",
            reply_markup=main_menu_keyboard()
        )
        return

    symbol = "?"
    chain  = "unknown"
    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            url = f"https://api.dexscreener.com/latest/dex/search?q={address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status == 200:
                    data  = await resp.json()
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
            f"You'll be notified when this token appears in a sweep.\n"
            f"Watching {len(existing) + 1}/{MAX_WATCHES} addresses.\n\n"
            "/mywatches — view your full list",
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "Already watching that address.\n/mywatches — view your list"
        )


async def unwatch_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            f"Removed {short} from your watchlist.\n/mywatches — view remaining",
            reply_markup=main_menu_keyboard()
        )
    else:
        await update.message.reply_text(
            "That address isn't on your watchlist.\n/mywatches — see what you're watching"
        )


async def mywatches_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    watches = await get_watches(update.effective_user.id)
    if not watches:
        await update.message.reply_text(
            "Your watchlist is empty.\n\nAdd tokens with:\n/watch <contract_address>",
            reply_markup=main_menu_keyboard()
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
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=main_menu_keyboard()
    )


async def chains_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chain_info = {
        "bsc":      ("BNB Chain",  "🟡", "$50K liq  $100K vol"),
        "base":     ("Base",       "🔵", "$75K liq  $150K vol"),
        "ethereum": ("Ethereum",   "⬡",  "$150K liq $300K vol"),
        "solana":   ("Solana",     "🟣", "$50K liq  $100K vol  24h min age"),
        "arbitrum": ("Arbitrum",   "🔷", "$75K liq  $150K vol"),
    }
    lines = ["DEX SCANNER — ACTIVE CHAINS", "─" * 30]
    for chain_id in SUPPORTED_CHAINS:
        info = chain_info.get(chain_id, (chain_id.upper(), "🔗", ""))
        name, emoji, thresholds = info
        lines.append(f"{emoji} {name}\n   ✅ Active  ·  {thresholds}")
    lines.append(
        "\n─" + "─" * 29 + "\n"
        "Data: DexScreener · GoPlus · GeckoTerminal\n"
        "Sweep: daily at 8 AM AEST  ·  1D candles only\n"
        "/gems — latest sweep results"
    )
    await update.message.reply_text(
        "\n".join(lines),
        reply_markup=main_menu_keyboard()
    )


# ─────────────────────────────────────────────
#  /volscan — on-demand vol scan
# ─────────────────────────────────────────────

async def volscan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /volscan — live scan for all coins with rel_vol >= 1.8x.
    Returns the same vol-first gate traffic-light format as the daily watch report.
    """
    from datetime import datetime, timezone

    await update.message.reply_text(
        "Scanning for high-volume coins...  this takes ~30s.",
        reply_markup=main_menu_keyboard()
    )

    scan_time = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    try:
        symbols = await _get_top_symbols(200)
        if not symbols:
            await update.message.reply_text(
                "Could not fetch coin list — please try again in a moment.",
                reply_markup=main_menu_keyboard()
            )
            return

        hits, errors = await _vol_scan(symbols, interval="1d")
        msg = _format_vol_report(hits, "1d", scan_time, source="CEX")
        await update.message.reply_text(msg, reply_markup=main_menu_keyboard())

    except Exception as e:
        logger.error(f"[volscan_cmd] {e}")
        await update.message.reply_text(
            "Vol scan failed — please try again shortly.",
            reply_markup=main_menu_keyboard()
        )


# ─────────────────────────────────────────────
#  Menu button tap handler
# ─────────────────────────────────────────────

async def menu_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle persistent keyboard button taps by routing to the right action."""
    text    = update.message.text.strip()
    db_user = await get_user(update.effective_user.id)
    lang    = _get_lang(db_user, update.effective_user)

    if text == MENU_SIGNAL:
        await update.message.reply_text(
            t("enter_symbol", lang),
            reply_markup=main_menu_keyboard()
        )
        context.user_data["awaiting"] = "symbol"
        return

    if text == MENU_DEX:
        await update.message.reply_text(
            t("enter_dex_address", lang),
            reply_markup=main_menu_keyboard()
        )
        context.user_data["awaiting"] = "dex"
        return

    if text == MENU_SWEEP:
        # Reuse gems_cmd logic
        context.args = []
        await gems_cmd(update, context)
        return

    if text == MENU_RECORD:
        context.args = []
        await record_cmd(update, context)
        return

    if text == MENU_ACCOUNT:
        context.args = []
        await status_cmd(update, context)
        return

    if text == MENU_HELP:
        await help_cmd(update, context)
        return

    # Not a menu button — fall through to AI agent
    await handle_message(update, context)


# ─────────────────────────────────────────────
#  Callback query handler (inline buttons)
# ─────────────────────────────────────────────

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query    = update.callback_query
    data     = query.data
    chat_id  = query.message.chat_id
    db_user  = await get_user(query.from_user.id)
    lang     = _get_lang(db_user, query.from_user)

    await query.answer()  # dismiss loading spinner

    # ── Onboarding buttons ──────────────────────────────────────────
    if data == "ob:signal":
        await query.message.reply_text(
            t("enter_symbol", lang),
            reply_markup=main_menu_keyboard()
        )
        context.user_data["awaiting"] = "symbol"
        return

    if data == "ob:dex":
        await query.message.reply_text(
            t("enter_dex_address", lang),
            reply_markup=main_menu_keyboard()
        )
        context.user_data["awaiting"] = "dex"
        return

    if data == "ob:sweep":
        board, _ = get_last_sweep()
        if board is None:
            await query.message.reply_text(
                "No sweep has run yet. The DEX scanner runs once daily at 8 AM AEST (22:00 UTC).",
                reply_markup=main_menu_keyboard()
            )
        else:
            msg = board.compose_sweep(top_n=10)
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg[:4096],
                reply_markup=sweep_inline_keyboard()
            )
        return

    if data == "ob:about":
        await query.message.reply_text(
            t("about", lang),
            reply_markup=main_menu_keyboard()
        )
        return

    # ── Signal buttons ──────────────────────────────────────────────
    if data.startswith("sig:"):
        parts = data.split(":")
        action = parts[1]

        if action in ("refresh", "tf"):
            symbol   = parts[2]
            interval = parts[3]
            await query.message.reply_text(f"Scanning {symbol}/{interval}...")
            result = await fetch_analysis(symbol, interval)
            await context.bot.send_message(
                chat_id=chat_id,
                text=result,
                reply_markup=signal_inline_keyboard(symbol, interval)
            )
            return

        if action == "dex":
            symbol = parts[2]
            await query.message.reply_text(
                f"Send me the contract address for {symbol} to run a DEX scan.\n"
                "Example: /gem 0xTokenAddress",
                reply_markup=main_menu_keyboard()
            )
            return

    # ── Gem/DEX buttons ─────────────────────────────────────────────
    if data.startswith("gem:"):
        parts  = data.split(":")
        action = parts[1]

        if action == "refresh":
            address = parts[2]
            await gem_lookup(address, context.bot, chat_id)
            return

        if action == "watch":
            address = parts[2]
            symbol  = parts[3] if len(parts) > 3 else "?"
            await upsert_user(query.from_user.id, query.from_user.first_name, query.from_user.username)
            existing = await get_watches(query.from_user.id)
            if len(existing) >= MAX_WATCHES:
                await query.message.reply_text(
                    f"Watch limit reached ({MAX_WATCHES} max). Remove one first.\n/mywatches"
                )
                return
            added = await add_watch(query.from_user.id, address.lower(), symbol, "unknown")
            short = f"{address[:8]}...{address[-6:]}" if len(address) > 16 else address
            if added:
                await query.message.reply_text(
                    f"Now watching {symbol} ({short}).\n/mywatches — view your list"
                )
            else:
                await query.message.reply_text(f"Already watching {symbol}.")
            return

    # ── Sweep buttons ───────────────────────────────────────────────
    if data == "sweep:show":
        board, _ = get_last_sweep()
        if board is None:
            await query.message.reply_text("No sweep data yet. Try again after the next hour.")
            return
        msg = board.compose_sweep(top_n=10)
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg[:4096],
            reply_markup=sweep_inline_keyboard()
        )
        return

    # ── Record buttons ──────────────────────────────────────────────
    if data.startswith("rec:show:"):
        source = data.split(":")[-1]
        src    = None if source == "all" else source
        msg    = format_record_message(source=src)
        await context.bot.send_message(
            chat_id=chat_id,
            text=msg,
            reply_markup=record_inline_keyboard(current=source)
        )
        return

    # ── Account buttons ─────────────────────────────────────────────
    if data == "acct:link":
        await query.message.reply_text(
            "Send me your Crypto Sniper account email to link it.\nOr /skip to cancel."
        )
        return


# ─────────────────────────────────────────────
#  Free-text handler — AI agent
# ─────────────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    text    = update.message.text.strip()
    db_user = await get_user(user.id)

    if not db_user:
        await upsert_user(user.id, user.first_name, user.username)
        db_user = await get_user(user.id)

    lang = _get_lang(db_user, user)

    # Check if we're waiting for a symbol or DEX address from menu tap
    awaiting = context.user_data.pop("awaiting", None)
    if awaiting == "symbol":
        parts    = text.upper().split()
        symbol   = parts[0]
        interval = parts[1] if len(parts) > 1 else "1H"
        await _typing(update)
        msg = await update.message.reply_text(f"Scanning {symbol}/{interval}...")
        result = await fetch_analysis(symbol, interval)
        await msg.edit_text(
            result,
            reply_markup=signal_inline_keyboard(symbol, interval)
        )
        return

    if awaiting == "dex":
        await _typing(update)
        await gem_lookup(text.strip(), context.bot, update.effective_chat.id)
        return

    await _typing(update)
    await save_message(user.id, "user", text)
    history  = await get_history(user.id, limit=16)
    response = await get_agent_response(text, history[:-1], db_user, lang=lang)

    # Check for ANALYSE trigger
    analyse_params = extract_analyse_command(response)
    if analyse_params:
        symbol, interval = analyse_params
        await update.message.reply_text(f"Running analysis on {symbol}/{interval}...")
        result = await fetch_analysis(symbol, interval)
        await save_message(user.id, "assistant", result)
        await update.message.reply_text(
            result,
            reply_markup=signal_inline_keyboard(symbol, interval)
        )
        return

    # Check for ESCALATE trigger
    esc_summary = extract_escalation(response)
    if esc_summary:
        transcript = await get_transcript(user.id, limit=20)
        await save_escalation(user.id, esc_summary, transcript)
        user_name  = db_user.get("first_name", str(user.id)) if db_user else str(user.id)
        user_email = (db_user.get("email") or "") if db_user else ""
        await escalate(user.id, user_name, user_email, esc_summary, transcript, bot=context.bot)
        esc_msg = (
            "This has been escalated to the Crypto Sniper support team.\n"
            "Kai will follow up — usually within a few hours.\n\n"
            "Anything else I can help with in the meantime?"
        )
        await save_message(user.id, "assistant", esc_msg)
        await update.message.reply_text(
            esc_msg,
            reply_markup=main_menu_keyboard()
        )
        return

    await save_message(user.id, "assistant", response)
    await update.message.reply_text(
        response,
        reply_markup=main_menu_keyboard()
    )


# ─────────────────────────────────────────────
#  Error handler
# ─────────────────────────────────────────────

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Exception: {context.error}", exc_info=context.error)


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _seconds_to_next_hour() -> int:
    from datetime import datetime, timezone
    now      = datetime.now(timezone.utc)
    secs_past = now.minute * 60 + now.second
    secs_until_next = 3600 - secs_past
    if secs_past <= 120:
        return 30
    return max(30, secs_until_next - 2)


def _seconds_to_next_daily_dex() -> int:
    """Seconds until next 22:00 UTC (8 AM AEST) — DEX daily scan trigger."""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    target = now.replace(hour=22, minute=0, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    secs = int((target - now).total_seconds())
    return max(30, secs)


# ─────────────────────────────────────────────
#  Post-init: DB + JobQueue
# ─────────────────────────────────────────────

async def post_init(application: Application):
    await init_db()
    logger.info("DB initialised")

    init_tracker()
    logger.info("Signal tracker DB initialised")

    job_queue = application.job_queue
    first_in  = _seconds_to_next_hour()

    job_queue.run_repeating(
        hourly_scan_job,
        interval=3600,
        first=first_in,
        name="hourly_scanner",
    )
    logger.info(f"Hourly CEX scanner scheduled — first run in {first_in}s")

    dex_first_in = _seconds_to_next_daily_dex()
    job_queue.run_repeating(
        dex_scan_job,
        interval=86400,          # once per day
        first=dex_first_in,
        name="dex_scanner",
        data={"chat_id": ADMIN_CHAT_ID},
    )
    logger.info(f"DEX daily scanner scheduled — first run in {dex_first_in}s (next 22:00 UTC)")

    monitor_first_in = first_in + 180
    job_queue.run_repeating(
        signal_monitor_job,
        interval=3600,
        first=monitor_first_in,
        name="signal_monitor",
        data={"chat_id": ADMIN_CHAT_ID},
    )
    logger.info(f"Signal monitor scheduled — first run in {monitor_first_in}s")

    # Vol spike poller — every hour, 90s after the hour mark
    spike_first_in = first_in + 90
    job_queue.run_repeating(
        vol_spike_job,
        interval=3600,
        first=spike_first_in,
        name="vol_spike_poller",
    )
    logger.info(f"Vol spike poller scheduled — first run in {spike_first_in}s (every hour)")

    # Trend Radar — Kalman scan every hour, 3min after the hour mark
    # 8h cooldown per coin prevents spam regardless of scan frequency
    radar_first_in = first_in + 180
    job_queue.run_repeating(
        trend_radar_job,
        interval=3600,           # every hour
        first=radar_first_in,
        name="trend_radar",
    )
    logger.info(f"Trend Radar (Kalman) scheduled — first run in {radar_first_in}s (every 1h)")

    # Trend Radar outcome checker — runs once daily at 22:00 UTC (same as daily scan)
    outcome_first_in = _seconds_to_next_daily_dex()
    job_queue.run_repeating(
        trend_radar_outcome_checker,
        interval=86400,
        first=outcome_first_in + 120,   # 2min after daily scan to avoid collision
        name="trend_radar_outcomes",
    )
    logger.info(f"Trend Radar outcome checker scheduled — first run in {outcome_first_in + 120}s (daily)")


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
            CommandHandler("link",  link_cmd),
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

    # Inline button callbacks
    app.add_handler(CallbackQueryHandler(button_callback))

    # Commands
    app.add_handler(CommandHandler("help",      help_cmd))
    app.add_handler(CommandHandler("analyse",   analyse_cmd))
    app.add_handler(CommandHandler("analyze",   analyse_cmd))
    app.add_handler(CommandHandler("status",    status_cmd))
    app.add_handler(CommandHandler("gem",       gem_cmd))
    app.add_handler(CommandHandler("gems",      gems_cmd))
    app.add_handler(CommandHandler("watch",     watch_cmd))
    app.add_handler(CommandHandler("unwatch",   unwatch_cmd))
    app.add_handler(CommandHandler("mywatches", mywatches_cmd))
    app.add_handler(CommandHandler("chains",    chains_cmd))
    app.add_handler(CommandHandler("record",    record_cmd))
    app.add_handler(CommandHandler("volscan",   volscan_cmd))

    # Menu taps + free-text (menu_tap routes known labels, falls through to AI)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_tap))
    app.add_error_handler(error_handler)

    logger.info("Crypto Sniper bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
