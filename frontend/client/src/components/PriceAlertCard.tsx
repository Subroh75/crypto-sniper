// PriceAlertCard.tsx
// Price & score alerts — repeat mode, cooldown, push notifications.

import { useState, useEffect, useCallback } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

const USER_EMAIL = "subroh.iyer@gmail.com";

export interface AlertHistoryEntry {
  id:         number;
  alert_id:   number;
  email:      string;
  symbol:     string;
  alert_type: string;
  threshold:  number;
  direction:  string;
  price:      number;
  score:      number;
  fired_ts:   number;
}

export interface Alert {
  id:                   number;
  symbol:               string;
  alert_type:           string;
  threshold:            number;
  direction:            string;
  active:               number;
  repeat:               number;
  cooldown_minutes:     number;
  fired_ts:             number | null;
  last_fired_ts:        number | null;
  fire_count:           number;
  cooldown_remaining_secs?: number;
}

// ── Shared alert state (exported so header bell can subscribe) ────────────
type AlertListener = (count: number, history: AlertHistoryEntry[]) => void;
const _listeners = new Set<AlertListener>();
let _unreadCount = 0;
let _history: AlertHistoryEntry[] = [];
let _lastSeenTs = 0;

export function subscribeAlertBadge(fn: AlertListener) {
  _listeners.add(fn);
  fn(_unreadCount, _history);
  return () => _listeners.delete(fn);
}
export function markAlertsRead() {
  _lastSeenTs = Math.floor(Date.now() / 1000);
  _unreadCount = 0;
  _listeners.forEach(fn => fn(0, _history));
  try { localStorage.setItem("alert_seen_ts", String(_lastSeenTs)); } catch {}
}

async function _pollBadge() {
  try {
    const sinceTs = _lastSeenTs;
    const r = await fetch(`${API}/alerts/unread?email=${encodeURIComponent(USER_EMAIL)}&since_ts=${sinceTs}`);
    if (!r.ok) return;
    const j = await r.json();
    const newCount = j.unread ?? 0;
    if (newCount !== _unreadCount) {
      _unreadCount = newCount;
      // Also refresh history if there are new alerts
      if (newCount > 0) {
        const hr = await fetch(`${API}/alerts/history?email=${encodeURIComponent(USER_EMAIL)}&limit=20`);
        if (hr.ok) {
          const hj = await hr.json();
          _history = hj.history ?? [];
        }
      }
      _listeners.forEach(fn => fn(_unreadCount, _history));
    }
  } catch {}
}

// Init: load last-seen ts from localStorage and start polling every 2 minutes
try {
  const saved = localStorage.getItem("alert_seen_ts");
  if (saved) _lastSeenTs = parseInt(saved, 10) || 0;
} catch {}
setInterval(_pollBadge, 2 * 60 * 1000);
_pollBadge(); // immediate first check

// ── Styles ────────────────────────────────────────────────────────────────
const btnStyle = {
  fontSize: 9, color: "#64748b", background: "#0f172a",
  border: "1px solid #1e293b", borderRadius: 4,
  padding: "2px 6px", cursor: "pointer",
} as const;

const primaryBtn = {
  fontSize: 10, fontWeight: 700, color: "#f1f5f9",
  background: "#7c3aed", border: "1px solid #6d28d9",
  borderRadius: 6, padding: "7px 14px", cursor: "pointer",
  letterSpacing: "0.04em",
} as const;

const inputStyle = {
  fontSize: 11, color: "#f1f5f9", background: "#0a0f1e",
  border: "1px solid #1e293b", borderRadius: 6,
  padding: "6px 10px", width: "100%", outline: "none",
  fontFamily: "monospace",
} as const;

const COOLDOWN_OPTIONS = [
  { label: "15m",  value: 15 },
  { label: "30m",  value: 30 },
  { label: "1h",   value: 60 },
  { label: "4h",   value: 240 },
  { label: "8h",   value: 480 },
  { label: "24h",  value: 1440 },
];

function fmtCooldownRemaining(secs: number): string {
  if (secs <= 0) return "ready";
  const m = Math.ceil(secs / 60);
  if (m < 60) return `${m}m`;
  return `${Math.ceil(m / 60)}h`;
}

function fmtTs(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
    " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

// ── Main component ────────────────────────────────────────────────────────
export function PriceAlertCard({ currentSymbol }: { currentSymbol?: string }) {
  const [alerts, setAlerts]     = useState<Alert[]>([]);
  const [loading, setLoading]   = useState(false);
  const [creating, setCreating] = useState(false);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushLoading, setPushLoading] = useState(false);
  const [tab, setTab]           = useState<"active" | "history">("active");
  const [history, setHistory]   = useState<AlertHistoryEntry[]>([]);

  // Form state
  const [symbol,    setSymbol]    = useState(currentSymbol ?? "BTC");
  const [alertType, setAlertType] = useState<"score" | "price">("score");
  const [threshold, setThreshold] = useState("9");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [repeat,    setRepeat]    = useState(false);
  const [cooldown,  setCooldown]  = useState(60);
  const [formError,   setFormError]   = useState("");
  const [formSuccess, setFormSuccess] = useState("");

  useEffect(() => { if (currentSymbol) setSymbol(currentSymbol); }, [currentSymbol]);

  useEffect(() => {
    if ("Notification" in window) setPushEnabled(Notification.permission === "granted");
    loadAlerts();
    loadHistory();
  }, []);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/alerts?email=${encodeURIComponent(USER_EMAIL)}`);
      const j = await r.json();
      setAlerts(j.alerts ?? []);
    } catch { setAlerts([]); }
    finally { setLoading(false); }
  }, []);

  const loadHistory = useCallback(async () => {
    try {
      const r = await fetch(`${API}/alerts/history?email=${encodeURIComponent(USER_EMAIL)}&limit=30`);
      const j = await r.json();
      setHistory(j.history ?? []);
      // Sync shared history
      _history = j.history ?? [];
    } catch {}
  }, []);

  async function enablePush() {
    if (!("Notification" in window) || !("serviceWorker" in navigator)) {
      setFormError("Push not supported in this browser"); return;
    }
    setPushLoading(true);
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { setFormError("Permission denied"); setPushLoading(false); return; }
      setPushEnabled(true);
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlB64ToUint8Array(
          "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBuyAjqh7X3LVNkyMJ4Q"
        ),
      }).catch(() => null);
      if (sub) {
        const s = sub.toJSON() as { endpoint: string; keys: { p256dh: string; auth: string } };
        await fetch(`${API}/push/subscribe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ endpoint: s.endpoint, p256dh: s.keys?.p256dh ?? "", auth: s.keys?.auth ?? "", user_id: USER_EMAIL }),
        });
      }
      setFormSuccess("Push notifications enabled");
    } catch { setFormError("Failed to enable push"); }
    setPushLoading(false);
  }

  async function createAlert(e: React.FormEvent) {
    e.preventDefault();
    setFormError(""); setFormSuccess("");
    const thr = parseFloat(threshold);
    if (isNaN(thr) || thr <= 0) { setFormError("Enter a valid threshold"); return; }
    setCreating(true);
    try {
      const r = await fetch(`${API}/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email:            USER_EMAIL,
          symbol:           symbol.toUpperCase().trim(),
          alert_type:       alertType,
          threshold:        thr,
          direction,
          repeat,
          cooldown_minutes: repeat ? cooldown : 60,
        }),
      });
      const j = await r.json();
      if (j.error) { setFormError(j.error); }
      else {
        setFormSuccess(`Alert set — ${symbol.toUpperCase()} ${alertType} ${direction} ${thr}${repeat ? ` (repeats every ${cooldown >= 60 ? cooldown/60 + "h" : cooldown + "m"})` : ""}`);
        await loadAlerts();
      }
    } catch { setFormError("Failed to create alert"); }
    setCreating(false);
  }

  async function deleteAlert(id: number) {
    try {
      await fetch(`${API}/alerts/${id}`, { method: "DELETE" });
      setAlerts(prev => prev.filter(a => a.id !== id));
    } catch {}
  }

  return (
    <div style={{ marginBottom: 14 }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "#f59e0b", fontSize: 13 }}>◎</span>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" }}>
            Price Alerts
          </span>
          {pushEnabled && (
            <span style={{ fontSize: 9, color: "#22c55e", background: "#0d2212", padding: "1px 5px", borderRadius: 3, border: "1px solid #14532d", fontWeight: 700 }}>
              PUSH ON
            </span>
          )}
        </div>
        {!pushEnabled && (
          <button onClick={enablePush} disabled={pushLoading} style={{ ...btnStyle, color: pushLoading ? "#334155" : "#7c3aed", borderColor: "#7c3aed44" }}>
            {pushLoading ? "…" : "Enable Push"}
          </button>
        )}
      </div>

      {/* Tab switcher */}
      <div style={{ display: "flex", gap: 4, marginBottom: 10 }}>
        {(["active", "history"] as const).map(t => (
          <button key={t} onClick={() => { setTab(t); if (t === "history") loadHistory(); }}
            style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
              padding: "4px 10px", borderRadius: 5, cursor: "pointer",
              background: tab === t ? "#7c3aed22" : "transparent",
              color: tab === t ? "#a78bfa" : "#475569",
              border: tab === t ? "1px solid #7c3aed44" : "1px solid #1e293b",
            }}>
            {t === "active" ? `Active (${alerts.length})` : `History (${history.length})`}
          </button>
        ))}
      </div>

      {/* === ACTIVE TAB === */}
      {tab === "active" && (<>
        {/* Create form */}
        <form onSubmit={createAlert} style={{ background: "#0a0f1e", border: "1px solid #1e293b", borderRadius: 10, padding: 12, marginBottom: 10 }}>
          <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", color: "#334155", textTransform: "uppercase", marginBottom: 8 }}>
            New Alert
          </div>

          {/* Symbol */}
          <div style={{ marginBottom: 8 }}>
            <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 3 }}>SYMBOL</label>
            <input value={symbol} onChange={e => setSymbol(e.target.value.toUpperCase())}
              placeholder="BTC" style={{ ...inputStyle, width: "calc(100% - 20px)" }} />
          </div>

          {/* Type + Direction */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
            <div>
              <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 3 }}>TYPE</label>
              <select value={alertType}
                onChange={e => { setAlertType(e.target.value as "score" | "price"); setThreshold(e.target.value === "score" ? "9" : ""); }}
                style={{ ...inputStyle, width: "100%" }}>
                <option value="score">Score</option>
                <option value="price">Price</option>
              </select>
            </div>
            <div>
              <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 3 }}>DIRECTION</label>
              <select value={direction} onChange={e => setDirection(e.target.value as "above" | "below")}
                style={{ ...inputStyle, width: "100%" }}>
                <option value="above">Above</option>
                <option value="below">Below</option>
              </select>
            </div>
          </div>

          {/* Threshold */}
          <div style={{ marginBottom: 10 }}>
            <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 3 }}>
              {alertType === "score" ? "SCORE THRESHOLD (1–16)" : "PRICE ($)"}
            </label>
            <input type="number" value={threshold} onChange={e => setThreshold(e.target.value)}
              placeholder={alertType === "score" ? "9" : "50000"}
              min={0} step={alertType === "score" ? 1 : "any"}
              style={{ ...inputStyle, width: "calc(100% - 20px)" }} />
          </div>

          {/* Repeat toggle */}
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: repeat ? 8 : 10 }}>
            <button type="button" onClick={() => setRepeat(p => !p)}
              style={{ width: 32, height: 18, borderRadius: 9, border: "none", cursor: "pointer",
                background: repeat ? "#7c3aed" : "#1e293b", position: "relative", flexShrink: 0, transition: "background 0.2s" }}>
              <span style={{ position: "absolute", top: 2, left: repeat ? 14 : 2, width: 14, height: 14,
                borderRadius: "50%", background: "#f1f5f9", transition: "left 0.2s" }} />
            </button>
            <span style={{ fontSize: 10, color: repeat ? "#a78bfa" : "#475569" }}>
              Repeat alert
            </span>
          </div>

          {/* Cooldown — only shown when repeat is on */}
          {repeat && (
            <div style={{ marginBottom: 10 }}>
              <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 5 }}>COOLDOWN (re-fire after)</label>
              <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                {COOLDOWN_OPTIONS.map(opt => (
                  <button key={opt.value} type="button"
                    onClick={() => setCooldown(opt.value)}
                    style={{ fontSize: 9, fontWeight: 700, padding: "3px 8px", borderRadius: 4, cursor: "pointer",
                      background: cooldown === opt.value ? "#7c3aed22" : "transparent",
                      color: cooldown === opt.value ? "#a78bfa" : "#475569",
                      border: cooldown === opt.value ? "1px solid #7c3aed" : "1px solid #1e293b",
                    }}>
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {formError   && <div style={{ fontSize: 10, color: "#ef4444", marginBottom: 6 }}>{formError}</div>}
          {formSuccess && <div style={{ fontSize: 10, color: "#22c55e", marginBottom: 6 }}>{formSuccess}</div>}

          <button type="submit" disabled={creating}
            style={{ ...primaryBtn, opacity: creating ? 0.6 : 1, cursor: creating ? "not-allowed" : "pointer" }}>
            {creating ? "Setting…" : "Set Alert"}
          </button>
        </form>

        {/* Active list */}
        {loading && <div style={{ padding: "10px 0", textAlign: "center", fontSize: 10, color: "#475569" }}>Loading…</div>}
        {!loading && alerts.length === 0 && (
          <div style={{ padding: "8px 0", fontSize: 10, color: "#334155", textAlign: "center" }}>No active alerts</div>
        )}
        {!loading && alerts.map(alert => {
          const inCooldown = alert.repeat && (alert.cooldown_remaining_secs ?? 0) > 0;
          const repeatLabel = alert.repeat
            ? `repeats every ${alert.cooldown_minutes >= 60 ? alert.cooldown_minutes/60 + "h" : alert.cooldown_minutes + "m"}`
            : "one-shot";
          return (
            <div key={alert.id} style={{
              display: "flex", alignItems: "flex-start", justifyContent: "space-between",
              padding: "9px 10px", marginBottom: 6,
              background: "#060b17", border: "1px solid #1e293b", borderRadius: 8,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#f1f5f9", fontFamily: "monospace" }}>
                    {alert.symbol}
                  </span>
                  {alert.repeat ? (
                    <span style={{ fontSize: 8, fontWeight: 700, color: "#7c3aed", background: "#1a0a3d", padding: "1px 5px", borderRadius: 3, border: "1px solid #4c1d95" }}>
                      REPEAT
                    </span>
                  ) : (
                    <span style={{ fontSize: 8, color: "#334155", background: "#0f172a", padding: "1px 5px", borderRadius: 3, border: "1px solid #1e293b" }}>
                      ONE-SHOT
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 10, color: "#475569" }}>
                  {alert.alert_type} {alert.direction} <span style={{ color: "#94a3b8", fontFamily: "monospace" }}>{alert.threshold}</span>
                  <span style={{ color: "#334155", marginLeft: 6 }}>· {repeatLabel}</span>
                </div>
                <div style={{ display: "flex", gap: 8, marginTop: 3 }}>
                  {alert.fire_count > 0 && (
                    <span style={{ fontSize: 9, color: "#22c55e" }}>
                      Fired {alert.fire_count}× {alert.last_fired_ts ? `· last ${fmtTs(alert.last_fired_ts)}` : ""}
                    </span>
                  )}
                  {inCooldown && (
                    <span style={{ fontSize: 9, color: "#f59e0b" }}>
                      Next in {fmtCooldownRemaining(alert.cooldown_remaining_secs ?? 0)}
                    </span>
                  )}
                </div>
              </div>
              <button onClick={() => deleteAlert(alert.id)}
                style={{ ...btnStyle, color: "#ef4444", borderColor: "#ef444433", padding: "3px 8px", flexShrink: 0, marginLeft: 8 }}>
                ×
              </button>
            </div>
          );
        })}
      </>)}

      {/* === HISTORY TAB === */}
      {tab === "history" && (<>
        {history.length === 0 && (
          <div style={{ padding: "12px 0", fontSize: 10, color: "#334155", textAlign: "center" }}>No fired alerts yet</div>
        )}
        {history.map(h => (
          <div key={h.id} style={{
            padding: "8px 10px", marginBottom: 6,
            background: "#060b17", border: "1px solid #1e293b", borderRadius: 8,
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#22c55e", fontFamily: "monospace" }}>{h.symbol}</span>
                  <span style={{ fontSize: 9, color: "#64748b" }}>{h.alert_type} {h.direction} {h.threshold}</span>
                </div>
                <div style={{ fontSize: 10, color: "#475569" }}>
                  {h.alert_type === "score" ? (
                    <>Score <span style={{ color: "#22c55e", fontFamily: "monospace" }}>{h.score}/16</span></>
                  ) : (
                    <>Price <span style={{ color: "#22c55e", fontFamily: "monospace" }}>${h.price.toFixed(6)}</span></>
                  )}
                </div>
              </div>
              <div style={{ fontSize: 9, color: "#334155", textAlign: "right", whiteSpace: "nowrap" }}>
                {fmtTs(h.fired_ts)}
              </div>
            </div>
          </div>
        ))}
      </>)}
    </div>
  );
}

function urlB64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
}
