// SignalStreakHeatmap.tsx
// Calendar heatmap: which coins had repeated signals over the last N days.
// Colours: grey = no signal, teal = BUY, purple = STRONG BUY.
//
// Filters and colors by signal tier (min_tier: "buy" | "strong_buy"), not a
// raw score cutoff. Under the current tier system (signals.py) a plain BUY
// only needs Trend+ADX confirmed and can legitimately score as low as 3/13,
// while STRONG BUY's own minimum possible score is 6 — so a fixed score
// threshold or gradient can no longer reliably tell the two apart. Same
// underlying bug as CSOVerdict.tsx and ScanAlertPoller.tsx, fixed the same
// way: trust the signal label the backend actually computed.

import { useState, useEffect } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

type SignalTier = "buy" | "strong_buy";

interface StreakCell {
  score: number;
  signal: string;
}

interface StreakData {
  dates: string[]; // ISO date strings, oldest → newest
  symbols: Record<string, (StreakCell | null)[]>;
  min_tier: SignalTier;
  days: number;
}

function cellColor(cell: StreakCell | null): string {
  if (cell == null) return "#0f172a";
  if (cell.signal === "STRONG BUY") return "#a78bfa"; // purple
  if (cell.signal === "BUY") return "#22c55e";         // teal/green
  return "#0f172a";
}

function cellBorder(cell: StreakCell | null): string {
  if (cell == null) return "#1e293b";
  if (cell.signal === "STRONG BUY") return "#a78bfa55";
  if (cell.signal === "BUY") return "#22c55e55";
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

const TIER_OPTIONS: { label: string; value: SignalTier }[] = [
  { label: "BUY+", value: "buy" },
  { label: "STRONG BUY", value: "strong_buy" },
];

export function SignalStreakHeatmap() {
  const [data, setData] = useState<StreakData | null>(null);
  const [loading, setLoading] = useState(false);
  const [minTier, setMinTier] = useState<SignalTier>("buy");
  const [days, setDays] = useState(5);
  const [tooltip, setTooltip] = useState<{ sym: string; date: string; cell: StreakCell } | null>(null);

  async function load() {
    setLoading(true);
    try {
      const r = await fetch(`${API}/streak?days=${days}&min_tier=${minTier}`);
      const j = await r.json();
      setData(j);
    } catch { setData(null); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, [minTier, days]);

  const symbols = data ? Object.keys(data.symbols) : [];
  const dates = data?.dates ?? [];
  // Show every 5th label on mobile-friendly 30-day view
  const labelEveryN = dates.length > 20 ? 5 : 3;
  const labelDates = labelEvery(dates, labelEveryN);

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
            {days}D
          </span>
        </div>
        <div style={{ display: "flex", gap: 4 }}>
          {TIER_OPTIONS.map(opt => (
            <button key={opt.value} onClick={() => setMinTier(opt.value)} style={minTier === opt.value ? activeBtnStyle : btnStyle}>
              {opt.label}
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
          { color: "#22c55e", border: "#22c55e55", label: "BUY" },
          { color: "#a78bfa", border: "#a78bfa55", label: "STRONG BUY" },
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
              const cells = data.symbols[sym];
              const streakDays = cells.filter(c => c != null).length;
              const strongDays = cells.filter(c => c != null && c.signal === "STRONG BUY").length;
              const bestCell = cells.reduce<StreakCell | null>((best, c) => {
                if (!c) return best;
                if (!best) return c;
                const rank = (s: string) => s === "STRONG BUY" ? 2 : s === "BUY" ? 1 : 0;
                if (rank(c.signal) > rank(best.signal)) return c;
                if (rank(c.signal) === rank(best.signal) && c.score > best.score) return c;
                return best;
              }, null);
              return (
                <div key={sym} style={{ display: "flex", alignItems: "center", marginBottom: 2 }}>
                  {/* Symbol label */}
                  <div style={{ width: 64, flexShrink: 0, display: "flex", justifyContent: "space-between", alignItems: "center", paddingRight: 4 }}>
                    <span style={{ fontSize: 9, fontWeight: 700, color: "#94a3b8", fontFamily: "monospace", letterSpacing: "0.04em" }}>
                      {sym}
                    </span>
                    <span style={{ fontSize: 8, color: strongDays >= 3 ? "#a78bfa" : streakDays >= 3 ? "#22c55e" : "#334155" }}>
                      {streakDays}d
                    </span>
                  </div>

                  {/* Day cells */}
                  {cells.map((cell, di) => (
                    <div
                      key={di}
                      onMouseEnter={() => cell != null ? setTooltip({ sym, date: dates[di], cell }) : undefined}
                      onMouseLeave={() => setTooltip(null)}
                      style={{
                        width: 12, height: 12, borderRadius: 2,
                        marginRight: 2, flexShrink: 0,
                        background: cellColor(cell),
                        border: `1px solid ${cellBorder(cell)}`,
                        transition: "transform 0.1s",
                      }}
                    />
                  ))}

                  {/* Best signal badge for this symbol in the window */}
                  {bestCell && (
                    <span style={{
                      fontSize: 8,
                      color: bestCell.signal === "STRONG BUY" ? "#a78bfa" : "#22c55e",
                      marginLeft: 4, fontFamily: "monospace", fontWeight: 700,
                    }}>
                      {bestCell.signal === "STRONG BUY" ? "SB" : "B"} {bestCell.score}
                    </span>
                  )}
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
          <strong style={{ color: tooltip.cell.signal === "STRONG BUY" ? "#a78bfa" : "#22c55e" }}>
            {tooltip.cell.signal} · {tooltip.cell.score}/13
          </strong>
        </div>
      )}
    </div>
  );
}
