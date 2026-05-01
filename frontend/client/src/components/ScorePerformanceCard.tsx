// ── ScorePerformanceCard.tsx ──────────────────────────────────────────────────
// Shows historical performance grouped by VPRTS score band.
// Answers: "If a coin scored 7/16 in the past, what return did it average?"
// Data: bar-by-bar backtest of current green coins from scan cache.

import { useScorePerformance } from "@/hooks/useApi";
import type { ScoreBand } from "@/lib/api";

// ── Shared card primitives ────────────────────────────────────────────────────
function Card({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <div id={id} className="rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-3">
      {children}
    </div>
  );
}

function CardHeader({ title, sub, right }: {
  title: string; sub?: string; right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
      <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
        <span className="text-purple">◈</span>
        <span>{title}</span>
        {sub && (
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-purple/10 text-purple border border-purple/20 uppercase tracking-wide">
            {sub}
          </span>
        )}
      </div>
      {right && <div className="flex items-center gap-2">{right}</div>}
    </div>
  );
}

// ── Bar + stats for one score band ───────────────────────────────────────────
function BandRow({ band, maxAbsReturn }: { band: ScoreBand; maxAbsReturn: number }) {
  const isPositive = band.avg_1d >= 0;
  const barWidth   = maxAbsReturn > 0 ? Math.abs(band.avg_1d) / maxAbsReturn * 100 : 0;
  const equity     = band.equity ?? 100;
  const equityGain = equity - 100;

  const returnColor =
    band.avg_1d >= 2  ? "#22c55e"
    : band.avg_1d >= 0  ? "#f59e0b"
    : "#ef4444";

  const winColor =
    band.win_rate >= 55 ? "#22c55e"
    : band.win_rate >= 40 ? "#f59e0b"
    : "#ef4444";

  return (
    <div className="grid gap-2 py-3 border-b border-border/20 last:border-none"
         style={{ gridTemplateColumns: "72px 1fr 64px 56px 56px 72px" }}>

      {/* Score label + sample count */}
      <div className="flex flex-col justify-center gap-0.5">
        <span className="text-[12px] font-mono font-black" style={{ color: band.color }}>
          {band.label}
        </span>
        <span className="text-[9px] font-mono text-text-muted/40">
          {band.n} bars
        </span>
      </div>

      {/* Avg 1D return bar */}
      <div className="flex items-center gap-2">
        <div className="flex-1 h-[6px] rounded-full bg-surface-2 overflow-hidden relative">
          <div
            className="absolute top-0 h-full rounded-full transition-all duration-500"
            style={{
              width: `${barWidth}%`,
              left:  isPositive ? "50%" : `${50 - barWidth / 2}%`,
              background: returnColor,
              opacity: 0.85,
            }}
          />
          {/* Midline */}
          <div className="absolute top-0 left-1/2 h-full w-px bg-border/60" />
        </div>
        <span className="text-[11px] font-mono font-bold w-14 text-right tabular-nums"
              style={{ color: returnColor }}>
          {isPositive ? "+" : ""}{band.avg_1d.toFixed(2)}%
        </span>
      </div>

      {/* Win rate */}
      <div className="flex flex-col justify-center">
        <span className="text-[11px] font-mono font-bold tabular-nums" style={{ color: winColor }}>
          {band.win_rate.toFixed(0)}%
        </span>
        <span className="text-[8px] font-mono text-text-muted/40">win rate</span>
      </div>

      {/* 3D avg */}
      <div className="flex flex-col justify-center">
        <span className="text-[10px] font-mono tabular-nums"
              style={{ color: band.avg_3d != null ? (band.avg_3d >= 0 ? "#22c55e" : "#ef4444") : "#334155" }}>
          {band.avg_3d != null ? `${band.avg_3d >= 0 ? "+" : ""}${band.avg_3d.toFixed(1)}%` : "—"}
        </span>
        <span className="text-[8px] font-mono text-text-muted/40">3D hold</span>
      </div>

      {/* 7D avg */}
      <div className="flex flex-col justify-center">
        <span className="text-[10px] font-mono tabular-nums"
              style={{ color: band.avg_7d != null ? (band.avg_7d >= 0 ? "#22c55e" : "#ef4444") : "#334155" }}>
          {band.avg_7d != null ? `${band.avg_7d >= 0 ? "+" : ""}${band.avg_7d.toFixed(1)}%` : "—"}
        </span>
        <span className="text-[8px] font-mono text-text-muted/40">7D hold</span>
      </div>

      {/* $100 compounded */}
      <div className="flex flex-col justify-center">
        <span className="text-[11px] font-mono font-bold tabular-nums"
              style={{ color: equityGain >= 0 ? "#22c55e" : "#ef4444" }}>
          ${equity.toFixed(0)}
        </span>
        <span className="text-[8px] font-mono text-text-muted/40">
          {equityGain >= 0 ? "+" : ""}{equityGain.toFixed(1)}% on $100
        </span>
      </div>
    </div>
  );
}

// ── Insight callout ───────────────────────────────────────────────────────────
function Insight({ bands }: { bands: ScoreBand[] }) {
  if (bands.length === 0) return null;

  const best = [...bands].sort((a, b) => b.avg_1d - a.avg_1d)[0];
  const buyBand = bands.find(b => b.min >= 9);

  return (
    <div className="rounded-lg bg-surface-2 border border-border/30 p-3 space-y-1.5">
      <div className="text-[9px] font-mono text-text-muted/50 uppercase tracking-wider">Key Takeaways</div>
      <div className="space-y-1">
        <div className="flex items-start gap-2">
          <span className="text-[9px] font-mono mt-0.5" style={{ color: best.color }}>▶</span>
          <span className="text-[10px] font-mono text-text-muted/80 leading-relaxed">
            Best performing band: <strong style={{ color: best.color }}>{best.label}/16</strong> averaged{" "}
            <strong style={{ color: best.avg_1d >= 0 ? "#22c55e" : "#ef4444" }}>
              {best.avg_1d >= 0 ? "+" : ""}{best.avg_1d.toFixed(2)}%
            </strong> per day ({best.n} samples, {best.win_rate}% win rate)
          </span>
        </div>
        {buyBand && (
          <div className="flex items-start gap-2">
            <span className="text-[9px] font-mono mt-0.5 text-[#22c55e]">▶</span>
            <span className="text-[10px] font-mono text-text-muted/80 leading-relaxed">
              STRONG BUY zone (<strong className="text-[#22c55e]">9+</strong>): avg{" "}
              <strong style={{ color: buyBand.avg_1d >= 0 ? "#22c55e" : "#ef4444" }}>
                {buyBand.avg_1d >= 0 ? "+" : ""}{buyBand.avg_1d.toFixed(2)}%
              </strong> 1D ·{" "}
              {buyBand.avg_3d != null && (
                <><strong style={{ color: buyBand.avg_3d >= 0 ? "#22c55e" : "#ef4444" }}>
                  {buyBand.avg_3d >= 0 ? "+" : ""}{buyBand.avg_3d.toFixed(2)}%
                </strong> 3D · </>
              )}
              <strong style={{ color: "#7c3aed" }}>${buyBand.equity.toFixed(0)}</strong> from $100 compounded
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────
export function ScorePerformanceCard() {
  const { data, loading, error, refetch } = useScorePerformance(15);

  const bands = data?.bands ?? [];
  const maxAbsReturn = bands.length
    ? Math.max(...bands.map(b => Math.abs(b.avg_1d)), 0.1)
    : 1;

  return (
    <Card>
      <CardHeader
        title="SCORE → PERFORMANCE"
        sub="BACKTEST"
        right={
          <div className="flex items-center gap-2">
            {data && (
              <span className="text-[9px] font-mono text-text-muted/40">
                {data.coins_used?.length ?? 0} coins · {data.total_bars ?? 0} bars
              </span>
            )}
            <button
              onClick={refetch}
              disabled={loading}
              className="text-[9px] font-mono text-text-muted/50 hover:text-text-muted px-2 py-1 rounded border border-border/40 hover:border-border/70 transition-all disabled:opacity-40"
            >
              {loading ? "…" : "↻"}
            </button>
          </div>
        }
      />

      <div className="p-4">
        {/* Loading */}
        {loading && bands.length === 0 && (
          <div className="space-y-3">
            <div className="text-[10px] font-mono text-text-muted/50 mb-3">
              Running bar-by-bar backtest across green coins…
            </div>
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-12 bg-surface-2 rounded-lg animate-pulse border border-border/20" />
            ))}
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="text-center py-6 text-[11px] font-mono text-red/70">
            {error}
          </div>
        )}

        {/* Column headers */}
        {bands.length > 0 && (
          <>
            <div className="grid gap-2 pb-2 border-b border-border/40 mb-1"
                 style={{ gridTemplateColumns: "72px 1fr 64px 56px 56px 72px" }}>
              <span className="text-[8px] font-mono text-text-muted/40 uppercase tracking-wider">Score</span>
              <span className="text-[8px] font-mono text-text-muted/40 uppercase tracking-wider pl-2">Avg 1D return</span>
              <span className="text-[8px] font-mono text-text-muted/40 uppercase tracking-wider">Win %</span>
              <span className="text-[8px] font-mono text-text-muted/40 uppercase tracking-wider">3D</span>
              <span className="text-[8px] font-mono text-text-muted/40 uppercase tracking-wider">7D</span>
              <span className="text-[8px] font-mono text-text-muted/40 uppercase tracking-wider">$100 →</span>
            </div>

            {/* Band rows */}
            {bands.map(band => (
              <BandRow key={band.label} band={band} maxAbsReturn={maxAbsReturn} />
            ))}

            {/* Insight */}
            <div className="mt-4">
              <Insight bands={bands} />
            </div>

            {/* Coins used */}
            <div className="mt-3 pt-3 border-t border-border/20">
              <div className="text-[8px] font-mono text-text-muted/30 leading-relaxed">
                Based on daily bar-by-bar replay of: {data?.coins_used?.join(", ")}.
                Entry at bar close when score matches band. Exit at next-day close.
                Not financial advice.
              </div>
            </div>
          </>
        )}

        {/* No data yet */}
        {!loading && !error && bands.length === 0 && (
          <div className="text-center py-8 text-[11px] font-mono text-text-muted/50">
            Run a scan first — backtest uses cached green coin data
          </div>
        )}
      </div>
    </Card>
  );
}
