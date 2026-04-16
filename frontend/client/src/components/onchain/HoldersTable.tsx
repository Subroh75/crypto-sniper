import { useState } from "react";
import type { AnalysisResult, HolderData } from "@/lib/onchain-api";
import { ExternalLink } from "lucide-react";

type SortKey = "rank" | "percentage" | "firstBuyDate" | "transactions" | "walletAgeMonths";

function shortAddr(addr: string, chain: string) {
  return chain === "solana" ? `${addr.slice(0, 6)}…${addr.slice(-6)}` : `${addr.slice(0, 8)}…${addr.slice(-6)}`;
}

function ageBadge(months: number) {
  if (months < 3)  return { label: "< 3mo",                color: "#f87171", bg: "rgba(248,113,113,0.1)" };
  if (months < 6)  return { label: `${months}mo`,          color: "#f97316", bg: "rgba(249,115,22,0.1)" };
  if (months < 12) return { label: `${months}mo`,          color: "#f59e0b", bg: "rgba(245,158,11,0.1)" };
  if (months < 24) return { label: `${(months/12).toFixed(1)}yr`, color: "#10b981", bg: "rgba(16,185,129,0.1)" };
  return              { label: `${(months/12).toFixed(1)}yr`, color: "#38bdf8", bg: "rgba(56,189,248,0.1)" };
}

function Bar({ pct, rank }: { pct: number; rank: number }) {
  const c = rank <= 3 ? "#f87171" : rank <= 5 ? "#f97316" : rank <= 10 ? "#f59e0b" : "#818cf8";
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono font-bold text-xs w-12 text-right shrink-0" style={{ color: c }}>{pct.toFixed(2)}%</span>
      <div className="flex-1 h-1.5 bg-surface rounded-full overflow-hidden min-w-[50px]">
        <div className="h-full rounded-full" style={{ width: `${Math.min(100, (pct / 15) * 100)}%`, background: c }} />
      </div>
    </div>
  );
}

export function HoldersTable({ result }: { result: AnalysisResult }) {
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "rank", dir: "asc" });
  const [filter, setFilter] = useState<"all" | "wallets" | "contracts">("all");
  const [expanded, setExpanded] = useState<string | null>(null);

  const rows = [...result.holders]
    .filter(h => filter === "all" ? true : filter === "wallets" ? !h.isContract : h.isContract)
    .sort((a, b) => {
      const m = sort.dir === "asc" ? 1 : -1;
      if (sort.key === "firstBuyDate") return m * (new Date(a.firstBuyDate).getTime() - new Date(b.firstBuyDate).getTime());
      return m * ((a[sort.key] as number) - (b[sort.key] as number));
    });

  const col = (key: SortKey, label: string, cls = "") => (
    <th className={`px-4 py-3 text-left text-xs font-semibold uppercase tracking-widest text-text-faint cursor-pointer hover:text-text-muted select-none whitespace-nowrap ${cls}`}
      onClick={() => setSort(p => p.key === key ? { key, dir: p.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" })}>
      {label} <span className="opacity-50">{sort.key === key ? (sort.dir === "asc" ? "↑" : "↓") : "↕"}</span>
    </th>
  );

  return (
    <div className="bg-surface-2 rounded-xl border border-border/50 overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-border/50 flex-wrap gap-3">
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-text-muted">Top 20 Holders</h3>
          <p className="text-xs mt-0.5" style={{ color: "#475569" }}>First buy-in · TX history · Wallet age</p>
        </div>
        <div className="flex gap-1 bg-surface rounded-lg p-1">
          {(["all", "wallets", "contracts"] as const).map(f => (
            <button key={f} data-testid={`button-filter-${f}`} onClick={() => setFilter(f)}
              className={`text-xs px-3 py-1.5 rounded-md font-medium transition-all capitalize ${
                filter === f ? "bg-surface-2 text-text" : "text-text-faint hover:text-text-muted"
              }`}>
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-border/50 bg-surface/50">
              {col("rank", "#")}
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-widest text-text-faint">Address</th>
              {col("percentage", "% Supply")}
              {col("firstBuyDate", "First Buy", "hidden md:table-cell")}
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-widest text-text-faint hidden md:table-cell whitespace-nowrap">Last Active</th>
              {col("transactions", "Txns", "hidden lg:table-cell")}
              {col("walletAgeMonths", "Age")}
              <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-widest text-text-faint hidden sm:table-cell">Type</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(h => {
              const age = ageBadge(h.walletAgeMonths);
              const isEx = expanded === h.address;
              const explorer = result.chain === "ethereum"
                ? `https://etherscan.io/address/${h.address}`
                : `https://solscan.io/account/${h.address}`;
              return (
                <>
                  <tr key={h.address} data-testid={`row-holder-${h.rank}`}
                    className="border-b border-border/30 cursor-pointer transition-colors hover:bg-surface/60"
                    onClick={() => setExpanded(isEx ? null : h.address)}>
                    <td className="px-4 py-3 font-mono font-bold"
                      style={{ color: h.rank === 1 ? "#f59e0b" : h.rank <= 3 ? "#818cf8" : "#475569" }}>
                      {h.rank <= 3 ? ["🥇","🥈","🥉"][h.rank - 1] : `#${h.rank}`}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-text-faint" style={{ fontSize: "11px" }}>
                          {shortAddr(h.address, result.chain)}
                        </span>
                        {h.label && (
                          <span className="text-xs px-1.5 py-0.5 rounded font-medium" style={{ fontSize: "10px", color: "#818cf8", background: "rgba(129,140,248,0.1)", border: "1px solid rgba(129,140,248,0.15)" }}>
                            {h.label}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 min-w-[110px]"><Bar pct={h.percentage} rank={h.rank} /></td>
                    <td className="px-4 py-3 font-mono text-text-faint hidden md:table-cell whitespace-nowrap">{h.firstBuyDate}</td>
                    <td className="px-4 py-3 font-mono text-text-faint hidden md:table-cell whitespace-nowrap">{h.lastActivityDate}</td>
                    <td className="px-4 py-3 font-mono text-text hidden lg:table-cell">{h.transactions.toLocaleString()}</td>
                    <td className="px-4 py-3">
                      <span className="text-xs px-1.5 py-0.5 rounded-full font-mono font-semibold"
                        style={{ color: age.color, background: age.bg }}>{age.label}</span>
                    </td>
                    <td className="px-4 py-3 hidden sm:table-cell">
                      <span className={`text-xs px-1.5 py-0.5 rounded font-medium`}
                        style={h.isContract
                          ? { color: "#818cf8", background: "rgba(129,140,248,0.1)" }
                          : { color: "#94a3b8", background: "rgba(148,163,184,0.1)" }}>
                        {h.isContract ? "Contract" : "Wallet"}
                      </span>
                    </td>
                  </tr>
                  {isEx && (
                    <tr key={`${h.address}-exp`} className="bg-surface/40">
                      <td colSpan={8} className="px-4 py-4">
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                          <div>
                            <p className="text-xs text-text-faint mb-1">Full Address</p>
                            <p className="font-mono text-text break-all" style={{ fontSize: "11px" }}>{h.address}</p>
                          </div>
                          <div>
                            <p className="text-xs text-text-faint mb-1">Token Balance</p>
                            <p className="font-mono font-bold text-text text-sm">{h.balance.toLocaleString()}</p>
                          </div>
                          <div>
                            <p className="text-xs text-text-faint mb-1">First Buy</p>
                            <p className="font-mono text-text text-sm">{h.firstBuyDate}</p>
                          </div>
                          <div>
                            <p className="text-xs text-text-faint mb-2">Explorer</p>
                            <a href={explorer} target="_blank" rel="noopener noreferrer"
                              className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded border border-border/50 font-mono transition-colors hover:bg-surface"
                              style={{ color: "#38bdf8" }} onClick={e => e.stopPropagation()}>
                              {result.chain === "ethereum" ? "Etherscan" : "Solscan"}
                              <ExternalLink size={11} />
                            </a>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="px-5 py-3 border-t border-border/50 flex items-center justify-between text-xs text-text-faint">
        <span>Showing {rows.length} of {result.holders.length} holders</span>
        <span className="font-mono hidden sm:inline">Click row to expand · Data via Etherscan / Helius</span>
      </div>
    </div>
  );
}
