import { useState, useEffect, useCallback, useRef } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface Signal {
  symbol: string; score: number; max_score: number; signal: string;
  v: number; p: number; r: number; t: number; s: number;
  price: number;
  change: number;
  change_24h?: number;
  rsi: number; adx: number;
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

const SCAN_TIMEOUT_MS = 90_000; // 90 seconds

export function TopSignals({ onSelect, interval = "1h", listMode = false }: Props) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastScan, setLastScan] = useState<string>("");
  const [elapsed, setElapsed] = useState(0);          // seconds since scan started
  const [error, setError] = useState<string | null>(null);
  const [universe, setUniverse] = useState<number>(0);
  const minScore = 7; // fixed — always show from 7 upwards, user filters in UI

  const [filterScore, setFilterScore] = useState(9);  // UI filter (doesn't re-fetch)
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const abortRef   = useRef<AbortController | null>(null);

  const stopElapsed = () => {
    if (elapsedRef.current) { clearInterval(elapsedRef.current); elapsedRef.current = null; }
  };

  const scan = useCallback(async () => {
    // Cancel any in-flight request
    if (abortRef.current) abortRef.current.abort();
    abortRef.current = new AbortController();

    setLoading(true);
    setError(null);
    setElapsed(0);

    // Tick elapsed every second
    stopElapsed();
    const start = Date.now();
    elapsedRef.current = setInterval(() => {
      setElapsed(Math.floor((Date.now() - start) / 1000));
    }, 1000);

    // Timeout after 90s
    const timeout = setTimeout(() => {
      abortRef.current?.abort();
    }, SCAN_TIMEOUT_MS);

    try {
      const r = await fetch(
        `${API}/scan?interval=${interval.toLowerCase()}&min_score=${minScore}&max_coins=500`,
        { signal: abortRef.current.signal }
      );
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const j = await r.json();
      setSignals(j.signals || []);
      setUniverse(j.universe || 0);
      setLastScan(new Date().toLocaleTimeString());
      setError(null);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("abort") || msg.includes("AbortError")) {
        setError("Scan timed out — Render may be waking up. Try again in 30s.");
      } else {
        setError("Scan failed — check API status.");
      }
    } finally {
      clearTimeout(timeout);
      stopElapsed();
      setLoading(false);
    }
  }, [interval]);

  // Initial scan + auto-refresh every 5 min
  useEffect(() => { scan(); }, [scan]);
  useEffect(() => {
    const t = setInterval(scan, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [scan]);

  // Cleanup on unmount
  useEffect(() => () => { stopElapsed(); abortRef.current?.abort(); }, []);

  // Progress status message
  const progressMsg = (() => {
    if (!loading) return null;
    if (elapsed < 5)  return "Waking Render...";
    if (elapsed < 15) return "Fetching Binance universe...";
    if (elapsed < 30) return `Scoring coins... (${elapsed}s)`;
    return `Still scanning — ${elapsed}s elapsed. Render is warming up.`;
  })();

  // Filtered view (client-side) — no extra fetch
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
          {universe > 0 && !loading && (
            <span style={{ fontSize: 8, color: "#334155", marginLeft: 2 }}>{universe} coins</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 5, alignItems: "center" }}>
          {/* Score filter — client side, no refetch */}
          <button
            onClick={() => setFilterScore(nextFilter)}
            style={btnStyle}
            title="Filter score threshold (client-side)"
          >
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

      {/* Timestamp row */}
      {(lastScan || loading) && (
        <div style={{ fontSize: 9, color: "#334155", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
          {lastScan && !loading && <span>Last scan: {lastScan}</span>}
          {loading && (
            <span style={{ color: "#475569", display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{
                display: "inline-block", width: 6, height: 6, borderRadius: "50%",
                background: "#7c3aed",
                animation: "topsig-pulse 1s ease-in-out infinite",
              }} />
              {progressMsg}
            </span>
          )}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div style={{
          padding: "10px 12px", borderRadius: 6, background: "#1a0a0a",
          border: "1px solid #7f1d1d", marginBottom: 8,
        }}>
          <div style={{ fontSize: 10, color: "#ef4444", fontWeight: 700, marginBottom: 4 }}>Scan Error</div>
          <div style={{ fontSize: 9, color: "#94a3b8", lineHeight: 1.5 }}>{error}</div>
          <button
            onClick={scan}
            style={{ marginTop: 8, fontSize: 9, color: "#7c3aed", background: "none", border: "1px solid #7c3aed", borderRadius: 4, padding: "2px 8px", cursor: "pointer" }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Empty filter message */}
      {isEmpty && (
        <div style={{ padding: "6px 0", fontSize: 9, color: "#475569" }}>
          No signals at &gt;={filterScore} — {signals.length} results at &gt;={minScore}. Lower the filter.
        </div>
      )}

      {/* No results */}
      {noResults && !error && (
        <div style={{ padding: "10px 0", textAlign: "center" as const, fontSize: 10, color: "#475569" }}>
          No strong signals found across {universe > 0 ? universe : "200+"} coins.
        </div>
      )}

      {/* LIST MODE — ranked rows for mobile signals tab */}
      {listMode && displaySigs.length > 0 && (
        <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b", opacity: loading ? 0.6 : 1, transition: "opacity 0.3s" }}>
          {/* Column headers */}
          <div style={{
            display: "grid",
            gridTemplateColumns: "28px 1fr 52px 44px 44px 44px 44px 44px",
            gap: 2, padding: "5px 8px",
            background: "#0a0f1e", borderBottom: "1px solid #1e293b",
          }}>
            {["#", "SYM", "SCORE", "V", "P", "R", "T", "S"].map(h => (
              <span key={h} style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.08em", color: "#334155", textTransform: "uppercase" as const, textAlign: h === "#" ? "center" as const : "left" as const }}>{h}</span>
            ))}
          </div>

          {displaySigs.map((sig, i) => {
            const chg = sig.change ?? sig.change_24h ?? 0;
            const chgColor = chg >= 0 ? "#22c55e" : "#ef4444";
            const overallColor = scoreColor(sig.score, sig.max_score ?? 16);
            const vColor = scoreColor(sig.v, 5);
            const pColor = scoreColor(sig.p, 3);
            const rColor = scoreColor(sig.r, 2);
            const tColor = scoreColor(sig.t, 3);
            const sColor = scoreColor(sig.s ?? 0, 3);
            return (
              <button
                key={sig.symbol}
                onClick={() => onSelect(sig.symbol)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "28px 1fr 52px 44px 44px 44px 44px 44px",
                  gap: 2, padding: "8px 8px",
                  width: "100%",
                  background: i % 2 === 0 ? "#060b17" : "#080e1c",
                  border: "none", borderBottom: "1px solid #0f172a",
                  cursor: "pointer", textAlign: "left" as const,
                  alignItems: "center", transition: "background 0.15s",
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
                <span style={{ fontSize: 11, fontWeight: 800, color: overallColor, fontFamily: "monospace" }}>
                  {sig.score}/{sig.max_score ?? 16}
                </span>
                {[
                  { val: sig.v, max: 5, color: vColor },
                  { val: sig.p, max: 3, color: pColor },
                  { val: sig.r, max: 2, color: rColor },
                  { val: sig.t, max: 3, color: tColor },
                  { val: sig.s ?? 0, max: 3, color: sColor },
                ].map(({ val, max, color }, ci) => (
                  <span key={ci} style={{ fontSize: 10, fontWeight: 700, color, fontFamily: "monospace" }}>
                    {val}/{max}
                  </span>
                ))}
              </button>
            );
          })}
        </div>
      )}

      {/* Scrolling ticker — desktop / non-listMode */}
      {!listMode && displaySigs.length > 0 && (
        <div style={{ overflow: "hidden", position: "relative", borderRadius: 6, background: "#060b17", border: "1px solid #1e293b", opacity: loading ? 0.7 : 1, transition: "opacity 0.3s" }}>
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 24, background: "linear-gradient(to right, #060b17, transparent)", zIndex: 2, pointerEvents: "none" }} />
          <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: 24, background: "linear-gradient(to left, #060b17, transparent)", zIndex: 2, pointerEvents: "none" }} />
          <div
            style={{
              display: "flex", gap: 8, padding: "8px 12px",
              width: "max-content",
              animation: `topsig-scroll ${duration}s linear infinite`,
            }}
          >
            {[...displaySigs, ...displaySigs].map((sig, i) => (
              <button
                key={`${sig.symbol}-${i}`}
                onClick={() => onSelect(sig.symbol)}
                style={{
                  display: "inline-flex", alignItems: "center", gap: 6,
                  background: "transparent", border: "1px solid #1e293b",
                  borderRadius: 20, padding: "4px 12px", cursor: "pointer",
                  whiteSpace: "nowrap" as const, flexShrink: 0,
                  transition: "border-color 0.2s, background 0.2s",
                }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "#22c55e"; e.currentTarget.style.background = "#0d2212"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = "#1e293b"; e.currentTarget.style.background = "transparent"; }}
              >
                <span style={{ fontSize: 11, fontWeight: 700, color: "#f1f5f9", fontFamily: "monospace" }}>{sig.symbol}</span>
                <span style={{ fontSize: 10, fontWeight: 700, color: "#22c55e" }}>{sig.score}/{sig.max_score}</span>
                <span style={{ fontSize: 10, color: (sig.change ?? sig.change_24h ?? 0) >= 0 ? "#22c55e" : "#ef4444" }}>
                  {(sig.change ?? sig.change_24h ?? 0) >= 0 ? "+" : ""}{(sig.change ?? sig.change_24h ?? 0).toFixed(1)}%
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Initial loading state — only when no cached results yet */}
      {loading && signals.length === 0 && !error && (
        <div style={{ padding: "16px 0", textAlign: "center" as const }}>
          <div style={{ fontSize: 10, color: "#475569", marginBottom: 6 }}>{progressMsg}</div>
          {elapsed >= 5 && (
            <div style={{ fontSize: 9, color: "#334155" }}>
              Scanning ~500 Binance pairs — this takes 20-40s cold start.
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
