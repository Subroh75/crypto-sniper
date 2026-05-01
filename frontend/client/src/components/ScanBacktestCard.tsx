// ── Scan → Backtest Card ───────────────────────────────────────────────────
// Takes today's BUY signals from TopSignals and runs a combined backtest.
// Shows portfolio equity curve, win rate, avg returns, and per-symbol breakdown.

import { useState } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface EquityPoint { date: string; symbol: string; equity: number; ret_1d: number; }
interface PerSymbol {
  symbol: string; total_trades: number;
  win_rate_1d: number | null; avg_ret_1d: number | null;
  avg_ret_3d: number | null; avg_ret_5d: number | null;
  total_return: number | null; max_drawdown: number | null;
  error?: string;
}
interface Portfolio {
  total_trades: number; wins_1d: number; losses_1d: number;
  win_rate_1d: number | null; avg_ret_1d: number | null;
  avg_ret_3d: number | null; avg_ret_5d: number | null;
  total_return: number | null; max_drawdown: number; sharpe_proxy: number | null;
}
interface BacktestMultiResult {
  symbols: string[]; results: PerSymbol[];
  equity: EquityPoint[]; portfolio: Portfolio; error?: string;
}

interface Props {
  buySignals: { symbol: string; score: number; change: number }[];
  onSelectSymbol: (sym: string) => void;
}

// ── Card primitives ───────────────────────────────────────────────────────
function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-3">
      {children}
    </div>
  );
}

function CardHeader({ right }: { right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
      <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
        <span className="text-purple">17</span>
        <span>◈</span>
        <span>Scan Backtest</span>
        <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-teal/10 text-teal border border-teal/15 uppercase tracking-wide">
          Portfolio
        </span>
      </div>
      <div className="flex items-center gap-2">{right}</div>
    </div>
  );
}

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

// ── Equity sparkline (pure SVG) ───────────────────────────────────────────
function EquityCurve({ points }: { points: EquityPoint[] }) {
  if (points.length < 2) return null;
  const W = 600, H = 80;
  const equities = points.map(p => p.equity);
  const minE = Math.min(...equities);
  const maxE = Math.max(...equities);
  const rangeE = maxE - minE || 1;
  const toX = (i: number) => (i / (points.length - 1)) * W;
  const toY = (v: number) => H - ((v - minE) / rangeE) * H;
  const path = points.map((p, i) => `${i === 0 ? "M" : "L"} ${toX(i).toFixed(1)} ${toY(p.equity).toFixed(1)}`).join(" ");
  const fill = [`M ${toX(0).toFixed(1)} ${H}`, ...points.map((p, i) => `L ${toX(i).toFixed(1)} ${toY(p.equity).toFixed(1)}`), `L ${toX(points.length - 1).toFixed(1)} ${H}`, "Z"].join(" ");
  const isProfit = equities[equities.length - 1] >= equities[0];
  const lineColor = isProfit ? "#22c55e" : "#ef4444";
  const fillColor = isProfit ? "rgba(34,197,94,0.06)" : "rgba(239,68,68,0.06)";
  const finalReturn = equities[equities.length - 1] - 100;
  return (
    <div className="w-full">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[9px] font-mono text-text-muted/50 uppercase tracking-wider">
          Portfolio equity curve ($100 start · {points.length} trades)
        </span>
        <span className={`text-[11px] font-mono font-bold ${finalReturn >= 0 ? "text-teal" : "text-red"}`}>
          {finalReturn >= 0 ? "+" : ""}{finalReturn.toFixed(1)}%
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 72 }} preserveAspectRatio="none">
        <line x1="0" y1={toY(100).toFixed(1)} x2={W} y2={toY(100).toFixed(1)} stroke="rgba(255,255,255,0.06)" strokeWidth="1" strokeDasharray="3,3" />
        <path d={fill} fill={fillColor} />
        <path d={path} fill="none" stroke={lineColor} strokeWidth="1.5" />
      </svg>
    </div>
  );
}

// ── Per-symbol row ────────────────────────────────────────────────────────
function SymbolRow({ row, score, change, onSelect }: {
  row: PerSymbol; score: number; change: number; onSelect: (s: string) => void;
}) {
  const wr = row.win_rate_1d;
  const ret = row.avg_ret_1d;
  const wrColor = wr == null ? "#475569" : wr >= 55 ? "#22c55e" : wr >= 40 ? "#f59e0b" : "#ef4444";
  const retColor = ret == null ? "#475569" : ret >= 1 ? "#22c55e" : ret >= 0 ? "#f59e0b" : "#ef4444";

  return (
    <button
      onClick={() => onSelect(row.symbol)}
      className="w-full text-left hover:bg-surface-2/50 transition-colors"
      style={{ display: "grid", gridTemplateColumns: "60px 40px 50px 52px 52px 52px 52px", alignItems: "center", padding: "7px 0", borderBottom: "1px solid rgba(30,41,59,0.5)" }}
    >
      <span className="text-[11px] font-mono font-bold text-text pl-1">{row.symbol}</span>
      <span className="text-[9px] font-mono text-teal">{score}/16</span>
      <span className="text-[9px] font-mono text-teal">+{change.toFixed(1)}%</span>
      <span className="text-[10px] font-mono font-bold" style={{ color: wrColor }}>
        {wr != null ? `${wr.toFixed(0)}%` : "—"}
      </span>
      <span className="text-[10px] font-mono font-bold" style={{ color: retColor }}>
        {ret != null ? `${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%` : "—"}
      </span>
      <span className="text-[9px] font-mono text-text-muted/60">
        {row.avg_ret_3d != null ? `${row.avg_ret_3d >= 0 ? "+" : ""}${row.avg_ret_3d.toFixed(1)}%` : "—"}
      </span>
      <span className="text-[9px] font-mono text-text-muted/60">
        {row.avg_ret_5d != null ? `${row.avg_ret_5d >= 0 ? "+" : ""}${row.avg_ret_5d.toFixed(1)}%` : "—"}
      </span>
    </button>
  );
}

// ── Main component ────────────────────────────────────────────────────────
export function ScanBacktestCard({ buySignals, onSelectSymbol }: Props) {
  const [data,    setData]    = useState<BacktestMultiResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);

  const run = async () => {
    if (!buySignals.length) return;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await fetch(`${API}/backtest-multi`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: buySignals.map(s => s.symbol) }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      if (json.error) throw new Error(json.error);
      setData(json);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const p = data?.portfolio;
  const fmtPct = (v: number | null | undefined) =>
    v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;

  const winRateColor = !p?.win_rate_1d ? "text-text-muted"
    : p.win_rate_1d >= 55 ? "text-teal" : p.win_rate_1d >= 40 ? "text-amber" : "text-red";
  const retColor = !p?.avg_ret_1d ? "text-text-muted"
    : p.avg_ret_1d >= 1 ? "text-teal" : p.avg_ret_1d >= 0 ? "text-amber" : "text-red";

  // Map signal info by symbol for the breakdown table
  const signalMap = Object.fromEntries(buySignals.map(s => [s.symbol, s]));

  return (
    <Card>
      <CardHeader
        right={
          buySignals.length > 0 ? (
            <button
              onClick={run}
              disabled={loading}
              className={`text-[9px] font-mono font-bold px-3 py-1 rounded border transition-all ${
                loading
                  ? "border-border/30 text-text-muted/40 cursor-not-allowed"
                  : "border-teal/40 text-teal bg-teal/5 hover:bg-teal/10 cursor-pointer"
              }`}
            >
              {loading ? "Running…" : `Backtest ${buySignals.length} signals`}
            </button>
          ) : undefined
        }
      />

      <div className="p-4">
        {/* Empty state — no signals yet */}
        {!buySignals.length && !loading && !data && (
          <div className="text-center py-6 text-[11px] font-mono text-text-muted/50">
            Run the scanner and filter to BUY signals first
          </div>
        )}

        {/* Waiting for user to click Run */}
        {buySignals.length > 0 && !loading && !data && !error && (
          <div className="text-center py-4">
            <div className="text-[11px] font-mono text-text-muted/60 mb-1">
              {buySignals.length} BUY signal{buySignals.length !== 1 ? "s" : ""} ready to backtest
            </div>
            <div className="flex flex-wrap gap-1.5 justify-center mb-3">
              {buySignals.map(s => (
                <span key={s.symbol} className="text-[9px] font-mono px-2 py-0.5 rounded bg-teal/10 text-teal border border-teal/20">
                  {s.symbol} {s.score}/16
                </span>
              ))}
            </div>
            <div className="text-[9px] font-mono text-text-muted/40">
              Click "Backtest {buySignals.length} signals" above to run historical analysis
            </div>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="space-y-2">
            <div className="text-[10px] font-mono text-text-muted/60 text-center mb-3">
              Running backtest on {buySignals.length} symbols…
            </div>
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-6 bg-surface-2 rounded animate-pulse border border-border/20" />
            ))}
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="p-3 rounded-lg bg-red/5 border border-red/20 mb-3">
            <div className="text-[10px] font-mono text-red font-bold mb-1">Backtest failed</div>
            <div className="text-[9px] font-mono text-text-muted/60">{error}</div>
            <button onClick={run} className="mt-2 text-[9px] font-mono text-purple border border-purple/30 px-2 py-0.5 rounded hover:bg-purple/10 cursor-pointer">
              Retry
            </button>
          </div>
        )}

        {/* Results */}
        {data && !loading && p && (
          <div className="space-y-4">

            {/* Equity curve */}
            {data.equity.length > 1 && <EquityCurve points={data.equity} />}

            {/* Portfolio stats */}
            <div className="grid grid-cols-2 gap-2">
              <Stat
                label="Win rate (1D)"
                value={p.win_rate_1d != null ? `${p.win_rate_1d.toFixed(0)}%` : "—"}
                sub={`${p.wins_1d}W / ${p.losses_1d}L of ${p.total_trades} trades`}
                color={winRateColor}
              />
              <Stat
                label="Avg return (1D)"
                value={fmtPct(p.avg_ret_1d)}
                sub={`3D: ${fmtPct(p.avg_ret_3d)}  5D: ${fmtPct(p.avg_ret_5d)}`}
                color={retColor}
              />
              <Stat
                label="Total return"
                value={fmtPct(p.total_return)}
                sub="Compounded 1D holds"
                color={!p.total_return ? "text-text-muted" : p.total_return >= 0 ? "text-teal" : "text-red"}
              />
              <Stat
                label="Max drawdown"
                value={`-${p.max_drawdown.toFixed(1)}%`}
                sub={p.sharpe_proxy != null ? `Sharpe ≈ ${p.sharpe_proxy.toFixed(2)}` : ""}
                color={p.max_drawdown > 20 ? "text-red" : p.max_drawdown > 10 ? "text-amber" : "text-teal"}
              />
            </div>

            {/* Per-symbol breakdown */}
            {data.results.length > 0 && (
              <div>
                <div className="text-[9px] font-mono text-text-muted/50 uppercase tracking-wider mb-2">
                  Per-signal breakdown (click to analyse)
                </div>
                {/* Header */}
                <div style={{ display: "grid", gridTemplateColumns: "60px 40px 50px 52px 52px 52px 52px", padding: "4px 0", borderBottom: "1px solid rgba(51,65,85,0.5)" }}>
                  {["Symbol","Score","Chg%","Win%","Avg 1D","Avg 3D","Avg 5D"].map(h => (
                    <span key={h} className="text-[8px] font-mono text-text-muted/40 uppercase tracking-wider pl-1">{h}</span>
                  ))}
                </div>
                {data.results.map(row => (
                  <SymbolRow
                    key={row.symbol}
                    row={row}
                    score={signalMap[row.symbol]?.score ?? 0}
                    change={signalMap[row.symbol]?.change ?? 0}
                    onSelect={onSelectSymbol}
                  />
                ))}
              </div>
            )}

            {/* Footer */}
            <div className="text-[9px] font-mono text-text-muted/30 leading-relaxed">
              Each signal backtested over ~90 days of daily bars. Entry at bar close, exit next day.
              Portfolio equity compounds all trades chronologically. Past performance is not indicative of future results.
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
