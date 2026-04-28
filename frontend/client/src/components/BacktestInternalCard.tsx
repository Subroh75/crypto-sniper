// ── Internal Signal Backtest Card ─────────────────────────────────────────
// Section 14. Replays the live scoring engine bar-by-bar over 1D OHLCV
// history (fetched from CoinGecko via Render /backtest-internal/{symbol}).
// Shows: equity curve sparkline, win rate, avg returns, trade list.

import { useBacktestInternal } from "@/hooks/useApi";
import type { BacktestInternalData, BacktestEquityPoint, BacktestTrade } from "@/types/api";

// ── Card primitives (match home.tsx exactly) ──────────────────────────────
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

// ── Stat tile ────────────────────────────────────────────────────────────
function Stat({ label, value, sub, color = "text-text" }: {
  label: string; value: string; sub?: string; color?: string;
}) {
  return (
    <div className="flex flex-col gap-0.5 p-3 rounded-lg bg-surface-2 border border-border/30">
      <span className="text-[9px] font-mono text-text-muted/50 uppercase tracking-wider">{label}</span>
      <span className={`text-[15px] font-mono font-black ${color}`}>{value}</span>
      {sub && <span className="text-[9px] font-mono text-text-muted/50">{sub}</span>}
    </div>
  );
}

// ── Equity sparkline (pure SVG — no chart library) ────────────────────────
function EquityCurve({ points }: { points: BacktestEquityPoint[] }) {
  if (points.length < 2) return null;

  const W = 600, H = 80;
  const equities = points.map(p => p.equity);
  const minE = Math.min(...equities);
  const maxE = Math.max(...equities);
  const rangeE = maxE - minE || 1;

  const toX = (i: number) => (i / (points.length - 1)) * W;
  const toY = (v: number) => H - ((v - minE) / rangeE) * H;

  // Build SVG path
  const path = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(p.equity).toFixed(1)}`)
    .join(" ");

  // Fill under the curve
  const fill = [
    `M ${toX(0).toFixed(1)} ${H}`,
    ...points.map((p, i) => `L ${toX(i).toFixed(1)} ${toY(p.equity).toFixed(1)}`),
    `L ${toX(points.length - 1).toFixed(1)} ${H}`,
    "Z",
  ].join(" ");

  // Mark STRONG BUY entry bars
  const tradeMarkers = points
    .filter(p => p.signal === "STRONG BUY")
    .map((p, _, arr) => {
      const idx = points.indexOf(p);
      return { x: toX(idx), y: toY(p.equity) };
    });

  const isProfit = equities[equities.length - 1] >= equities[0];
  const lineColor  = isProfit ? "#22c55e" : "#ef4444";
  const fillColor  = isProfit ? "rgba(34,197,94,0.06)" : "rgba(239,68,68,0.06)";

  const finalReturn = equities[equities.length - 1] - 100;

  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[9px] font-mono text-text-muted/50 uppercase tracking-wider">
          Equity curve (1D hold, $100 start)
        </span>
        <span className={`text-[11px] font-mono font-bold ${finalReturn >= 0 ? "text-teal" : "text-red"}`}>
          {finalReturn >= 0 ? "+" : ""}{finalReturn.toFixed(1)}%
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ height: 72 }}
        preserveAspectRatio="none"
      >
        {/* Zero line (at 100 = break even) */}
        <line
          x1="0" y1={toY(100).toFixed(1)}
          x2={W} y2={toY(100).toFixed(1)}
          stroke="rgba(255,255,255,0.06)" strokeWidth="1" strokeDasharray="3,3"
        />
        {/* Fill */}
        <path d={fill} fill={fillColor} />
        {/* Line */}
        <path d={path} fill="none" stroke={lineColor} strokeWidth="1.5" />
        {/* Trade entry markers */}
        {tradeMarkers.map((m, i) => (
          <circle
            key={i}
            cx={m.x.toFixed(1)} cy={m.y.toFixed(1)}
            r="3" fill="#7c3aed" opacity="0.8"
          />
        ))}
      </svg>
      <div className="flex items-center gap-2 mt-1">
        <div className="flex items-center gap-1">
          <div className="w-2 h-2 rounded-full bg-purple opacity-80" />
          <span className="text-[9px] font-mono text-text-muted/50">STRONG BUY signal</span>
        </div>
      </div>
    </div>
  );
}

// ── Score distribution mini-bars ─────────────────────────────────────────
function ScoreDist({ dist, total }: { dist: Record<string, number>; total: number }) {
  const scores = Array.from({ length: 17 }, (_, i) => i);
  const maxCount = Math.max(...Object.values(dist), 1);
  return (
    <div>
      <div className="text-[9px] font-mono text-text-muted/50 uppercase tracking-wider mb-2">
        Score distribution ({total} bars)
      </div>
      <div className="flex items-end gap-[2px] h-8">
        {scores.map(s => {
          const count = dist[String(s)] || 0;
          const pct   = (count / maxCount) * 100;
          const color = s >= 9 ? "#7c3aed" : s >= 5 ? "#f59e0b" : "rgba(255,255,255,0.12)";
          return (
            <div
              key={s}
              className="flex-1 rounded-sm transition-all duration-300"
              style={{ height: `${Math.max(pct, 3)}%`, background: color }}
              title={`Score ${s}: ${count} bars`}
            />
          );
        })}
      </div>
      <div className="flex items-center justify-between mt-1">
        <span className="text-[9px] font-mono text-text-muted/40">0</span>
        <div className="flex items-center gap-3 text-[9px] font-mono">
          <span className="text-amber">5+ MODERATE</span>
          <span className="text-purple">9+ STRONG BUY</span>
        </div>
        <span className="text-[9px] font-mono text-text-muted/40">16</span>
      </div>
    </div>
  );
}

// ── Trade row ────────────────────────────────────────────────────────────
function TradeRow({ trade, idx }: { trade: BacktestTrade; idx: number }) {
  const ret = trade.ret_1d;
  const win = trade.win_1d;
  const retColor = win ? "text-teal" : ret < 0 ? "text-red" : "text-amber";
  return (
    <div className={`flex items-center gap-2 py-1.5 border-b border-border/20 last:border-none ${
      idx % 2 === 0 ? "" : "bg-surface-2/30"
    }`}>
      <span className="text-[10px] font-mono text-text-muted/50 w-20 shrink-0">{trade.date.slice(5)}</span>
      <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded shrink-0 ${
        win ? "bg-teal/10 text-teal border border-teal/20" : ret < 0 ? "bg-red/10 text-red border border-red/20" : "bg-amber/10 text-amber border border-amber/20"
      }`}>
        {win ? "WIN" : ret < 0 ? "LOSS" : "FLAT"}
      </span>
      <span className="text-[10px] font-mono text-text-muted/60 shrink-0">
        {trade.score}/16
      </span>
      <span className="text-[10px] font-mono text-text-muted/40 flex-1 text-right shrink-0">
        ${trade.entry_price < 1 ? trade.entry_price.toFixed(6) : trade.entry_price.toFixed(2)}
      </span>
      <span className={`text-[11px] font-mono font-bold w-14 text-right shrink-0 ${retColor}`}>
        {ret >= 0 ? "+" : ""}{ret.toFixed(2)}%
      </span>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────
export function BacktestInternalCard({ symbol }: { symbol: string | null }) {
  const { data, loading, error } = useBacktestInternal(symbol);
  const s = data?.summary;

  const fmtPct = (v: number | null | undefined, decimals = 1) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(decimals)}%`;

  const winRateColor = !s?.win_rate_1d ? "text-text-muted"
    : s.win_rate_1d >= 55 ? "text-teal"
    : s.win_rate_1d >= 45 ? "text-amber"
    : "text-red";

  const retColor = !s?.avg_ret_1d ? "text-text-muted"
    : s.avg_ret_1d >= 1 ? "text-teal"
    : s.avg_ret_1d >= 0 ? "text-amber"
    : "text-red";

  return (
    <Card>
      <CardHeader
        num="14"
        icon="◈"
        title="SIGNAL BACKTEST"
        badge="1D"
        right={
          s?.total_trades ? (
            <span className="text-[9px] font-mono text-text-muted/60">
              {s.first_date?.slice(5)} → {s.last_date?.slice(5)}
            </span>
          ) : undefined
        }
      />

      <div className="p-4">
        {/* Loading */}
        {loading && !data && (
          <div className="space-y-2">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-6 bg-surface-2 rounded animate-pulse border border-border/20" />
            ))}
          </div>
        )}

        {/* No symbol */}
        {!symbol && !loading && (
          <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
            Run analysis to load signal backtest
          </div>
        )}

        {/* Error */}
        {(error || data?.error) && !loading && (
          <div className="text-center py-6 text-[11px] font-mono text-red/70">
            {data?.error ?? "Backtest unavailable"}
          </div>
        )}

        {/* Data */}
        {data && !data.error && s && (
          <div className="space-y-4">

            {/* Equity curve */}
            {data.equity && data.equity.length > 1 && (
              <EquityCurve points={data.equity} />
            )}

            {/* Key stats */}
            <div className="grid grid-cols-2 gap-2">
              <Stat
                label="Win rate (1D)"
                value={s.win_rate_1d != null ? `${s.win_rate_1d.toFixed(0)}%` : "—"}
                sub={`${s.wins_1d}W / ${s.losses_1d}L of ${s.total_trades} trades`}
                color={winRateColor}
              />
              <Stat
                label="Avg return (1D)"
                value={fmtPct(s.avg_ret_1d)}
                sub={`3D: ${fmtPct(s.avg_ret_3d)}  5D: ${fmtPct(s.avg_ret_5d)}`}
                color={retColor}
              />
              <Stat
                label="Total return"
                value={fmtPct(s.total_return)}
                sub="Compounded 1D holds"
                color={!s.total_return ? "text-text-muted" : s.total_return >= 0 ? "text-teal" : "text-red"}
              />
              <Stat
                label="Max drawdown"
                value={s.max_drawdown != null ? `-${s.max_drawdown.toFixed(1)}%` : "—"}
                sub={s.sharpe_proxy != null ? `Sharpe ≈ ${s.sharpe_proxy.toFixed(2)}` : ""}
                color={!s.max_drawdown ? "text-text-muted" : s.max_drawdown > 20 ? "text-red" : s.max_drawdown > 10 ? "text-amber" : "text-teal"}
              />
            </div>

            {/* Score distribution */}
            {s.score_dist && (
              <ScoreDist dist={s.score_dist} total={s.bars_scanned} />
            )}

            {/* Trade list */}
            {data.trades && data.trades.length > 0 && (
              <div>
                <div className="text-[9px] font-mono text-text-muted/50 uppercase tracking-wider mb-2">
                  Recent STRONG BUY trades (1D hold)
                </div>
                <div>
                  {/* Header */}
                  <div className="flex items-center gap-2 pb-1.5 border-b border-border/40 mb-1">
                    <span className="text-[9px] font-mono text-text-muted/40 w-20">Date</span>
                    <span className="text-[9px] font-mono text-text-muted/40 w-10">Result</span>
                    <span className="text-[9px] font-mono text-text-muted/40 w-10">Score</span>
                    <span className="text-[9px] font-mono text-text-muted/40 flex-1 text-right">Entry</span>
                    <span className="text-[9px] font-mono text-text-muted/40 w-14 text-right">Ret 1D</span>
                  </div>
                  {[...data.trades].reverse().slice(0, 15).map((t, i) => (
                    <TradeRow key={i} trade={t} idx={i} />
                  ))}
                </div>
                {data.trades.length > 15 && (
                  <div className="text-[9px] font-mono text-text-muted/40 text-center mt-2">
                    Showing last 15 of {data.trades.length} trades
                  </div>
                )}
              </div>
            )}

            {/* No trades */}
            {data.trades && data.trades.length === 0 && (
              <div className="text-center py-4 text-[11px] font-mono text-text-muted/50">
                No STRONG BUY (9+/16) signals in the backtest window
              </div>
            )}

            {/* Footer note */}
            <div className="text-[9px] font-mono text-text-muted/30 leading-relaxed">
              Entry at bar close, exit at next-day close. 1D bars from CoinGecko (~90 days).
              Past signal performance does not predict future results.
            </div>

          </div>
        )}
      </div>
    </Card>
  );
}
