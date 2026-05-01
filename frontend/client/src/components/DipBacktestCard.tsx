// ── DipBacktestCard.tsx ───────────────────────────────────────────────────────
// "If I bought every dip at score X, what happened?"
// Answers the contrarian question: which dip scores actually recover vs fall further.

import { useState, useCallback } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface Band {
  label:    string;
  color:    string;
  min:      number;
  max:      number;
  n:        number;
  avg_dip:  number;
  avg_1d:   number;
  avg_3d:   number | null;
  avg_7d:   number | null;
  win_rate: number;
  wins:     number;
  equity:   number;
}

interface DipPerfData {
  bands:      Band[];
  coins_used: string[];
  total_bars: number;
  min_dip:    number;
  error?:     string;
}

function ReturnPill({ val, suffix = "%" }: { val: number | null; suffix?: string }) {
  if (val == null) return <span className="text-[9px] font-mono text-text-muted/30">—</span>;
  const color = val >= 3 ? "#22c55e" : val >= 0 ? "#f59e0b" : "#ef4444";
  return (
    <span className="text-[10px] font-mono font-bold tabular-nums" style={{ color }}>
      {val >= 0 ? "+" : ""}{val.toFixed(1)}{suffix}
    </span>
  );
}

function BandRow({ band, maxAbs, isWinner }: { band: Band; maxAbs: number; isWinner: boolean }) {
  const barPct   = maxAbs > 0 ? Math.abs(band.avg_1d) / maxAbs * 100 : 0;
  const isPos    = band.avg_1d >= 0;
  const barColor = band.avg_1d >= 3 ? "#22c55e" : band.avg_1d >= 0 ? "#f59e0b" : "#ef4444";
  const equityGain = band.equity - 100;

  return (
    <div
      className="rounded-lg border transition-all"
      style={{
        borderColor: isWinner ? `${band.color}40` : "rgba(30,41,59,0.6)",
        background:  isWinner ? `${band.color}08` : "transparent",
        padding: "10px 12px",
        marginBottom: 6,
      }}
    >
      {/* Top row: score label + key stats */}
      <div className="flex items-center gap-3 mb-2">
        <div className="flex flex-col gap-0.5 w-14 shrink-0">
          <span className="text-[13px] font-mono font-black" style={{ color: band.color }}>
            {band.label}
          </span>
          <span className="text-[8px] font-mono text-text-muted/40">{band.n} dips</span>
        </div>

        {/* Return bar */}
        <div className="flex-1 flex items-center gap-2">
          <div className="flex-1 h-[5px] rounded-full bg-surface-2 overflow-hidden relative">
            <div
              className="absolute top-0 h-full rounded-full"
              style={{
                width: `${barPct}%`,
                [isPos ? "left" : "right"]: "0%",
                background: barColor,
                opacity: 0.9,
              }}
            />
          </div>
          <ReturnPill val={band.avg_1d} />
        </div>

        {/* Win rate */}
        <div className="flex flex-col items-end gap-0.5 w-12 shrink-0">
          <span
            className="text-[11px] font-mono font-bold"
            style={{ color: band.win_rate >= 55 ? "#22c55e" : band.win_rate >= 40 ? "#f59e0b" : "#ef4444" }}
          >
            {band.win_rate.toFixed(0)}%
          </span>
          <span className="text-[8px] font-mono text-text-muted/40">win rate</span>
        </div>
      </div>

      {/* Bottom row: 3D / 7D / $100 / avg dip size */}
      <div className="flex items-center gap-4 pl-[68px]">
        <div className="flex flex-col gap-0.5">
          <ReturnPill val={band.avg_3d} />
          <span className="text-[8px] font-mono text-text-muted/30">3D hold</span>
        </div>
        <div className="flex flex-col gap-0.5">
          <ReturnPill val={band.avg_7d} />
          <span className="text-[8px] font-mono text-text-muted/30">7D hold</span>
        </div>
        <div className="flex flex-col gap-0.5 ml-auto">
          <span
            className="text-[10px] font-mono font-bold tabular-nums"
            style={{ color: equityGain >= 0 ? "#22c55e" : "#ef4444" }}
          >
            ${band.equity.toFixed(0)}
          </span>
          <span className="text-[8px] font-mono text-text-muted/30">from $100</span>
        </div>
        <div className="flex flex-col gap-0.5 items-end">
          <span className="text-[10px] font-mono text-red/70 tabular-nums">
            {band.avg_dip.toFixed(1)}%
          </span>
          <span className="text-[8px] font-mono text-text-muted/30">avg dip</span>
        </div>
      </div>

      {/* Winner badge */}
      {isWinner && (
        <div className="mt-2 pl-[68px]">
          <span className="text-[8px] font-mono font-bold px-2 py-0.5 rounded"
                style={{ background: `${band.color}20`, color: band.color, border: `1px solid ${band.color}40` }}>
            ★ BEST DIP-BUY ZONE
          </span>
        </div>
      )}
    </div>
  );
}

function Verdict({ bands, minDip }: { bands: Band[]; minDip: number }) {
  if (bands.length === 0) return null;

  // Best band by avg 1D return
  const best  = [...bands].sort((a, b) => b.avg_1d - a.avg_1d)[0];
  // Worst (knife-catcher zone)
  const worst = [...bands].sort((a, b) => a.avg_1d - b.avg_1d)[0];
  // Score threshold where avg 1D goes positive
  const firstPositive = [...bands].sort((a, b) => a.min - b.min).find(b => b.avg_1d > 0);

  return (
    <div className="rounded-lg bg-surface-2 border border-border/30 p-3 space-y-2 mt-4">
      <div className="text-[9px] font-mono text-text-muted/50 uppercase tracking-wider">
        Dip Strategy Verdict (≥{minDip}% dips)
      </div>
      <div className="space-y-1.5">
        <div className="flex items-start gap-2">
          <span className="text-[10px] mt-0.5" style={{ color: best.color }}>★</span>
          <span className="text-[10px] font-mono text-text-muted/80 leading-relaxed">
            Sweet spot: score <strong style={{ color: best.color }}>{best.label}/16</strong> dips average{" "}
            <strong style={{ color: best.avg_1d >= 0 ? "#22c55e" : "#ef4444" }}>
              {best.avg_1d >= 0 ? "+" : ""}{best.avg_1d.toFixed(2)}%
            </strong> next day · {best.win_rate.toFixed(0)}% win rate · ${best.equity.toFixed(0)} from $100
          </span>
        </div>
        {firstPositive && (
          <div className="flex items-start gap-2">
            <span className="text-[10px] mt-0.5 text-[#22c55e]">✓</span>
            <span className="text-[10px] font-mono text-text-muted/80 leading-relaxed">
              Dips become buyable at score <strong className="text-[#22c55e]">{firstPositive.label}</strong> — below that the coin often continues falling
            </span>
          </div>
        )}
        {worst.avg_1d < -1 && (
          <div className="flex items-start gap-2">
            <span className="text-[10px] mt-0.5 text-[#ef4444]">✗</span>
            <span className="text-[10px] font-mono text-text-muted/80 leading-relaxed">
              Avoid score <strong style={{ color: worst.color }}>{worst.label}</strong> dips —
              averaged <strong className="text-[#ef4444]">{worst.avg_1d.toFixed(2)}%</strong> · falling knife territory
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export function DipBacktestCard() {
  const [data,    setData]    = useState<DipPerfData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [minDip,  setMinDip]  = useState(10);

  const DIP_OPTIONS = [5, 10, 15, 20];

  const run = useCallback(async (dip: number) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/dip-performance?min_dip=${dip}&top_n=20`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json: DipPerfData = await res.json();
      if (json.error) throw new Error(json.error);
      setData(json);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoading(false);
    }
  }, []);

  const bands = data?.bands ?? [];
  const maxAbs = bands.length ? Math.max(...bands.map(b => Math.abs(b.avg_1d)), 0.1) : 1;
  const winnerBand = bands.length ? [...bands].sort((a, b) => b.avg_1d - a.avg_1d)[0] : null;

  return (
    <div className="rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-3">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
          <span className="text-red">📉</span>
          <span>Dip Score Performance</span>
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-red/10 text-red border border-red/20">
            CONTRARIAN
          </span>
        </div>
        {data && (
          <span className="text-[9px] font-mono text-text-muted/40">
            {data.coins_used.length} coins · {data.total_bars} dip bars
          </span>
        )}
      </div>

      <div className="p-4">
        {/* Intro */}
        <p className="text-[10px] font-mono text-text-muted/60 leading-relaxed mb-4">
          For every bar where a coin was down the selected % in a day,
          what did the VPRTS score predict about the next 1D / 3D / 7D recovery?
        </p>

        {/* Dip threshold selector + run button */}
        <div className="flex items-center gap-2 mb-4">
          <span className="text-[9px] font-mono text-text-muted/50">Dip ≥</span>
          <div className="flex gap-1">
            {DIP_OPTIONS.map(d => (
              <button
                key={d}
                onClick={() => setMinDip(d)}
                className="text-[9px] font-mono px-2 py-1 rounded border transition-all"
                style={{
                  borderColor: minDip === d ? "rgba(239,68,68,0.5)" : "rgba(30,41,59,0.8)",
                  background:  minDip === d ? "rgba(239,68,68,0.1)" : "transparent",
                  color:       minDip === d ? "#ef4444" : "#64748b",
                }}
              >
                {d}%
              </button>
            ))}
          </div>
          <button
            onClick={() => run(minDip)}
            disabled={loading}
            className="ml-auto text-[9px] font-mono font-bold px-4 py-1.5 rounded border transition-all"
            style={loading
              ? { color: "#334155", borderColor: "#1e293b", cursor: "not-allowed" }
              : { color: "#ef4444", borderColor: "rgba(239,68,68,0.4)", background: "rgba(239,68,68,0.08)", cursor: "pointer" }
            }
          >
            {loading ? "Running…" : "Run Backtest"}
          </button>
        </div>

        {/* Loading */}
        {loading && (
          <div className="space-y-2">
            <div className="text-[10px] font-mono text-text-muted/50 mb-2">
              Running bar-by-bar dip backtest…
            </div>
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-16 bg-surface-2 rounded-lg animate-pulse border border-border/20" />
            ))}
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="text-[10px] font-mono text-red/70 py-4 text-center">{error}</div>
        )}

        {/* Empty state */}
        {!loading && !error && !data && (
          <div className="text-center py-8">
            <div className="text-3xl mb-3">📉</div>
            <div className="text-[11px] font-mono text-text-muted/50">
              Select a dip threshold and run the backtest
            </div>
            <div className="text-[9px] font-mono text-text-muted/30 mt-1">
              Uses daily bars across current dip coins
            </div>
          </div>
        )}

        {/* Results */}
        {!loading && bands.length > 0 && (
          <>
            {/* Column hint */}
            <div className="flex items-center gap-3 mb-3 pl-[68px]">
              <span className="text-[8px] font-mono text-text-muted/30 flex-1">Avg 1D return →</span>
              <span className="text-[8px] font-mono text-text-muted/30 w-12 text-right">Win%</span>
            </div>

            {bands.map(band => (
              <BandRow
                key={band.label}
                band={band}
                maxAbs={maxAbs}
                isWinner={winnerBand?.label === band.label}
              />
            ))}

            <Verdict bands={bands} minDip={minDip} />

            <div className="mt-3 text-[8px] font-mono text-text-muted/25 leading-relaxed">
              Coins used: {data?.coins_used?.join(", ")}.
              Entry at close of dip bar. Not financial advice.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
