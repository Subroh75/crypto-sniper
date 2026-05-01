import { useState, useEffect, useCallback, useRef } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface Signal {
  symbol: string; score: number; max_score: number; signal: string;
  v: number; p: number; r: number; t: number; s: number;
  price: number; change: number; change_24h?: number;
  rsi: number; adx: number; rel_vol?: number;
}

interface Props { onSelect: (symbol: string) => void; interval?: string; listMode?: boolean; }

const btnStyle: React.CSSProperties = {
  fontSize: 9, color: "#64748b", background: "#0f172a",
  border: "1px solid #1e293b", borderRadius: 4,
  padding: "2px 5px", cursor: "pointer",
};

function scoreColor(score: number, max: number): string {
  if (score === 0) return "#4a5470";
  const r = score / max;
  return r >= 0.67 ? "#22c55e" : r >= 0.34 ? "#f59e0b" : "#ef4444";
}

// How many results to show from /scan
const TOP_N             = 30;

export function TopSignals({ onSelect, interval = "1h", listMode = false }: Props) {
  const [signals,     setSignals]     = useState<Signal[]>([]);
  const [loading,     setLoading]     = useState(false);
  const [lastScan,    setLastScan]    = useState<string>("");
  const [elapsed,     setElapsed]     = useState(0);
  const [phase,       setPhase]       = useState<"idle"|"fetching"|"scoring"|"done">("idle");
  const [scored,      setScored]      = useState(0);   // how many deep-scored so far
  const [candidates,  setCandidates]  = useState(0);   // total going to deep-score
  const [universe,    setUniverse]    = useState(0);   // total green coins found
  const [error,       setError]       = useState<string | null>(null);
  const [filterScore, setFilterScore] = useState(9);

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
    setScored(0);
    setCandidates(0);
    setPhase("fetching");

    stopElapsed();
    const start = Date.now();
    elapsedRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);

    try {
      // ── Fetch scored signals from Render /scan (uses global Binance, 1h cache) ──
      // BinanceUS is too low volume to be useful — Render's /scan runs from Singapore
      // where global api.binance.com works fine. Results cached 1hr in SQLite.
      setPhase("scoring");
      const scanRes = await fetch(
        `${API}/scan?min_score=1&interval=${interval}&max_coins=300`,
        { signal: ctrl.signal, }
      );
      if (!scanRes.ok) throw new Error(`/scan ${scanRes.status}`);
      const scanData = await scanRes.json();

      const allSignals: Signal[] = (scanData.signals ?? []).map((s: Record<string, unknown>) => ({
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

      const top = allSignals.slice(0, TOP_N);

      if (!ctrl.signal.aborted) {
        setSignals(top);
        setUniverse(scanData.universe ?? allSignals.length);
        setCandidates(allSignals.length);
        setScored(allSignals.length);
        setLastScan(new Date().toLocaleTimeString());
        setPhase("done");
        setError(null);
      }

    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (!ctrl.signal.aborted) {
        setError(msg.includes("abort") || msg.includes("AbortError")
          ? "Scan cancelled."
          : `Scan failed: ${msg}`);
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

  // Progress message
  const progressMsg = (() => {
    if (phase === "fetching") return "Fetching Binance tickers...";
    if (phase === "scoring")  return `Deep-scoring ${scored}/${candidates} candidates... (${elapsed}s)`;
    return null;
  })();

  const nextFilter  = filterScore === 7 ? 9 : filterScore === 9 ? 11 : 7;
  const filtered    = signals.filter(s => s.score >= filterScore);
  const displaySigs = listMode ? filtered.slice(0, 25) : filtered;
  const isEmpty     = !loading && !error && signals.length > 0 && filtered.length === 0;
  const noResults   = !loading && !error && signals.length === 0 && !!lastScan;
  const duration    = Math.max(filtered.length * 4, 12);

  return (
    <div style={{ marginBottom: 14 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "#f59e0b", fontSize: 13 }}>{"!"}</span>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" as const }}>
            Top Signals
          </span>
          <span style={{ fontSize: 9, color: "#22c55e", background: "#0d2212", padding: "1px 5px", borderRadius: 3, border: "1px solid #14532d", fontWeight: 700 }}>
            STRONG
          </span>
          {universe > 0 && (
            <span style={{ fontSize: 8, color: "#334155", marginLeft: 2 }}>
              {universe} green
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
          <button onClick={() => setFilterScore(nextFilter)} style={btnStyle} title="Filter threshold">
            {">="}{filterScore}
          </button>
          <button
            onClick={scan}
            disabled={loading}
            style={{
              ...btnStyle,
              color: loading ? "#334155" : "#7c3aed",
              cursor: loading ? "not-allowed" : "pointer",
              minWidth: 36,
            }}
          >
            {loading ? `${elapsed}s` : "Scan"}
          </button>
        </div>
      </div>

      {/* Status row */}
      {(lastScan || loading) && (
        <div style={{ fontSize: 9, color: "#334155", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
          {lastScan && !loading && (
            <span>Last scan: {lastScan} · {universe} green coins · top {candidates} deep-scored</span>
          )}
          {loading && progressMsg && (
            <span style={{ color: "#475569", display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{
                display: "inline-block", width: 6, height: 6, borderRadius: "50%",
                background: "#7c3aed", animation: "topsig-pulse 1s ease-in-out infinite",
              }} />
              {progressMsg}
            </span>
          )}
        </div>
      )}

      {/* Progress bar during deep-scoring */}
      {loading && phase === "scoring" && candidates > 0 && (
        <div style={{ height: 2, background: "#1e293b", borderRadius: 1, marginBottom: 8, overflow: "hidden" }}>
          <div style={{
            height: "100%", background: "#7c3aed", borderRadius: 1,
            width: `${Math.round((scored / candidates) * 100)}%`,
            transition: "width 0.3s ease",
          }} />
        </div>
      )}

      {/* Error */}
      {error && (
        <div style={{ padding: "10px 12px", borderRadius: 6, background: "#1a0a0a", border: "1px solid #7f1d1d", marginBottom: 8 }}>
          <div style={{ fontSize: 10, color: "#ef4444", fontWeight: 700, marginBottom: 4 }}>Scan Error</div>
          <div style={{ fontSize: 9, color: "#94a3b8", lineHeight: 1.5 }}>{error}</div>
          <button onClick={scan} style={{ marginTop: 8, fontSize: 9, color: "#7c3aed", background: "none", border: "1px solid #7c3aed", borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}>
            Retry
          </button>
        </div>
      )}

      {isEmpty && (
        <div style={{ padding: "6px 0", fontSize: 9, color: "#475569" }}>
          No signals at &gt;={filterScore} — {signals.length} results at lower threshold. Try &gt;=7.
        </div>
      )}
      {noResults && !error && (
        <div style={{ padding: "10px 0", textAlign: "center" as const, fontSize: 10, color: "#475569" }}>
          No strong signals in {universe} green coins today.
        </div>
      )}

      {/* LIST MODE */}
      {listMode && displaySigs.length > 0 && (
        <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b", opacity: loading ? 0.6 : 1, transition: "opacity 0.3s" }}>
          <div style={{
            display: "grid", gridTemplateColumns: "28px 1fr 52px 44px 44px 44px 44px 44px",
            gap: 2, padding: "5px 8px", background: "#0a0f1e", borderBottom: "1px solid #1e293b",
          }}>
            {["#","SYM","SCORE","V","P","R","T","S"].map(h => (
              <span key={h} style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.08em", color: "#334155", textTransform: "uppercase" as const, textAlign: h === "#" ? "center" as const : "left" as const }}>{h}</span>
            ))}
          </div>
          {displaySigs.map((sig, i) => {
            const chg = sig.change ?? sig.change_24h ?? 0;
            const chgColor = chg >= 0 ? "#22c55e" : "#ef4444";
            return (
              <button
                key={sig.symbol}
                onClick={() => onSelect(sig.symbol)}
                style={{
                  display: "grid", gridTemplateColumns: "28px 1fr 52px 44px 44px 44px 44px 44px",
                  gap: 2, padding: "8px 8px", width: "100%",
                  background: i % 2 === 0 ? "#060b17" : "#080e1c",
                  border: "none", borderBottom: "1px solid #0f172a",
                  cursor: "pointer", textAlign: "left" as const, alignItems: "center", transition: "background 0.15s",
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#0d1a2e"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = i % 2 === 0 ? "#060b17" : "#080e1c"; }}
              >
                <span style={{ fontSize: 9, color: "#475569", fontWeight: 700, textAlign: "center" as const }}>{i + 1}</span>
                <div style={{ display: "flex", flexDirection: "column" as const, gap: 1, overflow: "hidden" }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#f1f5f9", fontFamily: "monospace", letterSpacing: "0.04em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" as const }}>
                    {sig.symbol}
                  </span>
                  <span style={{ fontSize: 9, color: chgColor, fontWeight: 600 }}>
                    {chg >= 0 ? "+" : ""}{chg.toFixed(1)}%
                  </span>
                </div>
                <span style={{ fontSize: 11, fontWeight: 800, color: scoreColor(sig.score, sig.max_score ?? 16), fontFamily: "monospace" }}>
                  {sig.score}/{sig.max_score ?? 16}
                </span>
                {[
                  { val: sig.v, max: 5 }, { val: sig.p, max: 3 },
                  { val: sig.r, max: 2 }, { val: sig.t, max: 3 }, { val: sig.s ?? 0, max: 3 },
                ].map(({ val, max }, ci) => (
                  <span key={ci} style={{ fontSize: 10, fontWeight: 700, color: scoreColor(val, max), fontFamily: "monospace" }}>
                    {val}/{max}
                  </span>
                ))}
              </button>
            );
          })}
        </div>
      )}

      {/* Scrolling ticker — desktop */}
      {!listMode && displaySigs.length > 0 && (
        <div style={{ overflow: "hidden", position: "relative", borderRadius: 6, background: "#060b17", border: "1px solid #1e293b", opacity: loading ? 0.7 : 1, transition: "opacity 0.3s" }}>
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 24, background: "linear-gradient(to right, #060b17, transparent)", zIndex: 2, pointerEvents: "none" }} />
          <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: 24, background: "linear-gradient(to left, #060b17, transparent)", zIndex: 2, pointerEvents: "none" }} />
          <div style={{ display: "flex", gap: 8, padding: "8px 12px", width: "max-content", animation: `topsig-scroll ${duration}s linear infinite` }}>
            {[...displaySigs, ...displaySigs].map((sig, i) => (
              <button
                key={`${sig.symbol}-${i}`}
                onClick={() => onSelect(sig.symbol)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  background: "transparent", border: "1px solid #1e293b",
                  borderRadius: 20, padding: "4px 12px", cursor: "pointer",
                  whiteSpace: "nowrap" as const, flexShrink: 0, transition: "border-color 0.2s, background 0.2s",
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "#22c55e"; e.currentTarget.style.background = "#0d2212"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = "#1e293b"; e.currentTarget.style.background = "transparent"; }}
              >
                <span style={{ fontSize: 11, fontWeight: 700, color: "#f1f5f9", fontFamily: "monospace" }}>{sig.symbol}</span>
                <span style={{ fontSize: 10, fontWeight: 700, color: "#22c55e" }}>{sig.score}/{sig.max_score}</span>
                <span style={{ fontSize: 10, color: (sig.change ?? 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                  {(sig.change ?? 0) >= 0 ? "+" : ""}{(sig.change ?? 0).toFixed(1)}%
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Initial loading — no results yet */}
      {loading && signals.length === 0 && !error && (
        <div style={{ padding: "16px 0", textAlign: "center" as const }}>
          <div style={{ fontSize: 10, color: "#475569", marginBottom: 4 }}>{progressMsg}</div>
          {phase === "scoring" && (
            <div style={{ fontSize: 9, color: "#334155" }}>
              Scoring top {candidates} green coins from {universe} — usually 5-10s.
            </div>
          )}
        </div>
      )}

      <style>{`
        @keyframes topsig-scroll {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        @keyframes topsig-pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50%       { opacity: 0.4; transform: scale(0.7); }
        }
      `}</style>
    </div>
  );
}
