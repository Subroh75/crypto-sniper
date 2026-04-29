// SignalStreakHeatmap.tsx
// Calendar heatmap: which coins had repeated strong signals over the last 30 days.
// Colours: grey = no signal, amber = 7-8, green = 9-11, bright green = 12+

import { useState, useEffect } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface StreakData {
  dates:    string[];       // ISO date strings, oldest → newest
  symbols:  Record<string, (number | null)[]>;
  min_score: number;
  days:     number;
}

function scoreColor(score: number | null): string {
  if (score == null) return "#0f172a";
  if (score >= 12)   return "#22c55e";
  if (score >= 9)    return "#16a34a";
  if (score >= 7)    return "#f59e0b";
  return "#0f172a";
}

function scoreBorder(score: number | null): string {
  if (score == null) return "#1e293b";
  if (score >= 12)   return "#22c55e55";
  if (score >= 9)    return "#16a34a55";
  if (score >= 7)    return "#f59e0b55";
  return "#1e293b";
}

function fmtDate(iso: string): string {
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
}

// Show only every Nth date label to avoid crowding
function labelEvery(dates: string[], n: number): (string | null)[] {
  return dates.map((d, i) => (i % n === 0 ? d : null));
}

export function SignalStreakHeatmap() {
  const [data, setData]       = useState<StreakData | null>(null);
  const [loading, setLoading] = useState(false);
  const [minScore, setMinScore] = useState(7);
  const [days, setDays]       = useState(30);
  const [tooltip, setTooltip] = useState<{ sym: string; date: string; score: number } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const r = await fetch(`${API}/streak?days=${days}&min_score=${minScore}`);
      const j = await r.json();
      setData(j);
    } catch { setData(null); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, [minScore, days]);

  const symbols = data ? Object.keys(data.symbols) : [];
  const dates   = data?.dates ?? [];
  // Show every 5th label on mobile-friendly 30-day view
  const labelEveryN = dates.length > 20 ? 5 : 3;
  const labelDates  = labelEvery(dates, labelEveryN);

  const btnStyle = {
    fontSize: 9, color: "#64748b", background: "#0f172a",
    border: "1px solid #1e293b", borderRadius: 4,
    padding: "2px 6px", cursor: "pointer",
  } as const;

  const activeBtnStyle = {
    ...btnStyle, color: "#f1f5f9", borderColor: "#7c3aed", background: "#1e0a3c",
  };

  return (
    <div style={{ marginBottom: 14 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ color: "#f59e0b", fontSize: 13 }}>{"▦"}</span>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" as const }}>
            Signal Streak
          </span>
          <span style={{ fontSize: 9, color: "#7c3aed", background: "#1e0a3c", padding: "1px 5px", borderRadius: 3, border: "1px solid #4c1d95", fontWeight: 700 }}>
            30D
          </span>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {([7, 9, 11] as const).map(s => (
            <button key={s} onClick={() => setMinScore(s)} style={minScore === s ? activeBtnStyle : btnStyle}>
              {">="}{s}
            </button>
          ))}
          <button onClick={load} disabled={loading} style={{ ...btnStyle, color: loading ? "#334155" : "#7c3aed", cursor: loading ? "not-allowed" : "pointer" }}>
            {loading ? "…" : "↻"}
          </button>
        </div>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8, flexWrap: "wrap" as const }}>
        {[
          { color: "#0f172a", border: "#1e293b", label: "No signal" },
          { color: "#f59e0b", border: "#f59e0b55", label: "7–8" },
          { color: "#16a34a", border: "#16a34a55", label: "9–11" },
          { color: "#22c55e", border: "#22c55e55", label: "12+" },
        ].map(l => (
          <div key={l.label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <div style={{ width: 10, height: 10, borderRadius: 2, background: l.color, border: `1px solid ${l.border}` }} />
            <span style={{ fontSize: 9, color: "#475569" }}>{l.label}</span>
          </div>
        ))}
      </div>

      {/* Empty / loading states */}
      {loading && !data && (
        <div style={{ padding: "20px 0", textAlign: "center" as const, fontSize: 10, color: "#475569" }}>
          Loading streak data…
        </div>
      )}
      {!loading && data && symbols.length === 0 && (
        <div style={{ padding: "16px 0", textAlign: "center" as const, fontSize: 10, color: "#475569" }}>
          No streak data yet — signals accumulate over time as you use the scanner.
        </div>
      )}

      {/* Heatmap grid */}
      {data && symbols.length > 0 && (
        <div style={{ overflowX: "auto", overflowY: "hidden" }}>
          <div style={{ minWidth: dates.length * 14 + 72 }}>
            {/* Date labels row */}
            <div style={{ display: "flex", marginLeft: 68, marginBottom: 3 }}>
              {labelDates.map((d, i) => (
                <div key={i} style={{ width: 12, marginRight: 2, flexShrink: 0 }}>
                  {d && (
                    <span style={{
                      fontSize: 7, color: "#334155", display: "block",
                      transform: "rotate(-45deg)", transformOrigin: "top left",
                      whiteSpace: "nowrap" as const, marginTop: 6,
                    }}>
                      {fmtDate(d)}
                    </span>
                  )}
                </div>
              ))}
            </div>

            {/* Symbol rows */}
            {symbols.slice(0, 40).map(sym => {
              const scores = data.symbols[sym];
              const streakDays = scores.filter(s => s != null && s >= minScore).length;
              const maxScore   = Math.max(...scores.filter((s): s is number => s != null));
              return (
                <div key={sym} style={{ display: "flex", alignItems: "center", marginBottom: 2 }}>
                  {/* Symbol label */}
                  <div style={{ width: 64, flexShrink: 0, display: "flex", justifyContent: "space-between", alignItems: "center", paddingRight: 4 }}>
                    <span style={{ fontSize: 9, fontWeight: 700, color: "#94a3b8", fontFamily: "monospace", letterSpacing: "0.04em" }}>
                      {sym}
                    </span>
                    <span style={{ fontSize: 8, color: streakDays >= 5 ? "#22c55e" : streakDays >= 3 ? "#f59e0b" : "#334155" }}>
                      {streakDays}d
                    </span>
                  </div>

                  {/* Day cells */}
                  {scores.map((score, di) => (
                    <div
                      key={di}
                      onMouseEnter={() => score != null ? setTooltip({ sym, date: dates[di], score }) : undefined}
                      onMouseLeave={() => setTooltip(null)}
                      style={{
                        width: 12, height: 12, borderRadius: 2,
                        marginRight: 2, flexShrink: 0,
                        background: scoreColor(score),
                        border: `1px solid ${scoreBorder(score)}`,
                        cursor: score != null ? "default" : "default",
                        transition: "transform 0.1s",
                      }}
                    />
                  ))}

                  {/* Max score badge */}
                  <span style={{ fontSize: 8, color: maxScore >= 12 ? "#22c55e" : maxScore >= 9 ? "#16a34a" : "#f59e0b", marginLeft: 4, fontFamily: "monospace", fontWeight: 700 }}>
                    {maxScore}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Tooltip */}
      {tooltip && (
        <div style={{
          marginTop: 8, padding: "6px 10px",
          background: "#0f172a", border: "1px solid #1e293b",
          borderRadius: 6, fontSize: 10, color: "#e2e8f0",
          display: "inline-block",
        }}>
          <strong style={{ color: "#f1f5f9" }}>{tooltip.sym}</strong>
          {" "}&mdash;{" "}
          {fmtDate(tooltip.date)}
          {": "}
          <strong style={{ color: tooltip.score >= 12 ? "#22c55e" : tooltip.score >= 9 ? "#16a34a" : "#f59e0b" }}>
            {tooltip.score}/16
          </strong>
        </div>
      )}
    </div>
  );
}
