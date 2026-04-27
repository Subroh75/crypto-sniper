"""
alerts.py — Price & score alerts for Crypto Sniper
Stores alerts in data.db. Fires via Gmail (SMTP or gcal connector stub).

Alert types:
  - price: notify when symbol price crosses a threshold
  - score: notify when symbol score >= threshold on next /analyse
"""

import sqlite3, os, time, logging, smtplib
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(os.path.dirname(__file__), "data.db")

# ── DB setup ────────────────────────────────────────────────────────────────
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init_alerts_db():
    with _get_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS alerts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    NOT NULL,
            symbol      TEXT    NOT NULL,
            alert_type  TEXT    NOT NULL DEFAULT 'price',  -- 'price' | 'score'
            threshold   REAL    NOT NULL,
            direction   TEXT    NOT NULL DEFAULT 'above',  -- 'above' | 'below'
            active      INTEGER NOT NULL DEFAULT 1,
            created_ts  INTEGER NOT NULL,
            fired_ts    INTEGER DEFAULT NULL,
            fire_count  INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_sym ON alerts(symbol, active);
        """)


_init_alerts_db()


# ── Pydantic model ───────────────────────────────────────────────────────────
class AlertRequest(BaseModel):
    email:      str
    symbol:     str
    alert_type: str   = "score"   # "price" | "score"
    threshold:  float = 9.0       # score >= 9 or price >= X
    direction:  str   = "above"   # "above" | "below"


# ── CRUD ────────────────────────────────────────────────────────────────────
def register_alert(req: AlertRequest) -> dict:
    """Create a new alert. Returns the created alert dict."""
    try:
        with _get_conn() as c:
            cur = c.execute(
                """INSERT INTO alerts (email, symbol, alert_type, threshold, direction, active, created_ts)
                   VALUES (?, ?, ?, ?, ?, 1, ?)""",
                (req.email.lower().strip(), req.symbol.upper().strip(),
                 req.alert_type, req.threshold, req.direction, int(time.time())),
            )
            alert_id = cur.lastrowid
        return {
            "alert_id": alert_id,
            "email": req.email,
            "symbol": req.symbol.upper(),
            "alert_type": req.alert_type,
            "threshold": req.threshold,
            "direction": req.direction,
            "active": True,
            "message": f"Alert set: notify when {req.symbol.upper()} {req.alert_type} is {req.direction} {req.threshold}",
        }
    except Exception as e:
        logger.warning(f"register_alert failed: {e}")
        return {"error": str(e)}


def get_alerts(email: str) -> list:
    """Return active alerts for an email."""
    try:
        with _get_conn() as c:
            rows = c.execute(
                "SELECT * FROM alerts WHERE email=? AND active=1 ORDER BY created_ts DESC",
                (email.lower().strip(),),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"get_alerts failed: {e}")
        return []


def delete_alert(alert_id: int) -> bool:
    """Soft-delete an alert (set active=0)."""
    try:
        with _get_conn() as c:
            c.execute("UPDATE alerts SET active=0 WHERE id=?", (alert_id,))
        return True
    except Exception as e:
        logger.warning(f"delete_alert failed: {e}")
        return False


# ── Alert firing ─────────────────────────────────────────────────────────────
def check_and_fire_alerts(symbol: str, current_price: float, current_score: int):
    """
    Called on each /analyse for the given symbol.
    Checks all active alerts and fires any that trip.
    """
    try:
        with _get_conn() as c:
            alerts = c.execute(
                "SELECT * FROM alerts WHERE symbol=? AND active=1",
                (symbol.upper(),),
            ).fetchall()

        for alert in alerts:
            a = dict(alert)
            triggered = False
            value = 0.0

            if a["alert_type"] == "price":
                value = current_price
            elif a["alert_type"] == "score":
                value = float(current_score)

            if a["direction"] == "above" and value >= a["threshold"]:
                triggered = True
            elif a["direction"] == "below" and value <= a["threshold"]:
                triggered = True

            if triggered:
                _fire_alert(a, symbol, current_price, current_score)
                # Deactivate after firing once (one-shot alerts)
                with _get_conn() as c:
                    c.execute(
                        "UPDATE alerts SET active=0, fired_ts=?, fire_count=fire_count+1 WHERE id=?",
                        (int(time.time()), a["id"]),
                    )
    except Exception as e:
        logger.warning(f"check_and_fire_alerts failed: {e}")


def _fire_alert(alert: dict, symbol: str, price: float, score: int):
    """Send email notification for a triggered alert."""
    email = alert["email"]
    subject = f"Crypto Sniper Alert — {symbol} {alert['alert_type']} {alert['direction']} {alert['threshold']}"

    if alert["alert_type"] == "score":
        body_html = f"""
        <div style="font-family:sans-serif;background:#0c1225;color:#e2e8f0;padding:24px;border-radius:12px;">
          <h2 style="color:#7c3aed;">🎯 Crypto Sniper Alert Triggered</h2>
          <p><strong style="color:#22c55e;">{symbol}</strong> just scored
             <strong style="color:#22c55e;">{score}/16</strong> — STRONG BUY signal detected.</p>
          <p>Alert set for: score ≥ {alert['threshold']}</p>
          <p>Current price: <strong>${price:,.6g}</strong></p>
          <hr style="border-color:#1e293b;"/>
          <p><a href="https://crypto-sniper.app" style="color:#7c3aed;">Open Crypto Sniper →</a></p>
          <p style="color:#475569;font-size:11px;">Not financial advice.</p>
        </div>"""
        body_plain = f"{symbol} scored {score}/16 — STRONG BUY. Price: ${price:.6g}\nhttps://crypto-sniper.app"
    else:
        direction_word = "crossed above" if alert["direction"] == "above" else "dropped below"
        body_html = f"""
        <div style="font-family:sans-serif;background:#0c1225;color:#e2e8f0;padding:24px;border-radius:12px;">
          <h2 style="color:#7c3aed;">💰 Crypto Sniper Price Alert</h2>
          <p><strong style="color:#22c55e;">{symbol}</strong> has {direction_word}
             <strong>${alert['threshold']:,.6g}</strong>.</p>
          <p>Current price: <strong style="color:#22c55e;">${price:,.6g}</strong></p>
          <hr style="border-color:#1e293b;"/>
          <p><a href="https://crypto-sniper.app" style="color:#7c3aed;">Open Crypto Sniper →</a></p>
          <p style="color:#475569;font-size:11px;">Not financial advice.</p>
        </div>"""
        body_plain = f"{symbol} {direction_word} ${alert['threshold']:,.6g}. Now: ${price:.6g}\nhttps://crypto-sniper.app"

    _send_email_smtp(email, subject, body_html, body_plain)


def _send_email_smtp(to: str, subject: str, html: str, plain: str):
    """
    Send via Gmail SMTP using env vars GMAIL_USER + GMAIL_APP_PASSWORD.
    Falls back silently if not configured (alerts still record as fired in DB).
    """
    user = os.getenv("GMAIL_USER", "")
    pwd  = os.getenv("GMAIL_APP_PASSWORD", "")

    if not user or not pwd:
        logger.info(f"Alert email not sent (SMTP not configured): {to} — {subject}")
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = f"Crypto Sniper <{user}>"
        msg["To"]      = to
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as s:
            s.login(user, pwd)
            s.sendmail(user, to, msg.as_string())
        logger.info(f"Alert email sent to {to}: {subject}")
    except Exception as e:
        logger.warning(f"SMTP send failed: {e}")
