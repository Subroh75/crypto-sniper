import { useState, useEffect, useCallback, useRef } from "react";
import { DexTopCoins } from "@/components/DexTopCoins";
import { useScanData } from "@/lib/useScanData";

const BUY_THRESHOLD = 5; // gate-based scoring: BUY/STRONG BUY uses signal label check
const PAGE_SIZE = 20;
const POLL_MS = 60 * 60 * 1000; // hourly

export interface Signal {
  scanned_at?: number;
  symbol: string; score: number; max_score: number; signal: string;
  v: number; p: number; r: number; t: number; s: number;
  price: number; change: number; change_24h?: number;
  rsi: number; adx: number; rel_vol?: number;
  z_price?: number; z_vol?: number; z_return?: number; z_quality?: string;
  exchange?: string; exchange_label?: string; binance_listed?: boolean;
}

interface BuySignal { symbol: string; score: number; change: number; }
interface Props { onSelect: (symbol: string) => void; interval?: string; listMode?: boolean; onBuySignalsChange?: (signals: BuySignal[]) => void; onAllSignalsChange?: (signals: Signal[]) => void; }

const TH: React.CSSProperties = {
  fontSize: 8, fontWeight: 700, letterSpacing: "0.08em",
  color: "#334155", textTransform: "uppercase", padding: "6px 8px",
  textAlign: "left", whiteSpace: "nowrap",
};

type FilterTab = "buy" | "wait" | "all";
type SortCol = "score" | "change" | "rsi";

function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth < 480);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 480);
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);
  return isMobile;
}

function mapSignal(s: Record<string, unknown>): Signal {
  return {
    symbol: String(s.symbol ?? ""),
    score: Number(s.score ?? 0),
    max_score: Number(s.max_score ?? 13),
    signal: String(s.signal ?? ""),
    v: Number(s.v ?? 0),
    p: Number(s.p ?? 0),
    r: Number(s.r ?? 0),
    t: Number(s.t ?? 0),
    s: Number(s.s ?? 0),
    z_price: s.z_price != null ? Number(s.z_price) : undefined,
    z_vol: s.z_vol != null ? Number(s.z_vol) : undefined,
    z_return: s.z_return != null ? Number(s.z_return) : undefined,
    z_quality: s.z_quality ? String(s.z_quality) : undefined,
    price: Number(s.price ?? 0),
    change: Number(s.change ?? 0),
    rsi: Number(s.rsi ?? 0),
    adx: Number(s.adx ?? 0),
    rel_vol: Number(s.rel_vol ?? 0),
    exchange: String(s.exchange ?? "binance"),
    exchange_label: String(s.exchange_label ?? "BINANCE"),
    binance_listed: Boolean(s.binance_listed ?? true),
    scanned_at: s.scanned_at ? Number(s.scanned_at) : undefined,
  };
}

export function TopSignals({ onSelect, interval = "1h", onBuySignalsChange, onAllSignalsChange }: Props) {
  const [sortBy, setSortBy] = useState<SortCol>("score");
  const [tab, setTab] = useState<FilterTab>("buy");
  const [page, setPage] = useState(1);
  const [elapsed, setElapsed] = useState(0);
  const isMobile = useIsMobile();

  // Single shared /scan call — TopSignals and VolRadar use identical params
  // by default (interval=1d, min_score=1, max_coins=200, min_volume=500000),
  // so when both are mounted they share one request/response via scanCache
  // instead of each firing their own.
  const { data, error: scanError, loading, refetch } = useScanData(
    { interval: interval.toLowerCase(), min_score: 1, max_coins: 200, min_volume: 500000 },
    { pollMs: POLL_MS }
  );

  const signals: Signal[] = (data?.signals ?? []).map(mapSignal);
  const universe = data?.universe ?? signals.length;
  const scanned = data?.scanned ?? data?.universe ?? signals.length;
  const cacheAge = data?.cached ? (data?.cached_age_mins ?? null) : null;
  const error = scanError ? `Scan failed: ${scanError}` : null;
  const lastScan = data ? new Date().toLocaleTimeString() : "";

  // Elapsed-seconds counter for the "Scan" button label while loading.
  useEffect(() => {
    if (!loading) { setElapsed(0); return; }
    const start = Date.now();
    const t = setInterval(() => setElapsed(Math.floor((Date.now() - start) / 1000)), 1000);
    return () => clearInterval(t);
  }, [loading]);

  // Reset to page 1 whenever fresh data arrives, or the tab/sort changes.
  useEffect(() => { setPage(1); }, [data, tab, sortBy]);

  // Surface the latest signals to the parent (used to drive the
  // "auto-watch" buy-signal list and the volume-coin map elsewhere on the page).
  useEffect(() => {
    if (onBuySignalsChange) {
      const buyList = signals
        .filter(s => s.signal === "STRONG BUY" || s.signal === "BUY")
        .sort((a, b) => b.score - a.score)
        .map(s => ({ symbol: s.symbol, score: s.score, change: s.change }));
      onBuySignalsChange(buyList);
    }
    if (onAllSignalsChange) {
      onAllSignalsChange(signals);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  const scan = useCallback(() => refetch(true), [refetch]);

  const buyCount = signals.filter(s => s.signal === "STRONG BUY" || s.signal === "BUY").length;
  const waitCount = signals.length - buyCount;

  // Filter by tab
  const filtered = [...signals].filter(s => {
    if (tab === "buy") return s.signal === "STRONG BUY" || s.signal === "BUY";
    if (tab === "wait") return s.signal !== "STRONG BUY" && s.signal !== "BUY";
    return true;
  });

  // Sort
  const sorted = filtered.sort((a, b) => {
    if (sortBy === "score") return b.score - a.score;
    if (sortBy === "change") return (b.change ?? 0) - (a.change ?? 0);
    if (sortBy === "rsi") return b.rsi - a.rsi;
    return 0;
  });

  // Paginate
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
  const pageClamped = Math.min(page, totalPages);
  const pageRows = sorted.slice((pageClamped - 1) * PAGE_SIZE, pageClamped * PAGE_SIZE);

  const SortBtn = ({ col, label }: { col: SortCol; label: string }) => (
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

  const TabBtn = ({ id, label, count, activeColor }: { id: FilterTab; label: string; count: number; activeColor: string }) => (
    <button
      onClick={() => setTab(id)}
      style={{
        fontSize: 9, fontWeight: 700, letterSpacing: "0.06em",
        padding: "2px 8px", borderRadius: 3, cursor: "pointer",
        border: `1px solid ${tab === id ? activeColor : "#1e293b"}`,
        background: tab === id ? `${activeColor}18` : "transparent",
        color: tab === id ? activeColor : "#475569",
        transition: "all 0.15s",
      }}
    >
      {count} {label}
    </button>
  );

  return (
    <div style={{ marginBottom: 14 }}>
      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
        <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" as const }}>
          Green Coins Today — All Exchanges
        </span>
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

      {/* Filter tabs */}
      {signals.length > 0 && (
        <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
          <TabBtn id="buy" label="BUY" count={buyCount} activeColor="#22c55e" />
          <TabBtn id="wait" label="WAIT" count={waitCount} activeColor="#f59e0b" />
          <TabBtn id="all" label="ALL" count={signals.length} activeColor="#7c3aed" />
        </div>
      )}

      {/* Status bar */}
      {lastScan && (
        <div style={{ fontSize: 9, color: "#334155", marginBottom: 6 }}>
          {lastScan} · {signals.length} signals · {scanned > 0 ? `${scanned} vol-screened` : ""}{universe > 0 ? ` · ${universe} universe` : " · multi-exchange"}
          {sorted.length > 0 && pageClamped > 0 && (
            <span style={{ color: "#1e293b" }}>
              {" "}· showing {(pageClamped - 1) * PAGE_SIZE + 1}–{Math.min(pageClamped * PAGE_SIZE, sorted.length)} of {sorted.length}
            </span>
          )}
        </div>
      )}

      {/* Stale cache warning — scores may differ from manual analysis */}
      {cacheAge !== null && cacheAge >= 2 && (
        <div style={{ fontSize: 9, color: "#f59e0b", background: "#1a1200", border: "1px solid #451a00", borderRadius: 4, padding: "4px 8px", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
          <span>⚠</span>
          <span>Scores from {cacheAge}m ago — market conditions may have changed. Tap a coin for a live re-score.</span>
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
            Scoring green coins from {universe > 0 ? `${universe}-coin` : "multi-exchange"} universe…
          </div>
          <div style={{ fontSize: 9, color: "#334155" }}>Binance + MEXC + Gate.io · Vol-screened for speed · Usually 15–30s cold start, &lt;1s cached</div>
        </div>
      )}

      {/* Table */}
      {pageRows.length > 0 && (
        <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid #1e293b", opacity: loading ? 0.6 : 1, transition: "opacity 0.3s" }}>
          {/* Column headers */}
          <div style={{ display: "grid", gridTemplateColumns: isMobile ? "24px 1fr 52px 60px 64px" : "28px 1fr 60px 70px 80px", background: "#0a0f1e", borderBottom: "1px solid #1e293b" }}>
            <span style={TH}>#</span>
            <span style={TH}>Symbol</span>
            <SortBtn col="change" label="Chg%" />
            <span style={TH}>Signal</span>
            <span style={{ ...TH, textAlign: "center" as const }}>Action</span>
          </div>

          {/* Rows — only current page */}
          {pageRows.map((sig, i) => {
            const globalIndex = (pageClamped - 1) * PAGE_SIZE + i + 1;
            const chg = sig.change ?? 0;
            const rowBg = i % 2 === 0 ? "#060b17" : "#080e1c";
            // Signal tier drives left-border colour
            const qualBorder = sig.signal === "STRONG BUY" ? "3px solid #22c55e"
              : sig.signal === "BUY" ? "3px solid #22c55e"
              : "3px solid #1e293b";

            return (
              <button
                key={sig.symbol}
                onClick={() => onSelect(sig.symbol)}
                style={{
                  display: "grid",
                  gridTemplateColumns: isMobile ? "24px 1fr 52px 60px 64px" : "28px 1fr 60px 70px 80px",
                  width: "100%", background: rowBg,
                  border: "none", borderBottom: "1px solid #0f172a",
                  borderLeft: qualBorder,
                  cursor: "pointer", textAlign: "left" as const,
                  alignItems: "center", transition: "background 0.12s",
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#0d1a2e"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = rowBg; }}
              >
                {/* # */}
                <span style={{ fontSize: 9, color: "#2d3a50", fontWeight: 700, textAlign: "center" as const, padding: "9px 0" }}>
                  {globalIndex}
                </span>

                {/* Symbol + price + exchange badge */}
                <div style={{ display: "flex", flexDirection: "column" as const, gap: 1, padding: "9px 0 9px 4px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: "#f1f5f9", fontFamily: "monospace", letterSpacing: "0.04em" }}>
                      {sig.symbol}
                    </span>
                    {sig.exchange_label && sig.exchange_label !== "BINANCE" && (() => {
                      const exchColor = sig.exchange_label === "MEXC" ? { bg: "rgba(14,165,233,0.12)", border: "rgba(14,165,233,0.3)", text: "#38bdf8" }
                        : sig.exchange_label === "GATE" ? { bg: "rgba(168,85,247,0.12)", border: "rgba(168,85,247,0.3)", text: "#c084fc" }
                        : sig.exchange_label === "MULTI" ? { bg: "rgba(251,146,60,0.12)", border: "rgba(251,146,60,0.3)", text: "#fb923c" }
                        : null;
                      if (!exchColor) return null;
                      return (
                        <span style={{
                          fontSize: 7, fontWeight: 800, letterSpacing: "0.05em",
                          color: exchColor.text, background: exchColor.bg,
                          padding: "1px 4px", borderRadius: 3,
                          border: `1px solid ${exchColor.border}`,
                          whiteSpace: "nowrap" as const,
                        }}>
                          {sig.exchange_label}
                        </span>
                      );
                    })()}
                  </div>
                  <span style={{ fontSize: 8, color: "#334155" }}>
                    ${sig.price < 0.01 ? sig.price.toFixed(6) : sig.price < 1 ? sig.price.toFixed(4) : sig.price.toFixed(2)}
                    {sig.scanned_at && (() => {
                      const ageM = Math.round((Date.now() / 1000 - sig.scanned_at) / 60);
                      return ageM >= 2 ? <span style={{ color: "#f59e0b", marginLeft: 4 }}>{ageM}m ago</span> : null;
                    })()}
                  </span>
                </div>

                {/* Chg% */}
                <span style={{ fontSize: 11, fontWeight: 700, color: chg >= 0 ? "#22c55e" : "#ef4444", fontFamily: "monospace", padding: "0 4px" }}>
                  {chg >= 0 ? "+" : ""}{chg.toFixed(1)}%
                </span>

                {/* Signal tier badge */}
                <div style={{ padding: "0 2px" }}>
                  {(sig.signal === "STRONG BUY" || sig.signal === "BUY") ? (
                    <span style={{
                      fontSize: 8, fontWeight: 800, letterSpacing: "0.04em",
                      color: sig.signal === "STRONG BUY" ? "#22c55e" : "#22c55e",
                      background: "rgba(34,197,94,0.10)",
                      padding: "3px 5px", borderRadius: 3,
                      border: "1px solid rgba(34,197,94,0.25)",
                      whiteSpace: "nowrap" as const,
                    }}>
                      {sig.signal === "STRONG BUY" ? "STR BUY" : "BUY"}
                    </span>
                  ) : (
                    <span style={{ fontSize: 8, color: "#334155", fontFamily: "monospace" }}>—</span>
                  )}
                </div>

                {/* Analyse CTA */}
                <div style={{ textAlign: "center" as const, padding: "0 6px" }}>
                  <span style={{ fontSize: 8, fontWeight: 800, letterSpacing: "0.05em", color: "#a78bfa", background: "#1e0a3c", padding: "3px 7px", borderRadius: 3, border: "1px solid #4c1d95", whiteSpace: "nowrap" as const }}>
                    Analyse →
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 8 }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={pageClamped <= 1}
            style={{
              fontSize: 9, fontWeight: 700, padding: "3px 10px", borderRadius: 4,
              border: "1px solid #1e293b", background: "#0a0f1e",
              color: pageClamped <= 1 ? "#1e293b" : "#7c3aed",
              cursor: pageClamped <= 1 ? "not-allowed" : "pointer",
            }}
          >
            ← Prev
          </button>

          {/* Page number pills */}
          <div style={{ display: "flex", gap: 4 }}>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter(p => p === 1 || p === totalPages || Math.abs(p - pageClamped) <= 1)
              .reduce<(number | "…")[]>((acc, p, idx, arr) => {
                if (idx > 0 && typeof arr[idx - 1] === "number" && (p as number) - (arr[idx - 1] as number) > 1) acc.push("…");
                acc.push(p);
                return acc;
              }, [])
              .map((p, idx) =>
                p === "…" ? (
                  <span key={`ellipsis-${idx}`} style={{ fontSize: 9, color: "#334155", padding: "3px 4px" }}>…</span>
                ) : (
                  <button
                    key={p}
                    onClick={() => setPage(p as number)}
                    style={{
                      fontSize: 9, fontWeight: 700, padding: "3px 7px", borderRadius: 4,
                      border: `1px solid ${pageClamped === p ? "#7c3aed" : "#1e293b"}`,
                      background: pageClamped === p ? "#7c3aed22" : "#0a0f1e",
                      color: pageClamped === p ? "#7c3aed" : "#475569",
                      cursor: "pointer",
                    }}
                  >
                    {p}
                  </button>
                )
              )}
          </div>

          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={pageClamped >= totalPages}
            style={{
              fontSize: 9, fontWeight: 700, padding: "3px 10px", borderRadius: 4,
              border: "1px solid #1e293b", background: "#0a0f1e",
              color: pageClamped >= totalPages ? "#1e293b" : "#7c3aed",
              cursor: pageClamped >= totalPages ? "not-allowed" : "pointer",
            }}
          >
            Next →
          </button>
        </div>
      )}

      {/* DEX Top Coins — below CEX scanner */}
      <DexTopCoins />
    </div>
  );
}
