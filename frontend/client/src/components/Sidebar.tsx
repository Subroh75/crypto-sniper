// ─── Sidebar.tsx — Right column panels ──────────────────────────────────────
import { useState, useRef, useEffect, useCallback } from "react";
import { fmtPrice, fmtPct } from "@/lib/api";
import type { TradeSetup, Conviction, KeyLevel, WatchlistScore, AnalyseResponse } from "@/types/api";
import { PieChart, Pie, Cell, Tooltip as RechartTooltip, ResponsiveContainer } from "recharts";

// ── Shared card wrapper ───────────────────────────────────────────────────────
function SideCard({
  children,
  className = "",
  glow = false,
}: {
  children: React.ReactNode;
  className?: string;
  glow?: boolean;
}) {
  return (
    <div
      className={`rounded-xl border overflow-hidden mb-3 ${
        glow
          ? "border-purple/30 bg-surface-card"
          : "border-border/60 bg-surface-card"
      } ${className}`}
      style={glow ? { boxShadow: "0 0 0 1px rgba(124,92,252,0.1) inset" } : undefined}
    >
      {children}
    </div>
  );
}

function SideCardHeader({ num, icon, title, badge, src }: {
  num?: string; icon?: string; title: string;
  badge?: string; src?: string;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
      <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
        {num && <span className="text-purple">{num}</span>}
        {icon && <span>{icon}</span>}
        <span>{title}</span>
        {badge && (
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-orange/10 text-orange border border-orange/15 uppercase tracking-wide">
            {badge}
          </span>
        )}
      </div>
      {src && (
        <span className="text-[9px] font-mono text-text-muted/60 px-2 py-0.5 rounded bg-surface-2 border border-border/40">
          {src}
        </span>
      )}
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 1. TRADE SETUP
// ════════════════════════════════════════════════════════════════════════════
export function TradeSetupCard({ setup, close }: { setup: TradeSetup | null; close: number }) {
  if (!setup) return null;

  const dir = setup.direction;
  const dirColor = dir === "LONG" ? "text-teal" : dir === "SHORT" ? "text-red" : "text-text-muted";
  const dirBg    = dir === "LONG" ? "bg-teal/10 border-teal/20" : dir === "SHORT" ? "bg-red/10 border-red/20" : "bg-surface-2 border-border/50";

  const levels = [
    setup.target  && { label: "Target",    price: setup.target,  type: "target" as const },
    close > 0     && { label: "NOW",       price: close,         type: "current" as const },
    setup.entry   && { label: "Entry",     price: setup.entry,   type: "entry" as const },
    setup.stop    && { label: "Stop Loss", price: setup.stop,    type: "stop" as const },
  ].filter(Boolean) as Array<{ label: string; price: number; type: string }>;

  const levelColors: Record<string, string> = {
    target:  "text-teal",
    current: "text-text",
    entry:   "text-purple",
    stop:    "text-red",
  };

  const dotColors: Record<string, string> = {
    target:  "bg-teal shadow-teal/50",
    current: "bg-text-muted",
    entry:   "bg-purple shadow-purple/50",
    stop:    "bg-red shadow-red/50",
  };

  const stopDistPct = setup.stop_dist_pct ? Math.abs(setup.stop_dist_pct) : null;

  return (
    <SideCard glow>
      {/* Top gradient bar */}
      <div className="h-[2px] w-full" style={{
        background: "linear-gradient(90deg, #7c5cfc, #00d4aa)"
      }} />
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
          <span>⚡ TRADE SETUP</span>
        </div>
        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${dirBg} ${dirColor}`}>
          {dir === "LONG" ? "LONG ↑" : dir === "SHORT" ? "SHORT ↓" : "NO TRADE"}
        </span>
      </div>
      <div className="p-4">
        {/* Price level stack */}
        <div className="space-y-1 mb-4">
          {levels.map(({ label, price, type }) => (
            <div key={label} className={`flex items-center gap-2.5 px-2.5 py-2 rounded-lg border ${
              type === "current" ? "bg-white/3 border-border/40"
              : type === "target" ? "bg-teal/4 border-teal/10"
              : type === "stop"   ? "bg-red/4 border-red/10"
              : "bg-purple/5 border-purple/15"
            }`}>
              <div className={`w-[6px] h-[6px] rounded-full flex-shrink-0 shadow ${dotColors[type] || "bg-text-muted"}`} />
              <span className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide min-w-[55px]">{label}</span>
              <span className={`text-[11px] font-mono font-bold ml-auto ${levelColors[type] || "text-text"} ${type === "current" ? "text-[13px]" : ""}`}>
                {fmtPrice(price)}
              </span>
            </div>
          ))}
        </div>

        {/* Metrics grid */}
        <div className="grid grid-cols-2 gap-1.5 mb-3">
          {[
            { label: "R/R Ratio",   value: setup.rr_ratio != null ? `${setup.rr_ratio.toFixed(2)}×` : "—", color: setup.rr_ratio && setup.rr_ratio >= 1.5 ? "text-teal" : "text-red" },
            { label: "Stop Dist",   value: stopDistPct ? `${stopDistPct.toFixed(2)}%` : "—", color: "text-text" },
            { label: "ATR",         value: fmtPrice(setup.atr), color: "text-text" },
            { label: "Direction",   value: dir, color: dirColor },
          ].map(({ label, value, color }) => (
            <div key={label} className="bg-surface-2 rounded-lg p-2 border border-border/40">
              <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">{label}</div>
              <div className={`text-[14px] font-mono font-bold ${color}`}>{value}</div>
            </div>
          ))}
        </div>

        {/* Position sizing helper */}
        <div className="bg-surface-2 rounded-lg border border-border/40 p-3 mb-3">
          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-2">Position Sizing (1% Risk)</div>
          {stopDistPct && close > 0 ? (
            <div className="space-y-1">
              {[
                ["Risk Amount",    "$100 (1% of $10K)"],
                ["Stop Distance",  `${stopDistPct ? (close * stopDistPct / 100).toFixed(0) : "—"}`],
                ["Position Size",  `${stopDistPct ? (100 / (close * stopDistPct / 100)).toFixed(4) : "—"} BTC`],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between text-[11px] font-mono">
                  <span className="text-text-muted/70">{k}</span>
                  <span className="text-text font-bold">{v}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-[10px] font-mono text-text-muted/60">No trade setup — score below threshold</div>
          )}
        </div>

        {/* Gate warning */}
        {(!setup.entry) && (
          <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-red/5 border border-red/15 text-[10px] font-mono text-red">
            <span className="text-sm flex-shrink-0">⛔</span>
            <span>Score below threshold — await signal ≥ 5 before entering</span>
          </div>
        )}
      </div>
    </SideCard>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 2. CONVICTION METER
// ════════════════════════════════════════════════════════════════════════════
export function ConvictionMeter({ conviction }: { conviction: Conviction | null }) {
  if (!conviction) return null;

  const { bull_pct, bear_pct, bull_signals, bear_signals } = conviction;

  const actionColor =
    bull_pct >= 60 ? "text-teal" :
    bear_pct >= 60 ? "text-red"  : "text-text-muted";

  const actionText =
    bull_pct >= 70 ? "STRONG BULL — trade with confidence" :
    bull_pct >= 55 ? "LEAN BULL — proceed with caution" :
    bear_pct >= 70 ? "STRONG BEAR — avoid longs" :
    bear_pct >= 55 ? "LEAN BEAR — risk is elevated" :
    "MIXED SIGNALS — wait for clarity";

  return (
    <SideCard>
      <SideCardHeader icon="🎯" title="CONVICTION METER" />
      <div className="p-4">
        {/* Bull bar */}
        <div className="mb-3">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-[10px] font-mono font-bold text-teal uppercase tracking-wide">🐂 Bull</span>
            <span className="text-[11px] font-mono font-bold text-teal">{bull_pct}%</span>
          </div>
          <div className="w-full h-2 bg-surface-2 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width: `${bull_pct}%`,
                background: "linear-gradient(90deg, rgba(0,212,170,0.4), #00d4aa)",
              }}
            />
          </div>
          {bull_signals.length > 0 && (
            <div className="text-[9px] font-mono text-text-muted/60 mt-1 truncate">
              {bull_signals[0]}
            </div>
          )}
        </div>

        {/* Bear bar */}
        <div className="mb-4">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-[10px] font-mono font-bold text-red uppercase tracking-wide">🐻 Bear</span>
            <span className="text-[11px] font-mono font-bold text-red">{bear_pct}%</span>
          </div>
          <div className="w-full h-2 bg-surface-2 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-700"
              style={{
                width: `${bear_pct}%`,
                background: "linear-gradient(90deg, rgba(255,61,90,0.4), #ff3d5a)",
              }}
            />
          </div>
          {bear_signals.length > 0 && (
            <div className="text-[9px] font-mono text-text-muted/60 mt-1 truncate">
              {bear_signals[0]}
            </div>
          )}
        </div>

        {/* R/R visual */}
        <div className="bg-surface-2 rounded-lg border border-border/40 p-3 mb-3">
          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-2">Signal balance</div>
          <div className="flex items-center gap-2">
            <div
              className="h-5 rounded flex items-center px-2"
              style={{ width: `${bull_pct}%`, background: "rgba(0,212,170,0.25)", minWidth: 20 }}
            >
              <span className="text-[9px] font-mono font-bold text-teal">{bull_pct}%</span>
            </div>
            <div
              className="h-5 rounded flex items-center px-2"
              style={{ width: `${bear_pct}%`, background: "rgba(255,61,90,0.25)", minWidth: 20 }}
            >
              <span className="text-[9px] font-mono font-bold text-red">{bear_pct}%</span>
            </div>
          </div>
        </div>

        {/* Action verdict */}
        <div className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-[10px] font-mono font-bold ${
          bear_pct >= 60
            ? "bg-red/5 border-red/15 text-red"
            : bull_pct >= 60
              ? "bg-teal/5 border-teal/15 text-teal"
              : "bg-surface-2 border-border/40 text-text-muted"
        }`}>
          <span className="text-sm flex-shrink-0">
            {bear_pct >= 60 ? "⛔" : bull_pct >= 60 ? "✅" : "⏳"}
          </span>
          <span>{actionText}</span>
        </div>
      </div>
    </SideCard>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 3. KEY PRICE LEVELS
// ════════════════════════════════════════════════════════════════════════════
export function KeyLevelsCard({ levels }: { levels: KeyLevel[] }) {
  if (!levels || levels.length === 0) return null;

  const kindStyle = {
    resistance: { text: "text-red",     bg: "bg-red/4 border-red/8" },
    dynamic:    { text: "text-teal",    bg: "bg-teal/4 border-teal/8" },
    current:    { text: "text-text",    bg: "bg-white/3 border-border/40" },
    support:    { text: "text-teal",    bg: "bg-teal/4 border-teal/8" },
    stop:       { text: "text-red",     bg: "bg-red/4 border-red/8" },
    target:     { text: "text-teal",    bg: "bg-teal/4 border-teal/8" },
  } as Record<string, { text: string; bg: string }>;

  return (
    <SideCard>
      <SideCardHeader icon="📍" title="KEY PRICE LEVELS" />
      <div className="p-3 space-y-1">
        {levels.map((level, i) => {
          const style = kindStyle[level.kind] ?? kindStyle.dynamic;
          const isCurrent = level.kind === "current";
          return (
            <div key={i} className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border ${style.bg}`}>
              <span className={`text-[9px] font-mono text-text-muted/70 uppercase tracking-wide min-w-[72px]`}>
                {level.label}
              </span>
              <span className={`text-[11px] font-mono font-bold ml-auto ${style.text} ${isCurrent ? "text-[13px] text-text" : ""}`}>
                {fmtPrice(level.price)}
              </span>
              {!isCurrent && (
                <span className={`text-[9px] font-mono ${level.dist_pct >= 0 ? "text-teal/60" : "text-red/60"}`}>
                  {level.dist_pct != null ? (level.dist_pct >= 0 ? "+" : "") + level.dist_pct.toFixed(2) + "%" : "—"}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </SideCard>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 4. WATCHLIST SCANNER (editable)
// ════════════════════════════════════════════════════════════════════════════
const PILL_STYLE: Record<string, string> = {
  BUY:   "bg-teal/10 text-teal border-teal/20",
  HOLD:  "bg-text-muted/10 text-text-muted border-border/40",
  WATCH: "bg-amber/10 text-amber border-amber/20",
};

// Top-100 coin list fetched from CoinGecko (CORS-open, no key needed)
type CgCoin = { symbol: string; name: string; change_24h: number; rank: number };

function useTop100() {
  const [coins, setCoins]   = useState<CgCoin[]>([]);
  const [loading, setLoading] = useState(false);
  const fetched = useRef(false);

  const fetch100 = useCallback(async () => {
    if (fetched.current) return;
    fetched.current = true;
    setLoading(true);
    try {
      const pages = await Promise.all([1, 2].map(page =>
        fetch(
          `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=50&page=${page}&sparkline=false`,
          { signal: AbortSignal.timeout(10000) }
        ).then(r => r.json()).catch(() => [])
      ));
      const all: CgCoin[] = [...pages[0], ...pages[1]]
        .filter(Boolean)
        .map((c: Record<string, unknown>, i: number) => ({
          symbol:    (c.symbol as string ?? "").toUpperCase(),
          name:      (c.name   as string ?? ""),
          change_24h: (c.price_change_percentage_24h as number ?? 0),
          rank:      i + 1,
        }));
      setCoins(all);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, []);

  return { coins, loading, fetch100 };
}

export function WatchlistCard({
  scores,
  loading,
  onSelect,
  currentSymbol,
  onAdd,
  onRemove,
}: {
  scores: WatchlistScore[];
  loading: boolean;
  onSelect: (sym: string) => void;
  currentSymbol: string;
  onAdd?: (sym: string) => void;
  onRemove?: (sym: string) => void;
}) {
  const [addMode, setAddMode] = useState(false);
  const [query,   setQuery]   = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const { coins: top100, loading: top100Loading, fetch100 } = useTop100();

  // Kick off top-100 fetch when picker opens
  useEffect(() => {
    if (addMode) {
      fetch100();
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery("");
    }
  }, [addMode, fetch100]);

  const alreadyAdded = new Set(scores.map(s => s.symbol));

  // Filter top-100 by query; also surface custom entry if not in list
  const q = query.trim().toUpperCase();
  const filtered = top100.filter(c =>
    !q ||
    c.symbol.startsWith(q) ||
    c.name.toUpperCase().includes(q)
  );
  // If user typed something not in top-100 list, show it as a manual option at top
  const customEntry = q && !top100.some(c => c.symbol === q)
    ? { symbol: q, name: "Custom", change_24h: 0, rank: 0 }
    : null;
  const displayList = customEntry ? [customEntry, ...filtered] : filtered;

  const handleAdd = (sym: string) => {
    if (sym && onAdd) {
      onAdd(sym);
      setAddMode(false);
      setQuery("");
    }
  };

  return (
    <SideCard>
      <SideCardHeader icon="👁" title="WATCHLIST" badge="LIVE" />
      <div className="p-3">
        <div className="space-y-1.5">
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 bg-surface-2 rounded-lg animate-pulse border border-border/30" />
            ))
          ) : scores.length === 0 ? (
            <div className="text-center text-[10px] font-mono text-text-muted/60 py-4">
              Add coins to your watchlist
            </div>
          ) : (
            scores.map((s) => (
              <div key={s.symbol} className="group relative">
                <button
                  onClick={() => onSelect(s.symbol)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border transition-all text-left ${
                    s.symbol === currentSymbol
                      ? "border-purple/40 bg-purple/5"
                      : "border-border/40 bg-surface-2 hover:border-purple/30"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className={`text-[13px] font-mono font-black ${
                      s.change_24h >= 0 ? "text-teal" : s.change_24h < -3 ? "text-red" : "text-text"
                    }`}>{s.symbol}</span>
                    <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border ${PILL_STYLE[s.signal] ?? PILL_STYLE.HOLD}`}>
                      {s.signal === "BUY" ? "⚡ " : ""}{s.signal}
                    </span>
                  </div>
                  <div className="text-right">
                    <div className="text-[11px] font-mono font-bold text-text">{fmtPrice(s.price)}</div>
                    <div className={`text-[10px] font-mono ${s.change_24h >= 0 ? "text-teal" : "text-red"}`}>
                      {s.change_24h != null ? (s.change_24h >= 0 ? "▲" : "▼") + " " + Math.abs(s.change_24h).toFixed(2) + "%" : "—"}
                    </div>
                  </div>
                </button>
                {/* Remove button — appears on hover */}
                {onRemove && (
                  <button
                    onClick={e => { e.stopPropagation(); onRemove(s.symbol); }}
                    className="absolute right-1 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 w-5 h-5 flex items-center justify-center rounded text-[10px] text-red/70 hover:text-red hover:bg-red/10 transition-all"
                    title={`Remove ${s.symbol}`}
                  >
                    ×
                  </button>
                )}
              </div>
            ))
          )}
        </div>

        {/* Add coin — searchable top-100 picker */}
        {addMode ? (
          <div className="mt-2">
            {/* Search input */}
            <div className="flex gap-1.5 mb-2">
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value.toUpperCase())}
                onKeyDown={e => {
                  if (e.key === "Escape") { setAddMode(false); }
                  if (e.key === "Enter" && displayList.length > 0) {
                    const first = displayList.find(c => !alreadyAdded.has(c.symbol));
                    if (first) handleAdd(first.symbol);
                  }
                }}
                placeholder="Search by name or symbol…"
                maxLength={20}
                className="flex-1 min-w-0 px-2.5 py-1.5 rounded-lg border border-purple/40 bg-surface-2 text-text text-[11px] font-mono placeholder:text-text-muted/40 focus:outline-none"
              />
              <button
                onClick={() => setAddMode(false)}
                className="px-2 py-1.5 rounded-lg text-[11px] font-mono text-text-muted/60 border border-border/40 hover:border-border/70 transition-all"
              >
                ✕
              </button>
            </div>

            {/* Scrollable coin list */}
            <div className="rounded-lg border border-border/40 bg-surface-2 overflow-hidden">
              {/* Header */}
              <div className="flex items-center gap-2 px-2.5 py-1.5 border-b border-border/30 bg-surface-offset">
                <span className="text-[8px] font-mono font-bold text-text-muted/40 uppercase tracking-widest flex-1">
                  {top100Loading ? "Loading top 100…" : `Top 100 by market cap${q ? ` · ${displayList.length} match` : ""}`}
                </span>
              </div>
              <div className="max-h-[220px] overflow-y-auto">
                {top100Loading ? (
                  Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="h-8 mx-2 my-1 bg-surface-offset rounded animate-pulse" />
                  ))
                ) : displayList.length === 0 ? (
                  <div className="text-center text-[10px] font-mono text-text-muted/50 py-4">No coins found</div>
                ) : (
                  displayList.map(coin => {
                    const added = alreadyAdded.has(coin.symbol);
                    return (
                      <button
                        key={coin.symbol}
                        onClick={() => !added && handleAdd(coin.symbol)}
                        disabled={added}
                        className={`w-full flex items-center justify-between px-2.5 py-1.5 border-b border-border/20 last:border-0 transition-all text-left ${
                          added
                            ? "opacity-40 cursor-default"
                            : "hover:bg-purple/5 hover:border-purple/10"
                        }`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          {coin.rank > 0 && (
                            <span className="text-[8px] font-mono text-text-muted/30 w-4 shrink-0 text-right">{coin.rank}</span>
                          )}
                          <span className="text-[11px] font-mono font-black text-text shrink-0">{coin.symbol}</span>
                          <span className="text-[9px] font-mono text-text-muted/50 truncate">{coin.name}</span>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          {coin.change_24h !== 0 && (
                            <span className={`text-[9px] font-mono ${
                              coin.change_24h >= 0 ? "text-teal" : "text-red"
                            }`}>
                              {coin.change_24h >= 0 ? "+" : ""}{coin.change_24h.toFixed(1)}%
                            </span>
                          )}
                          {added ? (
                            <span className="text-[8px] font-mono text-text-muted/40">Added</span>
                          ) : (
                            <span className="text-[9px] font-mono text-purple/60">+</span>
                          )}
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        ) : (
          <button
            onClick={() => setAddMode(true)}
            className="w-full mt-2 py-2 text-[10px] font-mono text-text-muted/60 border border-dashed border-border/40 rounded-lg hover:border-purple/40 hover:text-purple transition-all"
          >
            + Add coin
          </button>
        )}
      </div>
    </SideCard>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 5. SUBSCRIBE CTA — crypto payments
// ════════════════════════════════════════════════════════════════════════════
const COINS = [
  { sym: "USDT", net: "SOL", icon: "💵" },
  { sym: "USDC", net: "SOL", icon: "💵" },
  { sym: "BTC",  net: "BTC", icon: "₿"  },
  { sym: "ETH",  net: "ETH", icon: "⟠"  },
] as const;

const COIN_DATA: Record<string, { addr: string; amount: string; chain: string }> = {
  USDT: { addr: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU", amount: "29.00 USDT", chain: "SOLANA NETWORK" },
  USDC: { addr: "9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM", amount: "29.00 USDC", chain: "SOLANA NETWORK" },
  BTC:  { addr: "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",  amount: "0.000372 BTC", chain: "BITCOIN NETWORK" },
  ETH:  { addr: "0x71C7656EC7ab88b098defB751B7401B5f6d8976F",   amount: "0.01598 ETH",  chain: "ETHEREUM NETWORK" },
};

export function SubscribeCard() {
  const [plan,        setPlan]        = useState<"monthly" | "annual">("monthly");
  const [selectedCoin, setSelectedCoin] = useState<string>("USDT");
  const [copied,      setCopied]      = useState(false);

  const coin = COIN_DATA[selectedCoin];

  const copyAddr = () => {
    navigator.clipboard.writeText(coin.addr).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="rounded-xl overflow-hidden mb-3 border border-purple/30 relative"
         style={{ background: "var(--color-surface-card)" }}>
      {/* Rainbow top bar */}
      <div className="h-[3px]" style={{ background: "linear-gradient(90deg, #7c5cfc, #00d4aa, #ff8c42)" }} />
      {/* Radial glow */}
      <div className="absolute inset-0 pointer-events-none"
           style={{ background: "radial-gradient(ellipse at top, rgba(124,92,252,0.08), transparent 65%)" }} />

      <div className="p-4 relative z-10">
        <div className="text-center mb-4">
          <div className="text-2xl mb-2">⚡</div>
          <div className="text-[15px] font-black tracking-tight text-text mb-1">
            Unlock the Full Signal Engine
          </div>
          <div className="text-[11px] text-text-muted leading-snug">
            Free: 5 analyses/day · Pro: unlimited + live alerts + whale tracking
          </div>
        </div>

        {/* Pricing tabs */}
        <div className="grid grid-cols-2 gap-1.5 mb-4">
          {(["monthly","annual"] as const).map(p => (
            <button
              key={p}
              onClick={() => setPlan(p)}
              className={`relative rounded-lg p-2.5 border text-center transition-all ${
                plan === p ? "border-purple bg-purple/8" : "border-border/50 bg-surface-2"
              }`}
            >
              {p === "annual" && (
                <div className="absolute -top-2 right-1.5 text-[8px] font-mono font-black bg-teal text-black px-1.5 py-0.5 rounded">
                  SAVE 28%
                </div>
              )}
              <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-0.5">
                {p === "monthly" ? "Monthly" : "Annual"}
              </div>
              <div className="text-[18px] font-mono font-black text-text">
                {p === "monthly" ? "$29" : "$249"}
              </div>
              <div className="text-[9px] font-mono text-text-muted">
                USDT / {p === "monthly" ? "month" : "year"}
              </div>
            </button>
          ))}
        </div>

        {/* Features */}
        <div className="space-y-1.5 mb-4">
          {[
            ["Unlimited coin analyses",        false],
            ["All timeframes incl. 1m/5m",     true],
            ["Real-time Telegram alerts",       true],
            ["Whale tracker — on-chain data",   false],
            ["Perplexity deep research",        false],
            ["Watchlist scanner — 20 coins",    false],
            ["Fear & Greed + CryptoPanic",     false],
            ["PDF export + trade history",      false],
          ].map(([feature, isPro]) => (
            <div key={feature as string} className="flex items-center gap-2 text-[10px] font-mono text-text-muted">
              <span className="text-teal flex-shrink-0">✓</span>
              <span>{feature as string}</span>
              {isPro && (
                <span className="ml-auto text-[8px] font-bold px-1.5 py-0.5 rounded bg-orange/10 text-orange border border-orange/15">
                  PRO
                </span>
              )}
            </div>
          ))}
        </div>

        {/* Coin selector */}
        <div className="mb-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[9px] font-mono text-text-muted/70 uppercase tracking-[0.1em]">Pay with</span>
            <div className="flex-1 h-px bg-border/40" />
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            {COINS.map(({ sym, net, icon }) => (
              <button
                key={sym}
                onClick={() => setSelectedCoin(sym)}
                className={`flex flex-col items-center gap-1 py-2 px-1 rounded-lg border transition-all ${
                  selectedCoin === sym
                    ? "border-teal bg-teal/6"
                    : "border-border/50 bg-surface-2 hover:border-purple/30"
                }`}
              >
                <span className="text-[15px]">{icon}</span>
                <span className="text-[9px] font-mono font-black text-text">{sym}</span>
                <span className="text-[7px] font-mono text-text-muted/60">{net}</span>
              </button>
            ))}
          </div>
          <div className="flex gap-1.5 mt-1.5 flex-wrap">
            {["SOL","BNB","MATIC","LTC"].map(s => (
              <span key={s} className="text-[9px] font-mono px-2 py-0.5 rounded border border-border/40 bg-surface-2 text-text-muted/70 cursor-pointer hover:border-text-muted">
                {s}
              </span>
            ))}
            <span className="text-[9px] font-mono px-2 py-0.5 rounded border border-border/40 bg-surface-2 text-text-muted/60">
              +340 more
            </span>
          </div>
        </div>

        {/* Payment address */}
        <div className="bg-surface-2 rounded-lg border border-border/50 p-3 mb-3">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide">
              Send to this address
            </span>
            <span className="text-[8px] font-mono font-bold px-1.5 py-0.5 rounded bg-teal/10 text-teal border border-teal/15">
              {coin.chain}
            </span>
          </div>
          <div
            onClick={copyAddr}
            className="text-[9px] font-mono text-text bg-surface-offset rounded px-2 py-2 border border-border/40 cursor-pointer hover:border-purple/40 break-all leading-relaxed mb-2 transition-all"
            title="Click to copy"
          >
            {coin.addr}
          </div>
          <div className="flex items-center justify-between">
            <span className="text-[13px] font-mono font-black text-teal">{coin.amount}</span>
            <button onClick={copyAddr} className="text-[9px] font-mono font-bold px-2.5 py-1.5 rounded bg-purple/10 border border-purple/20 text-purple hover:bg-purple/18 transition-all">
              {copied ? "✓ Copied!" : "⎘ Copy address"}
            </button>
          </div>
        </div>

        {/* QR + instructions */}
        <div className="flex items-start gap-3 mb-4">
          <div className="w-16 h-16 flex-shrink-0 bg-white rounded flex items-center justify-center text-[8px] text-gray-800 font-mono text-center leading-snug p-1">
            QR<br />{coin.amount}<br />{selectedCoin}
          </div>
          <div className="text-[10px] font-mono text-text-muted leading-relaxed">
            <strong className="text-text">1.</strong> Open your {selectedCoin} wallet<br />
            <strong className="text-text">2.</strong> Send exactly <strong className="text-text">{coin.amount}</strong><br />
            <strong className="text-text">3.</strong> Pro activates <strong className="text-teal">within 60s</strong><br />
            <strong className="text-text">4.</strong> No account — wallet = identity
          </div>
        </div>

        {/* CTA button */}
        <button className="w-full py-3 rounded-lg font-sans font-black text-[13px] text-white flex items-center justify-center gap-2 transition-all"
                style={{
                  background: "linear-gradient(135deg, #7c5cfc, #5b3fd4)",
                  boxShadow: "0 4px 24px rgba(124,92,252,0.45)",
                }}>
          <span className="text-base">⚡</span>
          <span>I've sent payment — Activate Pro</span>
        </button>

        {/* Trust row */}
        <div className="flex items-center justify-center gap-4 mt-3 flex-wrap">
          {[["🔒","Non-custodial"],["⚡","Instant"],["🌍","No KYC"],["↩","Cancel anytime"]].map(([ic,txt]) => (
            <div key={txt} className="flex items-center gap-1 text-[9px] font-mono text-text-muted/60">
              <span>{ic}</span><span>{txt}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 6. EXPORT REPORT
// ════════════════════════════════════════════════════════════════════════════
export function ExportCard({
  symbol,
  interval,
  onRerun,
  onExport,
  exporting,
}: {
  symbol: string;
  interval: string;
  onRerun: () => void;
  onExport: () => void;
  exporting: boolean;
}) {
  return (
    <SideCard glow>
      <div className="h-[2px]" style={{ background: "linear-gradient(90deg, #7c5cfc, #00d4aa)" }} />
      <SideCardHeader num="10" icon="📄" title="EXPORT REPORT" />
      <div className="p-4">
        <div className="text-[10px] font-mono text-text-muted leading-relaxed mb-4">
          Includes: signal · components · chart · on-chain · forecast · agents · trending · news · macro · deep research
          <br />
          <span className="text-text-muted/50">{symbol}/USDT · {interval} · {new Date().toUTCString()}</span>
        </div>
        <div className="space-y-2">
          <button
            onClick={onExport}
            disabled={exporting}
            className="w-full py-3 rounded-lg font-mono font-black text-[13px] text-white flex items-center justify-center gap-2 disabled:opacity-60 transition-all"
            style={{
              background: exporting ? "#3a2a8a" : "linear-gradient(135deg, #7c5cfc, #5b3fd4)",
              boxShadow: exporting ? "none" : "0 4px 16px rgba(124,92,252,0.3)",
            }}
          >
            {exporting ? "⏳ Generating…" : "⬇ Download Full PDF Report"}
          </button>
          <button
            onClick={onRerun}
            className="w-full py-2.5 rounded-lg font-mono text-[11px] text-text-muted border border-border/50 hover:border-purple/40 hover:text-text transition-all flex items-center justify-center gap-2"
          >
            ↻ Re-run Analysis · {symbol} · {interval}
          </button>
        </div>
        <div className="flex justify-center gap-4 mt-3">
          {[["✓","Shareable link"],["✓","Pro feature"],["✓","Auto-updates"]].map(([ic,txt]) => (
            <div key={txt} className="flex items-center gap-1 text-[9px] font-mono text-text-muted/60">
              <span className="text-teal">{ic}</span><span>{txt}</span>
            </div>
          ))}
        </div>
      </div>
    </SideCard>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 11. BASKET SCANNER
// ════════════════════════════════════════════════════════════════════════════
const BASKETS: Array<{ id: string; label: string; icon: string; desc: string; symbols: string[] }> = [
  {
    id: "bluechip",
    label: "Blue Chip",
    icon: "💎",
    desc: "Top 6 by market cap",
    symbols: ["BTC", "ETH", "BNB", "SOL", "XRP", "ADA"],
  },
  {
    id: "ai",
    label: "AI Tokens",
    icon: "🤖",
    desc: "Artificial intelligence narrative",
    symbols: ["TAO", "RENDER", "FET", "AGIX", "OCEAN", "WLD", "AKT", "NMR"],
  },
  {
    id: "l2",
    label: "Layer 2",
    icon: "⚡",
    desc: "Ethereum scaling solutions",
    symbols: ["ARB", "OP", "MNT", "POL", "STRK", "METIS", "ZK"],
  },
  {
    id: "meme",
    label: "Meme",
    icon: "🐸",
    desc: "Meme supercycle basket",
    symbols: ["DOGE", "SHIB", "PEPE", "WIF", "BONK", "FLOKI", "BRETT"],
  },
  {
    id: "defi",
    label: "DeFi",
    icon: "🔗",
    desc: "Decentralised finance",
    symbols: ["UNI", "AAVE", "MKR", "CRV", "COMP", "LDO", "JUP", "GMX"],
  },
  {
    id: "solana",
    label: "Solana Eco",
    icon: "🌐",
    desc: "Solana ecosystem tokens",
    symbols: ["SOL", "RAY", "PYTH", "JUP", "BONK", "WIF", "JTO"],
  },
  {
    id: "btceco",
    label: "BTC Eco",
    icon: "₿",
    desc: "Bitcoin ecosystem tokens",
    symbols: ["BTC", "STX", "ORDI", "RUNE", "BCH", "ICP"],
  },
  {
    id: "rwa",
    label: "RWA",
    icon: "🏦",
    desc: "Real world assets",
    symbols: ["LINK", "ONDO", "MKR", "AVAX", "POLYX", "CFG"],
  },
];

// CoinGecko ID map for historical price fetching
const CG_BASKET_ID: Record<string, string> = {
  BTC:"bitcoin", ETH:"ethereum", BNB:"binancecoin", SOL:"solana",
  XRP:"ripple", ADA:"cardano", TAO:"bittensor", RENDER:"render-token",
  FET:"fetch-ai", AGIX:"singularitynet", OCEAN:"ocean-protocol",
  WLD:"worldcoin-wld", AKT:"akash-network", NMR:"numeraire",
  ARB:"arbitrum", OP:"optimism", MNT:"mantle", POL:"matic-network",
  STRK:"starknet", METIS:"metis-token", ZK:"zksync",
  DOGE:"dogecoin", SHIB:"shiba-inu", PEPE:"pepe", WIF:"dogwifhat",
  BONK:"bonk", FLOKI:"floki", BRETT:"brett",
  UNI:"uniswap", AAVE:"aave", MKR:"maker", CRV:"curve-dao-token",
  COMP:"compound-governance-token", LDO:"lido-dao",
  JUP:"jupiter-exchange-solana", GMX:"gmx",
  RAY:"raydium", PYTH:"pyth-network", JTO:"jito-governance-token",
  STX:"blockstack", ORDI:"ordinals", RUNE:"thorchain",
  BCH:"bitcoin-cash", ICP:"internet-computer",
  LINK:"chainlink", ONDO:"ondo-finance", AVAX:"avalanche-2",
  POLYX:"polymesh-network", CFG:"centrifuge",
};

// Binance symbols that need non-standard USDT pair names
const BINANCE_SYM_MAP: Record<string, string> = {
  "TAO": "TAOUSDT",
  "RENDER": "RENDERUSDT",
  "STX": "STXUSDT",
  "ORDI": "ORDIUSDT",
  "RUNE": "RUNEUSDT",
  "AKT": "AKTUSDT",
  "CFG": "CFGUSDT",
  "MNT": "MNTUSDT",
  "ZK": "ZKUSDT",
  "STRK": "STRKUSDT",
  "AGIX": "AGIXUSDT",
  "GMX": "GMXUSDT",
  "RAY": "RAYUSDT",
  "PYTH": "PYTHUSDT",
};

// Per-slot colour palette — vivid, distinct regardless of score
const SLOT_COLORS = [
  "#7c3aed", // purple
  "#22c55e", // teal
  "#f59e0b", // amber
  "#3b82f6", // blue
  "#ef4444", // red
  "#ec4899", // pink
  "#06b6d4", // cyan
  "#a3e635", // lime
  "#f97316", // orange
  "#8b5cf6", // violet
];

function scoreColor(score: number, max: number): string {
  const pct = score / max;
  if (pct >= 0.65) return "#22c55e";
  if (pct >= 0.40) return "#f59e0b";
  return "#64748b";
}

type BasketResult = {
  symbol: string;
  score:  number;
  max:    number;
  label:  string;
  change: number;
  price:  number;
  done:   boolean;
  error:  boolean;
};

type ReturnPeriod = "1W" | "1M" | "3M";

const PERIOD_DAYS: Record<ReturnPeriod, number> = { "1W": 7, "1M": 30, "3M": 90 };

// Fetch via Binance.US klines — fast, reliable, no rate limit issues
async function fetchFromBinance(symbol: string, days: number): Promise<number | null> {
  const sym = symbol.toUpperCase();
  const pair = BINANCE_SYM_MAP[sym] ?? `${sym}USDT`;
  const limit = days + 2;
  try {
    const r = await fetch(
      `https://api.binance.us/api/v3/klines?symbol=${pair}&interval=1d&limit=${limit}`,
      { signal: AbortSignal.timeout(8000) }
    );
    if (!r.ok) return null;
    const candles: [string,string,string,string,string,...unknown[]][] = await r.json();
    if (!Array.isArray(candles) || candles.length < 2) return null;
    // Use open of first candle as entry (= price N days ago), close of last as exit
    const entry = parseFloat(candles[0][1]);  // open
    const exit  = parseFloat(candles[candles.length - 1][4]); // close
    if (!entry || entry === 0) return null;
    return ((exit - entry) / entry) * 100;
  } catch {
    return null;
  }
}

// Fallback: CoinGecko market_chart (sequential to avoid 429)
async function fetchFromCoinGecko(symbol: string, days: number): Promise<number | null> {
  const cgId = CG_BASKET_ID[symbol.toUpperCase()];
  if (!cgId) return null;
  try {
    const r = await fetch(
      `https://api.coingecko.com/api/v3/coins/${cgId}/market_chart?vs_currency=usd&days=${days}&interval=daily`,
      { signal: AbortSignal.timeout(10000) }
    );
    if (!r.ok) return null;
    const j = await r.json();
    const prices: [number, number][] = j.prices ?? [];
    if (prices.length < 2) return null;
    const entry = prices[0][1];
    const exit  = prices[prices.length - 1][1];
    if (!entry || entry === 0) return null;
    return ((exit - entry) / entry) * 100;
  } catch {
    return null;
  }
}

async function fetchHistoricalReturn(symbol: string, days: number): Promise<number | null> {
  // Try Binance.US first (fastest, no rate limits)
  const binanceResult = await fetchFromBinance(symbol, days);
  if (binanceResult !== null) return binanceResult;
  // Fall back to CoinGecko
  return fetchFromCoinGecko(symbol, days);
}

const RENDER_BASE = "https://crypto-sniper.onrender.com";

export function BasketScanner({
  interval,
  onSelect,
}: {
  interval: string;
  onSelect: (sym: string) => void;
}) {
  const [activeBasket, setActiveBasket] = useState<string | null>(null);
  const [results,      setResults]      = useState<BasketResult[]>([]);
  const [scanning,     setScanning]     = useState(false);
  const [done,         setDone]         = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Returns calculator state
  const [calcAmount,  setCalcAmount]  = useState("100");
  const [calcPeriod,  setCalcPeriod]  = useState<ReturnPeriod>("1M");
  const [calcResult,  setCalcResult]  = useState<{ value: number; pct: number } | null>(null);
  const [calcLoading, setCalcLoading] = useState(false);
  const calcAbortRef = useRef<AbortController | null>(null);

  const basket = BASKETS.find(b => b.id === activeBasket) ?? null;

  const runScan = useCallback(async (b: typeof BASKETS[0]) => {
    // Abort any previous scan
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setActiveBasket(b.id);
    setScanning(true);
    setDone(false);
    setCalcResult(null);
    setResults(b.symbols.map(sym => ({
      symbol: sym, score: 0, max: 16, label: "—",
      change: 0, price: 0, done: false, error: false,
    })));

    await Promise.allSettled(
      b.symbols.map(async (sym) => {
        try {
          const res = await fetch(`${RENDER_BASE}/analyse`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ symbol: sym, interval }),
            signal: ctrl.signal,
          });
          if (!res.ok) throw new Error();
          const data = await res.json();
          const score  = data?.signal?.total    ?? 0;
          const max    = data?.signal?.max      ?? 16;
          const label  = data?.signal?.label    ?? "—";
          const change = data?.quote?.change_24h ?? 0;
          const price  = data?.quote?.price      ?? 0;
          setResults(prev => prev.map(r =>
            r.symbol === sym
              ? { ...r, score, max, label, change, price, done: true, error: false }
              : r
          ));
        } catch {
          if (!ctrl.signal.aborted) {
            setResults(prev => prev.map(r =>
              r.symbol === sym ? { ...r, done: true, error: true } : r
            ));
          }
        }
      })
    );

    if (!ctrl.signal.aborted) {
      setScanning(false);
      setDone(true);
    }
  }, [interval]);

  // Run returns calculator
  const runCalc = useCallback(async (period: ReturnPeriod, amount: string, syms: string[]) => {
    calcAbortRef.current?.abort();
    calcAbortRef.current = new AbortController();
    setCalcLoading(true);
    setCalcResult(null);
    const days = PERIOD_DAYS[period];
    // Fetch all in parallel, equal-weight average
    const returns = await Promise.all(syms.map(s => fetchHistoricalReturn(s, days)));
    const valid = returns.filter((r): r is number => r !== null);
    if (valid.length === 0) { setCalcLoading(false); return; }
    const avgPct = valid.reduce((a, b) => a + b, 0) / valid.length;
    const startAmt = parseFloat(amount) || 100;
    const endAmt = startAmt * (1 + avgPct / 100);
    setCalcResult({ value: parseFloat(endAmt.toFixed(2)), pct: parseFloat(avgPct.toFixed(2)) });
    setCalcLoading(false);
  }, []);

  // Auto-run calc when done changes, period changes, or amount changes
  useEffect(() => {
    if (!done || !basket) return;
    const doneSyms = results.filter(r => r.done && !r.error).map(r => r.symbol);
    if (doneSyms.length === 0) return;
    runCalc(calcPeriod, calcAmount, doneSyms);
  }, [done, calcPeriod]);  // eslint-disable-line

  // Sort: done by score desc, pending at bottom
  const sorted = [...results].sort((a, b) => {
    if (a.done !== b.done) return a.done ? -1 : 1;
    return b.score - a.score;
  });

  const top        = sorted.find(r => r.done && !r.error);
  const doneAll    = sorted.filter(r => r.done && !r.error);
  const strongBuys = doneAll.filter(r => r.score >= 9).length;

  // Donut data — use score as weight, min 1 for visibility
  // Colour by slot index so every wedge is vivid and distinct
  const donutData = doneAll.map((r, idx) => ({
    name:  r.symbol,
    value: Math.max(r.score, 1),
    color: SLOT_COLORS[idx % SLOT_COLORS.length],
  }));

  return (
    <SideCard>
      <SideCardHeader icon="🧺" title="BASKET SCANNER" badge="NEW" />
      <div className="p-3">

        {/* Theme pills — 4-col grid */}
        <div className="grid grid-cols-4 gap-1 mb-3">
          {BASKETS.map(b => (
            <button
              key={b.id}
              onClick={() => !scanning && runScan(b)}
              disabled={scanning}
              className={`flex flex-col items-center gap-0.5 py-2 px-1 rounded-lg border text-center transition-all ${
                activeBasket === b.id
                  ? "border-purple/60 bg-purple/10 text-purple"
                  : "border-border/40 bg-surface-2 text-text-muted/70 hover:border-purple/30 hover:text-text"
              } disabled:opacity-50 disabled:cursor-wait`}
            >
              <span className="text-[13px] leading-none">{b.icon}</span>
              <span className="text-[8px] font-mono font-bold leading-tight mt-0.5">{b.label}</span>
            </button>
          ))}
        </div>

        {/* Status row */}
        {basket && (
          <div className="flex items-center justify-between mb-2 px-0.5">
            <div>
              <span className="text-[9px] font-mono text-text-muted/60">{basket.desc}</span>
              <span className="text-[9px] font-mono text-text-muted/30"> · {interval}</span>
            </div>
            {scanning && (
              <span className="text-[8px] font-mono text-amber animate-pulse">scanning…</span>
            )}
            {done && (
              <span className={`text-[8px] font-mono font-bold ${strongBuys > 0 ? "text-teal" : "text-text-muted/50"}`}>
                {strongBuys > 0 ? `${strongBuys} strong buy${strongBuys > 1 ? "s" : ""}` : "no strong buys"}
              </span>
            )}
          </div>
        )}

        {/* ── Leaderboard ─────────────────────────────────────────── */}
        {results.length > 0 && (
          <div className="space-y-1 mb-3">
            {sorted.map((r, i) => {
              const isTop    = r === top && done && r.score >= 9;
              const pct      = Math.round((r.score / r.max) * 100);
              const bColor   = scoreColor(r.score, r.max);
              const sColor   = r.score >= 9 ? "text-teal" : r.score >= 6 ? "text-amber" : "text-text-muted/40";
              return (
                <button
                  key={r.symbol}
                  onClick={() => r.done && !r.error && onSelect(r.symbol)}
                  disabled={!r.done || r.error}
                  className={`w-full flex items-center gap-2 px-2.5 py-2 rounded-lg border transition-all text-left ${
                    isTop
                      ? "border-teal/40 bg-teal/5"
                      : "border-border/30 bg-surface-2 hover:border-purple/30"
                  } ${!r.done ? "opacity-50 cursor-default" : ""}`}
                >
                  <span className="text-[8px] font-mono text-text-muted/25 w-3 shrink-0 text-right">
                    {r.done && !r.error ? i + 1 : "·"}
                  </span>
                  <span className={`text-[11px] font-mono font-black w-10 shrink-0 ${
                    r.done && !r.error ? "text-text" : "text-text-muted/30"
                  }`}>{r.symbol}</span>
                  <div className="flex-1 min-w-0">
                    {r.done && !r.error ? (
                      <div className="relative h-1.5 bg-surface-offset rounded-full overflow-hidden">
                        <div
                          className="absolute left-0 top-0 h-full rounded-full transition-all duration-700"
                          style={{ width: `${pct}%`, background: bColor }}
                        />
                      </div>
                    ) : r.error ? (
                      <span className="text-[8px] font-mono text-red/40">err</span>
                    ) : (
                      <div className="h-1.5 rounded-full bg-surface-offset animate-pulse" />
                    )}
                  </div>
                  <span className={`text-[10px] font-mono font-bold shrink-0 ${sColor}`}>
                    {r.done && !r.error ? `${r.score}/${r.max}` : "—"}
                  </span>
                  {r.done && !r.error && (
                    <span className={`text-[8px] font-mono shrink-0 w-9 text-right ${
                      r.change >= 0 ? "text-teal" : "text-red"
                    }`}>
                      {r.change >= 0 ? "+" : ""}{r.change.toFixed(1)}%
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {/* ── Allocation Donut + Constituent Table ─────────────────── */}
        {done && donutData.length > 0 && (
          <>
            <div className="border-t border-border/20 pt-3 mb-3">
              <div className="text-[8px] font-mono text-text-muted/40 uppercase tracking-widest mb-2">
                Allocation by signal strength
              </div>

              {/* Donut + legend side-by-side */}
              <div className="flex items-center gap-3">
                {/* Donut */}
                <div className="shrink-0" style={{ width: 80, height: 80 }}>
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={donutData}
                        cx="50%"
                        cy="50%"
                        innerRadius={24}
                        outerRadius={38}
                        paddingAngle={2}
                        dataKey="value"
                      >
                        {donutData.map((entry, idx) => (
                          <Cell
                            key={`cell-${idx}`}
                            fill={entry.color}
                            opacity={1}
                            stroke="rgba(6,9,18,0.6)"
                            strokeWidth={1.5}
                          />
                        ))}
                      </Pie>
                      <RechartTooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0].payload;
                          return (
                            <div className="text-[9px] font-mono px-2 py-1 rounded bg-surface-card border border-border/60 text-text">
                              {d.name}: {d.value}/{doneAll.find(r=>r.symbol===d.name)?.max ?? 16}
                            </div>
                          );
                        }}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>

                {/* Legend — 2 column */}
                <div className="flex-1 grid grid-cols-2 gap-x-2 gap-y-0.5">
                  {donutData.map(d => (
                    <button
                      key={d.name}
                      onClick={() => onSelect(d.name)}
                      className="flex items-center gap-1 group"
                    >
                      <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: d.color }} />
                      <span className="text-[9px] font-mono text-text-muted/70 group-hover:text-text transition-colors truncate">
                        {d.name}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* ── Constituent table ──────────────────────────────── */}
            <div className="border-t border-border/20 pt-3 mb-3">
              <div className="text-[8px] font-mono text-text-muted/40 uppercase tracking-widest mb-2">
                Constituents
              </div>
              <div className="space-y-0.5">
                {doneAll.map((r, i) => {
                  const alloc = Math.round((Math.max(r.score, 1) / donutData.reduce((a,d)=>a+d.value,0)) * 100);
                  return (
                    <button
                      key={r.symbol}
                      onClick={() => onSelect(r.symbol)}
                      className="w-full flex items-center gap-2 py-1.5 px-1.5 rounded hover:bg-surface-2 transition-colors text-left group"
                    >
                      <span className="text-[8px] font-mono text-text-muted/30 w-3 shrink-0">{i+1}</span>
                      <span className="text-[10px] font-mono font-bold text-text w-10 shrink-0 group-hover:text-purple transition-colors">
                        {r.symbol}
                      </span>
                      <span className="flex-1 text-[9px] font-mono text-text-muted/50 text-right">
                        ${r.price < 0.01 ? r.price.toFixed(6) : r.price < 1 ? r.price.toFixed(4) : r.price.toFixed(2)}
                      </span>
                      <span className={`text-[9px] font-mono w-10 text-right shrink-0 ${r.change>=0?"text-teal":"text-red"}`}>
                        {r.change>=0?"+":""}{r.change.toFixed(1)}%
                      </span>
                      <span
                        className="text-[8px] font-mono font-bold w-6 text-right shrink-0"
                        style={{ color: scoreColor(r.score, r.max) }}
                      >
                        {alloc}%
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </>
        )}

        {/* ── Returns Calculator ────────────────────────────────────── */}
        {done && doneAll.length > 0 && (
          <div className="border-t border-border/20 pt-3 mb-3">
            <div className="text-[8px] font-mono text-text-muted/40 uppercase tracking-widest mb-2">
              Returns calculator
            </div>

            {/* Period tabs */}
            <div className="flex items-center gap-1.5 mb-2">
              <span className="text-[9px] font-mono text-text-muted/50 mr-1">If you invested</span>
              {(["1W","1M","3M"] as ReturnPeriod[]).map(p => (
                <button
                  key={p}
                  onClick={() => {
                    setCalcPeriod(p);
                    runCalc(p, calcAmount, doneAll.map(r => r.symbol));
                  }}
                  className={`text-[9px] font-mono px-2 py-0.5 rounded border transition-all ${
                    calcPeriod === p
                      ? "border-purple/50 bg-purple/10 text-purple font-bold"
                      : "border-border/40 text-text-muted/50 hover:border-purple/30"
                  }`}
                >
                  {p} ago
                </button>
              ))}
            </div>

            {/* Amount input */}
            <div className="flex items-center gap-2 mb-2">
              <span className="text-[9px] font-mono text-text-muted/40">$</span>
              <input
                type="number"
                value={calcAmount}
                onChange={e => setCalcAmount(e.target.value)}
                onBlur={() => runCalc(calcPeriod, calcAmount, doneAll.map(r=>r.symbol))}
                className="flex-1 bg-surface-2 border border-border/50 rounded px-2 py-1 text-[10px] font-mono text-text focus:outline-none focus:border-purple/50"
                placeholder="100"
                min="1"
              />
              <span className="text-[9px] font-mono text-text-muted/40">invested</span>
            </div>

            {/* Result */}
            {calcLoading && (
              <div className="h-12 rounded-lg bg-surface-2 animate-pulse" />
            )}
            {!calcLoading && calcResult && (
              <div
                className="rounded-lg px-3 py-3 border"
                style={
                  calcResult.pct >= 0
                    ? { background: "rgba(34,197,94,0.06)", borderColor: "rgba(34,197,94,0.2)" }
                    : { background: "rgba(239,68,68,0.06)", borderColor: "rgba(239,68,68,0.2)" }
                }
              >
                <div className="text-[8px] font-mono text-text-muted/50 mb-0.5">would have become</div>
                <div className="flex items-baseline justify-between">
                  <span
                    className="text-[20px] font-black font-mono"
                    style={{ color: calcResult.pct >= 0 ? "#22c55e" : "#ef4444" }}
                  >
                    ${calcResult.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  </span>
                  <span
                    className="text-[12px] font-bold font-mono"
                    style={{ color: calcResult.pct >= 0 ? "#22c55e" : "#ef4444" }}
                  >
                    {calcResult.pct >= 0 ? "+" : ""}{calcResult.pct.toFixed(1)}%
                  </span>
                </div>
                <div className="text-[8px] font-mono text-text-muted/30 mt-1">
                  Equal-weight avg across {doneAll.length} coins · {calcPeriod} historical
                </div>
              </div>
            )}
            {!calcLoading && !calcResult && done && (
              <div className="text-[9px] font-mono text-text-muted/40 text-center py-2">
                Historical data unavailable for this basket
              </div>
            )}
          </div>
        )}

        {/* Empty state */}
        {results.length === 0 && (
          <div className="text-center py-5">
            <div className="text-[20px] mb-2 opacity-40">🧺</div>
            <div className="text-[10px] font-mono text-text-muted/40 leading-relaxed">
              Pick a theme to scan all coins<br />in that basket ranked by score.
            </div>
          </div>
        )}

        {/* Top scorer CTA */}
        {done && top && top.score >= 5 && (
          <button
            onClick={() => onSelect(top.symbol)}
            className="w-full mt-1 py-2 rounded-lg text-[10px] font-mono font-bold text-white flex items-center justify-center gap-1.5 transition-all hover:opacity-90"
            style={{
              background: top.score >= 9
                ? "linear-gradient(135deg, #22c55e, #16a34a)"
                : "linear-gradient(135deg, #f59e0b, #d97706)",
              boxShadow: top.score >= 9
                ? "0 2px 12px rgba(34,197,94,0.25)"
                : "0 2px 12px rgba(245,158,11,0.20)",
            }}
          >
            ⚡ Analyse top scorer — {top.symbol} ({top.score}/{top.max})
          </button>
        )}

      </div>
    </SideCard>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 12. SCANNER CUMULATIVE RETURN
// ════════════════════════════════════════════════════════════════════════════
const SCAN_API = (import.meta as Record<string, unknown> & { env?: Record<string, string> })
  .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

export function ScannerCumulativeCard() {
  const [data, setData] = useState<{
    first_date: string | null;
    cumulative_pct: number | null;
    avg_return_pct: number | null;
    win_rate_pct: number | null;
    total_picks: number;
    checked: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${SCAN_API}/scanner-performance?days=365`)
      .then(r => r.json())
      .then(j => {
        const at = j.alltime;
        if (at && at.first_date) setData(at);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <SideCard>
        <SideCardHeader num="12" icon="📈" title="STRATEGY RETURN" badge="ALL-TIME" />
        <div className="px-4 py-5 text-[10px] font-mono text-text-muted/50 text-center animate-pulse">
          Loading...
        </div>
      </SideCard>
    );
  }

  const noData = !data || data.checked === 0;

  const cumPct   = data?.cumulative_pct ?? null;
  const isPos    = cumPct != null && cumPct >= 0;
  const cumColor = cumPct == null ? "text-text-muted/40"
                 : cumPct >= 0   ? "text-teal"
                 : "text-red";

  // Format date as "Apr 2026"
  const fmtDate = (d: string | null) => {
    if (!d) return "—";
    const [y, m] = d.split("-");
    const months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
    return `${months[parseInt(m, 10) - 1]} ${y}`;
  };

  return (
    <SideCard>
      <SideCardHeader num="12" icon="📈" title="STRATEGY RETURN" badge="ALL-TIME" />
      <div className="px-4 py-4">
        {noData ? (
          <div className="text-center py-3">
            <p className="text-[10px] font-mono text-text-muted/50">
              Accumulating signal history —
            </p>
            <p className="text-[9px] font-mono text-text-muted/30 mt-1">
              check back after the daily scan runs
            </p>
          </div>
        ) : (
          <>
            {/* Hero line */}
            <div className="flex items-baseline justify-between mb-3">
              <div>
                <div className="text-[9px] font-mono text-text-muted/50 uppercase tracking-widest mb-0.5">
                  Since {fmtDate(data!.first_date)}
                </div>
                <div className={`text-2xl font-black font-mono ${cumColor}`}>
                  {cumPct != null
                    ? `${isPos ? "+" : ""}${cumPct.toFixed(1)}%`
                    : "—"}
                </div>
              </div>
              {cumPct != null && (
                <div
                  className="text-[9px] font-mono font-bold px-2 py-1 rounded-md border"
                  style={
                    cumPct >= 0
                      ? { color: "#22c55e", background: "rgba(34,197,94,0.08)", borderColor: "rgba(34,197,94,0.2)" }
                      : { color: "#ef4444", background: "rgba(239,68,68,0.08)", borderColor: "rgba(239,68,68,0.2)" }
                  }
                >
                  {isPos ? "▲" : "▼"} {Math.abs(cumPct).toFixed(1)}%
                </div>
              )}
            </div>

            {/* Divider */}
            <div className="border-t border-border/30 mb-3" />

            {/* Stats row */}
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: "Avg/pick",  value: data!.avg_return_pct != null ? `${data!.avg_return_pct >= 0 ? "+" : ""}${data!.avg_return_pct.toFixed(1)}%` : "—",
                  color: data!.avg_return_pct != null && data!.avg_return_pct >= 0 ? "text-teal" : "text-red" },
                { label: "Win rate",  value: data!.win_rate_pct != null ? `${data!.win_rate_pct.toFixed(0)}%` : "—",
                  color: "text-text" },
                { label: "Picks",     value: `${data!.checked}/${data!.total_picks}`,
                  color: "text-text-muted" },
              ].map(({ label, value, color }) => (
                <div key={label} className="text-center">
                  <div className={`text-[12px] font-mono font-bold ${color}`}>{value}</div>
                  <div className="text-[8px] font-mono text-text-muted/50 uppercase tracking-wide mt-0.5">{label}</div>
                </div>
              ))}
            </div>

            {/* Disclaimer */}
            <p className="text-[8px] font-mono text-text-muted/30 mt-3 text-center leading-relaxed">
              Compound return on all resolved STRONG BUY picks.
              Not financial advice.
            </p>
          </>
        )}
      </div>
    </SideCard>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// 13. DIP SCANNER
// ════════════════════════════════════════════════════════════════════════════
interface DipSignal {
  symbol: string;
  score: number;
  max_score: number;
  signal: string;
  change: number;
  price: number;
}

export function DipScannerCard({ interval = "1h", onSelect }: { interval?: string; onSelect: (sym: string) => void }) {
  const [results, setResults] = useState<DipSignal[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanned, setScanned] = useState(false);
  const [minDip, setMinDip] = useState(10);   // % down threshold (absolute)
  const [minScore, setMinScore] = useState(7); // score floor

  const runDipScan = useCallback(async () => {
    setLoading(true);
    setScanned(false);
    try {
      // Fetch broad scan (min_score=1 to get full picture, then filter client-side)
      const r = await fetch(`${SCAN_API}/scan?interval=${interval.toLowerCase()}&min_score=1`);
      const j = await r.json();
      const all: DipSignal[] = j.signals ?? [];
      const filtered = all
        .filter(s => (s.change ?? 0) <= -minDip && s.score >= minScore)
        .sort((a, b) => b.score - a.score);
      setResults(filtered);
    } catch {
      setResults([]);
    } finally {
      setLoading(false);
      setScanned(true);
    }
  }, [interval, minDip, minScore]);

  const cycleMinDip  = () => setMinDip(d => d === 5 ? 10 : d === 10 ? 15 : 5);
  const cycleScore   = () => setMinScore(s => s === 5 ? 7 : s === 7 ? 9 : 5);

  const dipColor = (chg: number) =>
    chg <= -15 ? "#ef4444" : chg <= -10 ? "#f59e0b" : "#94a3b8";

  return (
    <SideCard>
      <SideCardHeader num="13" icon="📉" title="DIP SCANNER" badge="CONTRARIAN" />
      <div className="px-4 py-3">

        {/* Description */}
        <p className="text-[9px] font-mono text-text-muted/60 leading-relaxed mb-3">
          Coins down {minDip}%+ in 24h with score ≥{minScore}. Contrarian re-entry setups.
        </p>

        {/* Controls */}
        <div className="flex items-center gap-2 mb-3">
          <button
            onClick={cycleMinDip}
            className="text-[9px] font-mono px-2 py-1 rounded border border-border/60 text-text-muted hover:border-red/40 hover:text-red transition-colors"
          >
            Dip ≥{minDip}%
          </button>
          <button
            onClick={cycleScore}
            className="text-[9px] font-mono px-2 py-1 rounded border border-border/60 text-text-muted hover:border-purple/40 hover:text-purple transition-colors"
          >
            Score ≥{minScore}
          </button>
          <button
            onClick={runDipScan}
            disabled={loading}
            className="ml-auto text-[9px] font-mono font-bold px-3 py-1 rounded border transition-all"
            style={loading
              ? { color: "#334155", borderColor: "#1e293b", cursor: "not-allowed" }
              : { color: "#ef4444", borderColor: "rgba(239,68,68,0.3)", background: "rgba(239,68,68,0.06)", cursor: "pointer" }
            }
          >
            {loading ? "Scanning..." : "Scan"}
          </button>
        </div>

        {/* Results */}
        {loading && (
          <div className="space-y-1.5 py-1">
            {[1,2,3].map(i => (
              <div key={i} className="h-7 rounded bg-surface-2 animate-pulse" />
            ))}
          </div>
        )}

        {!loading && scanned && results.length === 0 && (
          <div className="text-center py-4">
            <div className="text-[10px] font-mono text-text-muted/50">No dip setups found</div>
            <div className="text-[9px] font-mono text-text-muted/30 mt-1">
              Try lowering the dip or score threshold
            </div>
          </div>
        )}

        {!loading && !scanned && (
          <div className="text-center py-4">
            <div className="text-[20px] mb-1">📉</div>
            <div className="text-[10px] font-mono text-text-muted/50">
              Find oversold coins with<br />strong underlying structure
            </div>
          </div>
        )}

        {!loading && results.length > 0 && (
          <div className="space-y-1">
            {results.slice(0, 8).map((s, i) => (
              <button
                key={s.symbol}
                onClick={() => onSelect(s.symbol)}
                className="w-full flex items-center gap-2 py-1.5 px-2 rounded-lg border border-border/20 hover:border-red/30 hover:bg-red/5 transition-all text-left"
              >
                <span className="text-[9px] font-mono text-text-muted/40 w-4">{i + 1}.</span>
                <span className="text-[11px] font-mono font-bold text-text flex-1">{s.symbol}</span>
                <span className="text-[10px] font-mono font-bold" style={{ color: dipColor(s.change) }}>
                  {s.change.toFixed(1)}%
                </span>
                <span className="text-[10px] font-mono text-purple/80">
                  {s.score}/{s.max_score}
                </span>
              </button>
            ))}
            <p className="text-[8px] font-mono text-text-muted/30 text-center pt-1">
              {results.length} setup{results.length !== 1 ? "s" : ""} found — click to analyse
            </p>
          </div>
        )}

      </div>
    </SideCard>
  );
}
