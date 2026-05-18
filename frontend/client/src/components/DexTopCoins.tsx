// DexTopCoins.tsx — DEX top coins section shown below the CEX scanner
import { useState, useEffect } from "react";

const API = ((import.meta as unknown) as { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

// Chain icon colours
const CHAIN_COLOR: Record<string, string> = {
  bsc:      "#f59e0b",
  base:     "#3b82f6",
  ethereum: "#8b5cf6",
  solana:   "#22c55e",
  arbitrum: "#60a5fa",
};
const CHAIN_SHORT: Record<string, string> = {
  bsc:      "BSC",
  base:     "BASE",
  ethereum: "ETH",
  solana:   "SOL",
  arbitrum: "ARB",
};

interface DexGem {
  symbol:     string;
  chain_id?:  string;
  chain_name?: string;
  price:      number;
  change_1h:  number;
  change_24h: number;
  rel_vol:    number;
  liquidity:  number;
  signal:     string;
  score:      number;
  dex_id?:    string;
  pool_address?: string;
}

interface DexVolHit {
  symbol:     string;
  chain_id?:  string;
  price:      number;
  change_1h:  number;
  rel_vol:    number;
  signal:     string;
}

interface DexData {
  gems:      DexGem[];
  vol_hits:  DexVolHit[];
  scan_time: string | null;
  scan_ts:   number | null;
  fresh:     boolean;
  age_h?:    number;
}

function fmtP(n: number) {
  if (!n || isNaN(n)) return "$0";
  if (n < 0.000001) return `$${n.toExponential(2)}`;
  if (n < 0.001)    return `$${n.toFixed(6)}`;
  if (n < 1)        return `$${n.toFixed(4)}`;
  if (n < 1000)     return `$${n.toFixed(2)}`;
  return `$${(n/1000).toFixed(1)}k`;
}

function ChainBadge({ chainId }: { chainId: string }) {
  const color = CHAIN_COLOR[chainId] ?? "#475569";
  const label = CHAIN_SHORT[chainId] ?? chainId.toUpperCase();
  return (
    <span style={{
      fontSize: 8, fontWeight: 800, letterSpacing: "0.06em",
      color, background: `${color}18`,
      border: `1px solid ${color}40`,
      padding: "1px 5px", borderRadius: 3,
    }}>
      {label}
    </span>
  );
}

type DexTab = "gems" | "vol";

export function DexTopCoins() {
  const [data,    setData]    = useState<DexData | null>(null);
  const [loading, setLoading] = useState(false);
  const [tab,     setTab]     = useState<DexTab>("gems");

  const load = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/dex-results`, { signal: AbortSignal.timeout(10_000) });
      if (r.ok) setData(await r.json());
    } catch { /* silent */ }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  // Nothing to show — don't render the section at all
  const gems    = data?.gems     ?? [];
  const volHits = data?.vol_hits ?? [];
  const hasGems = gems.length > 0;
  const hasVol  = volHits.length > 0;
  if (!loading && !hasGems && !hasVol) return null;

  const scanAge = data?.age_h != null
    ? data.age_h < 1
      ? `${Math.round((data.age_h ?? 0) * 60)}m ago`
      : `${data.age_h.toFixed(1)}h ago`
    : null;

  const gemsCount = gems.length;
  const volCount  = volHits.length;

  return (
    <div style={{ marginTop: 10, marginBottom: 14 }}>
      {/* Section header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" }}>
            DEX Signals
          </span>
          {/* LIVE/NEW badge */}
          <span style={{
            fontSize: 8, fontWeight: 800, letterSpacing: "0.1em",
            color: "#3b82f6", background: "#1e3a5f",
            border: "1px solid #2563eb40", padding: "1px 5px", borderRadius: 3,
          }}>
            LIVE
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {scanAge && (
            <span style={{ fontSize: 9, color: data?.fresh ? "#334155" : "#f59e0b" }}>
              {data?.fresh ? scanAge : `⚠ ${scanAge}`}
            </span>
          )}
          <button
            onClick={load}
            disabled={loading}
            style={{
              fontSize: 9, color: loading ? "#334155" : "#7c3aed",
              background: "#0f172a", border: "1px solid #1e293b",
              borderRadius: 4, padding: "2px 8px",
              cursor: loading ? "not-allowed" : "pointer",
            }}
          >
            {loading ? "…" : "↻"}
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
        <button
          onClick={() => setTab("gems")}
          style={{
            fontSize: 9, fontWeight: 700, letterSpacing: "0.06em",
            padding: "2px 8px", borderRadius: 3, cursor: "pointer",
            border: `1px solid ${tab === "gems" ? "#22c55e" : "#1e293b"}`,
            background: tab === "gems" ? "#22c55e18" : "transparent",
            color: tab === "gems" ? "#22c55e" : "#475569",
          }}
        >
          {gemsCount} SIGNALS
        </button>
        <button
          onClick={() => setTab("vol")}
          style={{
            fontSize: 9, fontWeight: 700, letterSpacing: "0.06em",
            padding: "2px 8px", borderRadius: 3, cursor: "pointer",
            border: `1px solid ${tab === "vol" ? "#f59e0b" : "#1e293b"}`,
            background: tab === "vol" ? "#f59e0b18" : "transparent",
            color: tab === "vol" ? "#f59e0b" : "#475569",
          }}
        >
          {volCount} VOL WATCH
        </button>
      </div>

      {/* Loading state */}
      {loading && (
        <div style={{ fontSize: 9, color: "#334155", padding: "8px 0" }}>
          Loading DEX results…
        </div>
      )}

      {/* GEMS tab */}
      {!loading && tab === "gems" && (
        hasGems ? (
          <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b" }}>
            {gems.slice(0, 10).map((gem, i) => {
              const chain    = gem.chain_id ?? "";
              const rowBg    = i % 2 === 0 ? "#060b17" : "#080e1c";
              const isStrong = gem.signal === "STRONG BUY";
              const sigColor = isStrong ? "#22c55e" : "#22c55e";
              const chg1h    = gem.change_1h ?? 0;
              const rv       = gem.rel_vol ?? 0;
              const volLabel = rv >= 3.5 ? "EXTREME" : rv >= 2.5 ? "HIGH" : "ELEVATED";
              const volColor = rv >= 3.5 ? "#ef4444" : rv >= 2.5 ? "#f59e0b" : "#22c55e";

              return (
                <div
                  key={`${gem.symbol}-${chain}-${i}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 52px 60px",
                    background: rowBg,
                    borderBottom: "1px solid #0f172a",
                    borderLeft: `3px solid ${sigColor}`,
                    padding: "8px 0 8px 8px",
                    alignItems: "center",
                  }}
                >
                  {/* Symbol + chain + dex */}
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span style={{ fontSize: 12, fontWeight: 800, color: "#f1f5f9", fontFamily: "monospace", letterSpacing: "0.04em" }}>
                        {gem.symbol}
                      </span>
                      <ChainBadge chainId={chain} />
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ fontSize: 8, color: "#334155" }}>
                        {fmtP(gem.price)}
                      </span>
                      {gem.dex_id && (
                        <span style={{ fontSize: 8, color: "#1e293b" }}>
                          {gem.dex_id.toUpperCase()}
                        </span>
                      )}
                    </div>
                    {/* Gate line */}
                    <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                      <span style={{ fontSize: 8, color: volColor, fontWeight: 700 }}>
                        ⚡ {rv.toFixed(1)}x {volLabel}
                      </span>
                      {gem.liquidity > 0 && (
                        <span style={{ fontSize: 8, color: "#1e293b" }}>
                          · ${(gem.liquidity / 1000).toFixed(0)}k liq
                        </span>
                      )}
                    </div>
                  </div>

                  {/* 1h change */}
                  <span style={{
                    fontSize: 11, fontWeight: 700, fontFamily: "monospace",
                    color: chg1h >= 0 ? "#22c55e" : "#ef4444",
                    textAlign: "center",
                  }}>
                    {chg1h >= 0 ? "+" : ""}{chg1h.toFixed(1)}%
                  </span>

                  {/* Signal badge */}
                  <div style={{ textAlign: "center", paddingRight: 8 }}>
                    <span style={{
                      fontSize: 8, fontWeight: 800, letterSpacing: "0.04em",
                      color: sigColor,
                      background: "rgba(34,197,94,0.10)",
                      padding: "3px 5px", borderRadius: 3,
                      border: "1px solid rgba(34,197,94,0.25)",
                      whiteSpace: "nowrap",
                    }}>
                      {isStrong ? "STR BUY" : "BUY"}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ fontSize: 9, color: "#334155", padding: "10px 0", textAlign: "center" }}>
            No DEX signals from last scan. Vol watch below.
          </div>
        )
      )}

      {/* VOL WATCH tab */}
      {!loading && tab === "vol" && (
        hasVol ? (
          <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b" }}>
            {volHits.slice(0, 12).map((hit, i) => {
              const chain   = hit.chain_id ?? "";
              const rowBg   = i % 2 === 0 ? "#060b17" : "#080e1c";
              const rv      = hit.rel_vol ?? 0;
              const volColor= rv >= 3.5 ? "#ef4444" : rv >= 2.5 ? "#f59e0b" : "#94a3b8";
              const volLabel= rv >= 3.5 ? "EXTREME" : rv >= 2.5 ? "HIGH" : "ELEVATED";
              const chg     = hit.change_1h ?? 0;

              return (
                <div
                  key={`vol-${hit.symbol}-${chain}-${i}`}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 52px 60px",
                    background: rowBg,
                    borderBottom: "1px solid #0f172a",
                    borderLeft: `3px solid ${volColor}40`,
                    padding: "7px 0 7px 8px",
                    alignItems: "center",
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: "#e2e8f0", fontFamily: "monospace" }}>
                        {hit.symbol}
                      </span>
                      <ChainBadge chainId={chain} />
                    </div>
                    <span style={{ fontSize: 8, color: "#334155" }}>{fmtP(hit.price)}</span>
                  </div>

                  <span style={{
                    fontSize: 11, fontWeight: 700, fontFamily: "monospace",
                    color: chg >= 0 ? "#22c55e" : "#ef4444",
                    textAlign: "center",
                  }}>
                    {chg >= 0 ? "+" : ""}{chg.toFixed(1)}%
                  </span>

                  <div style={{ textAlign: "center", paddingRight: 8 }}>
                    <span style={{
                      fontSize: 8, fontWeight: 800, letterSpacing: "0.03em",
                      color: volColor,
                      background: `${volColor}18`,
                      padding: "3px 5px", borderRadius: 3,
                      border: `1px solid ${volColor}40`,
                      whiteSpace: "nowrap",
                    }}>
                      {rv.toFixed(1)}x {volLabel}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ fontSize: 9, color: "#334155", padding: "10px 0", textAlign: "center" }}>
            No unusual DEX volume from last scan.
          </div>
        )
      )}

      {/* Footer note */}
      {data?.scan_time && (
        <div style={{ fontSize: 8, color: "#1e293b", marginTop: 6, textAlign: "center" }}>
          DEX scan: {data.scan_time} · BSC · Base · ETH · SOL · ARB
        </div>
      )}
    </div>
  );
}
