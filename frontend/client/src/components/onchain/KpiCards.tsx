import { Users, Star, Clock, AlertTriangle, Database, Activity } from "lucide-react";
import type { AnalysisResult } from "@/lib/onchain-api";

function fmt(n: number): string {
  if (n >= 1_000_000_000) return (n / 1_000_000_000).toFixed(2) + "B";
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return n.toLocaleString();
}

const RISK_STYLE = {
  LOW:      { text: "#10b981", bg: "rgba(16,185,129,0.1)",  border: "rgba(16,185,129,0.2)" },
  MEDIUM:   { text: "#f59e0b", bg: "rgba(245,158,11,0.1)",  border: "rgba(245,158,11,0.2)" },
  HIGH:     { text: "#f97316", bg: "rgba(249,115,22,0.1)",  border: "rgba(249,115,22,0.2)" },
  CRITICAL: { text: "#f87171", bg: "rgba(248,113,113,0.1)", border: "rgba(248,113,113,0.2)" },
};

export function KpiCards({ result }: { result: AnalysisResult }) {
  const rs = RISK_STYLE[result.riskLevel];
  const top10Color = result.top10Percentage > 40 ? "#f87171" : "#10b981";
  const concColor = result.concentrationScore > 60 ? "#10b981" : result.concentrationScore > 40 ? "#f59e0b" : "#f87171";

  const cards = [
    {
      icon: <Users size={14} />,
      label: "Total Holders",
      value: fmt(result.totalHolders),
      sub: "unique addresses",
      accent: "#818cf8",
    },
    {
      icon: <Star size={14} />,
      label: "Top 10 Hold",
      value: result.top10Percentage.toFixed(1) + "%",
      sub: "of total supply",
      accent: top10Color,
      highlight: result.top10Percentage > 40,
    },
    {
      icon: <Clock size={14} />,
      label: "Top 20 Hold",
      value: result.top20Percentage.toFixed(1) + "%",
      sub: "of total supply",
      accent: "#818cf8",
    },
    {
      icon: <AlertTriangle size={14} />,
      label: "Risk Level",
      value: null,
      riskBadge: result.riskLevel,
      sub: "concentration risk",
      accent: rs.text,
    },
    {
      icon: <Database size={14} />,
      label: "Total Supply",
      value: fmt(result.totalSupply),
      sub: result.tokenSymbol,
      accent: "#f59e0b",
    },
    {
      icon: <Activity size={14} />,
      label: "Concentration Score",
      value: result.concentrationScore.toFixed(0),
      sub: "100 = distributed",
      accent: concColor,
    },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5">
      {cards.map((card, i) => (
        <div
          key={i}
          data-testid={`card-kpi-${card.label.toLowerCase().replace(/\s+/g, "-")}`}
          className="bg-surface-2 rounded-xl p-4 border border-border/50 relative overflow-hidden hover:border-purple/30 transition-all"
          style={card.highlight ? { borderColor: "rgba(248,113,113,0.3)" } : {}}
        >
          <div className="absolute top-0 right-0 w-12 h-12 rounded-full blur-2xl opacity-20 pointer-events-none"
            style={{ background: card.accent, transform: "translate(30%,-30%)" }} />
          <div className="mb-2" style={{ color: card.accent, opacity: 0.8 }}>{card.icon}</div>
          {card.riskBadge ? (
            <div className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-bold border mb-1"
              style={{ color: rs.text, background: rs.bg, borderColor: rs.border }}>
              {card.riskBadge}
            </div>
          ) : (
            <div className="text-lg font-bold font-mono leading-tight mb-0.5 text-text"
              style={{ color: card.highlight ? "#f87171" : undefined }}>
              {card.value}
            </div>
          )}
          <div className="text-xs text-text-muted leading-tight">{card.label}</div>
          <div className="text-xs leading-tight mt-0.5" style={{ color: "#475569", fontSize: "10px" }}>{card.sub}</div>
        </div>
      ))}
    </div>
  );
}
