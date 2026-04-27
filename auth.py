"""
auth.py — Magic-link email authentication (no password)

Flow:
  1. POST /auth/magic-link  { email }
     → generates a signed token, emails a login link to the user
     → link: https://crypto-sniper.app/#/auth?token=XXX
  2. GET  /auth/verify?token=XXX
     → verifies signature + expiry, returns { email, user_id, session_token }
  3. GET  /auth/me?session_token=XXX
     → returns { email } if valid, 401 otherwise

Tables:
  users(id, email, created_ts, last_login_ts)
  magic_links(id, email, token_hash, expires_ts, used)

SMTP: set GMAIL_USER + GMAIL_APP_PASSWORD env vars on Render to send real emails.
      Without them, the link is logged to stdout (dev mode).
"""

import os, time, hashlib, secrets, smtplib, logging
import sqlite3
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

logger = logging.getLogger(__name__)

DB_PATH  = os.path.join(os.path.dirname(__file__), "data.db")
SECRET   = os.getenv("AUTH_SECRET", "crypto-sniper-auth-secret-change-me")
SIGNER   = URLSafeTimedSerializer(SECRET, salt="magic-link")
LINK_TTL = 15 * 60  # 15 minutes

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_APP_PASSWORD", "")
APP_URL    = os.getenv("APP_URL", "https://crypto-sniper.app")


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_auth_db():
    with _get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            email         TEXT NOT NULL UNIQUE,
            created_ts    INTEGER NOT NULL,
            last_login_ts INTEGER
        );

        CREATE TABLE IF NOT EXISTS magic_links (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    NOT NULL,
            token_hash  TEXT    NOT NULL UNIQUE,
            expires_ts  INTEGER NOT NULL,
            used        INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_ml_email ON magic_links(email);
        """)


_init_auth_db()


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _upsert_user(email: str):
    """Create user if not exists; return user row."""
    now = int(time.time())
    with _get_conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO users (email, created_ts) VALUES (?,?)",
            (email.lower().strip(), now),
        )
        row = c.execute("SELECT * FROM users WHERE email=?", (email.lower().strip(),)).fetchone()
    return dict(row) if row else None


def _update_last_login(email: str):
    with _get_conn() as c:
        c.execute("UPDATE users SET last_login_ts=? WHERE email=?",
                  (int(time.time()), email.lower().strip()))


def _send_email(to: str, link: str):
    subject = "Your Crypto Sniper login link"
    html = f"""
    <div style="font-family:monospace;background:#060912;color:#e2e8f0;padding:32px;max-width:480px;margin:auto;border-radius:12px;border:1px solid #1e293b;">
      <div style="font-size:20px;font-weight:900;color:#7c3aed;margin-bottom:8px;">CRYPTO SNIPER</div>
      <div style="font-size:13px;color:#94a3b8;margin-bottom:24px;">DETECT EARLY. ACT SMART.</div>
      <p style="font-size:14px;">Click the button below to log in. This link expires in 15 minutes.</p>
      <a href="{link}"
         style="display:inline-block;padding:12px 28px;background:linear-gradient(135deg,#7c5cfc,#5b3fd4);
                color:white;text-decoration:none;border-radius:8px;font-weight:bold;font-size:14px;margin:16px 0;">
        Log in to Crypto Sniper
      </a>
      <p style="font-size:11px;color:#475569;margin-top:24px;">
        Or copy this link:<br/>
        <span style="color:#7c3aed;word-break:break-all;">{link}</span>
      </p>
      <p style="font-size:10px;color:#334155;margin-top:16px;">
        If you didn't request this, ignore this email. Link expires in 15 minutes.
      </p>
    </div>
    """
    text = f"Log in to Crypto Sniper:\n{link}\n\nExpires in 15 minutes."

    if GMAIL_USER and GMAIL_PASS:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"]    = f"Crypto Sniper <{GMAIL_USER}>"
            msg["To"]      = to
            msg.attach(MIMEText(text, "plain"))
            msg.attach(MIMEText(html, "html"))
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
                s.login(GMAIL_USER, GMAIL_PASS)
                s.sendmail(GMAIL_USER, to, msg.as_string())
            logger.info(f"Magic link sent to {to}")
        except Exception as e:
            logger.error(f"SMTP send failed: {e}")
            logger.info(f"[DEV] Magic link for {to}: {link}")
    else:
        logger.info(f"[DEV] No SMTP configured. Magic link for {to}: {link}")


# ── Public API ────────────────────────────────────────────────────────────────

def send_magic_link(email: str) -> dict:
    """Generate a signed token, store its hash, send link by email."""
    email = email.lower().strip()
    if not email or "@" not in email:
        return {"error": "Invalid email address"}

    token = SIGNER.dumps(email)
    h     = _hash(token)
    exp   = int(time.time()) + LINK_TTL
    link  = f"{APP_URL}/#/auth?token={token}"

    try:
        with _get_conn() as c:
            # Clean up old tokens for this email
            c.execute("DELETE FROM magic_links WHERE email=? AND (used=1 OR expires_ts<?)",
                      (email, int(time.time())))
            c.execute(
                "INSERT OR REPLACE INTO magic_links (email, token_hash, expires_ts, used) VALUES (?,?,?,0)",
                (email, h, exp),
            )
    except Exception as e:
        logger.warning(f"Magic link DB write failed: {e}")
        return {"error": "Failed to create magic link"}

    _upsert_user(email)
    _send_email(email, link)

    return {
        "sent": True,
        "email": email,
        "expires_in": LINK_TTL,
        "message": f"Login link sent to {email}. Check your inbox.",
        # In dev mode (no SMTP), include link in response for testing
        "dev_link": link if not (GMAIL_USER and GMAIL_PASS) else None,
    }


def verify_magic_link(token: str) -> dict:
    """Verify token; return session_token on success."""
    try:
        email = SIGNER.loads(token, max_age=LINK_TTL)
    except SignatureExpired:
        return {"error": "Link has expired — request a new one"}
    except BadSignature:
        return {"error": "Invalid login link"}

    h = _hash(token)
    try:
        with _get_conn() as c:
            row = c.execute(
                "SELECT * FROM magic_links WHERE token_hash=? AND used=0 AND expires_ts>?",
                (h, int(time.time()))
            ).fetchone()
            if not row:
                return {"error": "Link already used or expired"}
            c.execute("UPDATE magic_links SET used=1 WHERE token_hash=?", (h,))
    except Exception as e:
        logger.warning(f"verify_magic_link DB error: {e}")
        return {"error": "Verification failed"}

    _update_last_login(email)

    # Session token = another signed payload (email + ts)
    session_token = SIGNER.dumps({"email": email, "ts": int(time.time())})
    return {
        "verified": True,
        "email": email,
        "session_token": session_token,
        "message": f"Welcome back, {email}",
    }


def verify_session(session_token: str) -> Optional[str]:
    """Return email if session token is valid (24H TTL), else None."""
    SESSION_TTL = 86_400 * 30  # 30 days
    try:
        payload = SIGNER.loads(session_token, max_age=SESSION_TTL)
        return payload.get("email")
    except Exception:
        return None
