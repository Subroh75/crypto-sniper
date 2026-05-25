/**
 * VolRadar — Volume spike scanner panel
 * Calls /scan once, shows all coins with rel_vol >= 1.8x sorted by vol descending.
 * Used as the "Vol Radar" tab on both mobile and desktop.
 */
import { useState, useEffect, useCallback, useRef } from "react";

const BASE_URL =
  (import.meta as Record<string, unknown> & { env?: Record<string, string> })
    .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

interface VolCoin {
  symbol: string;
  price: number;
  change: number;
  rel_vol: number;
  volume_24h: number;
  signal: string;
  score: number;
  exchange_label: string;
  adx: number;
  z_quality: string;
  vol_shield?: string;
  vol_shield_sigma?: number;
  vol_shield_sizing?: number;
}

interface ScanResult {
  signals: VolCoin[];
  universe: number;
  scanned: number;
  cached: boolean;
}

// Gate colour thresholds
function gateColor(rv: number): { bg: string; text: string; label: string } {
  if (rv >= 3.5) return { bg: "#16a34a22", text: "#22c55e", label: `${rv.toFixed(1)}x` };
  if (rv >= 2.5) return { bg: "#d9770622", text: "#f59e0b", label: `${rv.toFixed(1)}x` };
  return         { bg: "#6b21a822", text: "#a78bfa",  label: `${rv.toFixed(1)}x` };
}

function GateBadge({ rv }: { rv: number }) {
  const c = gateColor(rv);
  return (
    <span
      style={{
        background: c.bg,
        color: c.text,
        border: `1px solid ${c.text}44`,
        borderRadius: 6,
        padding: "2px 8px",
        fontFamily: "monospace",
        fontWeight: 800,
        fontSize: 13,
        letterSpacing: "0.02em",
        whiteSpace: "nowrap",
      }}
    >
      {c.label}
    </span>
  );
}

function ExchangeBadge({ label }: { label: string }) {
  const color =
    label === "BINANCE" ? "#f59e0b" :
    label === "MEXC"    ? "#22c55e" :
    label === "GATE"    ? "#60a5fa" : "#94a3b8";
  return (
    <span style={{ color, fontSize: 10, fontWeight: 700, fontFamily: "monospace", letterSpacing: "0.08em" }}>
      {label}
    </span>
  );
}

function ChangeCell({ pct }: { pct: number }) {
  const color = pct >= 0 ? "#22c55e" : "#ef4444";
  return (
    <span style={{ color, fontWeight: 700, fontSize: 13, fontFamily: "monospace" }}>
      {pct >= 0 ? "+" : ""}{pct.toFixed(2)}%
    </span>
  );
}

function SignalBadge({ signal, isDex = false }: { signal: string; isDex?: boolean }) {
  if (!signal || signal === "NO SIGNAL") return null;
  const isStrong = signal === "STRONG BUY";
  // Identity system: CEX=green ▲, DEX=purple ◆
  const col = isDex ? "#a855f7" : isStrong ? "#22c55e" : "#f59e0b";
  const bg  = isDex ? "#a855f722" : isStrong ? "#16a34a22" : "#d9770622";
  const lbl = isDex ? (isStrong ? "◆ STRONG BUY" : "◆ BUY") : (isStrong ? "▲ STRONG BUY" : "▲ BUY");
  return (
    <span style={{
      background: bg,
      color: col,
      border: `1px solid ${col}44`,
      borderRadius: 5,
      padding: "1px 6px",
      fontSize: 9,
      fontWeight: 800,
      fontFamily: "monospace",
      letterSpacing: "0.06em",
      textTransform: "uppercase" as const,
      marginLeft: 4,
    }}>
      {lbl}
    </span>
  );
}

// Vol Shield badge
function VolShieldBadge({ regime, sigma, sizing }: { regime: string; sigma: number; sizing: number }) {
  if (!regime) return null;
  const conf: Record<string, { color: string; bg: string; icon: string }> = {
    CALM:     { color: "#22c55e", bg: "#16a34a22", icon: "🟢" },
    ELEVATED: { color: "#f59e0b", bg: "#d9770622", icon: "⚠" },
    STORM:    { color: "#ef4444", bg: "#7f1d1d22", icon: "🔴" },
  };
  const c = conf[regime] ?? conf["ELEVATED"];
  const sizeNote = sizing >= 1.0 ? "full size" : sizing >= 0.6 ? "reduce exposure" : "small size only";
  return (
    <span style={{
      background: c.bg, color: c.color,
      border: `1px solid ${c.color}44`,
      borderRadius: 5, padding: "1px 7px",
      fontSize: 9, fontWeight: 800,
      fontFamily: "monospace", letterSpacing: "0.04em",
      marginLeft: 4, whiteSpace: "nowrap" as const,
    }}
      title={`Vol Shield: ${regime} | σ ${sigma.toFixed(1)}%/day | ${sizing}× — ${sizeNote}`}
    >
      {c.icon} {regime}
    </span>
  );
}

// Format large volume numbers
function fmtVol(n: number): string {
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

// Format price with sig figs
function fmtPrice(n: number): string {
  if (n === 0) return "0";
  if (n >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  if (n >= 1)    return n.toFixed(4);
  return n.toPrecision(4);
}

type SortKey = "rel_vol" | "change" | "score" | "volume_24h";

interface VolRadarProps {
  onSelect?: (symbol: string) => void;
}

export default function VolRadar({ onSelect }: VolRadarProps) {
  const [coins, setCoins]       = useState<VolCoin[]>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [lastRefresh, setLast]  = useState<Date | null>(null);
  const [sortBy, setSortBy]     = useState<SortKey>("rel_vol");
  const [universe, setUniverse] = useState(0);
  const [scanned, setScanned]   = useState(0);
  const [minRv, setMinRv]       = useState<1.8 | 2.5 | 3.5>(1.8);
  const intervalRef             = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${BASE_URL}/scan?interval=1d&min_score=1&max_coins=200&min_volume=500000`,
        { signal: AbortSignal.timeout(60_000) }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ScanResult = await res.json();

      // Pull all coins with rel_vol >= 1.8 from the scan (not just score >= 9)
      // The /scan endpoint only returns signals that pass scoring — but we want
      // the vol pre-filter list. Fallback: show all returned signals sorted by vol.
      const all = (data.signals ?? []).filter((c) => (c.rel_vol ?? 0) >= 1.8);
      all.sort((a, b) => (b.rel_vol ?? 0) - (a.rel_vol ?? 0));

      setCoins(all);
      setUniverse(data.universe ?? 0);
      setScanned(data.scanned ?? 0);
      setLast(new Date());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      if (!silent) setError(msg);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    intervalRef.current = setInterval(() => fetchData(true), 5 * 60 * 1000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchData]);

  const sorted = [...coins]
    .filter((c) => (c.rel_vol ?? 0) >= minRv)
    .sort((a, b) => {
      if (sortBy === "rel_vol")    return (b.rel_vol ?? 0)    - (a.rel_vol ?? 0);
      if (sortBy === "change")     return (b.change ?? 0)     - (a.change ?? 0);
      if (sortBy === "score")      return (b.score ?? 0)      - (a.score ?? 0);
      if (sortBy === "volume_24h") return (b.volume_24h ?? 0) - (a.volume_24h ?? 0);
      return 0;
    });

  const strongBuys = coins.filter(c => c.signal === "STRONG BUY").length;
  const buys       = coins.filter(c => c.signal === "BUY").length;

  // ── Header ─────────────────────────────────────────────────────────────────
  const Header = () => (
    <div style={{ marginBottom: 16 }}>
      {/* Title row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 16, fontWeight: 900, color: "#f1f5f9", letterSpacing: "0.04em", fontFamily: "monospace" }}>
              VOL RADAR
            </span>
            <span style={{
              background: "#7c3aed22", color: "#a78bfa",
              border: "1px solid #7c3aed44", borderRadius: 4,
              padding: "1px 6px", fontSize: 9, fontWeight: 700,
              fontFamily: "monospace", letterSpacing: "0.06em",
            }}>LIVE</span>
          </div>
          <div style={{ fontSize: 11, color: "#475569", marginTop: 2, fontFamily: "monospace" }}>
            {universe} universe · {scanned} scanned · {coins.length} spikes ≥ 1.8x
          </div>
        </div>
        <button
          onClick={() => fetchData()}
          disabled={loading}
          style={{
            background: "#1e293b", border: "1px solid #334155", borderRadius: 8,
            color: "#94a3b8", padding: "6px 12px", fontSize: 11,
            fontFamily: "monospace", fontWeight: 700, cursor: loading ? "wait" : "pointer",
            opacity: loading ? 0.5 : 1,
          }}
        >
          {loading ? "..." : "↻ Refresh"}
        </button>
      </div>

      {/* Signal summary pills */}
      {(strongBuys > 0 || buys > 0) && (
        <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
          {strongBuys > 0 && (
            <span style={{
              background: "#16a34a22", color: "#22c55e",
              border: "1px solid #22c55e44", borderRadius: 6,
              padding: "3px 10px", fontSize: 11, fontWeight: 800, fontFamily: "monospace",
            }}>
              ▲ {strongBuys} STRONG BUY
            </span>
          )}
          {buys > 0 && (
            <span style={{
              background: "#d9770622", color: "#f59e0b",
              border: "1px solid #f59e0b44", borderRadius: 6,
              padding: "3px 10px", fontSize: 11, fontWeight: 800, fontFamily: "monospace",
            }}>
              ◆ {buys} BUY
            </span>
          )}
        </div>
      )}

      {/* Filter + sort row */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        {/* Min vol gate filter */}
        <div style={{ display: "flex", gap: 4 }}>
          {([1.8, 2.5, 3.5] as const).map(v => (
            <button
              key={v}
              onClick={() => setMinRv(v)}
              style={{
                background: minRv === v ? "#7c3aed" : "#1e293b",
                color: minRv === v ? "#fff" : "#64748b",
                border: `1px solid ${minRv === v ? "#7c3aed" : "#334155"}`,
                borderRadius: 6, padding: "3px 10px",
                fontSize: 10, fontWeight: 700, fontFamily: "monospace",
                cursor: "pointer", transition: "all 0.15s",
              }}
            >
              ≥{v}x
            </button>
          ))}
        </div>
        {/* Sort selector */}
        <div style={{ display: "flex", gap: 4, marginLeft: "auto" }}>
          {(["rel_vol","volume_24h","change","score"] as SortKey[]).map(k => (
            <button
              key={k}
              onClick={() => setSortBy(k)}
              style={{
                background: sortBy === k ? "#1e40af22" : "transparent",
                color: sortBy === k ? "#60a5fa" : "#475569",
                border: `1px solid ${sortBy === k ? "#3b82f644" : "transparent"}`,
                borderRadius: 5, padding: "2px 8px",
                fontSize: 10, fontWeight: 700, fontFamily: "monospace",
                cursor: "pointer",
              }}
            >
              {k === "rel_vol" ? "Vol%" : k === "volume_24h" ? "$Vol" : k === "change" ? "Chg" : "Score"}
            </button>
          ))}
        </div>
      </div>

      {lastRefresh && (
        <div style={{ fontSize: 10, color: "#334155", marginTop: 8, fontFamily: "monospace" }}>
          Last refresh: {lastRefresh.toLocaleTimeString()}
        </div>
      )}
    </div>
  );

  // ── Empty / Error states ────────────────────────────────────────────────────
  if (error) return (
    <div style={{ padding: 24, color: "#ef4444", fontFamily: "monospace", fontSize: 13 }}>
      Error: {error}
      <button onClick={() => fetchData()} style={{ marginLeft: 12, color: "#60a5fa", background: "none", border: "none", cursor: "pointer" }}>Retry</button>
    </div>
  );

  if (loading && coins.length === 0) return (
    <div style={{ padding: 24 }}>
      <Header />
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} style={{
            background: "#0f172a", borderRadius: 10, height: 64,
            opacity: 0.4 - i * 0.05, animation: "pulse 1.5s infinite",
          }} />
        ))}
      </div>
    </div>
  );

  if (!loading && sorted.length === 0) return (
    <div style={{ padding: 24 }}>
      <Header />
      <div style={{
        background: "#0f172a", borderRadius: 12, padding: 32,
        textAlign: "center", border: "1px solid #1e293b",
      }}>
        <div style={{ fontSize: 28, marginBottom: 8 }}>📡</div>
        <div style={{ color: "#64748b", fontFamily: "monospace", fontSize: 13 }}>
          No volume spikes ≥ {minRv}x detected
        </div>
        <div style={{ color: "#334155", fontSize: 11, marginTop: 4, fontFamily: "monospace" }}>
          Market is quiet — check back soon
        </div>
      </div>
    </div>
  );

  // ── Mobile card list ────────────────────────────────────────────────────────
  const MobileList = () => (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {sorted.map((coin, idx) => {
        const gate = gateColor(coin.rel_vol);
        const hasSignal = coin.signal && coin.signal !== "NO SIGNAL";
        return (
          <div
            key={coin.symbol}
            onClick={() => onSelect?.(coin.symbol)}
            style={{
              background: "#0f172a",
              border: `1px solid ${hasSignal ? "#22c55e33" : "#1e293b"}`,
              borderRadius: 12,
              padding: "12px 14px",
              cursor: onSelect ? "pointer" : "default",
              transition: "border-color 0.15s",
              position: "relative",
              overflow: "hidden",
            }}
          >
            {/* Rank strip */}
            <span style={{
              position: "absolute", top: 0, left: 0, bottom: 0,
              width: 3, background: gate.text, borderRadius: "12px 0 0 12px",
              opacity: 0.7,
            }} />

            <div style={{ paddingLeft: 8 }}>
              {/* Top row: symbol + vol badge */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" as const }}>
                  <span style={{ fontFamily: "monospace", fontWeight: 900, fontSize: 15, color: "#f1f5f9" }}>
                    #{idx + 1} {coin.symbol}
                  </span>
                  <span style={{ color: "#475569", fontSize: 11, fontFamily: "monospace" }}>/USDT</span>
                  {hasSignal && <SignalBadge signal={coin.signal} isDex={false} />}
                  {coin.vol_shield && <VolShieldBadge regime={coin.vol_shield} sigma={coin.vol_shield_sigma ?? 0} sizing={coin.vol_shield_sizing ?? 1} />}
                </div>
                <GateBadge rv={coin.rel_vol} />
              </div>

              {/* Bottom row: price · change · vol · exchange */}
              <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap" }}>
                <span style={{ color: "#94a3b8", fontFamily: "monospace", fontSize: 12 }}>
                  {fmtPrice(coin.price)}
                </span>
                <ChangeCell pct={coin.change} />
                <span style={{ color: "#64748b", fontFamily: "monospace", fontSize: 11 }}>
                  {fmtVol(coin.volume_24h)}
                </span>
                <ExchangeBadge label={coin.exchange_label ?? "BINANCE"} />
                {coin.adx > 0 && (
                  <span style={{ color: "#475569", fontFamily: "monospace", fontSize: 10 }}>
                    ADX {coin.adx.toFixed(0)}
                  </span>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );

  // ── Desktop table ───────────────────────────────────────────────────────────
  const DesktopTable = () => (
    <div style={{
      background: "#0f172a", borderRadius: 14,
      border: "1px solid #1e293b", overflow: "hidden",
    }}>
      {/* Table header */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "32px 1fr 90px 80px 80px 80px 70px 56px",
        padding: "8px 16px",
        background: "#0a0f1e",
        borderBottom: "1px solid #1e293b",
      }}>
        {["#", "SYMBOL", "REL VOL", "PRICE", "24H CHG", "$VOL", "EXCH", "SIGNAL"].map(h => (
          <span key={h} style={{ fontSize: 9, fontWeight: 700, color: "#334155", fontFamily: "monospace", letterSpacing: "0.1em" }}>
            {h}
          </span>
        ))}
      </div>

      {/* Rows */}
      {sorted.map((coin, idx) => {
        const gate = gateColor(coin.rel_vol);
        const hasSignal = coin.signal && coin.signal !== "NO SIGNAL";
        const isStrong = coin.signal === "STRONG BUY";
        return (
          <div
            key={coin.symbol}
            onClick={() => onSelect?.(coin.symbol)}
            style={{
              display: "grid",
              gridTemplateColumns: "32px 1fr 90px 80px 80px 80px 70px 56px",
              padding: "10px 16px",
              borderBottom: "1px solid #0f172a",
              cursor: onSelect ? "pointer" : "default",
              background: hasSignal ? (isStrong ? "#16a34a08" : "#d9770608") : "transparent",
              transition: "background 0.15s",
              alignItems: "center",
            }}
            onMouseEnter={e => (e.currentTarget.style.background = "#1e293b55")}
            onMouseLeave={e => (e.currentTarget.style.background = hasSignal ? (isStrong ? "#16a34a08" : "#d9770608") : "transparent")}
          >
            <span style={{ color: "#334155", fontFamily: "monospace", fontSize: 11 }}>{idx + 1}</span>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontWeight: 900, fontSize: 13, color: "#f1f5f9", fontFamily: "monospace" }}>{coin.symbol}</span>
              <span style={{ color: "#334155", fontSize: 10, fontFamily: "monospace" }}>/USDT</span>
            </div>
            <GateBadge rv={coin.rel_vol} />
            <span style={{ color: "#94a3b8", fontFamily: "monospace", fontSize: 12 }}>{fmtPrice(coin.price)}</span>
            <ChangeCell pct={coin.change} />
            <span style={{ color: "#64748b", fontFamily: "monospace", fontSize: 11 }}>{fmtVol(coin.volume_24h)}</span>
            <ExchangeBadge label={coin.exchange_label ?? "BINANCE"} />
            <div style={{ display: "flex", flexDirection: "column" as const, gap: 2 }}>
              <span style={{
                color: isStrong ? "#22c55e" : hasSignal ? "#f59e0b" : "#334155",
                fontFamily: "monospace", fontSize: 9, fontWeight: 800,
                letterSpacing: "0.04em",
              }}>
                {isStrong ? "▲ STR BUY" : hasSignal ? "▲ BUY" : "—"}
              </span>
              {coin.vol_shield && (
                <span style={{
                  color: coin.vol_shield === "CALM" ? "#22c55e" : coin.vol_shield === "STORM" ? "#ef4444" : "#f59e0b",
                  fontFamily: "monospace", fontSize: 8, fontWeight: 700,
                }}>
                  {coin.vol_shield === "CALM" ? "🟢" : coin.vol_shield === "STORM" ? "🔴" : "⚠"} {coin.vol_shield}
                </span>
              )}
            </div>
          </div>
        );
      })}

      {/* Footer */}
      <div style={{ padding: "8px 16px", background: "#060912", borderTop: "1px solid #1e293b" }}>
        <span style={{ fontSize: 10, color: "#1e293b", fontFamily: "monospace" }}>
          Auto-refreshes every 5 min · Data: Binance, MEXC, Gate.io · Not financial advice
        </span>
      </div>
    </div>
  );

  return (
    <div style={{ padding: "0 0 16px" }}>
      <Header />
      {/* Responsive: detect via CSS — render both, hide via CSS classes */}
      <div className="block md:hidden"><MobileList /></div>
      <div className="hidden md:block"><DesktopTable /></div>
    </div>
  );
}
