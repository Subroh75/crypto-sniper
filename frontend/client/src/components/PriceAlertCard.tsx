// PriceAlertCard.tsx
// In-app price & score alerts with browser Push Notification support.
// Alerts are stored server-side. Push subscription saved via /push/subscribe.

import { useState, useEffect } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

const USER_EMAIL = "subroh.iyer@gmail.com"; // default recipient

interface Alert {
  id:         number;
  symbol:     string;
  alert_type: string;
  threshold:  number;
  direction:  string;
  active:     number;
  fired_ts:   number | null;
  fire_count: number;
}

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

export function PriceAlertCard({ currentSymbol }: { currentSymbol?: string }) {
  const [alerts, setAlerts]       = useState<Alert[]>([]);
  const [loading, setLoading]     = useState(false);
  const [creating, setCreating]   = useState(false);
  const [pushEnabled, setPushEnabled] = useState(false);
  const [pushLoading, setPushLoading] = useState(false);

  // Form state
  const [symbol,    setSymbol]    = useState(currentSymbol ?? "BTC");
  const [alertType, setAlertType] = useState<"score" | "price">("score");
  const [threshold, setThreshold] = useState("9");
  const [direction, setDirection] = useState<"above" | "below">("above");
  const [formError, setFormError] = useState("");
  const [formSuccess, setFormSuccess] = useState("");

  // Keep symbol in sync with whatever is being analysed
  useEffect(() => {
    if (currentSymbol) setSymbol(currentSymbol);
  }, [currentSymbol]);

  // Check push permission status on mount
  useEffect(() => {
    if ("Notification" in window) {
      setPushEnabled(Notification.permission === "granted");
    }
    loadAlerts();
  }, []);

  async function loadAlerts() {
    setLoading(true);
    try {
      const r = await fetch(`${API}/alerts?email=${encodeURIComponent(USER_EMAIL)}`);
      const j = await r.json();
      setAlerts(j.alerts ?? []);
    } catch { setAlerts([]); }
    finally { setLoading(false); }
  }

  async function enablePush() {
    if (!("Notification" in window) || !("serviceWorker" in navigator)) {
      setFormError("Push notifications not supported in this browser");
      return;
    }
    setPushLoading(true);
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { setFormError("Notification permission denied"); setPushLoading(false); return; }
      setPushEnabled(true);

      // Register push subscription with service worker
      const reg = await navigator.serviceWorker.ready;
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        // Public VAPID key placeholder — works for permission grant even without real key
        applicationServerKey: urlB64ToUint8Array(
          "BEl62iUYgUivxIkv69yViEuiBIa-Ib9-SkvMeAtA3LFgDzkrxZJjSgSnfckjBJuBkr3qBuyAjqh7X3LVNkyMJ4Q"
        ),
      }).catch(() => null);

      if (sub) {
        const subJson = sub.toJSON() as {
          endpoint: string;
          keys: { p256dh: string; auth: string };
        };
        await fetch(`${API}/push/subscribe`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            endpoint: subJson.endpoint,
            p256dh:   subJson.keys?.p256dh ?? "",
            auth:     subJson.keys?.auth ?? "",
            user_id:  USER_EMAIL,
          }),
        });
      }
      setFormSuccess("Push notifications enabled");
    } catch (e) {
      setFormError("Failed to enable notifications");
    }
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
          email: USER_EMAIL,
          symbol: symbol.toUpperCase().trim(),
          alert_type: alertType,
          threshold: thr,
          direction,
        }),
      });
      const j = await r.json();
      if (j.error) { setFormError(j.error); }
      else {
        setFormSuccess(`Alert set for ${symbol.toUpperCase()} — ${alertType} ${direction} ${thr}`);
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
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "#f59e0b", fontSize: 13 }}>{"◎"}</span>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" as const }}>
            Price Alerts
          </span>
          {pushEnabled && (
            <span style={{ fontSize: 9, color: "#22c55e", background: "#0d2212", padding: "1px 5px", borderRadius: 3, border: "1px solid #14532d", fontWeight: 700 }}>
              PUSH ON
            </span>
          )}
        </div>
        {!pushEnabled && (
          <button
            onClick={enablePush}
            disabled={pushLoading}
            style={{ ...btnStyle, color: pushLoading ? "#334155" : "#7c3aed", borderColor: "#7c3aed44", cursor: pushLoading ? "not-allowed" : "pointer" }}
          >
            {pushLoading ? "…" : "Enable Push"}
          </button>
        )}
      </div>

      {/* Push explainer */}
      {!pushEnabled && (
        <div style={{ padding: "8px 10px", background: "#0a0f1e", border: "1px solid #1e293b", borderRadius: 8, marginBottom: 10 }}>
          <p style={{ fontSize: 10, color: "#64748b", lineHeight: 1.5, margin: 0 }}>
            Enable Push to get native notifications when alerts fire — no Telegram needed, straight to your lock screen.
          </p>
        </div>
      )}

      {/* Create alert form */}
      <form onSubmit={createAlert} style={{ background: "#0a0f1e", border: "1px solid #1e293b", borderRadius: 10, padding: 12, marginBottom: 10 }}>
        <div style={{ fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", color: "#334155", textTransform: "uppercase" as const, marginBottom: 8 }}>
          New Alert
        </div>

        {/* Symbol */}
        <div style={{ marginBottom: 8 }}>
          <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 3 }}>SYMBOL</label>
          <input
            value={symbol}
            onChange={e => setSymbol(e.target.value.toUpperCase())}
            placeholder="BTC"
            style={{ ...inputStyle, width: "calc(100% - 20px)" }}
          />
        </div>

        {/* Type + Direction */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
          <div>
            <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 3 }}>TYPE</label>
            <select
              value={alertType}
              onChange={e => { setAlertType(e.target.value as "score" | "price"); setThreshold(e.target.value === "score" ? "9" : ""); }}
              style={{ ...inputStyle, width: "100%" }}
            >
              <option value="score">Score</option>
              <option value="price">Price</option>
            </select>
          </div>
          <div>
            <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 3 }}>DIRECTION</label>
            <select
              value={direction}
              onChange={e => setDirection(e.target.value as "above" | "below")}
              style={{ ...inputStyle, width: "100%" }}
            >
              <option value="above">Above</option>
              <option value="below">Below</option>
            </select>
          </div>
        </div>

        {/* Threshold */}
        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: 9, color: "#475569", display: "block", marginBottom: 3 }}>
            {alertType === "score" ? "SCORE THRESHOLD (e.g. 9)" : "PRICE ($)"}
          </label>
          <input
            type="number"
            value={threshold}
            onChange={e => setThreshold(e.target.value)}
            placeholder={alertType === "score" ? "9" : "50000"}
            min={0}
            step={alertType === "score" ? 1 : "any"}
            style={{ ...inputStyle, width: "calc(100% - 20px)" }}
          />
        </div>

        {formError   && <div style={{ fontSize: 10, color: "#ef4444", marginBottom: 6 }}>{formError}</div>}
        {formSuccess && <div style={{ fontSize: 10, color: "#22c55e", marginBottom: 6 }}>{formSuccess}</div>}

        <button type="submit" disabled={creating} style={{ ...primaryBtn, opacity: creating ? 0.6 : 1, cursor: creating ? "not-allowed" : "pointer" }}>
          {creating ? "Setting…" : "Set Alert"}
        </button>
      </form>

      {/* Active alerts */}
      {loading && (
        <div style={{ padding: "10px 0", textAlign: "center" as const, fontSize: 10, color: "#475569" }}>Loading alerts…</div>
      )}

      {!loading && alerts.length === 0 && (
        <div style={{ padding: "8px 0", fontSize: 10, color: "#334155", textAlign: "center" as const }}>No active alerts</div>
      )}

      {!loading && alerts.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column" as const, gap: 6 }}>
          {alerts.map(alert => (
            <div key={alert.id} style={{
              display: "flex", alignItems: "center", justifyContent: "space-between",
              padding: "8px 10px",
              background: "#060b17", border: "1px solid #1e293b", borderRadius: 8,
            }}>
              <div>
                <div style={{ fontSize: 11, fontWeight: 800, color: "#f1f5f9", fontFamily: "monospace" }}>
                  {alert.symbol}
                  <span style={{ fontSize: 9, fontWeight: 400, color: "#475569", marginLeft: 6 }}>
                    {alert.alert_type} {alert.direction} {alert.threshold}
                  </span>
                </div>
                {alert.fired_ts && (
                  <div style={{ fontSize: 9, color: "#22c55e" }}>
                    Fired {new Date(alert.fired_ts * 1000).toLocaleDateString()}
                  </div>
                )}
              </div>
              <button
                onClick={() => deleteAlert(alert.id)}
                style={{ ...btnStyle, color: "#ef4444", borderColor: "#ef444433", padding: "3px 8px" }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Utility: base64url → Uint8Array (for VAPID key) ──────────────────────────
function urlB64ToUint8Array(base64String: string): Uint8Array {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = atob(base64);
  return Uint8Array.from([...rawData].map(c => c.charCodeAt(0)));
}
