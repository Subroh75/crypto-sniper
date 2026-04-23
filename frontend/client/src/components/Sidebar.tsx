// ─── Sidebar.tsx — Right column panels ──────────────────────────────────────
import { useState } from "react";
import { fmtPrice, fmtPct } from "@/lib/api";
import type { TradeSetup, Conviction, KeyLevel, WatchlistScore, AnalyseResponse } from "@/types/api";

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
                ["Stop Distance",  `$${(close * stopDistPct / 100).toFixed(0)}`],
                ["Position Size",  `${(100 / (close * stopDistPct / 100)).toFixed(4)} ${" BTC"}`],
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
      <SideCardHeader icon="🎯" title="CONVICTION METER" src="Agent synthesis" />
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
      <SideCardHeader icon="📍" title="KEY PRICE LEVELS" src="Twelve Data · CoinGecko" />
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
                  {level.dist_pct >= 0 ? "+" : ""}{level.dist_pct.toFixed(2)}%
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
// 4. WATCHLIST SCANNER
// ════════════════════════════════════════════════════════════════════════════
const PILL_STYLE: Record<string, string> = {
  BUY:   "bg-teal/10 text-teal border-teal/20",
  HOLD:  "bg-text-muted/10 text-text-muted border-border/40",
  WATCH: "bg-amber/10 text-amber border-amber/20",
};

export function WatchlistCard({
  scores,
  loading,
  onSelect,
  currentSymbol,
}: {
  scores: WatchlistScore[];
  loading: boolean;
  onSelect: (sym: string) => void;
  currentSymbol: string;
}) {
  return (
    <SideCard>
      <SideCardHeader icon="👁" title="WATCHLIST SCANNER" badge="NEW" src="CoinGecko" />
      <div className="p-3">
        <div className="space-y-1.5">
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-10 bg-surface-2 rounded-lg animate-pulse border border-border/30" />
            ))
          ) : scores.length === 0 ? (
            <div className="text-center text-[10px] font-mono text-text-muted/60 py-4">
              No watchlist data
            </div>
          ) : (
            scores.map((s) => (
              <button
                key={s.symbol}
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
                    {s.change_24h >= 0 ? "▲" : "▼"} {Math.abs(s.change_24h).toFixed(2)}%
                  </div>
                </div>
              </button>
            ))
          )}
        </div>

        <button className="w-full mt-2 py-2 text-[10px] font-mono text-text-muted/60 border border-dashed border-border/40 rounded-lg hover:border-purple/40 hover:text-purple transition-all">
          + Add coin to watchlist
        </button>
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
            ["LunarCrush social sentiment",     false],
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
      <SideCardHeader num="10" icon="📄" title="EXPORT REPORT" src="Full intelligence pack" />
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
