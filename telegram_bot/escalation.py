"""
Escalation system — fires when bot cannot resolve an issue.
Sends:
  1. Telegram DM to the founder (chat_id = ADMIN_CHAT_ID)
  2. Email to subroh.iyer@gmail.com via SMTP or a webhook
"""
import os
import logging
import smtplib
import aiohttp
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

ADMIN_CHAT_ID   = int(os.environ.get("ADMIN_CHAT_ID", "5861457546"))
BOT_TOKEN       = os.environ.get("BOT_TOKEN", "")
ADMIN_EMAIL     = os.environ.get("ADMIN_EMAIL", "subroh.iyer@gmail.com")

# Optional SMTP config (Gmail app password recommended)
SMTP_HOST       = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT       = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER       = os.environ.get("SMTP_USER", "")
SMTP_PASS       = os.environ.get("SMTP_PASS", "")


async def escalate(
    telegram_id: int,
    user_name: str,
    user_email: str,
    summary: str,
    transcript: str,
    bot=None
):
    """Fire both escalation channels concurrently."""
    tg_ok    = await _notify_telegram(telegram_id, user_name, user_email, summary, transcript, bot=bot)
    email_ok = await _notify_email(telegram_id, user_name, user_email, summary, transcript)
    logger.info(f"Escalation fired — TG: {tg_ok}, Email: {email_ok}")
    return tg_ok, email_ok


async def _notify_telegram(
    telegram_id: int,
    user_name: str,
    user_email: str,
    summary: str,
    transcript: str,
    bot=None
):
    # Truncate transcript to fit Telegram's 4096 char limit
    max_transcript = 2800
    if len(transcript) > max_transcript:
        transcript = "..." + transcript[-max_transcript:]

    text = (
        f"ESCALATION — Crypto Sniper Support\n"
        f"{'─' * 32}\n"
        f"User:     {user_name} (TG ID: {telegram_id})\n"
        f"Email:    {user_email or 'not linked'}\n"
        f"Issue:    {summary}\n"
        f"{'─' * 32}\n"
        f"Transcript:\n{transcript}"
    )

    # Use bot instance directly if available (most reliable)
    if bot:
        try:
            await bot.send_message(chat_id=ADMIN_CHAT_ID, text=text)
            logger.info(f"Escalation TG DM sent to admin {ADMIN_CHAT_ID}")
            return True
        except Exception as e:
            logger.error(f"Bot.send_message escalation failed: {e}")

    # Fallback to raw HTTP if no bot instance
    if not BOT_TOKEN:
        logger.warning("BOT_TOKEN not set — cannot send Telegram escalation")
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id": ADMIN_CHAT_ID,
                "text":    text,
            }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                ok = resp.status == 200
                if not ok:
                    body = await resp.text()
                    logger.error(f"Telegram API error: {resp.status} {body}")
                return ok
    except Exception as e:
        logger.error(f"Telegram HTTP escalation failed: {e}")
        return False


async def _notify_email(
    telegram_id: int,
    user_name: str,
    user_email: str,
    summary: str,
    transcript: str
):
    if not SMTP_USER or not SMTP_PASS:
        logger.warning("SMTP not configured — skipping email escalation")
        return False

    subject = f"[Crypto Sniper Support] Escalation: {summary[:60]}"

    html = f"""
    <div style="font-family:monospace;background:#0c1225;color:#e2e8f0;padding:24px;border-radius:8px;max-width:600px;">
      <div style="color:#7c3aed;font-size:12px;font-weight:700;letter-spacing:3px;margin-bottom:8px;">CRYPTO SNIPER — SUPPORT ESCALATION</div>
      <hr style="border-color:#1e293b;"/>
      <p><b>User:</b> {user_name} (Telegram ID: {telegram_id})</p>
      <p><b>Email:</b> {user_email or 'not linked'}</p>
      <p><b>Issue:</b> {summary}</p>
      <hr style="border-color:#1e293b;"/>
      <p style="color:#94a3b8;font-size:12px;">CONVERSATION TRANSCRIPT</p>
      <pre style="background:#060912;padding:16px;border-radius:4px;font-size:11px;color:#cbd5e1;white-space:pre-wrap;">{transcript}</pre>
    </div>
    """

    plain = f"Escalation: {summary}\nUser: {user_name} (TG: {telegram_id})\nEmail: {user_email or 'not linked'}\n\nTranscript:\n{transcript}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = ADMIN_EMAIL
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, ADMIN_EMAIL, msg.as_string())
        return True
    except Exception as e:
        logger.error(f"Email escalation failed: {e}")
        return False
