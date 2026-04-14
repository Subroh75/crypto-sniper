import { useState, useRef, useCallback } from "react";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import {
  TrendingUp, TrendingDown, Minus, Zap, BarChart2, Activity,
  Clock, Brain, Download, Search, ChevronDown, RefreshCw,
  AlertTriangle, CheckCircle2, Shield, Target, Loader2,
} from "lucide-react";
import { analyse, kronos } from "@/lib/api";
import type { AnalyseResponse, KronosResponse } from "@/lib/api";
import { Logo } from "@/components/Logo";

// ─── Constants ──────────────────────────────────────────────────────────────
const INTERVALS = [
  { label: "1m",  value: "1m" },
  { label: "5m",  value: "5m" },
  { label: "15m", value: "15m" },
  { label: "1h",  value: "1h" },
  { label: "4h",  value: "4h" },
  { label: "1d",  value: "1d" },
];

const AGENT_ICONS: Record<string, { icon: typeof TrendingUp; color: string }> = {
  Bull:         { icon: TrendingUp,  color: "#10b981" },
  Bear:         { icon: TrendingDown,color: "#f87171" },
  "Risk Manager":{ icon: Shield,     color: "#f59e0b" },
  CIO:          { icon: Target,      color: "#818cf8" },
};

function getSignalMeta(signal: string) {
  if (signal === "STRONG BUY")
    return { color: "#10b981", glow: "glow-green", label: "STRONG BUY",  emoji: "🟢" };
  if (signal === "MODERATE")
    return { color: "#f59e0b", glow: "glow-amber", label: "MODERATE",    emoji: "🟡" };
  return   { color: "#64748b", glow: "glow-slate", label: "NO SIGNAL",   emoji: "⚪" };
}

function formatPrice(n: number) {
  if (n >= 1000) return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n >= 1)    return n.toFixed(4);
  return n.toFixed(6);
}

// ─── Sub-components ──────────────────────────────────────────────────────────

function SectionLabel({ num, label, icon: Icon }: { num: string; label: string; icon?: typeof Zap }) {
  return (
    <div className="flex items-center gap-2 mb-5">
      <span className="text-xs font-bold text-purple-DEFAULT font-mono tracking-widest">{num}</span>
      <span className="w-px h-3 bg-border" />
      {Icon && <Icon size={13} className="text-text-muted" />}
      <span className="text-xs font-semibold uppercase tracking-widest text-text-muted">{label}</span>
    </div>
  );
}

function ScoreBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = Math.round((value / max) * 100);
  return (
    <div className="h-1.5 w-full bg-surface-2 rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-700 ease-out"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}

function MetaCard({ label, value, mono = true }: { label: string; value: string | number; mono?: boolean }) {
  return (
    <div className="bg-surface-2 rounded-xl p-3 border border-border/50">
      <p className="text-xs text-text-muted mb-1">{label}</p>
      <p className={`text-sm font-semibold text-text ${mono ? "font-mono" : ""}`}>{value}</p>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export default function Home() {
  const [symbol, setSymbol] = useState("");
  const [interval, setInterval] = useState("1h");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<AnalyseResponse | null>(null);
  const [kronosData, setKronosData] = useState<KronosResponse | null>(null);
  const [kronosLoading, setKronosLoading] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  const handleAnalyse = useCallback(async () => {
    const sym = symbol.trim().toUpperCase().replace("/USDT", "").replace("-USDT", "");
    if (!sym) return;
    setLoading(true);
    setError(null);
    setKronosData(null);

    try {
      const result = await analyse({ symbol: sym, interval });
      setData(result);

      // Auto-run Kronos
      setKronosLoading(true);
      try {
        const kr = await kronos({ symbol: sym, interval });
        setKronosData(kr);
      } catch {
        setKronosData({ symbol: sym, interval, available: false });
      } finally {
        setKronosLoading(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Analysis failed. Check the symbol and try again.");
    } finally {
      setLoading(false);
    }
  }, [symbol, interval]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleAnalyse();
  };

  const handleDownloadPDF = async () => {
    if (!data || !reportRef.current) return;
    setPdfLoading(true);
    try {
      const { default: jsPDF } = await import("jspdf");
      const { default: html2canvas } = await import("html2canvas");
      const canvas = await html2canvas(reportRef.current, {
        backgroundColor: "#060912",
        scale: 2,
        useCORS: true,
        allowTaint: true,
      });
      const imgData = canvas.toDataURL("image/png");
      const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
      const pdfW = pdf.internal.pageSize.getWidth();
      const pdfH = (canvas.height * pdfW) / canvas.width;
      pdf.addImage(imgData, "PNG", 0, 0, pdfW, pdfH);
      pdf.save(`crypto-guru-${data.symbol}-${data.interval}.pdf`);
    } catch (err) {
      console.error("PDF export failed", err);
    } finally {
      setPdfLoading(false);
    }
  };

  const signalMeta = data ? getSignalMeta(data.signal) : null;

  return (
    <div className="min-h-screen bg-bg text-text">
      {/* ─── Header ─────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 border-b border-border/60 backdrop-blur-xl bg-bg/80">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <Logo size={28} />
            <span className="text-sm font-bold tracking-tight text-text">
              crypto<span className="gradient-text">.guru</span>
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-green-DEFAULT animate-pulse" />
            <span className="text-xs font-mono" style={{ color: '#94a3b8' }}>API LIVE</span>
          </div>
        </div>
      </header>

      {/* ─── Hero Input ──────────────────────────────────────────────── */}
      <section className="max-w-5xl mx-auto px-4 pt-12 pb-8">
        <div className="text-center mb-8">
          <h1
            className="text-3xl font-bold mb-2 gradient-text"
            style={{ fontFamily: "var(--font-body)" }}
          >
            Real-Time Crypto Signal Engine
          </h1>
          <p className="text-sm" style={{ color: '#94a3b8' }}>
            Paste any coin symbol — get live V/P/R/T scoring, Kronos AI forecast &amp; multi-agent debate
          </p>
        </div>

        {/* Input row */}
        <div className="flex gap-2 max-w-2xl mx-auto">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-text-faint" />
            <input
              type="text"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="BTC · ETH · SOL · DOGE…"
              data-testid="input-symbol"
              className="w-full h-11 pl-9 pr-4 bg-surface border border-border rounded-xl text-sm text-text placeholder:text-text-faint focus:outline-none focus:border-purple-DEFAULT focus:ring-1 focus:ring-purple-DEFAULT/40 transition-all"
            />
          </div>

          {/* Interval selector */}
          <div className="relative">
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
              data-testid="select-interval"
              className="h-11 px-3 pr-8 bg-surface border border-border rounded-xl text-sm text-text appearance-none focus:outline-none focus:border-purple-DEFAULT cursor-pointer"
            >
              {INTERVALS.map((iv) => (
                <option key={iv.value} value={iv.value}>{iv.label}</option>
              ))}
            </select>
            <ChevronDown size={13} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-text-faint pointer-events-none" />
          </div>

          {/* Analyse button */}
          <button
            onClick={handleAnalyse}
            disabled={loading || !symbol.trim()}
            data-testid="button-analyse"
            className="h-11 px-5 rounded-xl text-sm font-semibold text-white bg-purple-DEFAULT hover:bg-purple-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
            style={{ background: loading ? undefined : "linear-gradient(135deg, #7c3aed, #818cf8)" }}
          >
            {loading ? (
              <><Loader2 size={14} className="animate-spin" /><span>Analysing…</span></>
            ) : (
              <><Zap size={14} /><span>Analyse</span></>
            )}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="max-w-2xl mx-auto mt-3 flex items-center gap-2 bg-red-DEFAULT/10 border border-red-DEFAULT/30 rounded-lg px-4 py-3">
            <AlertTriangle size={14} className="text-red-DEFAULT shrink-0" />
            <p className="text-xs text-red-DEFAULT">{error}</p>
          </div>
        )}

        {/* Empty hint */}
        {!data && !loading && !error && (
          <p className="text-center text-xs mt-4" style={{ color: '#64748b' }}>
            Press <kbd className="px-1.5 py-0.5 bg-surface-2 border border-border rounded text-xs font-mono" style={{ color: '#94a3b8' }}>Enter</kbd> or click Analyse to run
          </p>
        )}
      </section>

      {/* ─── Results ─────────────────────────────────────────────────── */}
      {data && (
        <div ref={reportRef} className="max-w-5xl mx-auto px-4 pb-16 space-y-4 animate-fadeIn">

          {/* ── 01 Signal Output ───────────────────────────────────────── */}
          <div className="section-card" data-testid="section-signal">
            <SectionLabel num="01" label="Signal Output" icon={Zap} />
            <div className="flex flex-col sm:flex-row items-center gap-6">
              {/* Badge */}
              <div
                className={`rounded-2xl px-8 py-5 text-center shrink-0 border ${signalMeta!.glow}`}
                style={{
                  background: `${signalMeta!.color}18`,
                  borderColor: `${signalMeta!.color}40`,
                }}
              >
                <p className="text-xs text-text-muted font-mono mb-1">{data.symbol} · {data.interval}</p>
                <p
                  className="text-2xl font-bold font-mono tracking-wider"
                  style={{ color: signalMeta!.color }}
                >
                  {signalMeta!.label}
                </p>
              </div>

              {/* Score gauge */}
              <div className="flex-1 w-full">
                <div className="flex justify-between mb-2">
                  <span className="text-xs text-text-muted">Signal Score</span>
                  <span className="text-sm font-bold font-mono text-text">
                    {data.total_score} / {data.max_score}
                  </span>
                </div>
                <div className="h-3 bg-surface-2 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-1000 ease-out"
                    style={{
                      width: `${(data.total_score / data.max_score) * 100}%`,
                      background: `linear-gradient(90deg, ${signalMeta!.color}, ${signalMeta!.color}99)`,
                    }}
                  />
                </div>
                <div className="flex justify-between mt-1.5">
                  <span className="text-xs text-text-faint">0</span>
                  <span className="text-xs text-text-faint">5</span>
                  <span className="text-xs text-text-faint">9</span>
                  <span className="text-xs text-text-faint">13</span>
                </div>
                <div className="flex justify-between mt-3 text-xs text-text-faint">
                  <span>NO SIGNAL (&lt;5)</span>
                  <span>MODERATE (≥5)</span>
                  <span>STRONG BUY (≥9)</span>
                </div>
              </div>
            </div>
            <p className="text-xs text-text-faint mt-4 font-mono">
              {new Date(data.timestamp).toLocaleString("en-AU", { dateStyle: "medium", timeStyle: "short" })}
            </p>
          </div>

          {/* ── 02 Signal Components ───────────────────────────────────── */}
          <div className="section-card" data-testid="section-components">
            <SectionLabel num="02" label="Signal Components" icon={BarChart2} />
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { key: "V", label: "Volume",  value: data.score_components.volume_score, max: 5, color: "#7c3aed" },
                { key: "P", label: "Price",   value: data.score_components.price_score,  max: 3, color: "#38bdf8" },
                { key: "R", label: "Range",   value: data.score_components.range_score,  max: 2, color: "#818cf8" },
                { key: "T", label: "Trend",   value: data.score_components.trend_score,  max: 3, color: "#10b981" },
              ].map(({ key, label, value, max, color }) => (
                <div key={key} className="bg-surface-2 rounded-xl p-4 border border-border/50">
                  <div className="flex items-center justify-between mb-3">
                    <div>
                      <span className="text-xs font-bold font-mono" style={{ color }}>{key}</span>
                      <span className="text-xs text-text-muted ml-1">— {label}</span>
                    </div>
                    <span className="text-lg font-bold font-mono text-text">{value}</span>
                  </div>
                  <ScoreBar value={value} max={max} color={color} />
                  <p className="text-xs text-text-faint mt-1.5 text-right">{value} / {max}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 bg-surface rounded-xl p-3 border border-border/40">
              <p className="text-xs text-text-muted font-mono leading-relaxed">
                <span className="text-violet-DEFAULT font-semibold">V</span> = Relative Volume score (0-5) ·{" "}
                <span className="text-teal-DEFAULT font-semibold">P</span> = Price momentum vs ATR (0-3) ·{" "}
                <span className="text-violet-DEFAULT font-semibold">R</span> = Range position (0-2) ·{" "}
                <span className="text-green-DEFAULT font-semibold">T</span> = Trend alignment EMA+ADX (0-3)
              </p>
            </div>
          </div>

          {/* ── 03 Market Structure ────────────────────────────────────── */}
          <div className="section-card" data-testid="section-market">
            <SectionLabel num="03" label="Market Structure" icon={Activity} />
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2.5">
              <MetaCard label="Current Price"    value={`$${formatPrice(data.market_structure.current_price)}`} />
              <MetaCard label="Prev Close"       value={`$${formatPrice(data.market_structure.prev_close)}`} />
              <MetaCard label="ATR"              value={formatPrice(data.market_structure.atr)} />
              <MetaCard label="ATR Move"         value={`${data.market_structure.atr_move.toFixed(2)}x`} />
              <MetaCard label="EMA 20"           value={`$${formatPrice(data.market_structure.ema20)}`} />
              <MetaCard label="EMA 50"           value={`$${formatPrice(data.market_structure.ema50)}`} />
              <MetaCard label="ADX (14)"         value={data.market_structure.adx.toFixed(1)} />
              <MetaCard label="Relative Volume"  value={`${data.market_structure.relative_volume.toFixed(2)}x`} />
            </div>
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              <div
                className="rounded-xl p-3 border"
                style={{
                  background: data.market_structure.current_price > data.market_structure.ema20
                    ? "rgba(16,185,129,0.08)" : "rgba(248,113,113,0.08)",
                  borderColor: data.market_structure.current_price > data.market_structure.ema20
                    ? "rgba(16,185,129,0.3)" : "rgba(248,113,113,0.3)",
                }}
              >
                <p className="text-xs text-text-muted mb-0.5">Price vs EMA20</p>
                <p className="text-xs font-semibold font-mono"
                  style={{ color: data.market_structure.current_price > data.market_structure.ema20 ? "#10b981" : "#f87171" }}>
                  {data.market_structure.current_price > data.market_structure.ema20 ? "ABOVE ↑" : "BELOW ↓"}
                </p>
              </div>
              <div
                className="rounded-xl p-3 border"
                style={{
                  background: data.market_structure.ema20 > data.market_structure.ema50
                    ? "rgba(16,185,129,0.08)" : "rgba(248,113,113,0.08)",
                  borderColor: data.market_structure.ema20 > data.market_structure.ema50
                    ? "rgba(16,185,129,0.3)" : "rgba(248,113,113,0.3)",
                }}
              >
                <p className="text-xs text-text-muted mb-0.5">EMA20 vs EMA50</p>
                <p className="text-xs font-semibold font-mono"
                  style={{ color: data.market_structure.ema20 > data.market_structure.ema50 ? "#10b981" : "#f87171" }}>
                  {data.market_structure.ema20 > data.market_structure.ema50 ? "BULLISH ↑" : "BEARISH ↓"}
                </p>
              </div>
              <div
                className="rounded-xl p-3 border"
                style={{
                  background: data.market_structure.adx >= 20
                    ? "rgba(56,189,248,0.08)" : "rgba(100,116,139,0.08)",
                  borderColor: data.market_structure.adx >= 20
                    ? "rgba(56,189,248,0.3)" : "rgba(100,116,139,0.3)",
                }}
              >
                <p className="text-xs text-text-muted mb-0.5">ADX Strength</p>
                <p className="text-xs font-semibold font-mono"
                  style={{ color: data.market_structure.adx >= 20 ? "#38bdf8" : "#64748b" }}>
                  {data.market_structure.adx >= 20 ? "TRENDING" : "RANGING"}
                </p>
              </div>
            </div>
          </div>

          {/* ── 04 Timing Quality ───────────────────────────────────────── */}
          <div className="section-card" data-testid="section-timing">
            <SectionLabel num="04" label="Timing Quality" icon={Clock} />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Range position */}
              <div className="bg-surface-2 rounded-xl p-4 border border-border/50">
                <div className="flex justify-between mb-3">
                  <span className="text-xs text-text-muted">Range Position</span>
                  <span className="text-sm font-bold font-mono text-text">
                    {(data.market_structure.range_position * 100).toFixed(0)}%
                  </span>
                </div>
                <div className="h-2 bg-surface rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all duration-1000"
                    style={{
                      width: `${data.market_structure.range_position * 100}%`,
                      background: data.market_structure.range_position >= 0.85
                        ? "linear-gradient(90deg, #10b981, #38bdf8)"
                        : data.market_structure.range_position >= 0.70
                        ? "linear-gradient(90deg, #f59e0b, #818cf8)"
                        : "#64748b",
                    }}
                  />
                </div>
                <div className="flex justify-between mt-1.5 text-xs text-text-faint">
                  <span>0%</span>
                  <span className="text-amber-DEFAULT">70%</span>
                  <span className="text-green-DEFAULT">85%</span>
                  <span>100%</span>
                </div>
                <p className="text-xs font-semibold mt-2 font-mono"
                  style={{
                    color: data.market_structure.range_position >= 0.85 ? "#10b981"
                         : data.market_structure.range_position >= 0.70 ? "#f59e0b"
                         : "#64748b"
                  }}>
                  {data.market_structure.range_position >= 0.85 ? "Near Range High (+2pts)"
                 : data.market_structure.range_position >= 0.70 ? "Upper Range (+1pt)"
                 : "Low Range Position (0pts)"}
                </p>
              </div>

              {/* ATR move quality */}
              <div className="bg-surface-2 rounded-xl p-4 border border-border/50">
                <div className="flex justify-between mb-3">
                  <span className="text-xs text-text-muted">ATR Move</span>
                  <span className="text-sm font-bold font-mono text-text">
                    {data.market_structure.atr_move.toFixed(2)}x ATR
                  </span>
                </div>
                <div className="space-y-2">
                  {[
                    { threshold: 4, label: "≥4x ATR", pts: "+3 pts", color: "#10b981" },
                    { threshold: 2.5, label: "2.5-4x ATR", pts: "+2 pts", color: "#38bdf8" },
                    { threshold: 1.5, label: "1.5-2.5x ATR", pts: "+1 pt",  color: "#818cf8" },
                    { threshold: 0,   label: "<1.5x ATR",   pts: "0 pts",  color: "#64748b" },
                  ].map(({ threshold, label, pts, color }) => {
                    const active = threshold === 0
                      ? data.market_structure.atr_move < 1.5
                      : threshold === 1.5
                      ? data.market_structure.atr_move >= 1.5 && data.market_structure.atr_move < 2.5
                      : threshold === 2.5
                      ? data.market_structure.atr_move >= 2.5 && data.market_structure.atr_move < 4
                      : data.market_structure.atr_move >= 4;
                    return (
                      <div key={threshold} className={`flex justify-between items-center text-xs rounded-lg px-2 py-1.5 transition-all ${active ? "bg-surface border" : "opacity-35"}`}
                        style={active ? { borderColor: `${color}40`, background: `${color}12` } : {}}>
                        <span style={{ color: active ? color : "#475569" }}>{label}</span>
                        <span className="font-mono font-semibold" style={{ color: active ? color : "#475569" }}>{pts}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          {/* ── 05 Kronos AI Forecast ──────────────────────────────────── */}
          <div className="section-card" data-testid="section-kronos">
            <SectionLabel num="05" label="Kronos AI Forecast" icon={Brain} />
            {kronosLoading ? (
              <div className="flex items-center gap-3 py-8 justify-center">
                <Loader2 size={18} className="animate-spin text-violet-DEFAULT" />
                <span className="text-sm text-text-muted font-mono">Loading Kronos-mini model…</span>
              </div>
            ) : kronosData && kronosData.available ? (
              <>
                {/* Direction cards */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4">
                  <div className="bg-surface-2 rounded-xl p-3 border border-border/50 text-center">
                    <p className="text-xs text-text-muted mb-1">Direction</p>
                    <p className="text-base font-bold font-mono"
                      style={{ color: kronosData.direction === "UP" ? "#10b981" : "#f87171" }}>
                      {kronosData.direction === "UP" ? "▲ UP" : "▼ DOWN"}
                    </p>
                  </div>
                  <div className="bg-surface-2 rounded-xl p-3 border border-border/50 text-center">
                    <p className="text-xs text-text-muted mb-1">Predicted Δ</p>
                    <p className="text-base font-bold font-mono"
                      style={{ color: (kronosData.predicted_change ?? 0) >= 0 ? "#10b981" : "#f87171" }}>
                      {((kronosData.predicted_change ?? 0) >= 0 ? "+" : "")}{kronosData.predicted_change?.toFixed(2)}%
                    </p>
                  </div>
                  <div className="bg-surface-2 rounded-xl p-3 border border-border/50 text-center">
                    <p className="text-xs text-text-muted mb-1">Peak</p>
                    <p className="text-base font-bold font-mono text-text">
                      ${formatPrice(kronosData.peak_price ?? 0)}
                    </p>
                  </div>
                  <div className="bg-surface-2 rounded-xl p-3 border border-border/50 text-center">
                    <p className="text-xs text-text-muted mb-1">Trough</p>
                    <p className="text-base font-bold font-mono text-text">
                      ${formatPrice(kronosData.trough_price ?? 0)}
                    </p>
                  </div>
                </div>

                {/* Forecast chart */}
                {kronosData.forecast && kronosData.forecast.length > 0 && (
                  <div className="bg-surface-2 rounded-xl p-4 border border-border/50">
                    <p className="text-xs text-text-muted mb-3 font-mono">Predicted OHLCV — Next {kronosData.forecast.length} candles</p>
                    <ResponsiveContainer width="100%" height={160}>
                      <AreaChart data={kronosData.forecast} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                        <defs>
                          <linearGradient id="kronosGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%"  stopColor="#818cf8" stopOpacity={0.3} />
                            <stop offset="95%" stopColor="#818cf8" stopOpacity={0} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e2d45" />
                        <XAxis dataKey="timestamp" tick={{ fill: "#475569", fontSize: 10 }} tickLine={false} axisLine={false}
                          tickFormatter={(v) => new Date(v).toLocaleTimeString("en-AU", { hour: "2-digit", minute: "2-digit" })} />
                        <YAxis tick={{ fill: "#475569", fontSize: 10 }} tickLine={false} axisLine={false}
                          tickFormatter={(v) => `$${formatPrice(v)}`} width={70} />
                        <Tooltip
                          contentStyle={{ background: "#0f1623", border: "1px solid #243048", borderRadius: 8, fontSize: 12 }}
                          labelStyle={{ color: "#94a3b8" }}
                          itemStyle={{ color: "#818cf8", fontFamily: "var(--font-mono)" }}
                          labelFormatter={(v) => new Date(v).toLocaleString("en-AU")}
                        />
                        <Area type="monotone" dataKey="close" stroke="#818cf8" strokeWidth={2}
                          fill="url(#kronosGrad)" dot={false} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </>
            ) : kronosData && !kronosData.available ? (
              <div className="flex items-center gap-3 py-6">
                <AlertTriangle size={16} className="text-amber-DEFAULT shrink-0" />
                <div>
                  <p className="text-sm text-text-muted">Kronos-mini model not installed on this deployment.</p>
                  <p className="text-xs text-text-faint font-mono mt-0.5">
                    Install NeoQuasar/Kronos-mini + torch to enable live OHLCV forecasting.
                  </p>
                </div>
              </div>
            ) : (
              <p className="text-sm text-text-faint py-4 text-center font-mono">Run an analysis to load Kronos forecast</p>
            )}
          </div>

          {/* ── 06 AI Lab ──────────────────────────────────────────────── */}
          <div className="section-card" data-testid="section-ailab">
            <SectionLabel num="06" label="AI Lab — Agent Debate" icon={Brain} />
            <div className="space-y-3">
              {data.debate.map((agent, i) => {
                const meta = AGENT_ICONS[agent.role] || { icon: Minus, color: "#818cf8" };
                const IconComp = meta.icon;
                return (
                  <div
                    key={i}
                    className="debate-bubble flex gap-3 bg-surface-2 rounded-xl p-4 border border-border/50"
                    style={{ animationDelay: `${i * 0.1}s` }}
                  >
                    <div
                      className="shrink-0 w-8 h-8 rounded-lg flex items-center justify-center"
                      style={{ background: `${meta.color}20`, border: `1px solid ${meta.color}40` }}
                    >
                      <IconComp size={14} style={{ color: meta.color }} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-xs font-bold font-mono" style={{ color: meta.color }}>
                          {agent.role.toUpperCase()}
                        </span>
                        <span
                          className="text-xs px-2 py-0.5 rounded-full font-mono"
                          style={{ background: `${meta.color}15`, color: meta.color }}
                        >
                          {agent.view}
                        </span>
                      </div>
                      <p className="text-sm text-text leading-relaxed">{agent.argument}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── 07 Export ──────────────────────────────────────────────── */}
          <div className="section-card" data-testid="section-export">
            <SectionLabel num="07" label="Export Report" icon={Download} />
            <div className="flex justify-center">
              <button
                onClick={handleDownloadPDF}
                disabled={pdfLoading}
                data-testid="button-download-pdf"
                className="flex items-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold text-white transition-all hover:scale-105 active:scale-100 disabled:opacity-60 disabled:cursor-not-allowed"
                style={{ background: "linear-gradient(135deg, #7c3aed, #818cf8, #38bdf8)" }}
              >
                {pdfLoading ? (
                  <><Loader2 size={15} className="animate-spin" /><span>Generating PDF…</span></>
                ) : (
                  <><Download size={15} /><span>Download PDF Report</span></>
                )}
              </button>
            </div>
            <p className="text-xs text-text-faint text-center mt-3 font-mono">
              Full report: signal, components, structure, timing, Kronos forecast &amp; AI debate
            </p>
          </div>

          {/* Re-run hint */}
          <div className="flex justify-center pt-2">
            <button
              onClick={handleAnalyse}
              disabled={loading}
              className="flex items-center gap-1.5 text-xs text-text-faint hover:text-text-muted transition-colors"
            >
              <RefreshCw size={12} />
              <span>Re-run {data.symbol} · {data.interval}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
