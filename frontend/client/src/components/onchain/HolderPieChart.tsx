import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer } from "recharts";
import type { AnalysisResult } from "@/lib/onchain-api";

const COLORS = [
  "#7c3aed", "#818cf8", "#38bdf8", "#10b981", "#f59e0b",
  "#f97316", "#ec4899", "#f87171", "#a855f7", "#06b6d4",
  "#475569", "#374151",
];

const CustomTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-surface-card border border-border rounded-xl p-3 text-xs shadow-lg">
      <div className="font-semibold text-text mb-1">Rank #{d.rank}</div>
      <div className="font-mono text-text-faint mb-1" style={{ fontSize: "10px" }}>{d.address?.slice(0, 14)}…</div>
      {d.label && <div className="mb-1" style={{ color: "#818cf8" }}>{d.label}</div>}
      <div className="flex items-center gap-3">
        <span className="text-text-muted">Share:</span>
        <span className="font-bold font-mono" style={{ color: payload[0].fill }}>{d.percentage?.toFixed(2)}%</span>
      </div>
      <div className="flex items-center gap-3 mt-0.5">
        <span className="text-text-muted">Type:</span>
        <span>{d.isContract ? "Contract" : "Wallet"}</span>
      </div>
    </div>
  );
};

export function HolderPieChart({ result }: { result: AnalysisResult }) {
  const top5 = result.holders.slice(0, 5);
  const rest6to20 = result.holders.slice(5).reduce((s, h) => s + h.percentage, 0);
  const totalShown = result.holders.reduce((s, h) => s + h.percentage, 0);
  const remaining = Math.max(0, 100 - totalShown);

  const pieData = [
    ...top5.map(h => ({ ...h, name: h.label || `#${h.rank} ${h.address.slice(0, 8)}…` })),
    { rank: 99, address: "others", percentage: rest6to20, name: "Holders 6–20", isContract: false },
    ...(remaining > 0 ? [{ rank: 100, address: "rest", percentage: remaining, name: "Remaining", isContract: false }] : []),
  ].filter(d => d.percentage > 0) as any[];

  const top10Color = result.top10Percentage >= 70 ? "#f87171"
    : result.top10Percentage >= 50 ? "#f97316"
    : result.top10Percentage >= 40 ? "#f59e0b"
    : "#10b981";

  return (
    <div className="bg-surface-2 rounded-xl border border-border/50 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-text-muted">Holder Concentration</h3>
          <p className="text-xs mt-0.5" style={{ color: "#475569" }}>Supply distribution — top 20</p>
        </div>
        <div className="text-right">
          <div className="text-xs text-text-faint">Top 10 hold</div>
          <div className="text-lg font-bold font-mono" style={{ color: top10Color }}>
            {result.top10Percentage.toFixed(1)}%
          </div>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row items-center gap-4">
        <div className="w-full sm:w-44 h-44 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={pieData} cx="50%" cy="50%" innerRadius="55%" outerRadius="80%"
                paddingAngle={1} dataKey="percentage" startAngle={90} endAngle={-270}>
                {pieData.map((_, i) => (
                  <Cell key={i} fill={i < 5 ? COLORS[i] : i === 5 ? "#243048" : "#1e2d45"} stroke="transparent" />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="flex-1 w-full space-y-1.5">
          {top5.map((h, i) => (
            <div key={h.address} className="flex items-center gap-2 text-xs">
              <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: COLORS[i] }} />
              <span className="flex-1 truncate font-mono text-text-faint" style={{ fontSize: "11px" }}>
                {h.label || `${h.address.slice(0, 10)}…`}
              </span>
              <span className="font-mono font-bold text-text">{h.percentage.toFixed(1)}%</span>
            </div>
          ))}
          <div className="flex items-center gap-2 text-xs">
            <span className="w-2 h-2 rounded-sm shrink-0 bg-surface-offset-2" />
            <span className="flex-1 text-text-faint">Holders 6–20</span>
            <span className="font-mono font-bold text-text">{rest6to20.toFixed(1)}%</span>
          </div>
          {remaining > 0 && (
            <div className="flex items-center gap-2 text-xs">
              <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: "#1e2d45" }} />
              <span className="flex-1 text-text-faint">Remaining</span>
              <span className="font-mono font-bold text-text">{remaining.toFixed(1)}%</span>
            </div>
          )}

          {/* Threshold bar */}
          <div className="pt-2 mt-1 border-t border-border/40">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-text-faint">Concentration</span>
              <span className="font-mono" style={{ color: top10Color }}>{result.top10Percentage.toFixed(1)}%</span>
            </div>
            <div className="h-1.5 bg-surface rounded-full overflow-hidden">
              <div className="h-full rounded-full transition-all duration-700"
                style={{ width: `${Math.min(100, result.top10Percentage)}%`, background: top10Color }} />
            </div>
            <div className="flex justify-between text-xs mt-0.5" style={{ color: "#475569", fontSize: "10px" }}>
              <span>0%</span>
              <span style={{ color: "#f59e0b" }}>40% threshold</span>
              <span>100%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
