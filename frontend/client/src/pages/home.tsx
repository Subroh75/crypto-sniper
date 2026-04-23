// ??? home.tsx ? Crypto Sniper V2 Main Page ??????????????????????????????????
// Two-column terminal layout matching the V2 UX mockup exactly.
// Left: 10 analysis sections. Right: sidebar (Trade Setup, Conviction,
// Key Levels, Watchlist, Subscribe, Export).

import { useState, useCallback, useId, useRef } from "react";
import { Logo } from "@/components/Logo";
import { LiveTicker } from "@/components/LiveTicker";
import { MarketBar } from "@/components/MarketBar";
import { PriceChart } from "@/components/PriceChart";
import {
  TradeSetupCard, ConvictionMeter, KeyLevelsCard,
  WatchlistCard, SubscribeCard, ExportCard,
} from "@/components/Sidebar";
import {
  TrendingSection, NewsSection, MacroSection,
} from "@/components/BottomSections";
import { DeepResearchSection } from "@/components/DeepResearch";
import {
  useAnalyse, useKronos, useWatchlist, usePdfExport,
} from "@/hooks/useApi";
import { fmtPrice, fmtPct } from "@/lib/api";
import type { AnalyseResponse, KronosResponse } from "@/types/api";
import { LineChart, Line, ResponsiveContainer } from "recharts";

// ?? Constants ?????????????????????????????????????????????????????????????????
const INTERVALS = ["1m","5m","15m","30m","1H","4H","1D"] as const;
const QUICK_COINS = ["BTC","ETH","SOL","BNB","DOGE","KAVA"] as const;
const WATCHLIST_SYMS = ["BTC","ETH","SOL","BNB","DOGE","KAVA"] as const;

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

// ?? Shared card primitives ????????????????????????????????????????????????????
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

// ?? VPRT+S score bar ??????????????????????????????????????????????????????????
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

// ?? Agent verdict badge ???????????????????????????????????????????????????????
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

// ????????????????????????????????????????????????????????????????????????????
// MAIN PAGE
// ????????????????????????????????????????????????????????????????????????????
export default function Home() {
  const reportId = "cs-report-root";

  const [symbol,   setSymbol]   = useState("BTC");
  const [input,    setInput]    = useState("");
  const [interval, setInterval] = useState("1H");

  const analyse  = useAnalyse();
  const kronosHk = useKronos();
  const { scores: wlScores, loading: wlLoading } = useWatchlist([...WATCHLIST_SYMS]);
  const { exporting, exportPdf } = usePdfExport();

  const inputRef = useRef<HTMLInputElement>(null);

  // ?? Run full analysis ???????????????????????????????????????????????????????
  const runAnalysis = useCallback(async (sym?: string, iv?: string) => {
    const s = (sym ?? (input.trim().toUpperCase() || symbol));
    const i = iv ?? interval;
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

      {/* ?? HEADER ???????????????????????????????????????????????????????????? */}
      <header className="sticky top-0 z-50 border-b border-border/60 backdrop-blur-xl bg-bg/90">
        <div className="flex items-center gap-4 px-4 h-[50px]">
          <Logo />
          <LiveTicker />
          <div className="flex items-center gap-3 flex-shrink-0">
            <div className="flex items-center gap-1.5 text-[10px] font-mono text-teal">
              <div className="w-[6px] h-[6px] rounded-full bg-teal animate-pulse shadow-sm shadow-teal/50" />
              LIVE
            </div>
            <button className="text-[11px] font-mono text-text-muted border border-border/50 px-3 py-1.5 rounded hover:border-purple/40 hover:text-text transition-all">
              Log in
            </button>
            <button
              className="text-[11px] font-mono font-bold text-white px-3 py-1.5 rounded transition-all"
              style={{ background: "#7c3aed" }}
            >
              Subscribe ?
            </button>
          </div>
        </div>
      </header>

      {/* ?? MARKET BAR ???????????????????????????????????????????????????????? */}
      <MarketBar />

      {/* ?? HERO SEARCH ??????????????????????????????????????????????????????? */}
      <div className="text-center px-4 py-8">
        <h1 className="text-4xl sm:text-5xl font-black tracking-tight mb-2"
            style={{ background: "linear-gradient(140deg,#fff 20%,#7c3aed 80%)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent" }}>
          Real-Time Crypto Signal Engine
        </h1>
        <p className="text-text-muted text-[13px] mb-5">
          Live V/P/R/T/S scoring  �  Kronos AI forecast  �  On-chain signals  �  Multi-agent debate
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
            placeholder="BTC  �  ETH  �  SOL  �  KAVA..."
            className="flex-1 h-[46px] rounded-lg border border-border/60 bg-surface px-4 text-[15px] font-sans font-medium text-text placeholder:text-text-muted/50 outline-none focus:border-purple transition-all"
          />
          <button
            onClick={() => runAnalysis()}
            disabled={loading}
            className="h-[46px] px-5 rounded-lg font-sans font-bold text-[13px] text-white flex items-center gap-2 transition-all disabled:opacity-60"
            style={{ background: "#7c3aed" }}
          >
            {loading ? "?³" : "?¡"} {loading ? "Analysing..." : "Analyse"}
          </button>
        </div>

        {/* Quick coins */}
        <div className="flex justify-center gap-2 flex-wrap">
          <span className="text-[10px] font-mono text-text-muted/60 py-1 px-1">Try ?</span>
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

      {/* ?? MAIN TWO-COL LAYOUT ??????????????????????????????????????????????? */}
      <div className="max-w-[1380px] mx-auto px-4 pb-20">
        {!sig && !loading && (
          <div className="text-center py-16 text-text-muted text-[13px] font-mono">
            Enter a coin symbol above to get started
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

            {/* ?? LEFT COLUMN ??????????????????????????????????????????????? */}
            <div>

              {/* 01: Signal Output */}
              <Card>
                <CardHeader num="01" icon="?¡" title="SIGNAL OUTPUT" src="CoinGecko  �  Twelve Data" />
                <div className="p-4">
                  <div className="bg-surface-2 rounded-xl border border-border/50 p-5 text-center">
                    <div className="text-[10px] font-mono text-text-muted/70 mb-2 tracking-wide">
                      {symbol}/USDT  �  {interval}  �  {new Date(sig.timestamp * 1000).toUTCString().slice(0,-4)} UTC
                    </div>
                    <div className={`inline-block text-[10px] font-mono font-bold px-3 py-1 rounded border mb-3 ${VERDICT_BG[sig.signal.label] ?? VERDICT_BG["NO SIGNAL"]}`}>
                      {sig.signal.label}
                    </div>
                    <div className={`text-[34px] font-black mb-1 ${VERDICT_COLOR[sig.signal.label] ?? "text-text-muted"}`}>
                      {sig.signal.label}
                    </div>
                    <div className="text-[12px] font-mono text-text-muted mb-3">
                      {sig.signal.total} / {sig.signal.max} ? {sig.signal.label !== "STRONG BUY" ? "below threshold (<5)" : "strong setup!"}
                    </div>
                    <div className="flex justify-center gap-4 text-[11px] font-mono text-text-muted flex-wrap">
                      <span>CLOSE <span className="text-text font-bold">{fmtPrice(sig.quote.price)}</span></span>
                      <span>24H <span className={sig.quote.change_24h >= 0 ? "text-teal font-bold" : "text-red font-bold"}>{fmtPct(sig.quote.change_24h)}</span></span>
                      <span>VOL <span className="text-text font-bold">{sig.timing.rel_volume.toFixed(1)}?</span></span>
                      <span>ADX <span className="text-text font-bold">{sig.timing.adx.toFixed(0)}</span></span>
                      <span>RSI <span className={sig.timing.rsi >= 70 ? "text-red font-bold" : sig.timing.rsi <= 30 ? "text-teal font-bold" : "text-text font-bold"}>{sig.timing.rsi.toFixed(0)}</span></span>
                      <span>S <span className="text-orange font-bold">?{sig.components.S.score * 4}%</span></span>
                    </div>
                  </div>
                </div>
              </Card>

              {/* 02: Signal Components */}
              <Card>
                <CardHeader num="02" title="SIGNAL COMPONENTS V/P/R/T/S" src="CoinGecko  �  LunarCrush" />
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
                            {comp.label}
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
                  <CardHeader num="03" icon="?" title="MARKET STRUCTURE" />
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
                        <span className="text-[10px] font-mono text-text-muted/70 uppercase tracking-wide">{label as string}</span>
                        <span className={`text-[12px] font-mono font-bold ${
                          dir === "up" ? "text-teal" : dir === "warn" ? "text-red" : "text-text"
                        }`}>
                          {dir === "up" ? "?² " : dir === "warn" ? "?  " : "?¼ "}{fmtPrice(price as number)}
                        </span>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="mb-0">
                  <CardHeader num="04" icon="?±" title="TIMING QUALITY" />
                  <div className="p-4">
                    <div className="grid grid-cols-2 gap-2">
                      {[
                        { label: "RSI 14",  value: sig.timing.rsi.toFixed(1),    sub: sig.timing.rsi >= 70 ? "OVERBOUGHT" : sig.timing.rsi <= 30 ? "OVERSOLD" : "NEUTRAL",  color: sig.timing.rsi >= 70 ? "text-red" : sig.timing.rsi <= 30 ? "text-teal" : "text-text" },
                        { label: "ADX 14",  value: sig.timing.adx.toFixed(1),    sub: sig.timing.adx >= 25 ? "TRENDING" : "RANGING",   color: sig.timing.adx >= 25 ? "text-teal" : "text-text" },
                        { label: "ATR 14",  value: sig.timing.atr.toFixed(0),    sub: `${((sig.timing.atr / sig.quote.price) * 100).toFixed(2)}% of price`, color: "text-text" },
                        { label: "Rel Vol", value: `${sig.timing.rel_volume.toFixed(2)}?`, sub: sig.timing.rel_volume >= 2 ? "HIGH" : "NORMAL", color: sig.timing.rel_volume >= 2 ? "text-teal" : "text-text" },
                      ].map(({ label, value, sub, color }) => (
                        <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">{label}</div>
                          <div className={`text-[20px] font-mono font-black ${color}`}>{value}</div>
                          <div className={`text-[9px] font-mono mt-0.5 ${color} opacity-70`}>{sub}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </Card>
              </div>

              {/* 05: On-Chain Signals */}
              <Card>
                <CardHeader num="05" title="ON-CHAIN SIGNALS" badge="NEW" src="Etherscan  �  Covalent  �  Mempool" />
                <div className="p-4">
                  <div className="grid grid-cols-4 gap-2">
                    {[
                      { label: "Whale Transfers 24H", value: "$2.4B",    sub: "?34% vs avg", color: "text-teal" },
                      { label: "Exchange Netflow",     value: "-12,400",  sub: "Outflow ? bullish", color: "text-teal" },
                      { label: "Mempool Fees",         value: "45 sat/vB",sub: "High activity", color: "text-teal" },
                      { label: "Active Addresses",     value: "982K",     sub: "? Stable", color: "text-text" },
                    ].map(({ label, value, sub, color }) => (
                      <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-3">
                        <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1.5">{label}</div>
                        <div className={`text-[18px] font-mono font-black ${color}`}>{value}</div>
                        <div className={`text-[9px] font-mono mt-0.5 ${color} opacity-80`}>{sub}</div>
                      </div>
                    ))}
                  </div>
                </div>
              </Card>

              {/* 06: Kronos AI Forecast */}
              <Card>
                <CardHeader num="06" title="KRONOS AI FORECAST" src="Perplexity  �  Claude" />
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
                      <div className="grid grid-cols-3 gap-2 mb-3">
                        {[
                          { label: "AI Forecast",    value: kron.forecast.direction,        color: kron.forecast.direction === "Falling" ? "text-red" : kron.forecast.direction === "Rising" ? "text-teal" : "text-text" },
                          { label: "Expected Move",  value: `${kron.forecast.expected_move_pct >= 0 ? "?²" : "?¼"} ${Math.abs(kron.forecast.expected_move_pct).toFixed(2)}%`, color: kron.forecast.expected_move_pct >= 0 ? "text-teal" : "text-red" },
                          { label: "Trade Quality",  value: kron.forecast.trade_quality,    color: kron.forecast.trade_quality.includes("Avoid") ? "text-red" : "text-teal" },
                          { label: "Target Price",   value: fmtPrice(kron.forecast.target_price), color: "text-text" },
                          { label: "Bull Case",      value: kron.forecast.bull_case,        color: kron.forecast.bull_case === "TAKE" ? "text-teal" : "text-text-muted" },
                          { label: "Bear Case",      value: kron.forecast.bear_case,        color: kron.forecast.bear_case === "SHORT" ? "text-red" : "text-text-muted" },
                        ].map(({ label, value, color }) => (
                          <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-3">
                            <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">{label}</div>
                            <div className={`text-[16px] font-mono font-black ${color}`}>{value}</div>
                          </div>
                        ))}
                      </div>
                      {/* Forecast mini chart */}
                      <div className="bg-surface-2 rounded-lg border border-border/40 p-3" style={{ height: 130 }}>
                        <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-2">
                          PREDICTED OHLCV ? NEXT 24 CANDLES
                        </div>
                        <ResponsiveContainer width="100%" height={90}>
                          <LineChart data={kron.forecast.predicted_ohlcv}>
                            <Line type="monotone" dataKey="close" stroke="#7c5cfc" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
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
                <CardHeader num="07" icon="?§ " title="AI LAB ? AGENT DEBATE" src="Claude Haiku  �  Perplexity context" />
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

            </div>
            {/* ?? end LEFT column ?? */}

            {/* ?? RIGHT SIDEBAR ????????????????????????????????????????????? */}
            <div>
              <TradeSetupCard setup={sig.trade_setup} close={sig.quote.price} />
              <ConvictionMeter conviction={sig.conviction} />
              <KeyLevelsCard levels={sig.key_levels} />
              <WatchlistCard
                scores={wlScores}
                loading={wlLoading}
                onSelect={(sym) => runAnalysis(sym)}
                currentSymbol={symbol}
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
            {/* ?? end RIGHT sidebar ?? */}

          </div>
        )}
      </div>
    </div>
  );
}
