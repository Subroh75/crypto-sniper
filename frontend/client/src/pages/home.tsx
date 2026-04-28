//  home.tsx  Crypto Sniper V2 Main Page 
// Two-column terminal layout matching the V2 UX mockup exactly.
// Left: 10 analysis sections. Right: sidebar (Trade Setup, Conviction,
// Key Levels, Watchlist, Subscribe, Export).

import { useState, useCallback, useRef } from "react";
import { Logo } from "@/components/Logo";
import { LiveTicker } from "@/components/LiveTicker";
import { MarketBar } from "@/components/MarketBar";
import { PriceChart } from "@/components/PriceChart";
import {
  TradeSetupCard, ConvictionMeter, KeyLevelsCard,
  WatchlistCard, SubscribeCard, ExportCard,
} from "@/components/Sidebar";
import { TopSignals } from "@/components/TopSignals";
import { CSOVerdict } from "@/components/CSOVerdict";
import {
  TrendingSection, NewsSection, MacroSection,
} from "@/components/BottomSections";
import { DeepResearchSection } from "@/components/DeepResearch";
import { MultiTimeframeCard } from "@/components/MultiTimeframe";
import { BacktestCard } from "@/components/BacktestCard";
import { OnChainCard } from "@/components/OnChainCard";
import { BacktestInternalCard } from "@/components/BacktestInternalCard";
import { AuthModal, AuthButton } from "@/components/AuthModal";
import {
  useAnalyse, useKronos, useWatchlist, usePdfExport,
  useHitRate, useScannerPerformance, useAlerts,
  useEditableWatchlist, useAuth,
} from "@/hooks/useApi";
import { fmtPrice, fmtPct } from "@/lib/api";
import { MetricTooltip } from "@/components/Tooltip";
import type { AnalyseResponse, KronosResponse, DerivativesData } from "@/types/api";
import { ComposedChart, Bar, Line, ResponsiveContainer, YAxis, XAxis, CartesianGrid, ReferenceLine } from "recharts";

//  Constants 
const INTERVALS = ["1m","5m","15m","30m","1H","4H","1D"] as const;
const QUICK_COINS = ["BTC","ETH","SOL","BNB","DOGE","KAVA"] as const;

const VERDICT_COLOR: Record<string, string> = {
  "STRONG BUY": "text-teal",
  "MODERATE":   "text-amber",
  "NO SIGNAL":  "text-text-muted",
};

const VERDICT_BG: Record<string, string> = {
  "STRONG BUY": "bg-teal/8 border-teal/20",
  "MODERATE":   "bg-amber/8 border-amber/20",
  "NO SIGNAL":  "bg-surface-2 border-border/50",
};

//  Shared card primitives 
function Card({ children, className = "", id }: {
  children: React.ReactNode; className?: string; id?: string;
}) {
  return (
    <div id={id} className={`rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-3 ${className}`}>
      {children}
    </div>
  );
}

function CardHeader({ num, icon, title, badge, src, right }: {
  num?: string; icon?: string; title: string; badge?: string;
  src?: string; right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
      <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
        {num  && <span className="text-purple">{num}</span>}
        {icon && <span>{icon}</span>}
        <span>{title}</span>
        {badge && (
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-orange/10 text-orange border border-orange/15 uppercase tracking-wide">
            {badge}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {right}
        {src && (
          <span className="text-[9px] font-mono text-text-muted/60 px-2 py-0.5 rounded bg-surface-2 border border-border/40">
            {src}
          </span>
        )}
      </div>
    </div>
  );
}

//  VPRT+S score bar 
function ScoreBar({ score, max, color }: { score: number; max: number; color: string }) {
  return (
    <div className="w-full h-[3px] bg-surface-2 rounded-full overflow-hidden mt-1">
      <div
        className="h-full rounded-full transition-all duration-700"
        style={{ width: `${(score / max) * 100}%`, background: color }}
      />
    </div>
  );
}

//  Agent verdict badge 
function VerdictBadge({ verdict }: { verdict: string }) {
  const style: Record<string, string> = {
    "BUY":       "bg-teal/10 text-teal border-teal/20",
    "STRONG BUY":"bg-teal/10 text-teal border-teal/20",
    "SELL":      "bg-red/10 text-red border-red/20",
    "AVOID":     "bg-red/10 text-red border-red/20",
    "HOLD":      "bg-purple/10 text-purple border-purple/20",
    "GO":        "bg-teal/10 text-teal border-teal/20",
    "PASS":      "bg-surface-2 text-text-muted border-border/50",
  };
  return (
    <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${style[verdict] ?? style.HOLD}`}>
      {verdict}
    </span>
  );
}

// 
// MAIN PAGE
// 
export default function Home() {
  const reportId = "cs-report-root";

  const [symbol,   setSymbol]   = useState("BTC");
  const [input,    setInput]    = useState("");
  const [interval, setInterval] = useState("1H");

  const [alertEmail,   setAlertEmail]   = useState("");
  const [alertOpen,    setAlertOpen]    = useState(false);
  const [alertType,    setAlertType]    = useState<"score"|"price">("score");
  const [alertThreshold, setAlertThreshold] = useState(9);
  const [alertDirection, setAlertDirection] = useState<"above"|"below">("above");
  const [alertMsg,     setAlertMsg]     = useState("");
  const [authOpen,     setAuthOpen]     = useState(false);

  // Auth
  const auth = useAuth();
  // Stable user_id: logged-in users use email, anonymous users use a stable string
  const userId = auth.user?.email ?? "anon";

  const analyse  = useAnalyse();
  const kronosHk = useKronos();

  // Editable watchlist from backend DB
  const editableWL = useEditableWatchlist(userId);
  const { scores: wlScores, loading: wlLoading } = useWatchlist(editableWL.symbols.length ? editableWL.symbols : ["BTC","ETH","SOL","BNB","DOGE"]);

  const { exporting, exportPdf } = usePdfExport();
  const hitRate = useHitRate(null, 30);
  const scanPerf = useScannerPerformance(7);
  const alertsHk = useAlerts(alertEmail || null);

  const inputRef = useRef<HTMLInputElement>(null);

  //  Run full analysis 
  const runAnalysis = useCallback(async (sym?: string, iv?: string) => {
    const s = (sym ?? (input.trim().toUpperCase() || symbol));
    const i = iv ?? interval;
    if (!s) return;
    setSymbol(s);
    setInput(s);


    const result = await analyse.run(s, i);
    if (!result) return;

    // Build signal context for Kronos
    const ctx = {
      close:      result.quote.price,
      rsi:        result.timing.rsi,
      adx:        result.timing.adx,
      atr:        result.timing.atr,
      ema_stack:  result.structure.ema20 > 0 && result.structure.ema50 > 0
                    && result.quote.price > result.structure.ema20,
      ema20:      result.structure.ema20,
      ema50:      result.structure.ema50,
      ema200:     result.structure.ema200,
      bb_upper:   result.structure.bb_upper,
      signal:     result.signal.label,
      total:      result.signal.total,
      direction:  result.signal.direction,
      change_24h: result.quote.change_24h,
      rel_volume: result.timing.rel_volume,
      stop:       result.trade_setup.stop,
      target:     result.trade_setup.target,
      rr_ratio:   result.trade_setup.rr_ratio,
    } as Record<string, unknown>;

    kronosHk.run(s, i, ctx);
  }, [input, symbol, interval, analyse, kronosHk]);

  const sig    = analyse.data;
  const kron   = kronosHk.data;
  const loading = analyse.loading;

  return (
    <div className="min-h-screen bg-bg text-text" id={reportId}>

      {/*  HEADER  */}
      <header className="sticky top-0 z-50 border-b border-border/60 backdrop-blur-xl bg-bg/90">
        <div className="flex items-center gap-4 px-4 h-[50px]">
          <Logo />
          <LiveTicker />
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-teal">
              <div className="w-[6px] h-[6px] rounded-full bg-teal animate-pulse shadow-sm shadow-teal/50" />
              LIVE
            </div>
            <AuthButton user={auth.user} onClick={() => setAuthOpen(true)} />
            <button
              className="text-[11px] font-mono font-bold text-white px-3 py-1.5 rounded transition-all"
              style={{ background: "#7c3aed" }}
            >
              Subscribe
            </button>
          </div>
        </div>
      </header>

      {/*  MARKET BAR  */}
      <MarketBar />

      {/*  HERO SEARCH  */}
      <div className="text-center px-4 py-8">
        <h1 className="text-4xl sm:text-5xl font-black tracking-tight mb-2"
            style={{ background: "linear-gradient(140deg,#fff 20%,#7c3aed 80%)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent" }}>
          Real-Time Crypto Signal Engine
        </h1>
        <p className="text-text-muted text-[13px] mb-5">
          Live V/P/R/T/S scoring &middot; Kronos AI forecast &middot; On-chain signals &middot; Multi-agent debate
        </p>

        {/* Timeframe pills */}
        <div className="flex justify-center gap-1.5 mb-3">
          {INTERVALS.map(iv => (
            <button
              key={iv}
              onClick={() => setInterval(iv)}
              className={`text-[11px] font-mono font-bold px-3 py-1 rounded-md border transition-all ${
                iv === interval
                  ? "border-purple text-purple bg-purple/8"
                  : "border-border/50 text-text-muted hover:border-text-muted hover:text-text"
              }`}
            >
              {iv}
            </button>
          ))}
        </div>

        {/* Search row */}
        <div className="flex gap-2 max-w-[640px] mx-auto mb-3">
          <input
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === "Enter" && runAnalysis()}
            placeholder="BTC - ETH - SOL - KAVA..."
            className="flex-1 h-[46px] rounded-lg border border-border/60 bg-surface px-4 text-[15px] font-sans font-medium text-text placeholder:text-text-muted/50 outline-none focus:border-purple transition-all"
          />
          <button
            onClick={() => runAnalysis()}
            disabled={loading}
            className="h-[46px] px-5 rounded-lg font-sans font-bold text-[13px] text-white flex items-center gap-2 transition-all disabled:opacity-60"
            style={{ background: "#7c3aed" }}
          >
            {loading ? "..." : "Analyse"}
          </button>
        </div>

        {/* Quick coins */}
        <div className="flex justify-center gap-2 flex-wrap">
          <span className="text-[10px] font-mono text-text-muted/60 py-1 px-1">Try</span>
          {QUICK_COINS.map(sym => (
            <button
              key={sym}
              onClick={() => runAnalysis(sym)}
              className="text-[11px] font-mono px-3 py-1 rounded-md border border-border/50 bg-surface-2 text-text-muted hover:border-purple/40 hover:text-text transition-all"
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

      {/*  MAIN TWO-COL LAYOUT  */}
      <div className="max-w-[1380px] mx-auto px-4 pb-20">

        {!sig && !loading && (
          <div className="text-center py-10 text-text-muted text-[13px] font-mono">
            Enter a coin symbol above to analyse
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center gap-3 py-16 text-text-muted text-[12px] font-mono">
            <div className="flex gap-1">
              {[0,1,2].map(i => (
                <div key={i} className="w-2 h-2 rounded-full bg-purple animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />
              ))}
            </div>
            Analysing {symbol}...
          </div>
        )}

        {sig && !loading && (
          <div className="grid gap-3" style={{ gridTemplateColumns: "1fr 320px" }}>

            {/*  LEFT COLUMN  */}
            <div>

              {/* 01: Signal Output */}
              <Card>
                <CardHeader num="01" icon="!" title="SIGNAL OUTPUT" src="CoinGecko  ·  Twelve Data"
                  right={
                    hitRate.data?.hit_rate_pct != null ? (
                      <button
                        onClick={() => setAlertOpen(true)}
                        className="flex items-center gap-1.5 text-[9px] font-mono font-bold px-2 py-1 rounded border border-teal/30 bg-teal/5 text-teal hover:bg-teal/10 transition-all"
                      >
                        <span className="text-teal">&#9670;</span>
                        {hitRate.data.hit_rate_pct}% hit rate
                      </button>
                    ) : (
                      <button
                        onClick={() => setAlertOpen(true)}
                        className="flex items-center gap-1 text-[9px] font-mono font-bold px-2 py-1 rounded border border-purple/30 bg-purple/5 text-purple hover:bg-purple/10 transition-all"
                      >
                        &#43; Set Alert
                      </button>
                    )
                  }
                />
                <div className="p-4">
                  <div className="bg-surface-2 rounded-xl border border-border/50 p-5 text-center">
                    <div className="text-[10px] font-mono text-text-muted/70 mb-2 tracking-wide">
                      {symbol}/USDT  ·  {interval}  ·  {new Date(sig.timestamp * 1000).toUTCString().slice(0,-4)} UTC
                    </div>
                    <div className={`inline-block text-[10px] font-mono font-bold px-3 py-1 rounded border mb-3 ${VERDICT_BG[sig.signal.label] ?? VERDICT_BG["NO SIGNAL"]}`}>
                      {sig.signal.label}
                    </div>
                    <div className={`text-[34px] font-black mb-1 ${VERDICT_COLOR[sig.signal.label] ?? "text-text-muted"}`}>
                      {sig.signal.label}
                    </div>
                    <div className="text-[12px] font-mono text-text-muted mb-3">
                      {sig.signal.total} / {sig.signal.max}  {sig.signal.label === "STRONG BUY" ? "strong setup!" : sig.signal.label === "MODERATE" ? "approaching threshold" : "below threshold (<9)"}
                    </div>
                    <div className="flex justify-center gap-4 text-[11px] font-mono text-text-muted flex-wrap">
                      <span>CLOSE <span className={sig.quote.price > sig.structure.ema20 ? "text-teal font-bold" : "text-red font-bold"}>{fmtPrice((sig.quote?.price ?? 1))}</span></span>
                      <span>24H <span className={sig.quote.change_24h >= 0 ? "text-teal font-bold" : "text-red font-bold"}>{fmtPct(sig.quote.change_24h)}</span></span>
                      <span>VOL <span className={(sig.timing?.rel_volume ?? 0) >= 2 ? "text-teal font-bold" : "text-amber font-bold"}>{(sig.timing?.rel_volume ?? 0).toFixed(1)}x</span></span>
                      <span>ADX <span className={(sig.timing?.adx ?? 0) >= 25 ? "text-teal font-bold" : "text-amber font-bold"}>{(sig.timing?.adx ?? 0).toFixed(0)}</span></span>
                      <span>RSI <span className={(sig.timing?.rsi ?? 50) >= 70 ? "text-red font-bold" : (sig.timing?.rsi ?? 50) <= 30 ? "text-teal font-bold" : "text-amber font-bold"}>{(sig.timing?.rsi ?? 50).toFixed(0)}</span></span>
                      <span>S <span className="text-orange font-bold">{sig.components.S.score * 4}%</span></span>
                    </div>
                  </div>
                </div>
              </Card>

              {/* 02: Signal Components */}
              <Card>
                <CardHeader num="02" title="SIGNAL COMPONENTS V/P/R/T/S" src="CoinGecko  ·  LunarCrush" />
                <div className="p-4">
                  <div className="grid grid-cols-5 gap-2">
                    {(["V","P","R","T","S"] as const).map(key => {
                      const comp = sig.components[key];
                      const colors: Record<string, string> = { V:"#b8c2dc", P:"#b8c2dc", R:"#b8c2dc", T:"#00d4aa", S:"#ff8c42" };
                      const color = comp.score > 0 ? colors[key] : "#4a5470";
                      return (
                        <div key={key} className={`bg-surface-2 rounded-lg border p-3 ${key === "S" ? "border-orange/20" : "border-border/50"}`}>
                          <div className="text-[22px] font-black mb-0.5" style={{ color }}>{key}</div>
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-2">
                            <MetricTooltip id={key}>{comp.label}</MetricTooltip>
                            {key === "S" && <span className="ml-1 text-[7px] bg-orange/10 text-orange px-1 py-0.5 rounded">NEW</span>}
                          </div>
                          <div className="text-[16px] font-mono font-bold mb-0.5" style={{ color }}>
                            {comp.score}/{comp.max}
                          </div>
                          <ScoreBar score={comp.score} max={comp.max} color={color} />
                          <div className="text-[9px] font-mono text-text-muted/60 mt-1.5">{comp.detail}</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </Card>

              {/* 02b: Price Chart */}
              <PriceChart
                ohlcv={sig.ohlcv}
                structure={sig.structure}
                interval={interval}
                symbol={symbol}
                onTfChange={(tf) => { setInterval(tf); runAnalysis(symbol, tf); }}
              />

              {/* 03 + 04: Market Structure + Timing Quality */}
              <div className="grid grid-cols-2 gap-3 mb-3">
                <Card className="mb-0">
                  <CardHeader num="03" icon="-" title="MARKET STRUCTURE" />
                  <div className="p-4 space-y-2">
                    {[
                      ["Close",      sig.quote.price,        sig.quote.price > sig.structure.ema20 ? "up" : "dn"],
                      ["EMA 20",     sig.structure.ema20,    sig.quote.price > sig.structure.ema20 ? "up" : "dn"],
                      ["EMA 50",     sig.structure.ema50,    sig.quote.price > sig.structure.ema50 ? "up" : "dn"],
                      ["EMA 200",    sig.structure.ema200,   sig.quote.price > sig.structure.ema200 ? "up" : "dn"],
                      ["VWAP",       sig.structure.vwap,     sig.quote.price > sig.structure.vwap ? "up" : "dn"],
                      ["BB Upper",   sig.structure.bb_upper, sig.quote.price < sig.structure.bb_upper ? "warn" : "dn"],
                    ].map(([label, price, dir]) => (
                      <div key={label as string} className="flex justify-between items-center border-b border-border/30 pb-1.5 last:border-none last:pb-0">
                        <span className="text-[10px] font-mono text-text-muted/70 uppercase tracking-wide">
                          <MetricTooltip id={label as string}>{label as string}</MetricTooltip>
                        </span>
                        <span className={`text-[12px] font-mono font-bold flex items-center gap-1 ${
                          dir === "up" ? "text-teal" : dir === "warn" ? "text-red" : "text-red"
                        }`}>
                          <span className="text-[10px] leading-none">{dir === "up" ? "▲" : dir === "warn" ? "●" : "▼"}</span>{fmtPrice(price as number)}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="mb-0">
                  <CardHeader num="04" icon="-" title="TIMING QUALITY" />
                  <div className="p-4">
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { label: "RSI 14",  value: (sig.timing?.rsi ?? 50).toFixed(1),    sub: (sig.timing?.rsi ?? 50) >= 70 ? "OVERBOUGHT" : (sig.timing?.rsi ?? 50) <= 30 ? "OVERSOLD" : "NEUTRAL",  color: (sig.timing?.rsi ?? 50) >= 70 ? "text-red" : (sig.timing?.rsi ?? 50) <= 30 ? "text-teal" : "text-amber" },
                        { label: "ADX 14",  value: (sig.timing?.adx ?? 0).toFixed(1),    sub: (sig.timing?.adx ?? 0) >= 25 ? "TRENDING" : "RANGING",   color: (sig.timing?.adx ?? 0) >= 25 ? "text-teal" : "text-amber" },
                        { label: "ATR 14",  value: (sig.timing?.atr ?? 0).toFixed(0),    sub: `${((sig.timing.atr / ((sig.quote?.price ?? 0) || 1)) * 100).toFixed(2)}% of price`, color: "text-amber" },
                        { label: "Rel Vol", value: `${(sig.timing?.rel_volume ?? 0).toFixed(2)}x`, sub: (sig.timing?.rel_volume ?? 0) >= 2 ? "HIGH" : "NORMAL", color: (sig.timing?.rel_volume ?? 0) >= 2 ? "text-teal" : "text-amber" },
                      ].map(({ label, value, sub, color }) => (
                        <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">
                            <MetricTooltip id={label}>{label}</MetricTooltip>
                          </div>
                          <div className={`text-[20px] font-mono font-black ${color}`}>{value}</div>
                          <div className={`text-[9px] font-mono mt-0.5 ${color} opacity-70`}>{sub}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </Card>
              </div>

              {/* 05: Perp Derivatives — real data from Bybit */}
              {(() => {
                const d = sig.derivatives;
                if (!d || !d.has_perp) {
                  // Spot-only coin — show mempool + fear/greed instead
                  return (
                    <Card>
                      <CardHeader num="05" title="MARKET CONTEXT" src="CoinGecko" />
                      <div className="p-4">
                        <div className="grid grid-cols-2 gap-2">
                          <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                            <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">
                              <MetricTooltip id="RSI">Fear/Greed Index</MetricTooltip>
                            </div>
                            <div className={`text-[20px] font-mono font-black ${
                              (sig.fear_greed?.value ?? 50) >= 70 ? "text-red" :
                              (sig.fear_greed?.value ?? 50) <= 30 ? "text-teal" : "text-amber"
                            }`}>{sig.fear_greed?.value ?? "--"}</div>
                            <div className="text-[9px] font-mono text-text-muted/60 mt-0.5">{sig.fear_greed?.label ?? "--"}</div>
                          </div>
                          <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                            <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">No Perp Data</div>
                            <div className="text-[13px] font-mono text-text-muted">Spot-only coin</div>
                            <div className="text-[9px] font-mono text-text-muted/60 mt-0.5">Bybit / OKX not available</div>
                          </div>
                        </div>
                      </div>
                    </Card>
                  );
                }

                const fr = d.funding;
                const oi = d.open_interest;
                const ls = d.long_short;
                const frColor = fr.sentiment === "bullish" ? "text-teal" : fr.sentiment === "bearish" ? "text-red" : "text-amber";
                const oiColor = oi.trend === "rising" ? "text-teal" : oi.trend === "falling" ? "text-red" : "text-amber";
                const lsColor = ls.sentiment === "bullish" ? "text-teal" : ls.sentiment === "bearish" ? "text-red" : "text-amber";

                return (
                  <Card>
                    <CardHeader num="05" title="PERP DERIVATIVES" badge="LIVE" src={`${fr.source} · ${oi.source}`} />
                    <div className="p-4">
                      <div className="grid grid-cols-3 gap-2">
                        {/* Funding Rate */}
                        <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">
                            <MetricTooltip id="Funding Rate">Funding Rate</MetricTooltip>
                          </div>
                          <div className={`text-[18px] font-mono font-black ${frColor}`}>
                            {fr.rate >= 0 ? "+" : ""}{fr.rate.toFixed(4)}%
                          </div>
                          <div className={`text-[9px] font-mono mt-0.5 ${frColor} opacity-90`}>
                            {fr.sentiment} · {fr.rate_annualised.toFixed(0)}% p.a.
                          </div>
                          {fr.next_funding_ts > 0 && (
                            <div className="text-[8px] font-mono text-text-muted/40 mt-1">
                              Next: {new Date(fr.next_funding_ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                            </div>
                          )}
                        </div>

                        {/* Open Interest */}
                        <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">
                            <MetricTooltip id="Open Interest">Open Interest</MetricTooltip>
                          </div>
                          <div className={`text-[18px] font-mono font-black ${oiColor}`}>{oi.oi_usd_fmt}</div>
                          <div className={`text-[9px] font-mono mt-0.5 ${oiColor} opacity-90`}>
                            {oi.change_24h >= 0 ? "+" : ""}{oi.change_24h.toFixed(1)}% 24H · {oi.trend}
                          </div>
                        </div>

                        {/* L/S Ratio */}
                        <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">
                            <MetricTooltip id="L/S Ratio">L/S Ratio</MetricTooltip>
                          </div>
                          <div className={`text-[18px] font-mono font-black ${lsColor}`}>
                            {ls.long_pct.toFixed(0)}% / {ls.short_pct.toFixed(0)}%
                          </div>
                          <div className={`text-[9px] font-mono mt-0.5 ${lsColor} opacity-90`}>{ls.note}</div>
                          {/* Mini bar */}
                          <div className="mt-2 h-[3px] rounded-full bg-red/30 overflow-hidden">
                            <div className="h-full rounded-full bg-teal transition-all" style={{ width: `${ls.long_pct}%` }} />
                          </div>
                          <div className="flex justify-between text-[7px] font-mono text-text-muted/40 mt-0.5">
                            <span>Long</span><span>Short</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })()}

              {/* 06: Kronos AI Forecast */}
              <Card>
                <CardHeader num="06" title="KRONOS AI FORECAST" src="Perplexity  ·  Claude" />
                <div className="p-4">
                  {kronosHk.loading && (
                    <div className="flex items-center gap-3 py-8 justify-center text-text-muted text-[11px] font-mono">
                      <div className="flex gap-1">
                        {[0,1,2].map(i=><div key={i} className="w-1.5 h-1.5 rounded-full bg-purple animate-bounce" style={{animationDelay:`${i*0.15}s`}}/>)}
                      </div>
                      Kronos forecasting {symbol}...
                    </div>
                  )}
                  {kron && !kronosHk.loading && (
                    <>
                      {/* Row 1: direction / move / trade quality */}
                      <div className="grid grid-cols-3 gap-2 mb-2">
                        {[
                          { label: "AI Forecast",   value: kron.forecast.direction,
                            color: kron.forecast.direction === "Falling" ? "text-red" : kron.forecast.direction === "Rising" ? "text-teal" : "text-amber" },
                          { label: "Expected Move", value: `${(kron.forecast?.expected_move_pct ?? 0) >= 0 ? "▲" : "▼"} ${Math.abs(kron.forecast.expected_move_pct).toFixed(2)}%`,
                            color: (kron.forecast?.expected_move_pct ?? 0) >= 0 ? "text-teal" : "text-red" },
                          { label: "Trade Quality", value: kron.forecast.trade_quality,
                            color: kron.forecast.trade_quality.includes("Avoid") ? "text-red" : kron.forecast.trade_quality.includes("Moderate") ? "text-amber" : "text-teal" },
                        ].map(({ label, value, color }) => (
                          <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-3">
                            <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">{label}</div>
                            <div className={`text-[14px] font-mono font-black leading-tight ${color}`}>{value}</div>
                          </div>
                        ))}
                      </div>
                      {/* Row 2: target / bull / bear + conviction badges */}
                      <div className="grid grid-cols-3 gap-2 mb-2">
                        <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">Target Price</div>
                          <div className="text-[14px] font-mono font-black text-text">{fmtPrice(kron.forecast.target_price)}</div>
                          <div className="text-[9px] font-mono text-text-muted/60 mt-0.5">
                            H {fmtPrice(kron.forecast.high_24h)} / L {fmtPrice(kron.forecast.low_24h)}
                          </div>
                        </div>
                        <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">Bull Case</div>
                          <div className={`text-[14px] font-mono font-black ${kron.forecast.bull_case === "TAKE" ? "text-teal" : "text-text-muted"}`}>
                            {kron.forecast.bull_case}
                          </div>
                          <div className="text-[9px] font-mono text-text-muted/60 mt-0.5">{kron.forecast.bull_conviction} conviction</div>
                        </div>
                        <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">Bear Case</div>
                          <div className={`text-[14px] font-mono font-black ${kron.forecast.bear_case === "SHORT" ? "text-red" : "text-text-muted"}`}>
                            {kron.forecast.bear_case}
                          </div>
                          <div className="text-[9px] font-mono text-text-muted/60 mt-0.5">{kron.forecast.bear_conviction} conviction</div>
                        </div>
                      </div>
                      {/* Row 3: momentum strip */}
                      <div className="flex items-center gap-3 mb-3 px-1">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[9px] font-mono text-text-muted/60 uppercase tracking-wide">Momentum</span>
                          <span className={`text-[10px] font-mono font-bold ${
                            kron.forecast.momentum.includes("bullish") ? "text-teal" :
                            kron.forecast.momentum.includes("bearish") ? "text-red" : "text-amber"
                          }`}>{kron.forecast.momentum}</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <span className="text-[9px] font-mono text-text-muted/60 uppercase tracking-wide">Green Candles</span>
                          <span className={`text-[10px] font-mono font-bold ${
                            kron.forecast.green_candle_pct >= 55 ? "text-teal" :
                            kron.forecast.green_candle_pct <= 45 ? "text-red" : "text-amber"
                          }`}>{kron.forecast.green_candle_pct}%</span>
                        </div>
                        {/* mini progress bar */}
                        <div className="flex-1 h-[3px] bg-surface-2 rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all duration-700"
                            style={{
                              width: `${kron.forecast.green_candle_pct}%`,
                              background: kron.forecast.green_candle_pct >= 55 ? "#22c55e" :
                                          kron.forecast.green_candle_pct <= 45 ? "#ef4444" : "#f59e0b"
                            }}
                          />
                        </div>
                      </div>
                      {/* Forecast chart */}
                      <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                        <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-2">
                          PREDICTED OHLCV — NEXT 24 CANDLES
                        </div>
                        {(() => {
                          const candles = kron.forecast.predicted_ohlcv;
                          const allP = candles.flatMap((c: any) => [c.open, c.high, c.low, c.close]);
                          const kpMin = Math.min(...allP);
                          const kpMax = Math.max(...allP);
                          // Price-aware padding: at least 1.5% of price so low-price
                          // coins (DOGE $0.10, SHIB $0.00001) get visible candles
                          const kPad = Math.max((kpMax - kpMin) * 0.15, kpMin * 0.015);
                          const kDomMin = kpMin - kPad;
                          const kDomMax = kpMax + kPad;
                          const kRange = kDomMax - kDomMin || kpMin * 0.1 || 1;
                          // Smart tick formatter — show enough decimal places
                          const kFmt = (v: number) => {
                            if (v >= 1000)  return `$${(v/1000).toFixed(1)}k`;
                            if (v >= 1)     return `$${v.toFixed(2)}`;
                            if (v >= 0.01)  return `$${v.toFixed(4)}`;
                            if (v >= 0.0001)return `$${v.toFixed(6)}`;
                            return `$${v.toExponential(2)}`;
                          };
                          const kData = candles.map((c: any, i: number) => ({
                            ...c, i,
                            isGreen: c.close >= c.open,
                            kDomMin, kDomMax, kRange,
                          }));
                          return (
                            <ResponsiveContainer width="100%" height={190}>
                              <ComposedChart
                                margin={{ top: 4, right: 56, left: 0, bottom: 4 }}
                                data={kData}
                              >
                                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                                <XAxis dataKey="i"
                                  tickFormatter={(v) => v % 6 === 0 ? `+${v}h` : ""}
                                  tick={{ fontSize: 8, fill: "#475569" }} tickLine={false} axisLine={false}
                                />
                                <YAxis
                                  domain={[kDomMin, kDomMax]}
                                  tickFormatter={kFmt}
                                  tick={{ fontSize: 8, fill: "#475569" }} tickLine={false} axisLine={false}
                                  width={60} orientation="right"
                                />
                                <ReferenceLine
                                  y={kron.forecast.target_price}
                                  stroke="#7c3aed" strokeDasharray="4 4" strokeWidth={1}
                                  label={{ value: "Target", position: "right", fontSize: 8, fill: "#7c3aed" }}
                                />
                                <Bar dataKey="close" fill="transparent" stroke="none"
                                  isAnimationActive={false}
                                  background={{ fill: "transparent" }}
                                  shape={(props: any) => {
                                    const { x, width: w, background: bg, payload: pl } = props as any;
                                    if (!pl || !bg || bg.height <= 0) return null;
                                    const { open, high, low, close: c, isGreen: ig, kDomMin: dMin, kRange: range } = pl;
                                    // Use the SAME domain as YAxis — no independent mapping
                                    const py = (p: number) => bg.y + bg.height - ((p - dMin) / range) * bg.height;
                                    const yH=py(high), yL=py(low), yO=py(open), yC=py(c);
                                    const top=Math.min(yO,yC), bot=Math.max(yO,yC);
                                    const col = ig ? "#22c55e" : "#ef4444";
                                    const cx2 = x + w/2;
                                    const bW = Math.max(w - 1.5, 1.5);
                                    const bH = Math.max(bot - top, 1.5);
                                    return (
                                      <g>
                                        <line x1={cx2} y1={yH} x2={cx2} y2={top} stroke={col} strokeWidth={1}/>
                                        <line x1={cx2} y1={bot} x2={cx2} y2={yL} stroke={col} strokeWidth={1}/>
                                        <rect x={x+0.75} y={top} width={bW} height={bH}
                                          fill={col} fillOpacity={ig ? 0.85 : 0.75} rx={0.5}/>
                                      </g>
                                    );
                                  }}
                                />
                              </ComposedChart>
                            </ResponsiveContainer>
                          );
                        })()}
                      </div>
                    </>
                  )}
                  {!kron && !kronosHk.loading && (
                    <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
                      Waiting for signal analysis...
                    </div>
                  )}
                </div>
              </Card>

              {/* 07: Agent Debate */}
              <Card>
                <CardHeader num="07" icon="-" title="AI LAB - AGENT DEBATE" src="Claude Haiku  ·  Perplexity context" />
                <div className="p-4">
                  {kron?.agents ? (
                    <div className="grid grid-cols-2 gap-2">
                      {kron.agents.map(agent => (
                        <div key={agent.key} className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="flex items-center justify-between mb-2.5">
                            <div className="flex items-center gap-2">
                              <div className={`w-6 h-6 rounded-md flex items-center justify-center text-xs ${
                                agent.key === "bull" ? "bg-teal/10" :
                                agent.key === "bear" ? "bg-red/10"  :
                                agent.key === "risk" ? "bg-orange/10" : "bg-purple/10"
                              }`}>{agent.icon}</div>
                              <span className="text-[10px] font-mono font-bold text-text-muted/70 uppercase tracking-wide">
                                {agent.name}
                              </span>
                            </div>
                            <VerdictBadge verdict={agent.verdict} />
                          </div>
                          <p className="text-[11px] text-text-muted leading-relaxed">{agent.text}</p>
                        </div>
                      ))}
                    </div>
                  ) : kronosHk.loading ? (
                    <div className="grid grid-cols-2 gap-2">
                      {[...Array(4)].map((_,i) => (
                        <div key={i} className="h-28 bg-surface-2 rounded-lg animate-pulse border border-border/30" />
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
                      Waiting for signal analysis...
                    </div>
                  )}
                </div>
              </Card>

              {/* 08: Trending + News + Macro */}
              <TrendingSection onSelect={(sym) => runAnalysis(sym)} />
              <NewsSection symbol={symbol} />
              <MacroSection />

              {/* 09: Perplexity Deep Research */}
              <DeepResearchSection symbol={symbol} analyseData={sig} />

              {/* 10: Scanner Performance */}
              {scanPerf.data && (
                <Card>
                  <CardHeader num="10" title="SCANNER PERFORMANCE" badge="HISTORY"
                    src={`Last ${scanPerf.data.summary.days}d`}
                    right={
                      scanPerf.data.summary.win_rate_pct != null ? (
                        <span className="text-[9px] font-mono font-bold text-teal px-2 py-0.5 rounded bg-teal/5 border border-teal/20">
                          {scanPerf.data.summary.win_rate_pct}% win rate
                        </span>
                      ) : undefined
                    }
                  />
                  <div className="p-4">
                    {scanPerf.data.picks.length === 0 ? (
                      <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
                        No scanner picks yet — the daily cron will populate this after the first scan.
                      </div>
                    ) : (
                      <>
                        {/* Summary row */}
                        {scanPerf.data.summary.avg_return_pct != null && (
                          <div className="flex gap-4 mb-3 px-1 text-[11px] font-mono">
                            <span className="text-text-muted/60">Avg return</span>
                            <span className={scanPerf.data.summary.avg_return_pct >= 0 ? "text-teal font-bold" : "text-red font-bold"}>
                              {scanPerf.data.summary.avg_return_pct >= 0 ? "+" : ""}{scanPerf.data.summary.avg_return_pct.toFixed(2)}%
                            </span>
                            <span className="text-text-muted/60">{scanPerf.data.summary.checked} picks checked</span>
                          </div>
                        )}
                        {/* Table */}
                        <div className="space-y-1">
                          {scanPerf.data.picks.slice(0, 10).map((pick, i) => (
                            <div key={`${pick.symbol}-${pick.scan_date}-${i}`}
                              className="flex items-center gap-2 py-1.5 border-b border-border/20 last:border-none">
                              <span className="text-[10px] font-mono text-text-muted/50 w-8">{i + 1}.</span>
                              <button
                                onClick={() => runAnalysis(pick.symbol)}
                                className="text-[11px] font-mono font-bold text-purple hover:text-teal transition-colors w-14"
                              >{pick.symbol}</button>
                              <span className="text-[10px] font-mono text-text-muted/60 flex-1">{pick.scan_date}</span>
                              <span className="text-[10px] font-mono text-teal/80">{pick.score}/16</span>
                              {pick.outcome_pct != null ? (
                                <span className={`text-[11px] font-mono font-bold ${
                                  pick.outcome_pct >= 2 ? "text-teal" : pick.outcome_pct <= -2 ? "text-red" : "text-text-muted"
                                }`}>
                                  {pick.outcome_pct >= 0 ? "+" : ""}{pick.outcome_pct.toFixed(2)}%
                                </span>
                              ) : (
                                <span className="text-[10px] font-mono text-text-muted/40">pending</span>
                              )}
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                </Card>
              )}

              {/* 11: Backtest */}
              <BacktestCard symbol={symbol} />

              {/* 12: Multi-Timeframe Confluence */}
              <MultiTimeframeCard symbol={symbol} />

              {/* 13: On-Chain Intelligence */}
              <OnChainCard symbol={symbol} />

              {/* 14: Internal Signal Backtest */}
              <BacktestInternalCard symbol={symbol} />

            </div>
            {/*  end LEFT column  */}

            {/*  RIGHT SIDEBAR  */}
            <div>
              <CSOVerdict sig={sig} kron={kronosHk.data} fearGreed={sig?.fear_greed} />
              <TopSignals onSelect={(sym) => runAnalysis(sym)} interval={interval} />
              <TradeSetupCard setup={sig?.trade_setup ?? null} close={sig?.quote?.price ?? 0} />
              <ConvictionMeter conviction={sig.conviction} />
              <KeyLevelsCard levels={sig.key_levels} />
              <WatchlistCard
                scores={wlScores}
                loading={wlLoading}
                onSelect={(sym) => runAnalysis(sym)}
                currentSymbol={symbol}
                onAdd={editableWL.add}
                onRemove={editableWL.remove}
              />
              <SubscribeCard />
              <ExportCard
                symbol={symbol}
                interval={interval}
                onRerun={() => runAnalysis()}
                onExport={() => exportPdf(reportId, `crypto-sniper-${symbol}-${interval}.pdf`)}
                exporting={exporting}
              />
            </div>
            {/*  end RIGHT sidebar  */}

          </div>
        )}
      </div>

      {/* AUTH MODAL */}
      <AuthModal
        open={authOpen}
        onClose={() => setAuthOpen(false)}
        onLogin={auth.login}
        onVerify={auth.verify}
        user={auth.user}
        loading={auth.loading}
        error={auth.error}
        linkSent={auth.linkSent}
        onLogout={auth.logout}
      />

      {/* ALERTS MODAL */}
      {alertOpen && (
        <div
          className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={(e) => { if (e.target === e.currentTarget) setAlertOpen(false); }}
        >
          <div className="w-full max-w-sm mx-4 bg-[#0c1225] border border-border/60 rounded-2xl shadow-2xl overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border/50">
              <div>
                <div className="text-[10px] font-mono font-bold uppercase tracking-[0.12em] text-purple mb-0.5">Price Alerts</div>
                <div className="text-[13px] font-bold text-text">Notify me when {symbol} triggers</div>
              </div>
              <button onClick={() => { setAlertOpen(false); setAlertMsg(""); }} className="text-text-muted hover:text-text text-xl leading-none">&times;</button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="text-[10px] font-mono text-text-muted/70 uppercase tracking-wide mb-1 block">Your email</label>
                <input type="email" value={alertEmail} onChange={e => setAlertEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full h-[38px] rounded-lg border border-border/60 bg-surface px-3 text-[13px] font-sans text-text placeholder:text-text-muted/50 outline-none focus:border-purple transition-all"
                />
              </div>
              <div>
                <label className="text-[10px] font-mono text-text-muted/70 uppercase tracking-wide mb-1 block">Alert type</label>
                <div className="flex gap-2">
                  {(["score", "price"] as const).map(t => (
                    <button key={t} onClick={() => setAlertType(t)}
                      className={`flex-1 py-2 rounded-lg text-[11px] font-mono font-bold border transition-all ${
                        alertType === t ? "border-purple bg-purple/10 text-purple" : "border-border/50 text-text-muted hover:border-text-muted"
                      }`}>{t === "score" ? "Score threshold" : "Price level"}</button>
                  ))}
                </div>
              </div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="text-[10px] font-mono text-text-muted/70 uppercase tracking-wide mb-1 block">
                    {alertType === "score" ? "Min score (1-16)" : "Price ($)"}
                  </label>
                  <input type="number" value={alertThreshold} onChange={e => setAlertThreshold(Number(e.target.value))}
                    min={alertType === "score" ? 1 : 0} max={alertType === "score" ? 16 : undefined}
                    step={alertType === "score" ? 1 : "any"}
                    className="w-full h-[38px] rounded-lg border border-border/60 bg-surface px-3 text-[13px] font-mono text-text outline-none focus:border-purple transition-all"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-[10px] font-mono text-text-muted/70 uppercase tracking-wide mb-1 block">Direction</label>
                  <select value={alertDirection} onChange={e => setAlertDirection(e.target.value as "above"|"below")}
                    className="w-full h-[38px] rounded-lg border border-border/60 bg-surface px-3 text-[13px] font-mono text-text outline-none focus:border-purple transition-all">
                    <option value="above">Above / &gt;=</option>
                    <option value="below">Below / &lt;=</option>
                  </select>
                </div>
              </div>
              <button
                onClick={async () => {
                  if (!alertEmail.includes("@")) { setAlertMsg("Please enter a valid email."); return; }
                  const res = await alertsHk.create({ symbol, alert_type: alertType, threshold: alertThreshold, direction: alertDirection });
                  setAlertMsg((res as any)?.message ?? (res as any)?.error ?? "Alert saved!");
                }}
                className="w-full py-2.5 rounded-lg font-bold text-[13px] text-white transition-all"
                style={{ background: "#7c3aed" }}
              >Set Alert for {symbol}</button>
              {alertMsg && <div className="text-[11px] font-mono text-teal text-center">{alertMsg}</div>}
              {alertsHk.alerts.length > 0 && (
                <div className="border-t border-border/40 pt-3">
                  <div className="text-[9px] font-mono text-text-muted/60 uppercase tracking-wide mb-2">Active alerts</div>
                  {alertsHk.alerts.map(a => (
                    <div key={a.id} className="flex items-center justify-between py-1.5 border-b border-border/20 last:border-none">
                      <span className="text-[11px] font-mono text-text">{a.symbol} {a.alert_type} {a.direction} {a.threshold}</span>
                      <button onClick={() => alertsHk.remove(a.id)} className="text-[9px] text-red hover:opacity-70 font-mono">remove</button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
