"""
alerts.py — Price & score alerts for Crypto Sniper
Stores alerts in data.db. Fires via Gmail SMTP when configured.

Alert types:
  - price: notify when symbol price crosses a threshold
  - score: notify when symbol score >= threshold on next /analyse

Repeat / cooldown:
  - repeat=True  → alert stays active after firing; re-fires once cooldown_minutes has elapsed
  - repeat=False → one-shot, deactivated after first fire
  - cooldown_minutes default: 60 (score alerts), 240 (price alerts)
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
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            email            TEXT    NOT NULL,
            symbol           TEXT    NOT NULL,
            alert_type       TEXT    NOT NULL DEFAULT 'price',
            threshold        REAL    NOT NULL,
            direction        TEXT    NOT NULL DEFAULT 'above',
            active           INTEGER NOT NULL DEFAULT 1,
            repeat           INTEGER NOT NULL DEFAULT 0,
            cooldown_minutes INTEGER NOT NULL DEFAULT 60,
            created_ts       INTEGER NOT NULL,
            fired_ts         INTEGER DEFAULT NULL,
            last_fired_ts    INTEGER DEFAULT NULL,
            fire_count       INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_alerts_sym ON alerts(symbol, active);

        -- Fired alert history (separate table, never deleted)
        CREATE TABLE IF NOT EXISTS alert_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id   INTEGER NOT NULL,
            email      TEXT    NOT NULL,
            symbol     TEXT    NOT NULL,
            alert_type TEXT    NOT NULL,
            threshold  REAL    NOT NULL,
            direction  TEXT    NOT NULL,
            price      REAL    NOT NULL DEFAULT 0,
            score      INTEGER NOT NULL DEFAULT 0,
            fired_ts   INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ah_email ON alert_history(email, fired_ts DESC);

        -- Migration: add new columns if upgrading from old schema
        """)
        # Safe migrations — ignore errors if columns already exist
        for col_sql in [
            "ALTER TABLE alerts ADD COLUMN repeat INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE alerts ADD COLUMN cooldown_minutes INTEGER NOT NULL DEFAULT 60",
            "ALTER TABLE alerts ADD COLUMN last_fired_ts INTEGER DEFAULT NULL",
        ]:
            try:
                c.execute(col_sql)
            except Exception:
                pass


_init_alerts_db()


# ── Pydantic model ───────────────────────────────────────────────────────────
class AlertRequest(BaseModel):
    email:            str
    symbol:           str
    alert_type:       str   = "score"   # "price" | "score"
    threshold:        float = 9.0
    direction:        str   = "above"   # "above" | "below"
    repeat:           bool  = False
    cooldown_minutes: int   = 60        # min minutes between repeat fires


# ── CRUD ────────────────────────────────────────────────────────────────────
def register_alert(req: AlertRequest) -> dict:
    """Create a new alert. Returns the created alert dict."""
    try:
        cooldown = max(1, req.cooldown_minutes)
        with _get_conn() as c:
            cur = c.execute(
                """INSERT INTO alerts
                   (email, symbol, alert_type, threshold, direction, active,
                    repeat, cooldown_minutes, created_ts)
                   VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)""",
                (
                    req.email.lower().strip(),
                    req.symbol.upper().strip(),
                    req.alert_type,
                    req.threshold,
                    req.direction,
                    1 if req.repeat else 0,
                    cooldown,
                    int(time.time()),
                ),
            )
            alert_id = cur.lastrowid
        return {
            "alert_id":        alert_id,
            "email":           req.email,
            "symbol":          req.symbol.upper(),
            "alert_type":      req.alert_type,
            "threshold":       req.threshold,
            "direction":       req.direction,
            "repeat":          req.repeat,
            "cooldown_minutes": cooldown,
            "active":          True,
            "message": (
                f"Alert set: {req.symbol.upper()} {req.alert_type} {req.direction} {req.threshold}"
                + (f" | repeats every {cooldown}m" if req.repeat else " | one-shot")
            ),
        }
    except Exception as e:
        logger.warning(f"register_alert failed: {e}")
        return {"error": str(e)}


def get_alerts(email: str) -> list:
    """Return active alerts for an email, with next-fire info."""
    try:
        with _get_conn() as c:
            rows = c.execute(
                "SELECT * FROM alerts WHERE email=? AND active=1 ORDER BY created_ts DESC",
                (email.lower().strip(),),
            ).fetchall()
        result = []
        now = int(time.time())
        for r in rows:
            d = dict(r)
            # Add human-readable cooldown status
            if d.get("repeat") and d.get("last_fired_ts"):
                secs_since = now - d["last_fired_ts"]
                cooldown_secs = d.get("cooldown_minutes", 60) * 60
                d["cooldown_remaining_secs"] = max(0, cooldown_secs - secs_since)
            else:
                d["cooldown_remaining_secs"] = 0
            result.append(d)
        return result
    except Exception as e:
        logger.warning(f"get_alerts failed: {e}")
        return []


def get_alert_history(email: str, limit: int = 50) -> list:
    """Return recently fired alert history for an email (newest first)."""
    try:
        with _get_conn() as c:
            rows = c.execute(
                """SELECT * FROM alert_history
                   WHERE email=?
                   ORDER BY fired_ts DESC LIMIT ?""",
                (email.lower().strip(), limit),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"get_alert_history failed: {e}")
        return []


def get_unread_count(email: str, since_ts: int) -> int:
    """Count alerts fired after since_ts — used for badge."""
    try:
        with _get_conn() as c:
            row = c.execute(
                "SELECT COUNT(*) as cnt FROM alert_history WHERE email=? AND fired_ts > ?",
                (email.lower().strip(), since_ts),
            ).fetchone()
        return row["cnt"] if row else 0
    except Exception:
        return 0


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
    Repeating alerts are kept active but have a cooldown enforced.
    """
    try:
        with _get_conn() as c:
            alerts = c.execute(
                "SELECT * FROM alerts WHERE symbol=? AND active=1",
                (symbol.upper(),),
            ).fetchall()
    except Exception as e:
        logger.warning(f"check_and_fire_alerts DB read failed: {e}")
        return

    now = int(time.time())

    for alert in alerts:
        a = dict(alert)
        value = float(current_score) if a["alert_type"] == "score" else current_price

        # Check condition
        triggered = False
        if a["direction"] == "above" and value >= a["threshold"]:
            triggered = True
        elif a["direction"] == "below" and value <= a["threshold"]:
            triggered = True

        if not triggered:
            continue

        # Enforce cooldown for repeating alerts
        if a.get("repeat"):
            last_fired = a.get("last_fired_ts") or 0
            cooldown_secs = a.get("cooldown_minutes", 60) * 60
            if now - last_fired < cooldown_secs:
                continue  # Still in cooldown window — skip

        # Fire
        _fire_alert(a, symbol, current_price, current_score)
        _record_history(a, symbol, current_price, current_score, now)

        # Update alert state
        try:
            with _get_conn() as c:
                if a.get("repeat"):
                    # Keep active, just update last_fired_ts + fire_count
                    c.execute(
                        "UPDATE alerts SET last_fired_ts=?, fired_ts=?, fire_count=fire_count+1 WHERE id=?",
                        (now, now, a["id"]),
                    )
                else:
                    # One-shot: deactivate
                    c.execute(
                        "UPDATE alerts SET active=0, last_fired_ts=?, fired_ts=?, fire_count=fire_count+1 WHERE id=?",
                        (now, now, a["id"]),
                    )
        except Exception as e:
            logger.warning(f"check_and_fire_alerts DB update failed: {e}")


def _record_history(alert: dict, symbol: str, price: float, score: int, fired_ts: int):
    """Persist every fire event to alert_history."""
    try:
        with _get_conn() as c:
            c.execute(
                """INSERT INTO alert_history
                   (alert_id, email, symbol, alert_type, threshold, direction, price, score, fired_ts)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    alert["id"], alert["email"], symbol,
                    alert["alert_type"], alert["threshold"], alert["direction"],
                    price, score, fired_ts,
                ),
            )
    except Exception as e:
        logger.warning(f"_record_history failed: {e}")


def _fire_alert(alert: dict, symbol: str, price: float, score: int):
    """Send email notification for a triggered alert."""
    email = alert["email"]
    atype = alert["alert_type"]
    thr   = alert["threshold"]
    dirn  = alert["direction"]
    repeat_note = " (repeating)" if alert.get("repeat") else ""

    subject = f"Crypto Sniper Alert — {symbol} {atype} {dirn} {thr}{repeat_note}"

    if atype == "score":
        body_html = f"""
        <div style="font-family:sans-serif;background:#0c1225;color:#e2e8f0;padding:24px;border-radius:12px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:4px;color:#7c3aed;text-transform:uppercase;margin-bottom:6px;">Crypto Sniper Alert</div>
          <h2 style="margin:0 0 12px;color:#22c55e;">{symbol} — Score Alert Triggered</h2>
          <p><strong>{symbol}</strong> scored <strong style="color:#22c55e;">{score}/16</strong>
             — STRONG BUY signal detected.</p>
          <p style="color:#94a3b8;">Alert condition: score {dirn} {thr}</p>
          <p>Current price: <strong>${price:,.6g}</strong></p>
          {'<p style="color:#64748b;font-size:11px;">This is a repeating alert — it will fire again after the cooldown period.</p>' if alert.get("repeat") else ""}
          <hr style="border-color:#1e293b;"/>
          <p><a href="https://crypto-sniper.app" style="color:#7c3aed;">Open Crypto Sniper</a></p>
          <p style="color:#475569;font-size:11px;">Not financial advice.</p>
        </div>"""
        body_plain = f"{symbol} scored {score}/16 — STRONG BUY. Price: ${price:.6g}\nhttps://crypto-sniper.app"
    else:
        direction_word = "crossed above" if dirn == "above" else "dropped below"
        body_html = f"""
        <div style="font-family:sans-serif;background:#0c1225;color:#e2e8f0;padding:24px;border-radius:12px;">
          <div style="font-size:11px;font-weight:700;letter-spacing:4px;color:#7c3aed;text-transform:uppercase;margin-bottom:6px;">Crypto Sniper Alert</div>
          <h2 style="margin:0 0 12px;color:#22c55e;">{symbol} — Price Alert Triggered</h2>
          <p><strong>{symbol}</strong> has {direction_word}
             <strong>${thr:,.6g}</strong>.</p>
          <p>Current price: <strong style="color:#22c55e;">${price:,.6g}</strong></p>
          {'<p style="color:#64748b;font-size:11px;">This is a repeating alert — it will fire again after the cooldown period.</p>' if alert.get("repeat") else ""}
          <hr style="border-color:#1e293b;"/>
          <p><a href="https://crypto-sniper.app" style="color:#7c3aed;">Open Crypto Sniper</a></p>
          <p style="color:#475569;font-size:11px;">Not financial advice.</p>
        </div>"""
        body_plain = f"{symbol} {direction_word} ${thr:,.6g}. Now: ${price:.6g}\nhttps://crypto-sniper.app"

    _send_email_smtp(email, subject, body_html, body_plain)


def _send_email_smtp(to: str, subject: str, html: str, plain: str):
    """
    Send via Gmail SMTP using env vars GMAIL_USER + GMAIL_APP_PASSWORD.
    Falls back silently if not configured.
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
