import { AlertTriangle, ShieldAlert, Shield } from "lucide-react";
import type { AnalysisResult } from "@/lib/onchain-api";

const CONFIG = {
  CRITICAL: {
    color: "#f87171", bg: "rgba(248,113,113,0.08)", border: "rgba(248,113,113,0.3)",
    title: "CRITICAL CONCENTRATION RISK", pulse: true,
  },
  HIGH: {
    color: "#f97316", bg: "rgba(249,115,22,0.08)", border: "rgba(249,115,22,0.3)",
    title: "HIGH CONCENTRATION RISK", pulse: false,
  },
  MEDIUM: {
    color: "#f59e0b", bg: "rgba(245,158,11,0.08)", border: "rgba(245,158,11,0.25)",
    title: "ELEVATED CONCENTRATION", pulse: false,
  },
  LOW: {
    color: "#10b981", bg: "rgba(16,185,129,0.05)", border: "rgba(16,185,129,0.2)",
    title: "HEALTHY DISTRIBUTION", pulse: false,
  },
};

export function RiskAlert({ result }: { result: AnalysisResult }) {
  const c = CONFIG[result.riskLevel];
  const topWhales = result.holders.filter(h => !h.isContract).slice(0, 3);
  const topContracts = result.holders.filter(h => h.isContract).slice(0, 3);

  return (
    <div
      data-testid="alert-risk"
      className={`rounded-xl p-4 border ${c.pulse ? "pulse-alert" : ""}`}
      style={{ background: c.bg, borderColor: c.border }}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle size={16} style={{ color: c.color }} className="shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-xs font-bold tracking-widest font-mono" style={{ color: c.color }}>
              {c.title}
            </span>
            <span className="text-xs font-mono font-bold" style={{ color: c.color }}>
              Top 10 hold {result.top10Percentage.toFixed(1)}%
            </span>
          </div>
          <p className="text-xs mb-3" style={{ color: "#94a3b8" }}>
            {result.riskLevel === "CRITICAL"
              ? `Extreme whale concentration. Top 10 wallets control ${result.top10Percentage.toFixed(1)}% of supply — coordinated sell-off risk is very high.`
              : result.riskLevel === "HIGH"
              ? `Significant concentration. Top 10 wallets control ${result.top10Percentage.toFixed(1)}% of supply. Monitor large wallet movements closely.`
              : `Above the 40% threshold. Top 10 wallets hold ${result.top10Percentage.toFixed(1)}% of supply.`
            }
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="bg-surface rounded-xl p-3 border border-border/50">
              <p className="text-xs font-semibold mb-1.5" style={{ color: "#94a3b8" }}>Top Whale Wallets</p>
              {topWhales.map(h => (
                <div key={h.address} className="flex items-center justify-between gap-2 py-0.5">
                  <span className="text-xs font-mono truncate" style={{ color: "#64748b" }}>{h.address.slice(0, 8)}…</span>
                  <span className="text-xs font-bold font-mono shrink-0" style={{ color: c.color }}>{h.percentage.toFixed(1)}%</span>
                </div>
              ))}
            </div>
            <div className="bg-surface rounded-xl p-3 border border-border/50">
              <p className="text-xs font-semibold mb-1.5" style={{ color: "#94a3b8" }}>Contract Addresses</p>
              {topContracts.length > 0 ? topContracts.map(h => (
                <div key={h.address} className="flex items-center justify-between gap-2 py-0.5">
                  <span className="text-xs font-mono truncate" style={{ color: "#64748b" }}>{h.label || h.address.slice(0, 8) + "…"}</span>
                  <span className="text-xs font-bold font-mono shrink-0" style={{ color: "#818cf8" }}>{h.percentage.toFixed(1)}%</span>
                </div>
              )) : <p className="text-xs" style={{ color: "#475569" }}>None detected</p>}
            </div>
            <div className="bg-surface rounded-xl p-3 border border-border/50">
              <p className="text-xs font-semibold mb-1.5" style={{ color: "#94a3b8" }}>Risk Factors</p>
              <div className="space-y-1">
                <div className="flex items-center gap-1.5 text-xs" style={{ color: "#94a3b8" }}>
                  <span style={{ color: c.color }}>●</span> High concentration
                </div>
                {result.holders.filter(h => h.walletAgeMonths < 3).length > 3 && (
                  <div className="flex items-center gap-1.5 text-xs" style={{ color: "#94a3b8" }}>
                    <span style={{ color: "#f59e0b" }}>●</span> New wallets detected
                  </div>
                )}
                {topContracts.length > 0 && (
                  <div className="flex items-center gap-1.5 text-xs" style={{ color: "#94a3b8" }}>
                    <span style={{ color: "#818cf8" }}>●</span> Contract holders
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
