// ── Volume Surge Card ──────────────────────────────────────────────────────────
// Shows coins with unusual volume vs their 20-bar baseline, placed below the
// VPRTS signal components block. Tappable rows → runAnalysis on that coin.
// PRE-BREAKOUT = high RVOL + muted price (the early signal that matters most).

import { useState, useEffect, useCallback } from "react";

const API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface SurgeCoin {
  symbol:   string;
  rvol:     number;
  price:    number;
  change:   number;
  vol_24h:  number;
  label:    "PRE-BREAKOUT" | "BREAKOUT" | "DISTRIBUTION";
}

interface Props {
  onSelect: (symbol: string) => void;
}

const LABEL_STYLE: Record<string, { color: string; bg: string; border: string }> = {
  "PRE-BREAKOUT":  { color: "#f59e0b", bg: "#1a1200",  border: "#451a00" },
  "BREAKOUT":      { color: "#22c55e", bg: "#0d2212",  border: "#14532d" },
  "DISTRIBUTION":  { color: "#ef4444", bg: "#1a0a0a",  border: "#7f1d1d" },
};

function fmtVol(v: number): string {
  if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000)     return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtPrice(p: number): string {
  if (p < 0.000001) return p.toExponential(2);
  if (p < 0.001)    return p.toFixed(6);
  if (p < 0.1)      return p.toFixed(4);
  if (p < 10)       return p.toFixed(3);
  return p.toFixed(2);
}

export function VolumeSurgeCard({ onSelect }: Props) {
  const [coins,   setCoins]   = useState<SurgeCoin[]>([]);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState<string | null>(null);
  const [lastFetch, setLastFetch] = useState<string>("");
  const [noBaseline, setNoBaseline] = useState(false);

  const fetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    setNoBaseline(false);
    try {
      const res = await window.fetch(
        `${API}/volume-surge?min_rvol=2.5&max_price_chg=8&min_volume_usd=50000&top_n=8&interval=1h`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);
      if (!data.coins?.length) {
        setNoBaseline(true);
        setCoins([]);
      } else {
        setCoins(data.coins);
        setLastFetch(new Date().toLocaleTimeString());
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch on mount, refresh every 5 min
  useEffect(() => { fetch(); }, [fetch]);
  useEffect(() => {
    const t = setInterval(fetch, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [fetch]);

  return (
    <div style={{ marginTop: 12, marginBottom: 4 }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" as const }}>
            ⚡ Volume Surge
          </span>
          <span style={{ fontSize: 8, fontWeight: 700, letterSpacing: "0.05em", color: "#f59e0b", background: "#1a1200", border: "1px solid #451a00", borderRadius: 3, padding: "1px 5px" }}>
            LIVE
          </span>
          {lastFetch && (
            <span style={{ fontSize: 8, color: "#334155" }}>{lastFetch}</span>
          )}
        </div>
        <button
          onClick={fetch}
          disabled={loading}
          style={{
            fontSize: 9, color: loading ? "#334155" : "#7c3aed",
            background: "#0f172a", border: "1px solid #1e293b",
            borderRadius: 4, padding: "2px 8px",
            cursor: loading ? "not-allowed" : "pointer",
          }}
        >
          {loading ? "…" : "Refresh"}
        </button>
      </div>

      {/* No baseline yet */}
      {noBaseline && !loading && (
        <div style={{ padding: "10px 12px", borderRadius: 6, background: "#0a0f1e", border: "1px solid #1e293b", textAlign: "center" as const }}>
          <div style={{ fontSize: 9, color: "#475569", lineHeight: 1.5 }}>
            Building volume baseline… check back in ~60s
          </div>
          <div style={{ fontSize: 8, color: "#334155", marginTop: 3 }}>
            Render is computing 20-bar averages for all Binance pairs
          </div>
        </div>
      )}

      {/* Error */}
      {error && !loading && (
        <div style={{ padding: "8px 10px", borderRadius: 6, background: "#1a0a0a", border: "1px solid #7f1d1d" }}>
          <div style={{ fontSize: 9, color: "#ef4444", marginBottom: 3 }}>Surge scan failed</div>
          <div style={{ fontSize: 8, color: "#94a3b8" }}>{error}</div>
        </div>
      )}

      {/* Loading skeleton */}
      {loading && coins.length === 0 && (
        <div style={{ display: "flex", flexDirection: "column" as const, gap: 4 }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} style={{ height: 36, borderRadius: 6, background: "#0a0f1e", border: "1px solid #1e293b", opacity: 0.5 }} />
          ))}
        </div>
      )}

      {/* Coin rows */}
      {coins.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column" as const, gap: 3, opacity: loading ? 0.6 : 1, transition: "opacity 0.2s" }}>
          {coins.map((coin) => {
            const ls = LABEL_STYLE[coin.label] ?? LABEL_STYLE["PRE-BREAKOUT"];
            const chgColor = coin.change > 0 ? "#22c55e" : coin.change < 0 ? "#ef4444" : "#94a3b8";
            const rvolColor = coin.rvol >= 8 ? "#ef4444" : coin.rvol >= 5 ? "#f59e0b" : "#22c55e";

            return (
              <button
                key={coin.symbol}
                onClick={() => onSelect(coin.symbol)}
                style={{
                  display: "grid",
                  gridTemplateColumns: "68px 1fr 44px 44px 52px",
                  alignItems: "center",
                  width: "100%",
                  background: "#060b17",
                  border: "1px solid #1e293b",
                  borderRadius: 6,
                  padding: "7px 10px",
                  cursor: "pointer",
                  textAlign: "left" as const,
                  transition: "border-color 0.12s, background 0.12s",
                  gap: 4,
                }}
                onMouseEnter={e => {
                  (e.currentTarget as HTMLElement).style.background = "#0d1a2e";
                  (e.currentTarget as HTMLElement).style.borderColor = "#334155";
                }}
                onMouseLeave={e => {
                  (e.currentTarget as HTMLElement).style.background = "#060b17";
                  (e.currentTarget as HTMLElement).style.borderColor = "#1e293b";
                }}
              >
                {/* Symbol */}
                <div style={{ display: "flex", flexDirection: "column" as const, gap: 1 }}>
                  <span style={{ fontSize: 11, fontWeight: 800, color: "#f1f5f9", fontFamily: "monospace", letterSpacing: "0.03em" }}>
                    {coin.symbol}
                  </span>
                  <span style={{ fontSize: 8, color: "#334155", fontFamily: "monospace" }}>
                    {fmtPrice(coin.price)}
                  </span>
                </div>

                {/* Label badge */}
                <span style={{
                  fontSize: 7, fontWeight: 800, letterSpacing: "0.05em",
                  color: ls.color, background: ls.bg, border: `1px solid ${ls.border}`,
                  borderRadius: 3, padding: "2px 5px", whiteSpace: "nowrap" as const,
                  textTransform: "uppercase" as const,
                }}>
                  {coin.label}
                </span>

                {/* RVOL */}
                <div style={{ textAlign: "right" as const }}>
                  <div style={{ fontSize: 11, fontWeight: 800, color: rvolColor, fontFamily: "monospace" }}>
                    {coin.rvol.toFixed(1)}x
                  </div>
                  <div style={{ fontSize: 7, color: "#334155", letterSpacing: "0.05em" }}>RVOL</div>
                </div>

                {/* Price change */}
                <div style={{ textAlign: "right" as const }}>
                  <div style={{ fontSize: 10, fontWeight: 700, color: chgColor, fontFamily: "monospace" }}>
                    {coin.change >= 0 ? "+" : ""}{coin.change.toFixed(1)}%
                  </div>
                  <div style={{ fontSize: 7, color: "#334155", letterSpacing: "0.05em" }}>24H</div>
                </div>

                {/* 24h vol */}
                <div style={{ textAlign: "right" as const }}>
                  <div style={{ fontSize: 9, color: "#64748b", fontFamily: "monospace" }}>
                    {fmtVol(coin.vol_24h)}
                  </div>
                  <div style={{ fontSize: 7, color: "#334155", letterSpacing: "0.05em" }}>VOL</div>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Footer hint */}
      {coins.length > 0 && (
        <div style={{ fontSize: 8, color: "#1e293b", marginTop: 6, lineHeight: 1.5 }}>
          RVOL = current bar vs 20-bar avg · PRE-BREAKOUT = volume spike, price flat · tap any row to analyse
        </div>
      )}
    </div>
  );
}
