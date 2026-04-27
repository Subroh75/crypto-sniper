// ── MultiTimeframe.tsx — Confluence grid: 1H / 4H / 1D ──────────────────────
import { useConfluence } from "@/hooks/useApi";
import type { ConfluenceTF } from "@/types/api";

const TF_LABELS: Record<string, string> = {
  "1H": "1 Hour", "4H": "4 Hour", "1D": "Daily",
};

function SignalPill({ signal, score, max }: { signal: string; score: number; max: number }) {
  const isStrong = signal === "STRONG BUY";
  const isMod    = signal?.includes("MODERATE") || signal?.includes("BUY");
  const color    = isStrong ? "text-teal border-teal/30 bg-teal/8"
                 : isMod    ? "text-amber border-amber/30 bg-amber/8"
                 :            "text-text-muted border-border/40 bg-surface-2";
  return (
    <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded border ${color}`}>
      {signal || "NO SIGNAL"} · {score}/{max}
    </span>
  );
}

function DirectionArrow({ direction }: { direction: string }) {
  if (direction === "LONG")  return <span className="text-teal text-sm">▲</span>;
  if (direction === "SHORT") return <span className="text-red  text-sm">▼</span>;
  return <span className="text-text-muted text-sm">●</span>;
}

function TFCard({ tf }: { tf: ConfluenceTF }) {
  if (tf.error) {
    return (
      <div className="flex flex-col gap-2 p-3 rounded-xl border border-border/40 bg-surface-2 opacity-50">
        <div className="text-[10px] font-mono font-bold text-text-muted uppercase tracking-widest">
          {TF_LABELS[tf.interval] ?? tf.interval}
        </div>
        <div className="text-[10px] font-mono text-red">Error: {tf.error}</div>
      </div>
    );
  }

  const isStrong = tf.signal === "STRONG BUY";
  const borderGlow = isStrong
    ? "border-teal/30 shadow-[0_0_12px_rgba(0,212,170,0.08)]"
    : "border-border/40";

  const bars = [
    { key: "V", score: tf.components.V, max: 5 },
    { key: "P", score: tf.components.P, max: 3 },
    { key: "R", score: tf.components.R, max: 2 },
    { key: "T", score: tf.components.T, max: 3 },
    { key: "S", score: tf.components.S ?? 0, max: 3 },
  ];

  return (
    <div className={`flex flex-col gap-3 p-3 rounded-xl border bg-surface-card ${borderGlow} transition-all`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-mono font-bold text-purple uppercase tracking-widest">
          {TF_LABELS[tf.interval] ?? tf.interval}
        </span>
        <DirectionArrow direction={tf.direction} />
      </div>

      {/* Signal pill */}
      <SignalPill signal={tf.signal} score={tf.score} max={tf.max_score} />

      {/* Score bars */}
      <div className="space-y-1">
        {bars.map(({ key, score, max }) => (
          <div key={key} className="flex items-center gap-2">
            <span className="text-[9px] font-mono text-text-muted/60 w-4">{key}</span>
            <div className="flex-1 h-1.5 bg-surface-2 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${(score / max) * 100}%`,
                  background: score >= max * 0.7
                    ? "linear-gradient(90deg, rgba(0,212,170,0.5), #00d4aa)"
                    : score >= max * 0.4
                    ? "linear-gradient(90deg, rgba(245,158,11,0.5), #f59e0b)"
                    : "rgba(100,116,139,0.4)",
                }}
              />
            </div>
            <span className="text-[9px] font-mono text-text-muted w-6 text-right">{score}/{max}</span>
          </div>
        ))}
      </div>

      {/* Key metrics row */}
      <div className="grid grid-cols-3 gap-1 pt-1 border-t border-border/30">
        {[
          { label: "RSI",  value: tf.rsi?.toFixed(0) ?? "—" },
          { label: "ADX",  value: tf.adx?.toFixed(0) ?? "—" },
          { label: "Vol",  value: tf.rel_volume ? `${tf.rel_volume.toFixed(1)}x` : "—" },
        ].map(({ label, value }) => (
          <div key={label} className="text-center">
            <div className="text-[8px] font-mono text-text-muted/50 uppercase">{label}</div>
            <div className="text-[11px] font-mono font-bold text-text">{value}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MultiTimeframeCard({ symbol }: { symbol: string }) {
  const { data, loading, error, refetch } = useConfluence(symbol, "1H,4H,1D");

  return (
    <div className="rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-4">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
          <span className="text-purple">12</span>
          <span>⏱</span>
          <span>MULTI-TIMEFRAME CONFLUENCE</span>
          {data?.any_strong_buy && (
            <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-teal/10 text-teal border border-teal/20">
              ALIGNED
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
              data.confluence_score >= 9
                ? "text-teal border-teal/30 bg-teal/8"
                : data.confluence_score >= 5
                ? "text-amber border-amber/30 bg-amber/8"
                : "text-text-muted border-border/40 bg-surface-2"
            }`}>
              avg {data.confluence_score}/{data.timeframes?.[0]?.max_score ?? 16}
            </span>
          )}
          <button
            onClick={refetch}
            className="text-[9px] font-mono text-text-muted/60 hover:text-text-muted px-2 py-1 rounded border border-border/40 hover:border-border/70 transition-all"
          >
            ↻
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        {loading ? (
          <div className="grid grid-cols-3 gap-3">
            {[0, 1, 2].map(i => (
              <div key={i} className="h-44 bg-surface-2 rounded-xl animate-pulse border border-border/30" />
            ))}
          </div>
        ) : error ? (
          <div className="text-center py-6 text-[11px] font-mono text-red/70">
            Failed to load confluence data
          </div>
        ) : data ? (
          <>
            {/* 3-column TF grid */}
            <div className="grid grid-cols-3 gap-3 mb-4">
              {data.timeframes.map(tf => (
                <TFCard key={tf.interval} tf={tf} />
              ))}
            </div>

            {/* Confluence verdict */}
            {data.all_bullish ? (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-teal/6 border border-teal/20">
                <span className="text-xl">🎯</span>
                <div>
                  <div className="text-[11px] font-mono font-bold text-teal">ALL TIMEFRAMES BULLISH</div>
                  <div className="text-[10px] font-mono text-text-muted/70 mt-0.5">
                    High-conviction setup — 1H, 4H & Daily all point LONG
                  </div>
                </div>
              </div>
            ) : data.any_strong_buy ? (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-amber/6 border border-amber/20">
                <span className="text-xl">⚡</span>
                <div>
                  <div className="text-[11px] font-mono font-bold text-amber">PARTIAL CONFLUENCE</div>
                  <div className="text-[10px] font-mono text-text-muted/70 mt-0.5">
                    At least one strong timeframe — trade with position sizing caution
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-surface-2 border border-border/40">
                <span className="text-xl">⏳</span>
                <div>
                  <div className="text-[11px] font-mono font-bold text-text-muted">NO CONFLUENCE YET</div>
                  <div className="text-[10px] font-mono text-text-muted/60 mt-0.5">
                    Wait for at least one STRONG BUY before entering
                  </div>
                </div>
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
