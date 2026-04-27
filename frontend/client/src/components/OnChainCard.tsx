// ── On-Chain Intelligence Card ─────────────────────────────────────────────
// Section 13 in the left column. Shows supply metrics, MC/FDV, NVT proxy,
// TVL backing, unlock schedule, and derived risk signals.

import { useOnChain } from "@/hooks/useApi";
import { fmtBigNum } from "@/lib/api";
import type { OnChainData, OnChainSignal } from "@/types/api";

// ── Shared card primitives (must match home.tsx exactly) ──────────────────
function Card({ children, className = "", id }: {
  children: React.ReactNode; className?: string; id?: string;
}) {
  return (
    <div id={id} className={`rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-3 ${className}`}>
      {children}
    </div>
  );
}

function CardHeader({ num, icon, title, badge, src, right }: {
  num?: string; icon?: string; title: string; badge?: string;
  src?: string; right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
      <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
        {num  && <span className="text-purple">{num}</span>}
        {icon && <span>{icon}</span>}
        <span>{title}</span>
        {badge && (
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-orange/10 text-orange border border-orange/15 uppercase tracking-wide">
            {badge}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {right}
        {src && (
          <span className="text-[9px] font-mono text-text-muted/60 px-2 py-0.5 rounded bg-surface-2 border border-border/40">
            {src}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Signal badge ──────────────────────────────────────────────────────────
function SignalBadge({ signal }: { signal: OnChainSignal }) {
  const cfg = {
    positive: { text: "text-teal",  bg: "bg-teal/8  border-teal/20"  },
    caution:  { text: "text-amber", bg: "bg-amber/8 border-amber/20" },
    risk:     { text: "text-red",   bg: "bg-red/8   border-red/20"   },
  }[signal.type];

  return (
    <div className={`flex items-start gap-2 px-3 py-2 rounded-lg border ${cfg.bg}`}>
      <span className={`text-[10px] font-mono font-bold ${cfg.text} shrink-0 mt-[1px]`}>
        {signal.type === "positive" ? "▲" : signal.type === "risk" ? "▼" : "●"}
      </span>
      <div className="min-w-0">
        <div className={`text-[11px] font-mono font-bold ${cfg.text}`}>{signal.label}</div>
        <div className="text-[10px] text-text-muted/70 leading-relaxed">{signal.detail}</div>
      </div>
    </div>
  );
}

// ── Row helper ────────────────────────────────────────────────────────────
function Row({
  label, value, valueClass = "text-text",
}: { label: string; value: React.ReactNode; valueClass?: string }) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border/20 last:border-none">
      <span className="text-[10px] font-mono text-text-muted/60 uppercase tracking-wide">{label}</span>
      <span className={`text-[11px] font-mono font-bold ${valueClass}`}>{value}</span>
    </div>
  );
}

// ── Mini bar ──────────────────────────────────────────────────────────────
function MiniBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="w-full h-[3px] bg-surface-2 rounded-full overflow-hidden mt-1">
      <div
        className="h-full rounded-full transition-all duration-700"
        style={{ width: `${Math.min(100, pct)}%`, background: color }}
      />
    </div>
  );
}

// ── Risk gauge ────────────────────────────────────────────────────────────
function RiskGauge({ score }: { score: number }) {
  const color = score >= 60 ? "#ef4444" : score >= 40 ? "#f59e0b" : "#22c55e";
  const label = score >= 60 ? "HIGH RISK" : score >= 40 ? "MODERATE" : "LOW RISK";
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1">
        <div className="w-full h-2 bg-surface-2 rounded-full overflow-hidden">
          <div
            className="h-full rounded-full transition-all duration-700"
            style={{ width: `${score}%`, background: color }}
          />
        </div>
      </div>
      <span
        className="text-[10px] font-mono font-bold whitespace-nowrap"
        style={{ color }}
      >
        {label}
      </span>
    </div>
  );
}

// ── Format helpers ────────────────────────────────────────────────────────
function fmtSupply(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1e12) return `${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6)  return `${(n / 1e6).toFixed(2)}M`;
  if (n >= 1e3)  return `${(n / 1e3).toFixed(2)}K`;
  return n.toFixed(0);
}

function daysAway(ts: number): string {
  const d = Math.round((ts - Date.now() / 1000) / 86400);
  if (d <= 0) return "today";
  if (d === 1) return "tomorrow";
  return `in ${d}d`;
}

// ── Main component ────────────────────────────────────────────────────────
export function OnChainCard({ symbol }: { symbol: string | null }) {
  const { data, loading, error } = useOnChain(symbol);

  const sourceLabel = data?.source?.length
    ? data.source.join(" · ")
    : "CoinGecko · DeFiLlama";

  return (
    <Card>
      <CardHeader
        num="13"
        icon="⬡"
        title="ON-CHAIN INTELLIGENCE"
        badge="LIVE"
        src={sourceLabel}
        right={
          data?.risk_score != null ? (
            <span
              className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border"
              style={{
                color:            data.risk_score >= 60 ? "#ef4444" : data.risk_score >= 40 ? "#f59e0b" : "#22c55e",
                background:       data.risk_score >= 60 ? "rgba(239,68,68,0.08)" : data.risk_score >= 40 ? "rgba(245,158,11,0.08)" : "rgba(34,197,94,0.08)",
                borderColor:      data.risk_score >= 60 ? "rgba(239,68,68,0.20)" : data.risk_score >= 40 ? "rgba(245,158,11,0.20)" : "rgba(34,197,94,0.20)",
              }}
            >
              Risk {data.risk_score}/100
            </span>
          ) : undefined
        }
      />

      <div className="p-4">
        {loading && !data && (
          <div className="space-y-2">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-6 bg-surface-2 rounded animate-pulse border border-border/20" />
            ))}
          </div>
        )}

        {error && !data && (
          <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
            On-chain data unavailable
          </div>
        )}

        {!symbol && !loading && (
          <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
            Run analysis to load on-chain data
          </div>
        )}

        {data && (
          <div className="space-y-4">

            {/* Risk gauge */}
            {data.risk_score != null && (
              <div className="px-0.5">
                <RiskGauge score={data.risk_score} />
              </div>
            )}

            {/* ── Supply metrics ──────────────────────────────────────── */}
            <div>
              <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">
                Supply
              </div>
              <div className="space-y-0">
                <Row
                  label="Circulating"
                  value={fmtSupply(data.circulating_supply)}
                  valueClass="text-text"
                />
                {data.total_supply != null && (
                  <Row
                    label="Total supply"
                    value={fmtSupply(data.total_supply)}
                    valueClass="text-text-muted"
                  />
                )}
                {data.max_supply != null && (
                  <Row
                    label="Max supply"
                    value={fmtSupply(data.max_supply)}
                    valueClass="text-text-muted"
                  />
                )}
                {data.supply_pct != null && (
                  <div className="py-1.5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-mono text-text-muted/60 uppercase tracking-wide">
                        % Circulating
                      </span>
                      <span className={`text-[11px] font-mono font-bold ${data.supply_pct > 80 ? "text-teal" : data.supply_pct < 40 ? "text-red" : "text-amber"}`}>
                        {data.supply_pct.toFixed(1)}%
                      </span>
                    </div>
                    <MiniBar
                      pct={data.supply_pct}
                      color={data.supply_pct > 80 ? "#22c55e" : data.supply_pct < 40 ? "#ef4444" : "#f59e0b"}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* ── Valuation ───────────────────────────────────────────── */}
            <div>
              <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">
                Valuation
              </div>
              <div className="space-y-0">
                {data.market_cap_usd != null && (
                  <Row label="Market cap" value={fmtBigNum(data.market_cap_usd)} valueClass="text-text" />
                )}
                {data.fdv_usd != null && (
                  <Row label="Fully diluted" value={fmtBigNum(data.fdv_usd)} valueClass="text-text-muted" />
                )}
                {data.mc_fdv_ratio != null && (
                  <Row
                    label="MC / FDV"
                    value={`${(data.mc_fdv_ratio * 100).toFixed(0)}%`}
                    valueClass={
                      data.mc_fdv_ratio >= 0.8 ? "text-teal" :
                      data.mc_fdv_ratio >= 0.5 ? "text-amber" : "text-red"
                    }
                  />
                )}
                {data.nvt_proxy != null && (
                  <Row
                    label="NVT proxy"
                    value={`${data.nvt_proxy.toFixed(0)}x`}
                    valueClass={
                      data.nvt_proxy < 50 ? "text-teal" :
                      data.nvt_proxy < 150 ? "text-amber" : "text-red"
                    }
                  />
                )}
              </div>
            </div>

            {/* ── TVL (DeFi protocols only) ───────────────────────────── */}
            {(data.tvl_usd != null || data.tvl_mc_ratio != null) && (
              <div>
                <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">
                  DeFi TVL
                </div>
                <div className="space-y-0">
                  {data.tvl_usd != null && (
                    <Row label="Total value locked" value={fmtBigNum(data.tvl_usd)} valueClass="text-text" />
                  )}
                  {data.tvl_mc_ratio != null && (
                    <Row
                      label="TVL / Market cap"
                      value={`${data.tvl_mc_ratio.toFixed(2)}x`}
                      valueClass={data.tvl_mc_ratio >= 1 ? "text-teal" : data.tvl_mc_ratio >= 0.3 ? "text-amber" : "text-text-muted"}
                    />
                  )}
                </div>
              </div>
            )}

            {/* ── Unlock schedule ─────────────────────────────────────── */}
            {data.unlock?.next_unlock && (
              <div>
                <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">
                  Token Unlock
                </div>
                <div className={`flex items-center justify-between px-3 py-2.5 rounded-lg border ${
                  (() => {
                    const days = data.unlock.next_unlock.date
                      ? Math.round((data.unlock.next_unlock.date - Date.now() / 1000) / 86400)
                      : 999;
                    return days < 14
                      ? "bg-red/8 border-red/20"
                      : days < 30
                      ? "bg-amber/8 border-amber/20"
                      : "bg-surface-2 border-border/40";
                  })()
                }`}>
                  <div>
                    <div className={`text-[11px] font-mono font-bold ${
                      (() => {
                        const days = data.unlock.next_unlock.date
                          ? Math.round((data.unlock.next_unlock.date - Date.now() / 1000) / 86400)
                          : 999;
                        return days < 14 ? "text-red" : days < 30 ? "text-amber" : "text-text";
                      })()
                    }`}>
                      {data.unlock.next_unlock.label}
                    </div>
                    {data.unlock.next_unlock.amount_usd != null && (
                      <div className="text-[10px] font-mono text-text-muted/60">
                        {fmtBigNum(data.unlock.next_unlock.amount_usd)} unlocking
                      </div>
                    )}
                  </div>
                  {data.unlock.next_unlock.date && (
                    <span className="text-[10px] font-mono text-text-muted/60 shrink-0 ml-3">
                      {daysAway(data.unlock.next_unlock.date)}
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* ── Risk signals ─────────────────────────────────────────── */}
            {data.signals && data.signals.length > 0 && (
              <div>
                <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">
                  On-Chain Signals
                </div>
                <div className="space-y-1.5">
                  {data.signals.map((sig, i) => (
                    <SignalBadge key={i} signal={sig} />
                  ))}
                </div>
              </div>
            )}

          </div>
        )}
      </div>
    </Card>
  );
}
