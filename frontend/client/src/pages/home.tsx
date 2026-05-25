//  home.tsx  Crypto Sniper V2 Main Page 
// Two-column terminal layout matching the V2 UX mockup exactly.
// Left: 10 analysis sections. Right: sidebar (Trade Setup, Conviction,
// Key Levels, Watchlist, Subscribe, Export).

import { useState, useCallback, useRef, useEffect } from "react";
import { useMobile } from "@/hooks/useMobile";
import { Logo } from "@/components/Logo";
import { LiveTicker } from "@/components/LiveTicker";
import { MarketBar } from "@/components/MarketBar";
import { PriceChart } from "@/components/PriceChart";
import {
  TradeSetupCard, ConvictionMeter, KeyLevelsCard,
  WatchlistCard, SubscribeCard, ExportCard, BasketScanner,
  ScannerCumulativeCard, DipScannerCard,
} from "@/components/Sidebar";
import { TopSignals } from "@/components/TopSignals";
import { CSOVerdict, buildVerdict } from "@/components/CSOVerdict";
import {
  TrendingSection, VolRadarSection, NewsSection, MacroSection, OptionsIntelligenceSection,
} from "@/components/BottomSections";
import { DeepResearchSection } from "@/components/DeepResearch";
import { MultiTimeframeCard } from "@/components/MultiTimeframe";
import { SignalStreakHeatmap } from "@/components/SignalStreakHeatmap";
import { PriceAlertCard, subscribeAlertBadge, markAlertsRead } from "@/components/PriceAlertCard";
import type { AlertHistoryEntry } from "@/components/PriceAlertCard";
import { ScanAlertPoller } from "@/components/ScanAlertPoller";
import { AuthModal, AuthButton } from "@/components/AuthModal";
import { PremiumModal, usePremiumGate } from "@/components/PremiumModal";
import { PWAInstallBanner } from "@/components/PWAInstallBanner";
import {
  useAnalyse, useKronos, useWatchlist, usePdfExport,
  useHitRate, useAlerts,
  useEditableWatchlist, useAuth, tierAtLeast,
  useDexAnalyse, detectInputType,
} from "@/hooks/useApi";
import { fmtPrice, fmtPct } from "@/lib/api";
import { MetricTooltip } from "@/components/Tooltip";
import type { AnalyseResponse, KronosResponse, DerivativesData, DexAnalyseResponse } from "@/types/api";
import { ComposedChart, Bar, Line, ResponsiveContainer, YAxis, XAxis, CartesianGrid, ReferenceLine } from "recharts";
import VolRadar from "@/components/VolRadar";

//  Constants 
const INTERVALS = ["1m","5m","15m","30m","1H","4H","1D"] as const;
const QUICK_COINS = ["BTC","ETH","SOL","BNB","DOGE","KAVA"] as const;

const VERDICT_COLOR: Record<string, string> = {
  "STRONG BUY": "text-teal",
  "BUY":        "text-teal",
  "MODERATE":   "text-amber",
  "NO SIGNAL":  "text-text-muted",
};

const VERDICT_BG: Record<string, string> = {
  "STRONG BUY": "bg-teal/8 border-teal/20",
  "BUY":        "bg-teal/5 border-teal/15",
  "MODERATE":   "bg-amber/8 border-amber/20",
  "NO SIGNAL":  "bg-surface-2 border-border/50",
};

// ── Alert Bell ────────────────────────────────────────────────────────────
function AlertBell() {
  const [count, setCount]     = useState(0);
  const [history, setHistory] = useState<AlertHistoryEntry[]>([]);
  const [open, setOpen]       = useState(false);
  const bellRef               = useRef<HTMLDivElement>(null);

  useEffect(() => {
    return subscribeAlertBadge((c, h) => { setCount(c); setHistory(h); });
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (bellRef.current && !bellRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  function handleOpen() {
    setOpen(p => !p);
    if (!open && count > 0) markAlertsRead();
  }

  function fmtTs(ts: number) {
    const d = new Date(ts * 1000);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" }) +
      " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  return (
    <div ref={bellRef} style={{ position: "relative" }}>
      <button
        onClick={handleOpen}
        aria-label="Alert notifications"
        style={{ background: count > 0 ? "#f59e0b18" : "#7c3aed0d", border: `1px solid ${count > 0 ? "#f59e0b55" : "#7c3aed33"}`, borderRadius: 8,
          padding: "6px 9px", cursor: "pointer", display: "flex", alignItems: "center",
          color: count > 0 ? "#f59e0b" : "#a78bfa", position: "relative", minHeight: 36 }}
      >
        {/* Bell SVG */}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {/* Badge */}
        {count > 0 && (
          <span style={{ position: "absolute", top: -4, right: -4, minWidth: 16, height: 16,
            borderRadius: 8, background: "#ef4444", color: "#fff",
            fontSize: 9, fontWeight: 800, display: "flex", alignItems: "center", justifyContent: "center",
            padding: "0 3px", lineHeight: 1 }}>
            {count > 9 ? "9+" : count}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div style={{ position: "absolute", top: "calc(100% + 8px)", right: 0, zIndex: 200,
          width: 280, background: "#0c1225", border: "1px solid #1e293b", borderRadius: 12,
          boxShadow: "0 8px 32px #00000080", overflow: "hidden" }}>
          <div style={{ padding: "10px 14px", borderBottom: "1px solid #1e293b",
            fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" }}>
            Alert History
          </div>
          {history.length === 0 ? (
            <div style={{ padding: "16px 14px", fontSize: 11, color: "#334155", textAlign: "center" }}>
              No alerts fired yet
            </div>
          ) : (
            <div style={{ maxHeight: 320, overflowY: "auto" }}>
              {history.slice(0, 10).map(h => (
                <div key={h.id} style={{ padding: "9px 14px", borderBottom: "1px solid #0f172a",
                  display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
                      <span style={{ fontSize: 11, fontWeight: 800, color: "#22c55e", fontFamily: "monospace" }}>{h.symbol}</span>
                      <span style={{ fontSize: 9, color: "#475569" }}>{h.alert_type} {h.direction} {h.threshold}</span>
                    </div>
                    <div style={{ fontSize: 10, color: "#64748b" }}>
                      {h.alert_type === "score" ? `Score ${h.score}/16` : `$${h.price.toFixed(6)}`}
                    </div>
                  </div>
                  <div style={{ fontSize: 9, color: "#334155", whiteSpace: "nowrap", marginLeft: 8 }}>
                    {fmtTs(h.fired_ts)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

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

  const [volCoins,  setVolCoins]  = useState<Array<{symbol:string;price:number;change:number;rel_vol?:number;signal?:string}>>([]);
  const [symbol,   setSymbol]   = useState("BTC");
  const [input,    setInput]    = useState("");
  const [interval, setInterval] = useState("1D");

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
  // Tier helpers — admin/full always passes everything
  // GATE_ENABLED: false until Telegram payment bot is live. Flip to true to enforce tiers.
  const GATE_ENABLED = false;
  const isFullAccess = !GATE_ENABLED || tierAtLeast(auth.user, "full");
  const [premiumOpen, setPremiumOpen] = useState(false);
  const [premiumFeature, setPremiumFeature] = useState("");
  function requireFull(feature: string, action: () => void) {
    if (isFullAccess) { action(); return; }
    setPremiumFeature(feature);
    setPremiumOpen(true);
  }

  const analyse    = useAnalyse();
  const dexAnalyse  = useDexAnalyse();
  const kronosHk   = useKronos();
  // "cex" | "dex" — tracks which engine returned the current result
  const [activeSource, setActiveSource] = useState<"cex"|"dex">("cex");

  // Editable watchlist from backend DB
  const editableWL = useEditableWatchlist(userId);
  const { scores: wlScores, loading: wlLoading } = useWatchlist(editableWL.symbols.length ? editableWL.symbols : ["BTC","ETH","SOL","BNB","DOGE"]);

  const { exporting, exportPdf } = usePdfExport();
  const hitRate = useHitRate(null, 30);
  const alertsHk = useAlerts(alertEmail || null);

  const inputRef = useRef<HTMLInputElement>(null);

  //  Smart router — detects symbol vs contract address and routes accordingly 
  const runAnalysis = useCallback(async (sym?: string, iv?: string) => {
    const raw = sym ?? input.trim();
    if (!raw) return;

    const inputType = detectInputType(raw);

    if (inputType === "dex") {
      // ── DEX path: contract address or DexScreener URL ──────────────────
      setInput(raw);
      setActiveSource("dex");
      await dexAnalyse.run(raw, "auto");
      return;
    }

    // ── CEX path: symbol (default) ─────────────────────────────────────
    const s = raw.toUpperCase();
    const i = iv ?? interval;
    setSymbol(s);
    setInput(s);
    setActiveSource("cex");

    const result = await analyse.run(s, i);
    if (!result) return;

    // Build signal context for Kronos — include all VPRTS + market structure + conviction data.
    // All numeric fields default to 0 (never null/undefined) to prevent backend format-string crashes.
    const n = (v: number | null | undefined, fallback = 0) => v ?? fallback;
    const ctx = {
      close:        n(result.quote.price),
      rsi:          n(result.timing.rsi, 50),
      adx:          n(result.timing.adx),
      atr:          n(result.timing.atr),
      rel_volume:   n(result.timing.rel_volume, 1),
      ema_stack:    result.structure.ema20 > 0 && result.structure.ema50 > 0
                      && result.quote.price > result.structure.ema20,
      ema20:        n(result.structure.ema20),
      ema50:        n(result.structure.ema50),
      ema200:       n(result.structure.ema200),
      vwap:         n(result.structure.vwap),
      bb_upper:     n(result.structure.bb_upper),
      bb_lower:     n(result.structure.bb_lower),
      signal:       result.signal.label,
      total:        n(result.signal.total),
      direction:    result.signal.direction,
      change_24h:   n(result.quote.change_24h),
      v_score:      n(result.components?.V?.score ?? 0),
      p_score:      n(result.components?.P?.score ?? 0),
      r_score:      n(result.components?.R?.score ?? 0),
      t_score:      n(result.components?.T?.score ?? 0),
      s_score:      0,
      entry:        result.trade_setup.entry ?? 0,
      stop:         result.trade_setup.stop ?? 0,
      target:       result.trade_setup.target ?? 0,
      rr_ratio:     result.trade_setup.rr_ratio ?? 0,
      stop_dist_pct: result.trade_setup.stop_dist_pct ?? 0,
      bull_pct:     n(result.conviction?.bull_pct),
      bear_pct:     n(result.conviction?.bear_pct),
      bull_signals: result.conviction?.bull_signals ?? [],
      bear_signals: result.conviction?.bear_signals ?? [],
      fg_value:     result.fear_greed?.value ?? 50,
      fg_label:     result.fear_greed?.label ?? "Neutral",
    } as Record<string, unknown>;

    kronosHk.run(s, i, ctx);
  }, [input, symbol, interval, analyse, dexAnalyse, kronosHk]);

  const sig     = analyse.data;
  const dexSig  = dexAnalyse.data;
  const kron    = kronosHk.data;
  const loading = activeSource === "dex" ? dexAnalyse.loading : analyse.loading;
  const isMobile = useMobile();
  // Mobile tab: which panel is visible
  const [mobileTab, setMobileTab] = useState<"analyse"|"signals"|"sidebar"|"scanner"|"volradar">("analyse");

  // Scroll-to-top when switching mobile tabs
  useEffect(() => {
    if (isMobile) window.scrollTo({ top: 0, behavior: "smooth" });
  }, [mobileTab, isMobile]);

  return (
    <div className="min-h-screen bg-bg text-text" id={reportId}>
      {isMobile && <PWAInstallBanner />}
      <ScanAlertPoller />

      {/*  HEADER  */}
      <header className="sticky top-0 z-50 border-b border-border/60 backdrop-blur-xl bg-bg/90" style={{ paddingTop: 'env(safe-area-inset-top, 0px)' }}>
        <div className="flex items-center gap-2 md:gap-4 px-3 md:px-4 h-[50px]">
          <Logo />
          {/* LiveTicker hidden on mobile to save space */}
          <div className="hidden md:block flex-1 min-w-0">
            <LiveTicker />
          </div>
          <div className="flex-1 md:flex-none" />
          <div className="flex items-center gap-2 md:gap-3 flex-shrink-0">
            <div className="flex items-center gap-1 text-[10px] font-mono text-teal">
              <div className="w-[6px] h-[6px] rounded-full bg-teal animate-pulse shadow-sm shadow-teal/50" />
              <span className="hidden sm:inline">LIVE</span>
            </div>
            <AuthButton user={auth.user} onClick={() => setAuthOpen(true)} />
            <AlertBell />
            {!isFullAccess && (
              <a
                href="https://t.me/Niftysnipabot?start=subscribe"
                target="_blank"
                rel="noopener noreferrer"
                className="hidden md:flex items-center gap-1.5 text-[11px] font-mono font-bold text-white px-2.5 md:px-3 py-1.5 rounded transition-all min-h-[36px]"
                style={{ background: "linear-gradient(135deg,#7c3aed,#4f46e5)", textDecoration: "none" }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="#fff">
                  <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/>
                </svg>
                Get Full Access
              </a>
            )}
          </div>
        </div>
      </header>

      {/*  MARKET BAR  */}
      <MarketBar />

      {/*  HERO SEARCH  */}
      <div className="text-center px-4 py-6 md:py-8">
        <h1 className="text-2xl sm:text-4xl md:text-5xl font-black tracking-tight mb-2 leading-tight"
            style={{ background: "linear-gradient(140deg,#fff 20%,#7c3aed 80%)", WebkitBackgroundClip:"text", WebkitTextFillColor:"transparent" }}>
          Real-Time Crypto Signal Engine
        </h1>
        <p className="text-text-muted text-[11px] md:text-[13px] mb-4 md:mb-5 px-2">
          V/P/R/T scoring &middot; Kronos AI &middot; On-chain &middot; Agent debate
        </p>

        {/* Timeframe pills */}
        <div className="flex justify-center gap-1 md:gap-1.5 mb-3 flex-wrap">
          {INTERVALS.map(iv => (
            <button
              key={iv}
              onClick={() => setInterval(iv)}
              className={`text-[11px] font-mono font-bold px-2.5 md:px-3 py-1.5 rounded-md border transition-all min-h-[36px] ${
                iv === interval
                  ? "border-purple text-purple bg-purple/8"
                  : "border-border/50 text-text-muted hover:border-text-muted hover:text-text"
              }`}
            >
              {iv}
            </button>
          ))}
        </div>

        {/* Search row — stacks on mobile */}
        <div className="flex flex-col sm:flex-row gap-2 max-w-[640px] mx-auto mb-3">
          <input
            ref={inputRef}
            value={input}
            onChange={e => {
              const v = e.target.value;
              // Don't force uppercase for contract addresses (0x...) or URLs
              const isContract = v.startsWith("0x") || v.startsWith("http") || v.length > 12;
              setInput(isContract ? v : v.toUpperCase());
            }}
            onKeyDown={e => e.key === "Enter" && requireFull("Deep analysis", () => { runAnalysis(); })}
            onClick={() => { if (!isFullAccess) requireFull("Deep analysis", () => {}); }}
            readOnly={!isFullAccess}
            placeholder={isFullAccess ? "BTC, ETH, SOL  or paste a contract address..." : "Full App only — upgrade to search any coin"}
            className={`flex-1 h-[48px] rounded-lg border border-border/60 bg-surface px-4 text-[15px] font-sans font-medium text-text placeholder:text-text-muted/50 outline-none focus:border-purple transition-all w-full ${
              !isFullAccess ? "cursor-pointer opacity-70" : ""
            }`}
          />
          <button
            onClick={() => requireFull("Deep analysis", () => { runAnalysis(); if (isMobile) setMobileTab("analyse"); })}
            disabled={loading && isFullAccess}
            className="h-[48px] px-5 rounded-lg font-sans font-bold text-[13px] text-white flex items-center justify-center gap-2 transition-all disabled:opacity-60 w-full sm:w-auto"
            style={{ background: "#7c3aed" }}
          >
            {loading && isFullAccess ? "Analysing..." : isFullAccess ? "Analyse" : "🔒 Upgrade to Analyse"}
          </button>
        </div>

        {/* Smart input hint */}
        {input && (() => {
          const t = detectInputType(input);
          if (t === "dex") return (
            <div className="flex justify-center mb-2">
              <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border border-blue/40 bg-blue/10 text-blue">
                Contract detected — will run DEX analysis
              </span>
            </div>
          );
          return null;
        })()}

        {/* Quick coins */}
        <div className="flex justify-center gap-1.5 flex-wrap">
          <span className="text-[10px] font-mono text-text-muted/60 py-1 px-1">Try</span>
          {QUICK_COINS.map(sym => (
            <button
              key={sym}
              onClick={() => requireFull("Deep analysis", () => { runAnalysis(sym); if (isMobile) setMobileTab("analyse"); })}
              className="text-[11px] font-mono px-2.5 py-1 rounded-md border border-border/50 bg-surface-2 text-text-muted hover:border-purple/40 hover:text-text transition-all min-h-[32px]"
            >
              {sym}
            </button>
          ))}
        </div>
      </div>

      {/*  MAIN LAYOUT  */}
      <div className="max-w-[1380px] mx-auto px-3 md:px-4 pb-tab-bar md:pb-20">

        {!sig && !loading && (
          <div className="max-w-[640px] mx-auto px-2 py-6">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-6">
              {[
                { icon: "V", label: "Volume",    desc: "Relative volume vs 20-bar avg" },
                { icon: "P", label: "Momentum",  desc: "ATR-adjusted price move" },
                { icon: "R", label: "Range",     desc: "Position within Bollinger Bands" },
                { icon: "T", label: "Trend",     desc: "EMA stack + ADX confirmation" },
              ].map(f => (
                <div key={f.icon} className="bg-surface-card border border-border/50 rounded-xl p-3 text-center">
                  <div className="text-[22px] font-black text-purple mb-1">{f.icon}</div>
                  <div className="text-[11px] font-mono font-bold text-text mb-0.5">{f.label}</div>
                  <div className="text-[9px] font-mono text-text-muted/60 leading-relaxed">{f.desc}</div>
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {[
                { icon: "🤖", label: "Kronos AI",     desc: "Expected move, target price, conviction" },
                { icon: "⚖",  label: "Agent Debate",  desc: "Bull / Bear / Risk / CIO verdicts" },
                { icon: "📊", label: "Derivatives",   desc: "Funding rate, OI, long/short ratio" },
              ].map(f => (
                <div key={f.label} className="bg-surface-card border border-border/50 rounded-xl p-3 flex items-start gap-2.5">
                  <span className="text-[18px] leading-none mt-0.5">{f.icon}</span>
                  <div>
                    <div className="text-[11px] font-mono font-bold text-text mb-0.5">{f.label}</div>
                    <div className="text-[9px] font-mono text-text-muted/60 leading-relaxed">{f.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {loading && (
          <div className="flex items-center justify-center gap-3 py-16 text-text-muted text-[12px] font-mono">
            <div className="flex gap-1">
              {[0,1,2].map(i => (
                <div key={i} className="w-2 h-2 rounded-full bg-purple animate-bounce" style={{ animationDelay: `${i*0.15}s` }} />
              ))}
            </div>
            {activeSource === "dex" ? "Scanning DEX..." : `Analysing ${symbol}...`}
          </div>
        )}

        {/* ── DEX RESULT ─────────────────────────────────────────────────────── */}
        {dexSig && !loading && activeSource === "dex" && (() => {
          const ds = dexSig;
          const RISK_COLOR: Record<string, string> = {
            LOW: "#22c55e", MEDIUM: "#f59e0b", HIGH: "#ef4444", CRITICAL: "#ef4444", UNKNOWN: "#94a3b8"
          };
          const riskColor = RISK_COLOR[ds.risk?.level ?? "UNKNOWN"] ?? "#94a3b8";
          const verdictColor = ds.signal.label === "STRONG BUY" ? "#22c55e" : ds.signal.label === "BUY" ? "#22c55e" : "#94a3b8";
          const fmtUsd = (n: number) => n >= 1e9 ? `$${(n/1e9).toFixed(2)}B` : n >= 1e6 ? `$${(n/1e6).toFixed(2)}M` : n >= 1e3 ? `$${(n/1e3).toFixed(1)}K` : `$${n.toFixed(2)}`;
          const fmtAge = (h: number) => h >= 720 ? `${Math.floor(h/720)}mo` : h >= 24 ? `${Math.floor(h/24)}d` : `${Math.round(h)}h`;
          return (
            <div className={isMobile ? "flex flex-col gap-3" : "grid gap-3"} style={isMobile ? undefined : { gridTemplateColumns: "1fr 320px" }}>
              <div className={isMobile && mobileTab !== "analyse" ? "hidden" : ""}>

                {/* DEX 01: Signal Output */}
                <Card>
                  <CardHeader num="01" icon="!" title="SIGNAL OUTPUT"
                    right={<span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border border-blue/40 bg-blue/10 text-blue">DEX • {ds.chain?.toUpperCase()}</span>}
                  />
                  <div className="p-4">
                    <div className="bg-surface-2 rounded-xl border border-border/50 p-5 text-center">
                      <div className="text-[10px] font-mono text-text-muted/70 mb-2 tracking-wide">
                        {ds.symbol}  ·  {ds.dex?.toUpperCase()}  ·  {new Date(ds.timestamp * 1000).toUTCString().slice(0,-4)} UTC
                      </div>
                      <div className="text-[34px] font-black mb-1" style={{ color: verdictColor }}>
                        {ds.signal.label}
                      </div>
                      <div className="text-[12px] font-mono text-text-muted mb-3">
                        {ds.signal.label === "STRONG BUY" ? "all gates confirmed" : ds.signal.label === "BUY" ? "VOL + TREND + ADX confirmed" : "conditions not met"}
                      </div>
                      {/* Gate summary chips */}
                      <div className="flex justify-center gap-2 mb-4 flex-wrap">
                        {(["v","t","adx"] as const).map(g => (
                          <span key={g} className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded ${
                            ds.signal.gates[g] ? "bg-teal/10 text-teal" : "bg-red/10 text-red"
                          }`}>
                            {g.toUpperCase()} {ds.signal.gates[g] ? "✓" : "✗"}
                          </span>
                        ))}
                      </div>
                      {/* Key metrics */}
                      <div className="flex justify-center gap-4 text-[11px] font-mono text-text-muted flex-wrap">
                        <span>PRICE <span className="text-text font-bold">{ds.market.price < 0.01 ? ds.market.price.toExponential(3) : fmtPrice(ds.market.price)}</span></span>
                        <span>24H <span className={ds.market.change_24h >= 0 ? "text-teal font-bold" : "text-red font-bold"}>{ds.market.change_24h >= 0 ? "+" : ""}{ds.market.change_24h.toFixed(2)}%</span></span>
                        <span>LIQ <span className="text-amber font-bold">{fmtUsd(ds.market.liquidity)}</span></span>
                        <span>VOL <span className="text-text font-bold">{fmtUsd(ds.market.volume_24h)}</span></span>
                        <span>AGE <span className="text-text-muted font-bold">{fmtAge(ds.market.pair_age_h)}</span></span>
                      </div>
                    </div>
                    {/* Low liquidity warning */}
                    {ds.market.liquidity < 100_000 && (
                      <div className="flex items-start gap-2 bg-amber-950/40 border border-amber-800/50 rounded-lg px-3 py-2 mt-3 text-left">
                        <span className="text-amber-400 text-[13px] flex-shrink-0 mt-px">⚠</span>
                        <div>
                          <div className="text-[10px] font-bold text-amber-400 tracking-wide mb-0.5">LOW LIQUIDITY</div>
                          <div className="text-[9px] font-mono text-amber-200/70">Under $100K liquidity — high slippage risk. Small orders can move the price significantly.</div>
                        </div>
                      </div>
                    )}
                    {/* Plain-English AI summary */}
                    <div className="mt-3 bg-purple/5 border border-purple/20 rounded-lg px-4 py-3">
                      <div className="text-[8px] font-mono font-bold text-purple/70 tracking-widest uppercase mb-1">Analysis</div>
                      <div className="text-[12px] font-sans text-text/80 leading-relaxed">{ds.summary}</div>
                    </div>
                  </div>
                </Card>

                {/* DEX 02: VPRT Components */}
                <Card>
                  <CardHeader num="02" title="SIGNAL COMPONENTS" />
                  <div className="p-4">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                      {(["V","P","R","T"] as const).map(key => {
                        const comp = ds.components[key];
                        const isGate = key === "V" || key === "T";
                        const confirmed = comp.confirmed;
                        const color = confirmed ? "#22c55e" : isGate ? "#ef4444" : "#f59e0b";
                        const borderColor = confirmed ? "rgba(34,197,94,0.25)" : isGate ? "rgba(239,68,68,0.2)" : "rgba(245,158,11,0.15)";
                        return (
                          <div key={key} className="bg-surface-2 rounded-lg border p-3" style={{ borderColor }}>
                            <div className="flex items-start justify-between mb-1">
                              <div className="text-[22px] font-black" style={{ color }}>{key}</div>
                              <div className="text-[8px] font-mono font-bold px-1.5 py-0.5 rounded mt-1" style={{ color, background: confirmed ? "rgba(34,197,94,0.1)" : isGate ? "rgba(239,68,68,0.1)" : "rgba(245,158,11,0.1)" }}>
                                {confirmed ? (isGate ? "CONFIRMED" : "YES") : (isGate ? "NOT MET" : "NO")}
                              </div>
                            </div>
                            <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-2">{comp.label}</div>
                            <div className="text-[9px] font-mono leading-relaxed" style={{ color: confirmed ? "#22c55e" : "#94a3b8" }}>{comp.detail}</div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </Card>

                {/* DEX 03: Price Timeframes */}
                <Card>
                  <CardHeader num="03" icon="-" title="PRICE ACROSS TIMEFRAMES" />
                  <div className="p-4">
                    <div className="grid grid-cols-4 gap-2">
                      {(["5m","1h","6h","24h"] as const).map(tf => {
                        const v = tf === "5m" ? ds.market.change_5m : tf === "1h" ? ds.market.change_1h : tf === "6h" ? ds.market.change_6h : ds.market.change_24h;
                        return (
                          <div key={tf} className="bg-surface-2 rounded-lg border border-border/40 p-3 text-center">
                            <div className="text-[9px] font-mono text-text-muted/70 uppercase mb-1">{tf}</div>
                            <div className={`text-[16px] font-mono font-black ${v >= 0 ? "text-teal" : "text-red"}`}>{v >= 0 ? "+" : ""}{v.toFixed(2)}%</div>
                          </div>
                        );
                      })}
                    </div>
                    {/* Buy/Sell pressure */}
                    {(ds.market.buys_1h + ds.market.sells_1h) > 0 && (() => {
                      const total = ds.market.buys_1h + ds.market.sells_1h;
                      const buyPct = Math.round(ds.market.buys_1h / total * 100);
                      return (
                        <div className="mt-3">
                          <div className="flex justify-between text-[9px] font-mono mb-1">
                            <span className="text-teal font-bold">BUY {buyPct}%</span>
                            <span className="text-text-muted/60">1H TXN FLOW</span>
                            <span className="text-red font-bold">SELL {100-buyPct}%</span>
                          </div>
                          <div className="h-2 rounded-full bg-red/30 overflow-hidden">
                            <div className="h-full rounded-full bg-teal" style={{ width: `${buyPct}%` }} />
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                </Card>

                {/* DEX 04: Risk Scan */}
                <Card>
                  <CardHeader num="04" icon="!" title="RISK SCAN"
                    right={<span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded" style={{ color: riskColor, background: `${riskColor}15` }}>{ds.risk?.level ?? "UNKNOWN"}</span>}
                  />
                  <div className="p-4">
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
                      {[
                        { label: "Honeypot",  val: ds.risk?.honeypot,  good: false },
                        { label: "Verified",  val: ds.risk?.verified,  good: true  },
                        { label: "Renounced", val: ds.risk?.renounced, good: true  },
                        { label: "Mintable",  val: ds.risk?.mintable,  good: false },
                      ].map(({ label, val, good }) => (
                        <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-2.5 text-center">
                          <div className="text-[9px] font-mono text-text-muted/70 mb-1">{label}</div>
                          <div className={`text-[11px] font-mono font-bold ${
                            val === null ? "text-text-muted/50" :
                            (val === good) ? "text-teal" : "text-red"
                          }`}>
                            {val === null ? "—" : val ? "YES" : "NO"}
                          </div>
                        </div>
                      ))}
                    </div>
                    {ds.risk?.buy_tax !== null && (
                      <div className="flex gap-3 text-[10px] font-mono mb-2">
                        <span>BUY TAX <span className={`font-bold ${(ds.risk?.buy_tax ?? 0) > 5 ? "text-red" : "text-teal"}`}>{ds.risk?.buy_tax?.toFixed(1)}%</span></span>
                        <span>SELL TAX <span className={`font-bold ${(ds.risk?.sell_tax ?? 0) > 5 ? "text-red" : "text-teal"}`}>{ds.risk?.sell_tax?.toFixed(1)}%</span></span>
                        {ds.risk?.top10_pct !== null && <span>TOP 10 HOLD <span className={`font-bold ${(ds.risk?.top10_pct ?? 0) > 60 ? "text-red" : "text-amber"}`}>{ds.risk?.top10_pct?.toFixed(1)}%</span></span>}
                      </div>
                    )}
                    {ds.risk?.flags && ds.risk.flags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {ds.risk.flags.map(f => (
                          <span key={f} className="text-[8px] font-mono font-bold px-1.5 py-0.5 rounded bg-red/10 text-red border border-red/20">{f}</span>
                        ))}
                      </div>
                    )}
                    {(ds.risk?.flags?.length === 0) && (
                      <div className="text-[10px] font-mono text-teal">No risk flags detected</div>
                    )}
                  </div>
                </Card>

                {/* DEX 05: Trade Setup */}
                {ds.trade_setup?.entry > 0 && (
                  <Card>
                    <CardHeader num="05" icon="-" title="TRADE SETUP" />
                    <div className="p-4">
                      <div className="grid grid-cols-3 gap-2">
                        {[
                          { label: "Entry",   val: ds.trade_setup.entry,  color: "text-text" },
                          { label: "Stop",    val: ds.trade_setup.stop,   color: "text-red"  },
                          { label: "Target",  val: ds.trade_setup.target, color: "text-teal" },
                        ].map(({ label, val, color }) => (
                          <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-3 text-center">
                            <div className="text-[9px] font-mono text-text-muted/70 mb-1">{label}</div>
                            <div className={`text-[13px] font-mono font-bold ${color}`}>
                              {val < 0.01 ? val.toExponential(3) : fmtPrice(val)}
                            </div>
                          </div>
                        ))}
                      </div>
                      <div className="mt-2 text-center text-[10px] font-mono text-text-muted/70">
                        R:R {ds.trade_setup.rr?.toFixed(1)}:1  ·  5% stop  ·  10% target
                      </div>
                      {ds.dex_url && (
                        <a href={ds.dex_url} target="_blank" rel="noopener noreferrer"
                          className="mt-3 flex items-center justify-center gap-1.5 text-[10px] font-mono font-bold text-purple hover:text-purple/80 transition-colors">
                          View on DexScreener ↗
                        </a>
                      )}
                    </div>
                  </Card>
                )}

              </div>
              {/* DEX sidebar — minimal for now */}
              <div className={isMobile && mobileTab !== "sidebar" ? "hidden" : ""}>
                <WatchlistCard
                  scores={wlScores}
                  loading={wlLoading}
                  editableSymbols={editableWL.symbols}
                  onAdd={editableWL.add}
                  onRemove={editableWL.remove}
                  onSelect={(sym) => { runAnalysis(sym); if(isMobile) setMobileTab("analyse"); }}
                />
              </div>
            </div>
          );
        })()}

        {sig && !loading && activeSource === "cex" && (
          <div
            className={isMobile ? "flex flex-col gap-3" : "grid gap-3"}
            style={isMobile ? undefined : { gridTemplateColumns: "1fr 320px" }}
          >
            {/* LEFT COLUMN — full on desktop; hidden on mobile unless tab=analyse */}
            <div className={isMobile && mobileTab !== "analyse" ? "hidden" : ""}>

              {/* 01: Signal Output */}
              <Card>
                <CardHeader num="01" icon="!" title="SIGNAL OUTPUT"
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
                    <div className={`text-[34px] font-black mb-1 ${VERDICT_COLOR[sig.signal.label] ?? "text-text-muted"}`}>
                      {sig.signal.label}
                    </div>
                    <div className="text-[12px] font-mono text-text-muted mb-3">
                      {sig.signal.label === "STRONG BUY" ? "All gates confirmed" : sig.signal.label === "BUY" ? "VOL + TREND + ADX confirmed" : "Gates not met"}
                    </div>

                    {/* Low liquidity / thin book warning */}
                    {(sig.low_liquidity || sig.microstructure?.signal === "thin_book") && (
                      <div className="flex items-start gap-2 bg-amber-950/40 border border-amber-800/50 rounded-lg px-3 py-2 mb-3 text-left">
                        <span className="text-amber-400 text-[13px] flex-shrink-0 mt-px">⚠</span>
                        <div>
                          <div className="text-[10px] font-bold text-amber-400 tracking-wide mb-0.5">
                            {sig.low_liquidity && sig.microstructure?.signal === "thin_book"
                              ? "LOW LIQUIDITY — THIN BOOK"
                              : sig.low_liquidity
                              ? "LOW LIQUIDITY COIN"
                              : "THIN ORDER BOOK"}
                          </div>
                          <div className="text-[9px] font-mono text-amber-200/70 leading-relaxed">
                            {sig.low_liquidity && (
                              <span>24h volume under $1M — VPRT scores can be inflated by single large trades. </span>
                            )}
                            {sig.microstructure?.signal === "thin_book" && (
                              <span>Spread {sig.microstructure.spread_pct.toFixed(3)}% — expect slippage on entry. </span>
                            )}
                            <span className="text-amber-400/60">Raise your conviction threshold before acting.</span>
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="flex justify-center gap-4 text-[11px] font-mono text-text-muted flex-wrap">
                      <span>CLOSE <span className={sig.quote.price > sig.structure.ema20 ? "text-teal font-bold" : "text-red font-bold"}>{fmtPrice((sig.quote?.price ?? 1))}</span></span>
                      <span>24H <span className={sig.quote.change_24h >= 0 ? "text-teal font-bold" : "text-red font-bold"}>{fmtPct(sig.quote.change_24h)}</span></span>
                      <span>VOL <span className={(sig.timing?.rel_volume ?? 0) >= 1.8 ? "text-teal font-bold" : "text-amber font-bold"}>{(sig.timing?.rel_volume ?? 0) >= 3.5 ? "Extreme" : (sig.timing?.rel_volume ?? 0) >= 2.5 ? "High" : (sig.timing?.rel_volume ?? 0) >= 1.8 ? "Elevated" : "Normal"}</span></span>
                      <span>ADX <span className={(sig.timing?.adx ?? 0) >= 25 ? "text-teal font-bold" : "text-amber font-bold"}>{(sig.timing?.adx ?? 0) >= 25 ? "Trending" : "Ranging"}</span></span>
                      {sig.timing?.z_quality && sig.timing.z_quality !== "UNKNOWN" && (() => {
                        const zq = sig.timing.z_quality as string;
                        const zColor = zq === "IDEAL" ? "#22c55e" : zq === "GOOD" ? "#22c55e" : zq === "CAUTION" ? "#f59e0b" : "#ef4444";
                        return (
                          <span style={{ color: zColor }} className="font-bold" title={`Entry quality: ${zq}. Z-score measures if price/vol/return are statistically extended.`}>
                            ENTRY {zq}
                          </span>
                        );
                      })()}
                    </div>
                  </div>
                  {/* Plain-English summary — one line any trader can act on */}
                  {(() => {
                    const label = sig.signal.label;
                    const vol   = (sig.timing?.rel_volume ?? 0).toFixed(1);
                    const adx   = sig.timing?.adx ?? 0;
                    const chg   = sig.quote.change_24h ?? 0;
                    const rsi   = sig.timing?.rsi ?? 50;
                    let summary = "";
                    if (label === "STRONG BUY") {
                      summary = `${symbol} is showing strong conditions — volume is unusually elevated, trend is fully aligned across all MAs, and ADX confirms a trending market. All gates are green.`;
                    } else if (label === "BUY") {
                      summary = `${symbol} has elevated volume and trend is aligned${adx >= 25 ? " with ADX confirming a trending market" : ""} — core conditions are met.`;
                    } else {
                      const issues = [];
                      if (!sig.signal.gates?.v) issues.push("volume is below threshold");
                      if (!sig.signal.gates?.t) issues.push("trend is not aligned across all MAs");
                      if (!sig.signal.gates?.adx) issues.push(`ADX is ${adx.toFixed(0)} — market is ranging, not trending`);
                      summary = `No clear signal for ${symbol} right now — ${issues.join(" and ")}. Worth watching if conditions improve.`;
                    }
                    return (
                      <div className="mt-3 mx-4 mb-0 bg-purple/5 border border-purple/20 rounded-lg px-4 py-3">
                        <div className="text-[8px] font-mono font-bold text-purple/70 tracking-widest uppercase mb-1">Analysis</div>
                        <div className="text-[12px] font-sans text-text/80 leading-relaxed">{summary}</div>
                      </div>
                    );
                  })()}
                </div>
              </Card>

              {/* 02: Signal Components */}
              <Card>
                <CardHeader num="02" title="SIGNAL COMPONENTS" />
                <div className="p-4">
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {(["V","P","R","T"] as const).map(key => {
                      const comp = sig.components[key];
                      // V and T are hard gates; P and R are context only
                      const isGate = key === "V" || key === "T";
                      const confirmed = comp.confirmed;
                      const color = confirmed
                        ? "#22c55e"
                        : isGate
                          ? "#ef4444"
                          : "#f59e0b";
                      const borderColor = confirmed
                        ? "rgba(34,197,94,0.25)"
                        : isGate
                          ? "rgba(239,68,68,0.2)"
                          : "rgba(245,158,11,0.15)";
                      const statusLabel = confirmed
                        ? (isGate ? "CONFIRMED" : "YES")
                        : (isGate ? "NOT MET" : "NO");
                      return (
                        <div key={key} className="bg-surface-2 rounded-lg border p-3"
                          style={{ borderColor }}>
                          <div className="flex items-start justify-between mb-1">
                            <div className="text-[22px] font-black" style={{ color }}>{key}</div>
                            <div className="text-[8px] font-mono font-bold px-1.5 py-0.5 rounded mt-1"
                              style={{
                                color,
                                background: confirmed ? "rgba(34,197,94,0.1)" : isGate ? "rgba(239,68,68,0.1)" : "rgba(245,158,11,0.1)"
                              }}>
                              {statusLabel}
                            </div>
                          </div>
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-2">
                            <MetricTooltip id={key}>{comp.label}</MetricTooltip>
                          </div>
                          <div className="text-[9px] font-mono leading-relaxed" style={{ color: confirmed ? "#22c55e" : "#94a3b8" }}>
                            {comp.detail}
                          </div>
                        </div>
                      );
                    })}

                  </div>
                  {/* Gate summary row */}
                  {sig.signal && (
                    <div className="mt-3 flex items-center gap-2 flex-wrap">
                      {sig.signal.gates && (
                        <>
                          <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded ${
                            sig.signal.gates.v ? "bg-teal/10 text-teal" : "bg-red/10 text-red"
                          }`}>VOL {sig.signal.gates.v ? "✓" : "✗"}</span>
                          <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded ${
                            sig.signal.gates.t ? "bg-teal/10 text-teal" : "bg-red/10 text-red"
                          }`}>TREND {sig.signal.gates.t ? "✓" : "✗"}</span>
                          <span className={`text-[9px] font-mono font-bold px-2 py-0.5 rounded ${
                            sig.signal.gates.adx ? "bg-teal/10 text-teal" : "bg-red/10 text-red"
                          }`}>ADX {sig.signal.gates.adx ? "✓" : "✗"}</span>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </Card>

              {/* 02c: Price Chart */}
              <PriceChart
                ohlcv={sig.ohlcv}
                structure={sig.structure}
                interval={interval}
                symbol={symbol}
                onTfChange={(tf) => { setInterval(tf); runAnalysis(symbol, tf); }}
              />

              {/* 03 + 04: Market Structure + Timing Quality */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
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
                        { label: "ADX 14",  value: (sig.timing?.adx ?? 0).toFixed(1),    sub: (sig.timing?.adx ?? 0) >= 25 ? "TRENDING" : "RANGING",   color: (sig.timing?.adx ?? 0) >= 25 ? "text-teal" : "text-amber" },
                        { label: "ATR 14",  value: (sig.timing?.atr ?? 0).toFixed(0),    sub: `${((sig.timing.atr / ((sig.quote?.price ?? 0) || 1)) * 100).toFixed(2)}% of price`, color: "text-amber" },
                        { label: "Volume",  value: (sig.timing?.rel_volume ?? 0) >= 3.5 ? "Extreme" : (sig.timing?.rel_volume ?? 0) >= 2.5 ? "High" : (sig.timing?.rel_volume ?? 0) >= 1.8 ? "Elevated" : "Normal", sub: (sig.timing?.rel_volume ?? 0) >= 1.8 ? "ABOVE THRESHOLD" : "BELOW THRESHOLD", color: (sig.timing?.rel_volume ?? 0) >= 1.8 ? "text-teal" : "text-amber" },
                        { label: "MAs",     value: sig.quote.price > sig.structure.ema20 && sig.structure.ema20 > sig.structure.ema50 && sig.structure.ema50 > sig.structure.ema200 ? "Aligned" : "Not aligned", sub: sig.quote.price > sig.structure.ema20 && sig.structure.ema20 > sig.structure.ema50 && sig.structure.ema50 > sig.structure.ema200 ? "20 > 50 > 200" : "Stack broken", color: sig.quote.price > sig.structure.ema20 && sig.structure.ema20 > sig.structure.ema50 && sig.structure.ema50 > sig.structure.ema200 ? "text-teal" : "text-red" },
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
                      <CardHeader num="05" title="MARKET CONTEXT" />
                      <div className="p-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
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
                    <CardHeader num="05" title="PERP DERIVATIVES" badge="LIVE" />
                    <div className="p-4">
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
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

              {/* 06: Order Book Microstructure */}
              {sig.microstructure && (() => {
                const ms = sig.microstructure;
                const sigColor =
                  ms.signal === "bullish"   ? "text-teal"  :
                  ms.signal === "bearish"   ? "text-red"   :
                  ms.signal === "thin_book" ? "text-amber" : "text-text-muted";
                const sigBg =
                  ms.signal === "bullish"   ? "bg-teal/8 border-teal/20"   :
                  ms.signal === "bearish"   ? "bg-red/8 border-red/20"     :
                  ms.signal === "thin_book" ? "bg-amber/8 border-amber/20" : "bg-surface-2 border-border/40";
                const totalVol = (ms.bid_vol_usd ?? 0) + (ms.ask_vol_usd ?? 0);
                const bidPct   = totalVol > 0 ? (ms.bid_vol_usd / totalVol) * 100 : 50;
                const askPct   = 100 - bidPct;
                const fmtVol   = (v: number) => v >= 1_000_000 ? `$${(v/1_000_000).toFixed(2)}M` : v >= 1_000 ? `$${(v/1_000).toFixed(0)}K` : `$${v}`;
                return (
                  <Card>
                    <CardHeader num="06" title="ORDER BOOK" badge="LIVE" />
                    <div className="p-4">
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-3">

                        {/* Combined signal */}
                        <div className={`rounded-lg border p-3 ${sigBg}`}>
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">Book Signal</div>
                          <div className={`text-[18px] font-mono font-black uppercase ${sigColor}`}>
                            {ms.signal === "thin_book" ? "THIN BOOK" : ms.signal}
                          </div>
                          <div className={`text-[9px] font-mono mt-0.5 ${sigColor} opacity-80`}>
                            {ms.signal === "bullish"   ? "Bids dominating asks" :
                             ms.signal === "bearish"   ? "Asks dominating bids" :
                             ms.signal === "thin_book" ? "Wide spread — expect slippage" :
                             "Balanced pressure"}
                          </div>
                        </div>

                        {/* Spread */}
                        <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">Spread</div>
                          <div className={`text-[18px] font-mono font-black ${
                            ms.liquidity_quality === "tight"  ? "text-teal"  :
                            ms.liquidity_quality === "wide"   ? "text-red"   : "text-amber"
                          }`}>{ms.spread_pct.toFixed(4)}%</div>
                          <div className={`text-[9px] font-mono mt-0.5 capitalize ${
                            ms.liquidity_quality === "tight"  ? "text-teal"  :
                            ms.liquidity_quality === "wide"   ? "text-red"   : "text-amber"
                          } opacity-80`}>{ms.liquidity_quality} liquidity</div>
                        </div>

                        {/* Imbalance */}
                        <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                          <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">Imbalance</div>
                          <div className={`text-[18px] font-mono font-black ${
                            (ms.imbalance_pct ?? 0) > 10 ? "text-teal" : (ms.imbalance_pct ?? 0) < -10 ? "text-red" : "text-text-muted"
                          }`}>
                            {(ms.imbalance_pct ?? 0) >= 0 ? "+" : ""}{(ms.imbalance_pct ?? 0).toFixed(1)}%
                          </div>
                          <div className="text-[9px] font-mono text-text-muted/60 mt-0.5">
                            {(ms.imbalance_pct ?? 0) > 0 ? "Bid-heavy" : (ms.imbalance_pct ?? 0) < 0 ? "Ask-heavy" : "Balanced"}
                          </div>
                        </div>
                      </div>

                      {/* Bid / Ask depth bar */}
                      <div className="bg-surface-2 rounded-lg border border-border/40 p-3">
                        <div className="flex justify-between text-[9px] font-mono text-text-muted/70 mb-2">
                          <span className="text-teal font-bold">BID {fmtVol(ms.bid_vol_usd ?? 0)} ({bidPct.toFixed(0)}%)</span>
                          <span className="text-[9px] font-mono text-text-muted/40">within 1% of mid</span>
                          <span className="text-red font-bold">ASK {fmtVol(ms.ask_vol_usd ?? 0)} ({askPct.toFixed(0)}%)</span>
                        </div>
                        {/* Stacked bar */}
                        <div className="h-3 rounded-full overflow-hidden flex">
                          <div className="h-full bg-teal/70 transition-all" style={{ width: `${bidPct}%` }} />
                          <div className="h-full bg-red/60 transition-all" style={{ width: `${askPct}%` }} />
                        </div>
                        <div className="flex justify-between text-[7px] font-mono text-text-muted/40 mt-1">
                          <span>Buyers</span><span>Sellers</span>
                        </div>
                      </div>
                    </div>
                  </Card>
                );
              })()}

              {/* 07: Kronos AI Forecast */}
              <Card>
                <CardHeader num="07" title="KRONOS AI FORECAST" badge={!isFullAccess ? "PREMIUM" : undefined} />
                <div className="p-4">
                  {!isFullAccess && (
                    <PremiumModal open inline feature="Kronos AI forecast"
                      requiredTier="full" currentTier={auth.user?.tier ?? "free"}
                      onDismiss={() => {}} />
                  )}
                  {isFullAccess && kronosHk.loading && (
                    <div className="flex items-center gap-3 py-8 justify-center text-text-muted text-[11px] font-mono">
                      <div className="flex gap-1">
                        {[0,1,2].map(i=><div key={i} className="w-1.5 h-1.5 rounded-full bg-purple animate-bounce" style={{animationDelay:`${i*0.15}s`}}/>)}
                      </div>
                      Kronos forecasting {symbol}...
                    </div>
                  )}
                  {isFullAccess && kron && !kronosHk.loading && (
                    <>
                      {/* Row 1: direction / move / trade quality */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-2">
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
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-2">
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
                  {isFullAccess && !kron && !kronosHk.loading && (
                    <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
                      Waiting for signal analysis...
                    </div>
                  )}
                </div>
              </Card>

              {/* 07: Agent Debate */}
              <Card>
                <CardHeader num="08" icon="⚖" title="AI LAB - AGENT DEBATE" badge={!isFullAccess ? "PREMIUM" : undefined} />
                <div className="p-3 space-y-2">
                  {!isFullAccess && (
                    <PremiumModal open inline feature="Agent debate"
                      requiredTier="full" currentTier={auth.user?.tier ?? "free"}
                      onDismiss={() => {}} />
                  )}
                  {isFullAccess && kron?.agents ? (
                    kron.agents.map(agent => {
                      const accentClass =
                        agent.key === "bull" ? "border-teal/25 bg-teal/4"  :
                        agent.key === "bear" ? "border-red/25 bg-red/4"    :
                        agent.key === "risk" ? "border-orange/25 bg-orange/4" :
                        "border-purple/25 bg-purple/4";
                      const iconBg =
                        agent.key === "bull" ? "bg-teal/10 text-teal"  :
                        agent.key === "bear" ? "bg-red/10 text-red"    :
                        agent.key === "risk" ? "bg-orange/10 text-amber" :
                        "bg-purple/10 text-purple";
                      // Split text into paragraphs on newlines or VERDICT: line
                      const lines = agent.text
                        .split(/\n+/)
                        .map((l: string) => l.trim())
                        .filter((l: string) => l.length > 0);
                      const bodyLines = lines.filter((l: string) => !l.toUpperCase().startsWith("VERDICT:"));
                      const verdictLine = lines.find((l: string) => l.toUpperCase().startsWith("VERDICT:"));
                      return (
                        <div key={agent.key} className={`rounded-lg border ${accentClass} overflow-hidden`}>
                          {/* Agent header */}
                          <div className="flex items-center justify-between px-3 py-2 border-b border-border/30">
                            <div className="flex items-center gap-2">
                              <div className={`w-6 h-6 rounded-md flex items-center justify-center text-sm ${iconBg}`}>
                                {agent.icon}
                              </div>
                              <span className="text-[10px] font-mono font-bold text-text-muted/80 uppercase tracking-widest">
                                {agent.name}
                              </span>
                            </div>
                            <VerdictBadge verdict={agent.verdict} />
                          </div>
                          {/* Agent body — full elaborated text */}
                          <div className="px-3 pt-2.5 pb-3 space-y-1.5">
                            {bodyLines.map((line: string, li: number) => (
                              <p key={li} className="text-[11px] text-text-muted leading-relaxed">
                                {line}
                              </p>
                            ))}
                            {verdictLine && (
                              <p className="text-[10px] font-mono font-bold text-text-muted/40 uppercase tracking-widest pt-1">
                                {verdictLine}
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })
                  ) : isFullAccess && kronosHk.loading ? (
                    <div className="space-y-2">
                      {[...Array(4)].map((_,i) => (
                        <div key={i} className="h-24 bg-surface-2 rounded-lg animate-pulse border border-border/30" />
                      ))}
                    </div>
                  ) : isFullAccess ? (
                    <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
                      Waiting for signal analysis...
                    </div>
                  ) : null}
                </div>
              </Card>

              {/* 08: Trending + News + Macro */}
              <VolRadarSection onSelect={(sym) => runAnalysis(sym)} coins={volCoins} />
              <NewsSection symbol={symbol} />
              <MacroSection />

              {/* 09: Perplexity Deep Research */}
              {isFullAccess
                ? <DeepResearchSection symbol={symbol} analyseData={sig} />
                : <Card><CardHeader num="09" title="DEEP RESEARCH" badge="PREMIUM" /><div className="p-4"><PremiumModal open inline feature="Deep research" requiredTier="full" currentTier={auth.user?.tier ?? "free"} onDismiss={() => {}} /></div></Card>
              }

              {/* 12: Multi-Timeframe Confluence */}
              <MultiTimeframeCard symbol={symbol} />


            </div>
            {/*  end LEFT column  */}

            {/* RIGHT SIDEBAR */}
            <div>
              {/* Desktop Vol Radar tab toggle */}
              {!isMobile && (
                <div style={{ display: "flex", gap: 0, marginBottom: 12, background: "#0a0f1e", borderRadius: 10, padding: 3, border: "1px solid #1e293b" }}>
                  {(["signals", "volradar"] as const).map(t => (
                    <button
                      key={t}
                      onClick={() => setMobileTab(t as typeof mobileTab)}
                      style={{
                        flex: 1, padding: "6px 0", borderRadius: 8,
                        fontFamily: "monospace", fontWeight: 800, fontSize: 10,
                        letterSpacing: "0.08em", textTransform: "uppercase",
                        border: "none", cursor: "pointer", transition: "all 0.15s",
                        background: mobileTab === t ? "#7c3aed" : "transparent",
                        color: mobileTab === t ? "#fff" : "#475569",
                      }}
                    >
                      {t === "signals" ? "▲ Signals" : "⚡ Vol Radar"}
                    </button>
                  ))}
                </div>
              )}
              {/* Vol Radar — desktop panel */}
              {!isMobile && mobileTab === "volradar" && (
                <VolRadar onSelect={(sym) => runAnalysis(sym)} />
              )}
              {/* Signals group */}
              <div className={isMobile && mobileTab !== "signals" ? "hidden" : ((!isMobile && mobileTab === "volradar") ? "hidden" : "")}>
                <CSOVerdict sig={sig} kron={kronosHk.data} fearGreed={sig?.fear_greed} />
                {!isMobile && <TopSignals
                  onSelect={(sym) => { runAnalysis(sym); }}
                  interval={interval}
                  listMode={false}
                  onAllSignalsChange={(sigs) => {
                    setVolCoins(sigs.map(s => ({ symbol: s.symbol, price: s.price, change: s.change, rel_vol: s.rel_vol, signal: s.signal })));
                  }}
                />}
                {isMobile && <SignalStreakHeatmap />}
                <TradeSetupCard setup={sig?.trade_setup ?? null} close={sig?.quote?.price ?? 0} csoGo={buildVerdict(sig, kronosHk.data, sig?.fear_greed).go} />
                <ConvictionMeter conviction={sig.conviction} />
                <KeyLevelsCard levels={sig.key_levels} />
              </div>
              {/* Scanner tab — mobile only */}
              <div className={isMobile && mobileTab !== "scanner" ? "hidden" : isMobile ? "" : "hidden"}>
                {isFullAccess ? (
                  <>
                    <TopSignals
                      onSelect={(sym) => { runAnalysis(sym); if(isMobile) setMobileTab("analyse"); }}
                      interval={interval}
                      listMode={true}
                      onAllSignalsChange={(sigs) => {
                        setVolCoins(sigs.map(s => ({ symbol: s.symbol, price: s.price, change: s.change, rel_vol: s.rel_vol, signal: s.signal })));
                      }}
                    />
                    <DipScannerCard
                      interval={interval}
                      onSelect={(sym) => { runAnalysis(sym); if(isMobile) setMobileTab("analyse"); }}
                    />
                  </>
                ) : (
                  <div className="p-4">
                    <PremiumModal open inline feature="Live scanner"
                      requiredTier="full" currentTier={auth.user?.tier ?? "free"}
                      onDismiss={() => setMobileTab("analyse")} />
                  </div>
                )}
              </div>
              {/* Vol Radar tab — mobile */}
              <div className={isMobile && mobileTab !== "volradar" ? "hidden" : ""}>
                <VolRadar onSelect={(sym) => { runAnalysis(sym); if(isMobile) setMobileTab("analyse"); }} />
              </div>
              {/* Watchlist + Tools group */}
              <div className={isMobile && mobileTab !== "sidebar" ? "hidden" : ""}>
                <WatchlistCard
                  scores={wlScores}
                  loading={wlLoading}
                  onSelect={(sym) => { runAnalysis(sym); if(isMobile) setMobileTab("analyse"); }}
                  currentSymbol={symbol}
                  onAdd={editableWL.add}
                  onRemove={editableWL.remove}
                />
                <SubscribeCard />
                <ExportCard
                  symbol={symbol}
                  interval={interval}
                  onRerun={() => runAnalysis()}
                  onExport={() => exportPdf(reportId, `crypto-sniper-${symbol}-${interval}.pdf`, { ...(sig as unknown as Record<string, unknown>), agents: kron?.agents ?? undefined, forecast: kron?.forecast ?? undefined })}
                  exporting={exporting}
                />
                <BasketScanner
                  interval={interval}
                  onSelect={(sym) => { runAnalysis(sym); if(isMobile) setMobileTab("analyse"); }}
                />
                <ScannerCumulativeCard />
                <DipScannerCard
                  interval={interval}
                  onSelect={(sym) => { runAnalysis(sym); if(isMobile) setMobileTab("analyse"); }}
                />
                <OptionsIntelligenceSection />
                <SignalStreakHeatmap />
                <PriceAlertCard currentSymbol={symbol} />

                {/* Telegram Support Card — Tools tab */}
                <div className="rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-3">
                  <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
                    <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
                      <span style={{ fontSize: 13 }}>✈</span>
                      <span>SUPPORT</span>
                    </div>
                    <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded" style={{ background: "rgba(124,58,237,0.15)", color: "#7c3aed" }}>LIVE</span>
                  </div>
                  <div className="p-4">
                    <p className="text-[11px] font-mono text-text-muted mb-3 leading-relaxed">
                      Chat with Kai — signal questions, account help, bug reports.
                    </p>
                    <a
                      href="https://t.me/Niftysnipabot"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg font-bold text-[12px] text-white transition-opacity hover:opacity-80"
                      style={{ background: "linear-gradient(135deg,#7c3aed,#4f46e5)", textDecoration: "none" }}
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path d="M21.94 2.29a1 1 0 0 0-1.02-.17L2.33 9.36a1 1 0 0 0 .06 1.87l4.17 1.38 1.62 5.03a1 1 0 0 0 1.7.37l2.32-2.54 4.54 3.33a1 1 0 0 0 1.55-.59l3-14a1 1 0 0 0-.35-.92zM10.27 14.27l-.9 2.78-.9-2.78L16 8z" fill="white"/>
                      </svg>
                      Open Telegram Support
                    </a>
                  </div>
                </div>
              </div>
            </div>
            {/* end RIGHT sidebar */}

          </div>
        )}
      </div>

      {/* MOBILE BOTTOM TAB BAR */}
      {isMobile && (
        <nav
          className="fixed bottom-0 left-0 right-0 z-50 bg-bg/95 backdrop-blur-xl border-t border-border/60"
          style={{ paddingBottom: "env(safe-area-inset-bottom, 0px)" }}
        >
          <div className="flex items-stretch">
            {([
              { key: "analyse",  label: "Analyse",  icon: "◎" },
              { key: "signals",  label: "Signals",  icon: "▲" },
              { key: "volradar", label: "Vol Radar", icon: "⚡" },
              { key: "sidebar",  label: "Tools",    icon: "◈" },
              { key: "scanner",  label: "Scanner",  icon: "⊕" },
            ] as const).map(tab => {
              const active = mobileTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => setMobileTab(tab.key)}
                  className="flex-1 flex flex-col items-center justify-center gap-0.5 py-2 min-h-[52px] transition-colors relative"
                  style={{ color: active ? "#7c3aed" : "rgba(148,163,184,0.5)" }}
                >
                  {/* Active top-border indicator */}
                  {active && (
                    <span style={{ position: "absolute", top: 0, left: "25%", right: "25%", height: 2, background: "#7c3aed", borderRadius: "0 0 2px 2px" }} />
                  )}
                  <span className="text-[16px] leading-none">{tab.icon}</span>
                  <span className="text-[9px] font-mono font-bold uppercase tracking-wider">{tab.label}</span>
                </button>
              );
            })}
          </div>
        </nav>
      )}

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

      {/* PREMIUM UPGRADE MODAL — global, triggered by requireFull() */}
      <PremiumModal
        open={premiumOpen}
        feature={premiumFeature}
        requiredTier="full"
        currentTier={auth.user?.tier ?? "free"}
        onDismiss={() => setPremiumOpen(false)}
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

      {/* Telegram floating button — desktop only */}
      {!isMobile && (
        <a
          href="https://t.me/Niftysnipabot"
          target="_blank"
          rel="noopener noreferrer"
          title="Chat with Kai — Crypto Sniper Support"
          style={{
            position: "fixed",
            bottom: "24px",
            right: "20px",
            zIndex: 9999,
            width: 52,
            height: 52,
            borderRadius: "50%",
            background: "linear-gradient(135deg,#7c3aed,#4f46e5)",
            boxShadow: "0 4px 24px rgba(124,58,237,0.45)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            textDecoration: "none",
            transition: "transform 0.15s ease, box-shadow 0.15s ease",
          }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLAnchorElement).style.transform = "scale(1.1)";
            (e.currentTarget as HTMLAnchorElement).style.boxShadow = "0 6px 32px rgba(124,58,237,0.65)";
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLAnchorElement).style.transform = "scale(1)";
            (e.currentTarget as HTMLAnchorElement).style.boxShadow = "0 4px 24px rgba(124,58,237,0.45)";
          }}
        >
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
            <path d="M21.94 2.29a1 1 0 0 0-1.02-.17L2.33 9.36a1 1 0 0 0 .06 1.87l4.17 1.38 1.62 5.03a1 1 0 0 0 1.7.37l2.32-2.54 4.54 3.33a1 1 0 0 0 1.55-.59l3-14a1 1 0 0 0-.35-.92zM10.27 14.27l-.9 2.78-.9-2.78L16 8z" fill="white"/>
          </svg>
          <span style={{
            position: "absolute",
            inset: -3,
            borderRadius: "50%",
            border: "2px solid rgba(124,58,237,0.4)",
            animation: "tg-ping 2s cubic-bezier(0,0,0.2,1) infinite",
          }} />
        </a>
      )}
      <style>{`
        @keyframes tg-ping {
          0%   { transform: scale(1);   opacity: 0.6; }
          80%  { transform: scale(1.5); opacity: 0; }
          100% { transform: scale(1.5); opacity: 0; }
        }
      `}</style>
    </div>
  );
}
