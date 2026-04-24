import { useState, useEffect, useCallback } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface Signal {
  symbol: string;
  score: number;
  max_score: number;
  signal: string;
  v: number; p: number; r: number; t: number; s: number;
  price: number;
  change_24h: number;
  rsi: number;
  adx: number;
}

interface Props {
  onSelect: (symbol: string) => void;
  interval?: string;
}

function ScoreBar({ score, max }: { score: number; max: number }) {
  const pct = Math.round((score / max) * 100);
  const color = score >= 9 ? "#22c55e" : score >= 7 ? "#f59e0b" : "#6b7280";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ flex: 1, height: 4, background: "#1e293b", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ width: pct + "%", height: "100%", background: color, borderRadius: 2, transition: "width 0.4s" }} />
      </div>
      <span style={{ fontSize: 11, color, fontWeight: 700, minWidth: 28 }}>{score}/{max}</span>
    </div>
  );
}

export function TopSignals({ onSelect, interval = "1h" }: Props) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastScan, setLastScan] = useState<string>("");
  const [minScore, setMinScore] = useState(7);

  const scan = useCallback(async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/scan?interval=${interval}&min_score=${minScore}`);
      const j = await r.json();
      setSignals(j.signals || []);
      setLastScan(new Date().toLocaleTimeString());
    } catch {
      setSignals([]);
    } finally {
      setLoading(false);
    }
  }, [interval, minScore]);

  // Auto-scan on mount
  useEffect(() => { scan(); }, [scan]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const t = setInterval(scan, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [scan]);

  return (
    <div style={{ marginBottom: 16 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ color: "#f59e0b", fontSize: 14 }}>⚡</span>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" }}>
            Top Signals
          </span>
          <span style={{ fontSize: 10, color: "#475569", background: "#0f172a", padding: "1px 6px", borderRadius: 4, border: "1px solid #1e293b" }}>
            score >= {minScore}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {/* Min score toggle */}
          <button
            onClick={() => setMinScore(s => s === 7 ? 8 : s === 8 ? 9 : 7)}
            style={{ fontSize: 10, color: "#64748b", background: "#0f172a", border: "1px solid #1e293b", borderRadius: 4, padding: "2px 6px", cursor: "pointer" }}
          >
            >={minScore}
          </button>
          {/* Refresh */}
          <button
            onClick={scan}
            disabled={loading}
            style={{ fontSize: 10, color: loading ? "#334155" : "#7c3aed", background: "#0f172a", border: "1px solid #1e293b", borderRadius: 4, padding: "2px 6px", cursor: loading ? "not-allowed" : "pointer" }}
          >
            {loading ? "..." : "↻"}
          </button>
        </div>
      </div>

      {/* Last scan time */}
      {lastScan && (
        <div style={{ fontSize: 10, color: "#334155", marginBottom: 8 }}>
          Scanned top 50 coins · {lastScan}
        </div>
      )}

      {/* Loading state */}
      {loading && signals.length === 0 && (
        <div style={{ padding: "20px 0", textAlign: "center" }}>
          <div style={{ fontSize: 11, color: "#475569" }}>Scanning top 50 coins...</div>
          <div style={{ fontSize: 10, color: "#334155", marginTop: 4 }}>Takes ~20s on first run</div>
        </div>
      )}

      {/* Empty state */}
      {!loading && signals.length === 0 && lastScan && (
        <div style={{ padding: "16px 0", textAlign: "center" }}>
          <div style={{ fontSize: 11, color: "#475569" }}>No coins scoring >= {minScore}</div>
          <div style={{ fontSize: 10, color: "#334155", marginTop: 4 }}>Market may be ranging</div>
        </div>
      )}

      {/* Signal rows */}
      {signals.map((sig) => (
        <button
          key={sig.symbol}
          onClick={() => onSelect(sig.symbol)}
          style={{
            width: "100%", display: "block", background: "transparent",
            border: "1px solid #1e293b", borderRadius: 8, padding: "10px 12px",
            marginBottom: 6, cursor: "pointer", textAlign: "left",
            transition: "border-color 0.2s",
          }}
          onMouseEnter={e => (e.currentTarget.style.borderColor = "#7c3aed")}
          onMouseLeave={e => (e.currentTarget.style.borderColor = "#1e293b")}
        >
          {/* Top row: symbol + signal badge + change */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", fontFamily: "monospace" }}>
                {sig.symbol}
              </span>
              <span style={{
                fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                background: sig.signal === "STRONG BUY" ? "#14532d" : sig.signal === "MODERATE BUY" ? "#713f12" : "#1e293b",
                color: sig.signal === "STRONG BUY" ? "#22c55e" : sig.signal === "MODERATE BUY" ? "#f59e0b" : "#64748b",
                letterSpacing: "0.05em"
              }}>
                {sig.signal.replace(" BUY", "")}
              </span>
            </div>
            <span style={{ fontSize: 11, color: sig.change_24h >= 0 ? "#22c55e" : "#ef4444", fontWeight: 600 }}>
              {sig.change_24h >= 0 ? "+" : ""}{sig.change_24h.toFixed(1)}%
            </span>
          </div>

          {/* Score bar */}
          <ScoreBar score={sig.score} max={sig.max_score} />

          {/* Bottom row: V/P/R/T/S breakdown */}
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            {[["V", sig.v, 5], ["P", sig.p, 3], ["R", sig.r, 2], ["T", sig.t, 3], ["S", sig.s, 3]].map(([k, v, m]) => (
              <div key={k as string} style={{ flex: 1, textAlign: "center" }}>
                <div style={{ fontSize: 9, color: "#475569", marginBottom: 2 }}>{k}</div>
                <div style={{ fontSize: 11, color: (v as number) > 0 ? "#a78bfa" : "#334155", fontWeight: 600 }}>
                  {v}/{m}
                </div>
              </div>
            ))}
          </div>
        </button>
      ))}
    </div>
  );
}
