import { useState, useEffect, useCallback, useRef } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

// Score threshold for BUY vs WAIT (STRONG BUY = 9+/16)
const BUY_THRESHOLD = 9;

interface Signal {
  symbol: string; score: number; max_score: number; signal: string;
  v: number; p: number; r: number; t: number; s: number;
  price: number; change: number; change_24h?: number;
  rsi: number; adx: number; rel_vol?: number;
}

interface Props { onSelect: (symbol: string) => void; interval?: string; listMode?: boolean; } // listMode kept for compat

function scoreColor(score: number, max: number): string {
  if (score === 0) return "#4a5470";
  const r = score / max;
  return r >= 0.67 ? "#22c55e" : r >= 0.34 ? "#f59e0b" : "#ef4444";
}

function subScoreColor(val: number, max: number): string {
  const r = val / max;
  return r >= 0.67 ? "#22c55e" : r >= 0.34 ? "#f59e0b" : "#64748b";
}

const TH: React.CSSProperties = {
  fontSize: 8, fontWeight: 700, letterSpacing: "0.08em",
  color: "#334155", textTransform: "uppercase", padding: "6px 8px",
  textAlign: "left", whiteSpace: "nowrap",
};

export function TopSignals({ onSelect, interval = "1h" }: Props) {
  const [signals,    setSignals]    = useState<Signal[]>([]);
  const [loading,    setLoading]    = useState(false);
  const [lastScan,   setLastScan]   = useState<string>("");
  const [elapsed,    setElapsed]    = useState(0);
  const [universe,   setUniverse]   = useState(0);
  const [error,      setError]      = useState<string | null>(null);
  const [sortBy,     setSortBy]     = useState<"score"|"change"|"rsi">("score");

  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef   = useRef<AbortController | null>(null);

  const stopElapsed = () => {
    if (elapsedRef.current) { clearInterval(elapsedRef.current); elapsedRef.current = null; }
  };

  const scan = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    setElapsed(0);

    stopElapsed();
    const start = Date.now();
    elapsedRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);

    try {
      // Fetch ALL scored coins from Render /scan (min_score=1 = everything)
      // Render uses global Binance from Singapore, 1-hour SQLite cache
      const res = await fetch(
        `${API}/scan?min_score=1&interval=${interval}&max_coins=300`,
        { signal: ctrl.signal }
      );
      if (!res.ok) throw new Error(`/scan returned ${res.status}`);
      const data = await res.json();

      const all: Signal[] = (data.signals ?? []).map((s: Record<string, unknown>) => ({
        symbol:    String(s.symbol ?? ""),
        score:     Number(s.score ?? 0),
        max_score: Number(s.max_score ?? 16),
        signal:    String(s.signal ?? ""),
        v:         Number(s.v ?? 0),
        p:         Number(s.p ?? 0),
        r:         Number(s.r ?? 0),
        t:         Number(s.t ?? 0),
        s:         Number(s.s ?? 0),
        price:     Number(s.price ?? 0),
        change:    Number(s.change ?? 0),
        rsi:       Number(s.rsi ?? 0),
        adx:       Number(s.adx ?? 0),
        rel_vol:   Number(s.rel_vol ?? 0),
      }));

      if (!ctrl.signal.aborted) {
        setSignals(all);
        setUniverse(data.universe ?? all.length);
        setLastScan(new Date().toLocaleTimeString());
        setError(null);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (!ctrl.signal.aborted) {
        setError(msg.includes("abort") || msg.includes("AbortError") ? null : `Scan failed: ${msg}`);
      }
    } finally {
      stopElapsed();
      setLoading(false);
    }
  }, [interval]);

  useEffect(() => { scan(); }, [scan]);
  // Hourly auto-refresh — matches backend 1-hour scan cache TTL
  useEffect(() => {
    const t = setInterval(scan, 60 * 60 * 1000);
    return () => clearInterval(t);
  }, [scan]);
  useEffect(() => () => { stopElapsed(); abortRef.current?.abort(); }, []);

  // Sort
  const sorted = [...signals].sort((a, b) => {
    if (sortBy === "score")  return b.score - a.score;
    if (sortBy === "change") return (b.change ?? 0) - (a.change ?? 0);
    if (sortBy === "rsi")    return b.rsi - a.rsi;
    return 0;
  });

  const buyCount  = signals.filter(s => s.score >= BUY_THRESHOLD).length;
  const waitCount = signals.length - buyCount;

  const SortBtn = ({ col, label }: { col: "score"|"change"|"rsi"; label: string }) => (
    <button
      onClick={() => setSortBy(col)}
      style={{
        fontSize: 8, fontWeight: 700, letterSpacing: "0.08em",
        textTransform: "uppercase" as const, padding: "6px 8px",
        textAlign: "left" as const, whiteSpace: "nowrap" as const,
        background: "none", border: "none", cursor: "pointer",
        color: sortBy === col ? "#f1f5f9" : "#334155",
        borderBottom: sortBy === col ? "1px solid #7c3aed" : "1px solid transparent",
      }}
    >
      {label}{sortBy === col ? " ↓" : ""}
    </button>
  );

  return (
    <div style={{ marginBottom: 14 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" as const }}>
            Green Coins Today
          </span>
          {signals.length > 0 && (
            <>
              <span style={{ fontSize: 9, color: "#22c55e", background: "#0d2212", padding: "1px 6px", borderRadius: 3, border: "1px solid #14532d", fontWeight: 700 }}>
                {buyCount} BUY
              </span>
              <span style={{ fontSize: 9, color: "#f59e0b", background: "#1a1200", padding: "1px 6px", borderRadius: 3, border: "1px solid #451a00", fontWeight: 700 }}>
                {waitCount} WAIT
              </span>
            </>
          )}
        </div>
        <button
          onClick={scan}
          disabled={loading}
          style={{
            fontSize: 9, color: loading ? "#334155" : "#7c3aed",
            background: "#0f172a", border: "1px solid #1e293b",
            borderRadius: 4, padding: "2px 8px",
            cursor: loading ? "not-allowed" : "pointer", minWidth: 36,
          }}
        >
          {loading ? `${elapsed}s…` : "Scan"}
        </button>
      </div>

      {/* Status */}
      {lastScan && (
        <div style={{ fontSize: 9, color: "#334155", marginBottom: 6 }}>
          {lastScan} · {signals.length} green coins scored · {universe} total universe
          {signals.length > 0 && (
            <span style={{ color: "#475569" }}> · sorted by </span>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ padding: "10px 12px", borderRadius: 6, background: "#1a0a0a", border: "1px solid #7f1d1d", marginBottom: 8 }}>
          <div style={{ fontSize: 10, color: "#ef4444", fontWeight: 700, marginBottom: 4 }}>Scan Error</div>
          <div style={{ fontSize: 9, color: "#94a3b8" }}>{error}</div>
          <button onClick={scan} style={{ marginTop: 8, fontSize: 9, color: "#7c3aed", background: "none", border: "1px solid #7c3aed", borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>Retry</button>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && signals.length === 0 && (
        <div style={{ padding: "16px 0", textAlign: "center" as const }}>
          <div style={{ fontSize: 10, color: "#475569", marginBottom: 4 }}>
            Scoring green coins from {universe > 0 ? universe : "Binance"} universe…
          </div>
          <div style={{ fontSize: 9, color: "#334155" }}>Usually 5–15s on cold start, &lt;1s cached</div>
        </div>
      )}

      {/* Table */}
      {sorted.length > 0 && (
        <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b", opacity: loading ? 0.6 : 1, transition: "opacity 0.3s" }}>
          {/* Column headers */}
          <div style={{ display: "grid", gridTemplateColumns: "28px 80px 54px 56px 34px 34px 34px 34px 36px 48px", background: "#0a0f1e", borderBottom: "1px solid #1e293b" }}>
            <span style={TH}>#</span>
            <span style={TH}>Symbol</span>
            <SortBtn col="change" label="Chg%" />
            <SortBtn col="score" label="Score" />
            <span style={TH}>V</span>
            <span style={TH}>P</span>
            <span style={TH}>R</span>
            <span style={TH}>T</span>
            <SortBtn col="rsi" label="RSI" />
            <span style={{ ...TH, textAlign: "center" as const }}>Action</span>
          </div>

          {/* Rows */}
          {sorted.map((sig, i) => {
            const chg     = sig.change ?? 0;
            const isBuy   = sig.score >= BUY_THRESHOLD;
            const rowBg   = i % 2 === 0 ? "#060b17" : "#080e1c";

            return (
              <button
                key={sig.symbol}
                onClick={() => onSelect(sig.symbol)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "28px 80px 54px 56px 34px 34px 34px 34px 36px 48px",
                  width: "100%", background: rowBg,
                  border: "none", borderBottom: "1px solid #0f172a",
                  cursor: "pointer", textAlign: "left" as const,
                  alignItems: "center", transition: "background 0.12s",
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#0d1a2e"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = rowBg; }}
              >
                {/* # */}
                <span style={{ fontSize: 9, color: "#2d3a50", fontWeight: 700, textAlign: "center" as const, padding: "9px 0" }}>
                  {i + 1}
                </span>

                {/* Symbol */}
                <div style={{ display: "flex", flexDirection: "column" as const, gap: 1, padding: "9px 0 9px 4px" }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#f1f5f9", fontFamily: "monospace", letterSpacing: "0.04em" }}>
                    {sig.symbol}
                  </span>
                  <span style={{ fontSize: 8, color: "#334155" }}>
                    ${sig.price < 0.01 ? sig.price.toFixed(6) : sig.price < 1 ? sig.price.toFixed(4) : sig.price.toFixed(2)}
                  </span>
                </div>

                {/* Chg% */}
                <span style={{ fontSize: 11, fontWeight: 700, color: "#22c55e", fontFamily: "monospace", padding: "0 4px" }}>
                  +{chg.toFixed(1)}%
                </span>

                {/* Score */}
                <span style={{ fontSize: 11, fontWeight: 800, color: scoreColor(sig.score, sig.max_score ?? 16), fontFamily: "monospace", padding: "0 4px" }}>
                  {sig.score}/{sig.max_score ?? 16}
                </span>

                {/* V P R T sub-scores */}
                <span style={{ fontSize: 10, fontWeight: 700, color: subScoreColor(sig.v, 5), fontFamily: "monospace", padding: "0 2px" }}>{sig.v}</span>
                <span style={{ fontSize: 10, fontWeight: 700, color: subScoreColor(sig.p, 3), fontFamily: "monospace", padding: "0 2px" }}>{sig.p}</span>
                <span style={{ fontSize: 10, fontWeight: 700, color: subScoreColor(sig.r, 2), fontFamily: "monospace", padding: "0 2px" }}>{sig.r}</span>
                <span style={{ fontSize: 10, fontWeight: 700, color: subScoreColor(sig.t, 3), fontFamily: "monospace", padding: "0 2px" }}>{sig.t}</span>

                {/* RSI */}
                <span style={{ fontSize: 10, fontWeight: 600, color: sig.rsi > 70 ? "#ef4444" : sig.rsi < 30 ? "#22c55e" : "#94a3b8", fontFamily: "monospace", padding: "0 2px" }}>
                  {sig.rsi.toFixed(0)}
                </span>

                {/* BUY / WAIT badge */}
                <div style={{ textAlign: "center" as const, padding: "0 4px" }}>
                  {isBuy ? (
                    <span style={{
                      fontSize: 8, fontWeight: 800, letterSpacing: "0.06em",
                      color: "#22c55e", background: "#0d2212",
                      padding: "2px 6px", borderRadius: 3,
                      border: "1px solid #14532d",
                    }}>BUY</span>
                  ) : (
                    <span style={{
                      fontSize: 8, fontWeight: 800, letterSpacing: "0.06em",
                      color: "#f59e0b", background: "#1a1200",
                      padding: "2px 5px", borderRadius: 3,
                      border: "1px solid #451a00",
                    }}>WAIT</span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}

      <style>{`
        @keyframes topsig-pulse {
          0%, 100% { opacity: 1; } 50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}
