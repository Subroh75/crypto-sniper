import { useState } from "react";
import { fmtPrice } from "@/lib/api";

interface Props { sig: any; kron: any; fearGreed?: any; }

function calcConfidence(sig: any, kron: any, fg: any): number {
  if (!sig) return 0;
  const score = sig.signal?.total ?? 0;
  const maxScore = sig.signal?.max ?? 16;
  const kronDir = kron?.forecast?.direction ?? "NEUTRAL";
  const sigDir = sig.signal?.direction ?? "NEUTRAL";
  const kronosAligns = kronDir === sigDir ? 1 : 0.5;
  const fgVal = fg?.value ?? 50;
  const fgAligns = sigDir === "LONG" ? (fgVal < 30 ? 1 : fgVal < 50 ? 0.7 : 0.4)
    : sigDir === "SHORT" ? (fgVal > 70 ? 1 : fgVal > 50 ? 0.7 : 0.4) : 0.5;
  return Math.round(((score / maxScore * 0.5) + (kronosAligns * 0.3) + (fgAligns * 0.2)) * 100);
}

function buildVerdict(sig: any, kron: any, fg: any) {
  if (!sig?.signal) return { verdict: "WAIT", reason: "Run an analysis first.", go: false };
  const dir = sig.signal?.direction ?? "NEUTRAL";
  const score = sig.signal?.total ?? 0;
  const entry = sig.trade_setup?.entry;
  const stop = sig.trade_setup?.stop;
  const target = sig.trade_setup?.target;
  const fgVal = fg?.value ?? 50;
  const fgLabel = fg?.label ?? "Neutral";
  const move = kron?.forecast?.expected_move_pct ?? 0;

  let verdict = "WAIT", go = false;
  if (dir === "LONG" && score >= 7)       { verdict = "BUY";       go = true; }
  else if (dir === "SHORT" && score >= 7) { verdict = "SELL";      go = true; }
  else if (dir === "LONG" && score >= 5)  { verdict = "LEAN BUY";  go = false; }
  else if (dir === "SHORT" && score >= 5) { verdict = "LEAN SELL"; go = false; }

  const parts: string[] = [];
  if (Math.abs(move) > 0.3) parts.push("Kronos forecasts " + Math.abs(move).toFixed(1) + "% " + (move > 0 ? "upside" : "downside") + " over 24h");
  if (fgVal <= 25) parts.push("Fear & Greed at " + fgVal + " signals extreme fear - historically a buy zone");
  else if (fgVal >= 75) parts.push("Fear & Greed at " + fgVal + " signals extreme greed - caution advised");
  else parts.push("Fear & Greed at " + fgVal + " (" + fgLabel + ")");
  if (entry && stop && target) parts.push("Entry " + fmtPrice(entry) + " - Stop " + fmtPrice(stop) + " - Target " + fmtPrice(target));

  return { verdict, reason: parts.slice(0, 3).join(". ") + ".", go };
}

export function CSOVerdict({ sig, kron, fearGreed }: Props) {
  const [exp, setExp] = useState(false);
  if (!sig) return null;
  const fg = fearGreed ?? sig?.fear_greed;
  const conf = calcConfidence(sig, kron, fg);
  const { verdict, reason, go } = buildVerdict(sig, kron, fg);
  const isBuy = verdict.includes("BUY");
  const isSell = verdict.includes("SELL");
  const color = isBuy ? "#22c55e" : isSell ? "#ef4444" : "#f59e0b";
  const bg = isBuy ? "rgba(34,197,94,0.07)" : isSell ? "rgba(239,68,68,0.07)" : "rgba(245,158,11,0.07)";

  return (
    <div style={{ border: "1.5px solid " + color + "40", borderRadius: 12, background: bg, padding: "14px 16px", marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#64748b", textTransform: "uppercase" }}>CSO Verdict</span>
          <span style={{ fontSize: 9, color: "#475569", background: "#0f172a", padding: "1px 6px", borderRadius: 4, border: "1px solid #1e293b" }}>Chief Signal Officer</span>
        </div>
        <button onClick={() => setExp(e => !e)} style={{ fontSize: 10, color: "#475569", background: "transparent", border: "none", cursor: "pointer" }}>
          {exp ? "less" : "why?"}
        </button>
      </div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ background: go ? color : "#1e293b", color: go ? "#fff" : "#64748b", fontWeight: 800, fontSize: 13, padding: "6px 14px", borderRadius: 8, border: go ? "none" : "1px solid #334155" }}>
            {go ? "GO" : "NO GO"}
          </div>
          <span style={{ fontSize: 20, fontWeight: 800, color }}>{verdict}</span>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 24, fontWeight: 800, color, lineHeight: 1 }}>{conf}</div>
          <div style={{ fontSize: 9, color: "#475569", marginTop: 2 }}>/100 confidence</div>
        </div>
      </div>
      {(exp || go) && (
        <div style={{ fontSize: 12, color: "#94a3b8", lineHeight: 1.6, marginTop: 10, paddingTop: 10, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
          {reason}
        </div>
      )}
    </div>
  );
}
