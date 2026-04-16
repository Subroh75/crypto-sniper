import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { AnalysisResult } from "@/lib/onchain-api";

const BAR_COLORS = ["#f87171", "#f97316", "#f59e0b", "#10b981", "#38bdf8"];

const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-surface-card border border-border rounded-xl p-3 text-xs shadow-lg">
      <div className="font-semibold text-text mb-1">{label}</div>
      <div className="flex items-center gap-2">
        <span className="text-text-muted">Holders:</span>
        <span className="font-bold font-mono text-text">{payload[0].value}</span>
      </div>
    </div>
  );
};

export function WalletAgeChart({ result }: { result: AnalysisResult }) {
  const data = result.walletAgeDistribution;
  const avgMonths = result.holders.reduce((s, h) => s + h.walletAgeMonths, 0) / result.holders.length;
  const newWallets = data.find(d => d.label === "< 3mo")?.count || 0;
  const total = data.reduce((s, d) => s + d.count, 0);
  const newPct = total > 0 ? Math.round((newWallets / total) * 100) : 0;

  return (
    <div className="bg-surface-2 rounded-xl border border-border/50 p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-text-muted">Wallet Age Distribution</h3>
          <p className="text-xs mt-0.5" style={{ color: "#475569" }}>Top 20 holders by wallet age</p>
        </div>
        <div className="text-right">
          <div className="text-xs text-text-faint">Avg age</div>
          <div className="text-lg font-bold font-mono" style={{ color: "#38bdf8" }}>
            {avgMonths.toFixed(0)}mo
          </div>
        </div>
      </div>

      {/* Badges */}
      <div className="flex gap-2 mb-4 flex-wrap">
        {newWallets > 0 && (
          <span className="text-xs px-2 py-0.5 rounded-full border font-mono"
            style={{ color: "#f87171", background: "rgba(248,113,113,0.08)", borderColor: "rgba(248,113,113,0.2)" }}>
            {newWallets} new (&lt;3mo)
          </span>
        )}
        {newPct > 30 && (
          <span className="text-xs px-2 py-0.5 rounded-full border"
            style={{ color: "#f97316", background: "rgba(249,115,22,0.08)", borderColor: "rgba(249,115,22,0.2)" }}>
            ⚠ {newPct}% fresh wallets
          </span>
        )}
      </div>

      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 4, left: -28, bottom: 4 }} barCategoryGap="20%">
            <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#475569" }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 10, fill: "#475569" }} axisLine={false} tickLine={false} allowDecimals={false} />
            <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(129,140,248,0.05)" }} />
            <Bar dataKey="count" radius={[3, 3, 0, 0]}>
              {data.map((_, i) => <Cell key={i} fill={BAR_COLORS[i % BAR_COLORS.length]} opacity={0.85} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="mt-3 pt-3 border-t border-border/40 flex flex-wrap gap-x-4 gap-y-1">
        {data.map((d, i) => (
          <div key={d.label} className="flex items-center gap-1.5 text-xs">
            <span className="w-2 h-2 rounded-sm" style={{ background: BAR_COLORS[i % BAR_COLORS.length] }} />
            <span className="text-text-faint">{d.label}</span>
            <span className="font-mono font-semibold text-text">{d.count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
