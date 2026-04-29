import { useState } from "react";
import { fmtPrice } from "@/lib/api";

interface Props { sig: any; kron: any; fearGreed?: any; }

// ── Confidence score ──────────────────────────────────────────────────────────
// Weights: score strength 50%, Kronos alignment 25%, Fear & Greed 15%, conviction 10%
function calcConfidence(sig: any, kron: any, fg: any): number {
  if (!sig) return 0;

  const score    = sig.signal?.total ?? 0;
  const maxScore = sig.signal?.max   ?? 16;
  const label    = (sig.signal?.label ?? "").toUpperCase();
  const dir      = (sig.signal?.direction ?? "NEUTRAL").toUpperCase();

  // Score component (0–50)
  const scoreComp = (score / maxScore) * 50;

  // Kronos alignment (0–25)
  // If direction is NEUTRAL we check if Kronos forecast is positive for score-based signals
  const kronDir  = (kron?.forecast?.direction ?? "NEUTRAL").toUpperCase();
  const kronMove = kron?.forecast?.expected_move_pct ?? 0;
  let kronComp = 12; // neutral baseline
  if (dir === "LONG"  && (kronDir === "LONG"  || kronMove > 0.5)) kronComp = 25;
  else if (dir === "SHORT" && (kronDir === "SHORT" || kronMove < -0.5)) kronComp = 25;
  else if (dir === "NEUTRAL" && label.includes("BUY")  && (kronDir !== "SHORT" && kronMove >= 0)) kronComp = 18;
  else if (dir === "NEUTRAL" && label.includes("SELL") && (kronDir !== "LONG"  && kronMove <= 0)) kronComp = 18;
  else if ((dir === "LONG" && kronDir === "SHORT") || (dir === "SHORT" && kronDir === "LONG")) kronComp = 3;

  // Fear & Greed (0–15)
  const fgVal = fg?.value ?? 50;
  let fgComp = 7;
  if (label.includes("BUY")) {
    fgComp = fgVal <= 25 ? 15 : fgVal <= 45 ? 11 : fgVal <= 60 ? 7 : 4;
  } else if (label.includes("SELL")) {
    fgComp = fgVal >= 75 ? 15 : fgVal >= 55 ? 11 : fgVal >= 40 ? 7 : 4;
  }

  // Conviction (0–10)
  const bullPct = sig.conviction?.bull_pct ?? 50;
  const convComp = label.includes("BUY")
    ? (bullPct >= 70 ? 10 : bullPct >= 55 ? 7 : 4)
    : label.includes("SELL")
    ? (bullPct <= 30 ? 10 : bullPct <= 45 ? 7 : 4)
    : 5;

  return Math.min(99, Math.round(scoreComp + kronComp + fgComp + convComp));
}

// ── Verdict logic ─────────────────────────────────────────────────────────────
function buildVerdict(sig: any, kron: any, fg: any) {
  if (!sig?.signal) return { verdict: "WAIT", go: false, goLabel: "NO GO", color: "#f59e0b", reason: "Run an analysis first.", note: null };

  const label    = (sig.signal?.label ?? "").toUpperCase();
  const dir      = (sig.signal?.direction ?? "NEUTRAL").toUpperCase();
  const score    = sig.signal?.total ?? 0;
  const maxScore = sig.signal?.max   ?? 16;
  const fgVal    = fg?.value ?? 50;
  const fgLabel  = fg?.label ?? "Neutral";
  const kronDir  = (kron?.forecast?.direction ?? "NEUTRAL").toUpperCase();
  const kronMove = kron?.forecast?.expected_move_pct ?? 0;
  const entry    = sig.trade_setup?.entry;
  const stop     = sig.trade_setup?.stop;
  const target   = sig.trade_setup?.target;
  const bullPct  = sig.conviction?.bull_pct ?? 50;

  // ── Primary verdict from signal label + score ────────────────────────────
  let verdict: string;
  let go: boolean;
  let goLabel: string;
  let color: string;
  let note: string | null = null;

  if (label === "STRONG BUY" || (label.includes("BUY") && score >= 9)) {
    verdict = "BUY";   go = true;  goLabel = "GO";    color = "#22c55e";
  } else if (label === "STRONG SELL" || (label.includes("SELL") && score >= 9)) {
    verdict = "SELL";  go = true;  goLabel = "GO";    color = "#ef4444";
  } else if (label.includes("BUY") && score >= 6) {
    verdict = "BUY";   go = true;  goLabel = "CAUTION"; color = "#22c55e";
  } else if (label.includes("SELL") && score >= 6) {
    verdict = "SELL";  go = true;  goLabel = "CAUTION"; color = "#ef4444";
  } else if (label.includes("BUY")) {
    verdict = "LEAN BUY";  go = false; goLabel = "WAIT"; color = "#f59e0b";
  } else if (label.includes("SELL")) {
    verdict = "LEAN SELL"; go = false; goLabel = "WAIT"; color = "#ef4444";
  } else {
    verdict = "WAIT";  go = false; goLabel = "WAIT";  color = "#f59e0b";
  }

  // ── Direction note (explain NEUTRAL without overriding the verdict) ───────
  if (go && dir === "NEUTRAL") {
    note = "Trade setup is NEUTRAL — the API couldn't produce clean entry/stop levels. Score and momentum are bullish; consider a manual entry near VWAP with a stop below the nearest support.";
  } else if (go && dir !== "NEUTRAL") {
    // No conflict — direction and label agree
    note = null;
  }

  // ── Kronos conflict flag ──────────────────────────────────────────────────
  const kronConflict =
    (verdict === "BUY"  && kronDir === "SHORT" && kronMove < -0.5) ||
    (verdict === "SELL" && kronDir === "LONG"  && kronMove > 0.5);

  if (kronConflict) {
    goLabel = "CAUTION";
    note = `Kronos AI forecasts ${Math.abs(kronMove).toFixed(1)}% ${kronMove < 0 ? "downside" : "upside"} — conflicts with the BUY score. Consider waiting for Kronos alignment before entering.`;
  }

  // ── Reason sentence ───────────────────────────────────────────────────────
  const parts: string[] = [];

  parts.push(`Score ${score}/${maxScore} — ${label}`);

  if (bullPct !== 50) {
    parts.push(`${bullPct}% bull conviction`);
  }

  if (Math.abs(kronMove) > 0.3) {
    parts.push(`Kronos forecasts ${Math.abs(kronMove).toFixed(1)}% ${kronMove > 0 ? "upside" : "downside"} (24h)`);
  } else if (kronDir !== "NEUTRAL") {
    parts.push(`Kronos direction: ${kronDir}`);
  }

  if (fgVal <= 25)      parts.push(`Fear & Greed ${fgVal} — extreme fear, historically a buy zone`);
  else if (fgVal >= 75) parts.push(`Fear & Greed ${fgVal} — extreme greed, caution advised`);
  else                  parts.push(`Fear & Greed ${fgVal} (${fgLabel})`);

  if (entry && stop && target) {
    parts.push(`Entry ${fmtPrice(entry)} · Stop ${fmtPrice(stop)} · Target ${fmtPrice(target)}`);
  }

  return { verdict, go, goLabel, color, reason: parts.join(" · "), note };
}

// ── Component ─────────────────────────────────────────────────────────────────
export function CSOVerdict({ sig, kron, fearGreed }: Props) {
  const [exp, setExp] = useState(false);
  if (!sig) return null;

  const fg = fearGreed ?? sig?.fear_greed;
  const conf = calcConfidence(sig, kron, fg);
  const { verdict, go, goLabel, color, reason, note } = buildVerdict(sig, kron, fg);

  const goColors: Record<string, { bg: string; text: string; border: string }> = {
    "GO":      { bg: color,      text: "#fff",     border: "transparent" },
    "CAUTION": { bg: "#f59e0b22", text: "#f59e0b",  border: "#f59e0b55" },
    "WAIT":    { bg: "#1e293b",   text: "#64748b",  border: "#334155" },
  };
  const gc = goColors[goLabel] ?? goColors["WAIT"];
  const cardBg = color + "10";
  const cardBorder = color + "40";

  return (
    <div style={{ border: `1.5px solid ${cardBorder}`, borderRadius: 12, background: cardBg, padding: "14px 16px", marginBottom: 16 }}>

      {/* Title row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#64748b", textTransform: "uppercase" }}>
            CSO Verdict
          </span>
          <span style={{ fontSize: 9, color: "#475569", background: "#0f172a", padding: "1px 6px", borderRadius: 4, border: "1px solid #1e293b" }}>
            Chief Signal Officer
          </span>
        </div>
        <button onClick={() => setExp(e => !e)}
          style={{ fontSize: 10, color: "#475569", background: "transparent", border: "none", cursor: "pointer" }}>
          {exp ? "less" : "why?"}
        </button>
      </div>

      {/* Verdict row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* GO / CAUTION / WAIT pill */}
          <div style={{ background: gc.bg, color: gc.text, fontWeight: 800, fontSize: 12,
            padding: "5px 12px", borderRadius: 8, border: `1px solid ${gc.border}`,
            letterSpacing: "0.06em" }}>
            {goLabel}
          </div>
          <span style={{ fontSize: 20, fontWeight: 800, color }}>{verdict}</span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 24, fontWeight: 800, color, lineHeight: 1 }}>{conf}</div>
          <div style={{ fontSize: 9, color: "#475569", marginTop: 2 }}>/100 confidence</div>
        </div>
      </div>

      {/* Conflict / neutral direction note — always visible when present */}
      {note && (
        <div style={{ marginTop: 10, padding: "8px 10px", background: "#f59e0b0d",
          border: "1px solid #f59e0b33", borderRadius: 7 }}>
          <div style={{ fontSize: 9, fontWeight: 700, color: "#f59e0b", letterSpacing: "0.06em",
            textTransform: "uppercase", marginBottom: 3 }}>
            Note
          </div>
          <div style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.55 }}>{note}</div>
        </div>
      )}

      {/* Expanded reason */}
      {(exp || go) && (
        <div style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.65, marginTop: 10,
          paddingTop: 10, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          {reason}
        </div>
      )}
    </div>
  );
}
