import { useState, useEffect, useCallback } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface Signal {
  symbol: string; score: number; max_score: number; signal: string;
  v: number; p: number; r: number; t: number; s: number;
  price: number;
  change: number;    // /scan returns 'change', not 'change_24h'
  change_24h?: number; // kept for type compat
  rsi: number; adx: number;
}
interface Props { onSelect: (symbol: string) => void; interval?: string; }

const btnStyle: React.CSSProperties = {
  fontSize: 9, color: "#64748b", background: "#0f172a",
  border: "1px solid #1e293b", borderRadius: 4,
  padding: "2px 5px", cursor: "pointer",
};

export function TopSignals({ onSelect, interval = "1h" }: Props) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastScan, setLastScan] = useState<string>("");
  const [minScore, setMinScore] = useState(5);

  const scan = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/scan?interval=${interval.toLowerCase()}&min_score=${minScore}`);
      const j = await r.json();
      setSignals((j.signals || []).filter((s: Signal) => s.signal === "STRONG BUY"));
      setLastScan(new Date().toLocaleTimeString());
    } catch { setSignals([]); }
    finally { setLoading(false); }
  }, [interval, minScore]);

  useEffect(() => { scan(); }, [scan]);
  useEffect(() => { const t = setInterval(scan, 5 * 60 * 1000); return () => clearInterval(t); }, [scan]);

  const nextScore = minScore === 5 ? 7 : minScore === 7 ? 9 : 5;
  const isEmpty = !loading && signals.length === 0 && !!lastScan;
  const duration = Math.max(signals.length * 4, 12);

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
        </div>
        <div style={{ display: "flex", gap: 5 }}>
          <button onClick={() => setMinScore(nextScore)} style={btnStyle}>{">="}{minScore}</button>
          <button onClick={scan} disabled={loading} style={{ ...btnStyle, color: loading ? "#334155" : "#7c3aed", cursor: loading ? "not-allowed" : "pointer" }}>
            {loading ? "..." : "Scan"}
          </button>
        </div>
      </div>

      {/* Timestamp */}
      {lastScan && (
        <div style={{ fontSize: 9, color: "#334155", marginBottom: 6 }}>{lastScan}</div>
      )}

      {/* Scrolling ticker */}
      {signals.length > 0 && (
        <div style={{ overflow: "hidden", position: "relative", borderRadius: 6, background: "#060b17", border: "1px solid #1e293b" }}>
          {/* fade edges */}
          <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: 24, background: "linear-gradient(to right, #060b17, transparent)", zIndex: 2, pointerEvents: "none" }} />
          <div style={{ position: "absolute", right: 0, top: 0, bottom: 0, width: 24, background: "linear-gradient(to left, #060b17, transparent)", zIndex: 2, pointerEvents: "none" }} />

          <div
            style={{
              display: "flex", gap: 8, padding: "8px 12px",
              width: "max-content",
              animation: `topsig-scroll ${duration}s linear infinite`,
            }}
          >
            {[...signals, ...signals].map((sig, i) => (
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

          <style>{`
            @keyframes topsig-scroll {
              0%   { transform: translateX(0); }
              100% { transform: translateX(-50%); }
            }
          `}</style>
        </div>
      )}

      {loading && signals.length === 0 && (
        <div style={{ padding: "12px 0", textAlign: "center" as const, fontSize: 10, color: "#475569" }}>Scanning...</div>
      )}
      {isEmpty && (
        <div style={{ padding: "10px 0", textAlign: "center" as const, fontSize: 10, color: "#475569" }}>No strong signals — try score {">=5"}</div>
      )}
    </div>
  );
}
