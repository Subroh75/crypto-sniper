"""
Crypto Sniper Telegram Bot
Full agent: CS + crypto Q&A + live /analyse commands
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

from db import init_db, get_user, upsert_user, set_user_email, save_message, get_history, get_transcript, save_escalation
from agent import get_agent_response, extract_analyse_command, extract_escalation
from analyse import fetch_analysis
from escalation import escalate
from scanner import hourly_scan_job

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN    = os.environ["BOT_TOKEN"]
ADMIN_CHAT_ID = int(os.environ.get("ADMIN_CHAT_ID", "5861457546"))

# ConversationHandler state
AWAITING_EMAIL = 1


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

async def _typing(update: Update):
    await update.effective_chat.send_action("typing")


def _is_valid_email(s: str) -> bool:
    return bool(re.match(r"[^@\s]+@[^@\s]+\.[^@\s]+", s.strip()))


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
            "/analyse BTC — live signal\n"
            "/status      — your account\n"
            "/help        — all commands"
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
        "/analyse BTC 1H — live signal\n"
        "/status         — account info\n"
        "/help           — all commands\n\n"
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
        "  Live VPRT signal for any coin\n"
        "  Example: /analyse BTC 4H\n"
        "  Intervals: 1m 5m 15m 30m 1H 4H 1D\n\n"
        "/status  — Your account & tier\n"
        "/link    — Link your email\n"
        "/help    — This list\n\n"
        "Or just type your question — I handle:\n"
        "- Signal explanations\n"
        "- Subscription & payment issues\n"
        "- Bug reports\n"
        "- General crypto Q&A\n\n"
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

    email     = db_user.get("email") or "not linked"
    tier      = (db_user.get("tier") or "free").upper()
    verified  = db_user.get("verified_at") or "—"

    await update.message.reply_text(
        f"ACCOUNT STATUS\n"
        f"──────────────\n"
        f"Name:     {db_user.get('first_name','')}\n"
        f"Email:    {email}\n"
        f"Tier:     {tier}\n"
        f"Linked:   {verified[:10] if verified != '—' else '—'}\n\n"
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
#  Main
# ─────────────────────────────────────────────

async def post_init(application: Application):
    await init_db()
    logger.info("DB initialised")

    # Schedule hourly scanner
    job_queue = application.job_queue
    job_queue.run_repeating(
        hourly_scan_job,
        interval=3600,   # every hour
        first=60,        # first run 60s after bot starts (gives API time to wake)
        name="hourly_scanner",
    )
    logger.info("Hourly scanner scheduled (first run in 60s)")


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
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("analyse", analyse_cmd))
    app.add_handler(CommandHandler("analyze", analyse_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    logger.info("Crypto Sniper bot polling...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
