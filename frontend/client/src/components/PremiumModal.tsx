/**
 * PremiumModal — Tier-gating lockout overlay.
 *
 * Usage:
 *   const { gate } = usePremiumGate(user, "full");
 *   if (gate) return gate;          // renders lockout in-place
 *
 *   // Or as a modal over content:
 *   <PremiumModal open={!allowed} feature="Live Scanner" requiredTier="full" />
 */
import type { UserTier } from "@/types/api";

// ── Tier display config ───────────────────────────────────────────────────────
const TIER_LABELS: Record<UserTier, string> = {
  free:       "Free",
  basic:      "Signals Basic",
  pro:        "Signals Pro",
  pro_kronos: "Pro + Kronos",
  full:       "Full App",
  admin:      "Admin",
};

const TIER_STARS: Record<UserTier, string> = {
  free:       "",
  basic:      "250 Stars/mo",
  pro:        "500 Stars/mo",
  pro_kronos: "750 Stars/mo",
  full:       "1,500 Stars/mo",
  admin:      "",
};

// What each full-app feature looks like
const FULL_APP_FEATURES = [
  "Live scanner — 200 coins",
  "Deep analysis on any coin",
  "Kronos AI forecast",
  "Signal streak heatmap",
  "Trade setup with entry / SL / TP",
  "Agent debate (Bull / Bear / CIO)",
];

// Telegram bot deep-link for upgrade
const TG_UPGRADE_URL = "https://t.me/Niftysnipabot?start=subscribe";

interface PremiumModalProps {
  /** Whether the modal is visible */
  open: boolean;
  /** Short feature name for contextual headline, e.g. "Live scanner" */
  feature?: string;
  /** The minimum tier required */
  requiredTier?: UserTier;
  /** Current user tier (to show contextual upsell copy) */
  currentTier?: UserTier;
  /** Called when user clicks "Maybe Later" */
  onDismiss?: () => void;
  /** If true, renders inline (no backdrop/overlay). Default false = full modal */
  inline?: boolean;
}

export function PremiumModal({
  open,
  feature,
  requiredTier = "full",
  currentTier  = "free",
  onDismiss,
  inline = false,
}: PremiumModalProps) {
  if (!open) return null;

  const headline = feature
    ? `${feature} — ${TIER_LABELS[requiredTier]} only`
    : `${TIER_LABELS[requiredTier]} required`;

  const subline = currentTier !== "free"
    ? `You're on ${TIER_LABELS[currentTier]}. Upgrade to unlock this.`
    : "Upgrade to unlock full access.";

  const stars = TIER_STARS[requiredTier];

  const content = (
    <div
      style={{
        background: "#0c1225",
        border: "1px solid #1e293b",
        borderRadius: 16,
        padding: "28px 24px",
        width: "100%",
        maxWidth: 360,
        margin: inline ? "0 auto" : undefined,
        boxShadow: inline ? "none" : "0 24px 64px rgba(0,0,0,0.8)",
        position: "relative",
      }}
    >
      {/* Top accent bar */}
      <div style={{
        position: "absolute", top: 0, left: 0, right: 0, height: 3,
        background: "linear-gradient(90deg,#7c3aed,#4f46e5)",
        borderRadius: "16px 16px 0 0",
      }} />

      {/* Lock icon */}
      <div style={{ textAlign: "center", marginBottom: 12 }}>
        <div style={{
          display: "inline-flex", alignItems: "center", justifyContent: "center",
          width: 48, height: 48, borderRadius: "50%",
          background: "rgba(124,58,237,0.12)", border: "1px solid rgba(124,58,237,0.3)",
        }}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#7c3aed" strokeWidth="2.5">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
            <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
          </svg>
        </div>
      </div>

      {/* Headline */}
      <div style={{
        textAlign: "center", fontSize: 15, fontWeight: 900,
        color: "#f1f5f9", fontFamily: "monospace", marginBottom: 4,
        letterSpacing: "0.02em",
      }}>
        {headline}
      </div>
      <div style={{
        textAlign: "center", fontSize: 11, color: "#64748b",
        fontFamily: "monospace", marginBottom: 20,
      }}>
        {subline}
      </div>

      {/* Feature list (only for full tier) */}
      {requiredTier === "full" && (
        <div style={{ marginBottom: 20 }}>
          {FULL_APP_FEATURES.map(f => (
            <div key={f} style={{
              display: "flex", alignItems: "center", gap: 8,
              padding: "5px 0", borderBottom: "1px solid #0f172a",
            }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              <span style={{ fontSize: 11, fontFamily: "monospace", color: "#94a3b8" }}>{f}</span>
            </div>
          ))}
        </div>
      )}

      {/* CTA */}
      <a
        href={TG_UPGRADE_URL}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          display: "flex", alignItems: "center", justifyContent: "center",
          gap: 8, width: "100%", padding: "12px 0",
          borderRadius: 10, background: "linear-gradient(135deg,#7c3aed,#4f46e5)",
          color: "#fff", fontFamily: "monospace", fontWeight: 700,
          fontSize: 13, textDecoration: "none", marginBottom: 10,
          boxShadow: "0 4px 16px rgba(124,58,237,0.35)",
          transition: "opacity 0.15s",
        }}
      >
        {/* Star icon */}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="#fff">
          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
        </svg>
        Upgrade on Telegram{stars ? ` — ${stars}` : ""}
      </a>

      {/* Dismiss */}
      {onDismiss && (
        <button
          onClick={onDismiss}
          style={{
            display: "block", width: "100%", padding: "8px 0",
            background: "none", border: "none", cursor: "pointer",
            fontFamily: "monospace", fontSize: 11, color: "#334155",
            transition: "color 0.15s",
          }}
          onMouseEnter={e => (e.currentTarget.style.color = "#64748b")}
          onMouseLeave={e => (e.currentTarget.style.color = "#334155")}
        >
          Maybe Later
        </button>
      )}
    </div>
  );

  if (inline) return content;

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 2000,
        display: "flex", alignItems: "center", justifyContent: "center",
        background: "rgba(0,0,0,0.75)", backdropFilter: "blur(6px)",
        padding: "0 16px",
      }}
      onClick={e => { if (e.target === e.currentTarget) onDismiss?.(); }}
    >
      {content}
    </div>
  );
}


// ── usePremiumGate — inline gate helper ───────────────────────────────────────
// Returns { allowed: boolean, gate: JSX | null }
// If allowed, gate is null. If blocked, gate renders the inline lockout.

import { useState } from "react";
import type { AuthUser } from "@/types/api";
import { tierAtLeast } from "@/hooks/useApi";

export function usePremiumGate(
  user: AuthUser | null,
  required: UserTier,
  feature?: string,
) {
  const [dismissed, setDismissed] = useState(false);
  const allowed = tierAtLeast(user, required);

  const gate = (!allowed && !dismissed) ? (
    <PremiumModal
      open
      inline
      feature={feature}
      requiredTier={required}
      currentTier={user?.tier ?? "free"}
      onDismiss={() => setDismissed(true)}
    />
  ) : null;

  return { allowed, gate, dismissed };
}
