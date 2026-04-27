// ── BacktestCard.tsx — Backtest section using signal history DB ───────────────
import { useState } from "react";
import { useBacktest } from "@/hooks/useApi";
import type { BacktestTrade } from "@/types/api";
import { fmtPrice } from "@/lib/api";

function ReturnBadge({ pct }: { pct: number | null }) {
  if (pct == null) return (
    <span className="text-[9px] font-mono text-text-muted/50 px-1.5 py-0.5 rounded bg-surface-2 border border-border/30">
      Pending
    </span>
  );
  const color = pct >= 2 ? "text-teal bg-teal/8 border-teal/20"
              : pct >= 0 ? "text-text bg-surface-2 border-border/40"
              :            "text-red bg-red/8 border-red/20";
  return (
    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${color}`}>
      {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
    </span>
  );
}

function StatBox({ label, value, sub, color = "text-text" }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="flex flex-col items-center justify-center py-3 px-2 rounded-xl bg-surface-2 border border-border/40">
      <div className="text-[8px] font-mono text-text-muted/60 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-[18px] font-mono font-black ${color}`}>{value}</div>
      {sub && <div className="text-[9px] font-mono text-text-muted/50 mt-0.5">{sub}</div>}
    </div>
  );
}

export function BacktestCard({ symbol }: { symbol?: string | null }) {
  const [days, setDays] = useState(30);
  const { data, loading, error, refetch } = useBacktest(symbol, days);

  const summary = data?.summary;
  const trades  = data?.trades ?? [];

  const noData = !loading && data && summary?.total === 0;
  const insufficientResolved = !loading && data && summary?.total > 0 && summary?.resolved === 0;

  return (
    <div className="rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-3">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
          <span className="text-purple">11</span>
          <span>📊</span>
          <span>BACKTEST — IF YOU FOLLOWED EVERY STRONG BUY</span>
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-orange/10 text-orange border border-orange/15">
            BETA
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Day selector */}
          <div className="flex gap-1">
            {[7, 30, 90].map(d => (
              <button
                key={d}
                onClick={() => setDays(d)}
                className={`text-[9px] font-mono px-2 py-1 rounded border transition-all ${
                  days === d
                    ? "border-purple/50 bg-purple/10 text-purple"
                    : "border-border/40 bg-surface-2 text-text-muted hover:border-purple/30"
                }`}
              >
                {d}d
              </button>
            ))}
          </div>
          <button
            onClick={refetch}
            className="text-[9px] font-mono text-text-muted/60 hover:text-text-muted px-2 py-1 rounded border border-border/40 hover:border-border/70 transition-all"
          >
            ↻
          </button>
        </div>
      </div>

      <div className="p-4">
        {loading ? (
          <div className="space-y-3">
            <div className="grid grid-cols-4 gap-3">
              {[0,1,2,3].map(i => (
                <div key={i} className="h-20 bg-surface-2 rounded-xl animate-pulse border border-border/30" />
              ))}
            </div>
            <div className="space-y-2">
              {[0,1,2,3].map(i => (
                <div key={i} className="h-10 bg-surface-2 rounded-lg animate-pulse border border-border/30" />
              ))}
            </div>
          </div>
        ) : error ? (
          <div className="text-center py-8 text-[11px] font-mono text-red/70">
            Failed to load backtest data
          </div>
        ) : noData ? (
          <div className="flex flex-col items-center justify-center py-10 gap-3">
            <span className="text-3xl">📭</span>
            <div className="text-[12px] font-mono font-bold text-text-muted text-center">
              No STRONG BUY signals recorded yet
            </div>
            <div className="text-[10px] font-mono text-text-muted/60 text-center max-w-xs">
              Run the scanner and analyse coins — signals accumulate automatically.
              Return here in 24H for first backtest results.
            </div>
          </div>
        ) : insufficientResolved ? (
          <div className="flex flex-col items-center justify-center py-10 gap-3">
            <span className="text-3xl">⏳</span>
            <div className="text-[12px] font-mono font-bold text-text-muted text-center">
              {summary?.total} signal{summary?.total !== 1 ? "s" : ""} recorded — outcomes pending
            </div>
            <div className="text-[10px] font-mono text-text-muted/60 text-center max-w-xs">
              Outcomes are resolved 24H after each signal. Check back tomorrow.
            </div>
          </div>
        ) : summary ? (
          <>
            {/* Stats grid */}
            <div className="grid grid-cols-4 gap-3 mb-5">
              <StatBox
                label="Win Rate"
                value={summary.win_rate != null ? `${summary.win_rate}%` : "—"}
                sub={`${summary.wins}W · ${summary.losses}L`}
                color={summary.win_rate != null && summary.win_rate >= 50 ? "text-teal" : "text-red"}
              />
              <StatBox
                label="Avg Return"
                value={summary.avg_return != null ? `${summary.avg_return >= 0 ? "+" : ""}${summary.avg_return}%` : "—"}
                sub="per trade (24H)"
                color={summary.avg_return != null && summary.avg_return >= 0 ? "text-teal" : "text-red"}
              />
              <StatBox
                label="Total Return"
                value={summary.total_return != null ? `${summary.total_return >= 0 ? "+" : ""}${summary.total_return}%` : "—"}
                sub="all signals combined"
                color={summary.total_return != null && summary.total_return >= 0 ? "text-teal" : "text-red"}
              />
              <StatBox
                label="Signals"
                value={String(summary.total)}
                sub={`${summary.resolved} resolved`}
                color="text-text"
              />
            </div>

            {/* Visual bar — if you put $1000 in each trade */}
            {summary.avg_return != null && (
              <div className="mb-5 p-3 rounded-xl bg-surface-2 border border-border/40">
                <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-2">
                  If you invested $1,000 in every STRONG BUY ({summary.resolved} trades)
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-[22px] font-mono font-black">
                    <span className={summary.total_return! >= 0 ? "text-teal" : "text-red"}>
                      ${(1000 + 10 * (summary.total_return ?? 0)).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </span>
                  </div>
                  <div className="text-[10px] font-mono text-text-muted/60">
                    from $1,000 base · {days}d window
                  </div>
                </div>
              </div>
            )}

            {/* Trade history table */}
            {trades.length > 0 && (
              <>
                <div className="text-[9px] font-mono text-text-muted/60 uppercase tracking-wide mb-2">
                  Recent signals
                </div>
                <div className="space-y-1 max-h-52 overflow-y-auto pr-1 custom-scroll">
                  {trades.slice().reverse().slice(0, 20).map((t, i) => (
                    <div key={i} className="flex items-center justify-between px-3 py-2 rounded-lg border border-border/30 bg-surface-2 hover:border-border/60 transition-all">
                      <div className="flex items-center gap-2.5">
                        <span className="text-[11px] font-mono font-bold text-text">{t.symbol}</span>
                        <span className="text-[9px] font-mono text-text-muted/50">{t.interval}</span>
                        <span className="text-[9px] font-mono text-text-muted/40">
                          {new Date(t.ts * 1000).toLocaleDateString()}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] font-mono text-text-muted/60">
                          @ {fmtPrice(t.entry_price)}
                        </span>
                        <ReturnBadge pct={t.outcome_pct} />
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Disclaimer */}
            <div className="mt-4 pt-3 border-t border-border/30">
              <p className="text-[9px] font-mono text-text-muted/40 leading-relaxed">
                Backtest uses actual signal history from this app's database. Outcomes are measured as 24H price change from signal time.
                Past performance does not guarantee future results. Not financial advice.
              </p>
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
