// ─── DeepResearch.tsx — Section 09: Perplexity Deep Research ────────────────
import { useState } from "react";
import { useDeepResearch } from "@/hooks/useApi";
import type { AnalyseResponse } from "@/types/api";

const DEPTH_OPTIONS = [
  { key: "quick", label: "Quick", time: "~5s",  model: "sonar" },
  { key: "deep",  label: "Deep",  time: "~18s", model: "sonar-deep-research" },
  { key: "max",   label: "Max",   time: "~45s", model: "sonar-reasoning-pro" },
] as const;

const FINDING_STYLE = {
  bull:    "bg-teal/5 border-teal/20 text-teal",
  bear:    "bg-red/5  border-red/20  text-red",
  neutral: "bg-amber/5 border-amber/20 text-amber",
} as const;

const FINDING_DOT = {
  bull: "bg-teal",
  bear: "bg-red",
  neutral: "bg-amber",
} as const;

interface Props {
  symbol: string;
  analyseData: AnalyseResponse | null;
}

export function DeepResearchSection({ symbol, analyseData }: Props) {
  const [depth, setDepth] = useState<"quick" | "deep" | "max">("deep");
  const { data, loading, error, run, reset } = useDeepResearch();

  const handleRun = () => {
    const context = analyseData ? {
      close:      analyseData.quote.price,
      rsi:        analyseData.timing.rsi,
      adx:        analyseData.timing.adx,
      signal:     analyseData.signal.label,
      total:      analyseData.signal.total,
      direction:  analyseData.signal.direction,
      change_24h: analyseData.quote.change_24h,
    } : {};
    run(symbol, depth, context);
  };

  const report = data?.report;

  return (
    <div className="card mb-3"
         style={{ borderColor: "rgba(0,212,170,0.18)", position: "relative" }}>
      {/* Teal-purple top bar */}
      <div className="h-[2px]" style={{ background: "linear-gradient(90deg, #00d4aa, #7c5cfc)" }} />

      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
        <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
          <span className="text-teal">09</span>
          <span>🔭 PERPLEXITY DEEP RESEARCH</span>
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-orange/10 text-orange border border-orange/15 uppercase tracking-wide">NEW</span>
        </div>
        <div className="flex items-center gap-2">
          {report && (
            <span className="text-[9px] font-mono text-text-muted/60">
              {report.generation_time_s}s · {report.sources_count} sources
            </span>
          )}
          <span className="text-[9px] font-mono text-teal/70 px-2 py-0.5 rounded bg-teal/8 border border-teal/15">
            {DEPTH_OPTIONS.find(d => d.key === depth)?.model ?? "sonar-deep-research"}
          </span>
          <span className="text-[9px] font-mono text-text-muted/60 px-2 py-0.5 rounded bg-surface-2 border border-border/40">
            Perplexity AI
          </span>
        </div>
      </div>

      <div className="p-4">
        {/* Depth selector */}
        <div className="flex gap-1.5 mb-4">
          {DEPTH_OPTIONS.map(opt => (
            <button
              key={opt.key}
              onClick={() => setDepth(opt.key)}
              className={`flex-1 py-1.5 rounded-lg text-center font-mono text-[9px] font-bold border transition-all uppercase tracking-wide ${
                depth === opt.key
                  ? "border-teal text-teal bg-teal/6"
                  : "border-border/50 text-text-muted hover:border-text-muted"
              }`}
            >
              {opt.label} <span className="opacity-50">{opt.time}</span>
            </button>
          ))}
        </div>

        {/* Run button when no data */}
        {!report && !loading && (
          <button
            onClick={handleRun}
            className="w-full py-3 rounded-lg font-mono font-bold text-[12px] flex items-center justify-center gap-2 border transition-all mb-4"
            style={{
              background: "rgba(0,212,170,0.08)",
              borderColor: "rgba(0,212,170,0.2)",
              color: "#00d4aa",
            }}
          >
            🔭 Run Deep Research on {symbol}
          </button>
        )}

        {/* Loading state */}
        {loading && (
          <div className="flex items-center gap-3 px-4 py-3 rounded-lg bg-surface-2 border border-border/40 mb-4">
            <div className="flex gap-1">
              {[0,1,2].map(i => (
                <div key={i} className="w-1.5 h-1.5 rounded-full bg-teal animate-bounce"
                     style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
            <span className="text-[11px] font-mono text-text-muted">
              Perplexity is researching {symbol} across live sources…
            </span>
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="px-4 py-3 rounded-lg bg-red/5 border border-red/15 text-[11px] font-mono text-red mb-4">
            Research failed: {error}
            <button onClick={reset} className="ml-3 underline opacity-70">Try again</button>
          </div>
        )}

        {/* Report */}
        {report && !loading && (
          <>
            {/* Verdict banner */}
            <div className={`flex items-start gap-3 p-3.5 rounded-xl mb-4 border ${
              report.consensus.toLowerCase().includes("bear")
                ? "bg-red/5 border-red/15"
                : "bg-teal/5 border-teal/15"
            }`}>
              <span className="text-xl flex-shrink-0">🧠</span>
              <div>
                <div className="text-[14px] font-black text-text leading-snug mb-1">
                  {report.verdict_headline}
                </div>
                <div className="text-[9px] font-mono text-text-muted/70">
                  Confidence: {report.confidence} · Sources: {report.sources_count} · Consensus: {report.consensus}
                </div>
              </div>
            </div>

            {/* Key findings chips */}
            <div className="flex flex-wrap gap-1.5 mb-4">
              {report.findings.map((f, i) => (
                <div key={i} className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[10px] font-mono ${
                  FINDING_STYLE[f.type] ?? FINDING_STYLE.neutral
                }`}>
                  <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${FINDING_DOT[f.type] ?? FINDING_DOT.neutral}`} />
                  {f.text}
                </div>
              ))}
            </div>

            {/* Research sections 2×2 */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              {[
                ["Market Context",      report.sections.market_context],
                ["Narrative & Sentiment", report.sections.narrative_sentiment],
                ["Risk Factors",        report.sections.risk_factors],
                ["30-Day Outlook",      report.sections.outlook_30d],
              ].map(([title, text]) => (
                <div key={title}>
                  <div className="flex items-center gap-2 mb-1.5">
                    <span className="text-[9px] font-mono font-bold text-text-muted/70 uppercase tracking-[0.1em]">{title}</span>
                    <div className="flex-1 h-px bg-border/40" />
                  </div>
                  <p className="text-[11px] text-text-muted leading-relaxed"
                     dangerouslySetInnerHTML={{ __html: text.replace(/\*\*(.*?)\*\*/g, '<strong class="text-text">$1</strong>') }}
                  />
                </div>
              ))}
            </div>

            {/* Sources */}
            <div className="flex items-center gap-2 px-3 py-2 bg-surface-2 rounded-lg border border-border/40 mb-4 flex-wrap">
              <span className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide flex-shrink-0">Sources</span>
              {report.sources.slice(0, 7).map(s => (
                <span key={s} className="text-[9px] font-mono font-bold px-2 py-0.5 rounded bg-surface-offset border border-border/40 text-text-muted cursor-pointer hover:text-teal hover:border-teal/30 transition-all">
                  {s}
                </span>
              ))}
              {report.sources.length > 7 && (
                <span className="text-[9px] font-mono text-text-muted/50 ml-1">
                  +{report.sources.length - 7} more
                </span>
              )}
            </div>

            {/* Regenerate */}
            <div className="flex items-center gap-2">
              <button
                onClick={handleRun}
                disabled={loading}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-[11px] font-mono font-bold transition-all border"
                style={{ background: "rgba(0,212,170,0.08)", borderColor: "rgba(0,212,170,0.2)", color: "#00d4aa" }}
              >
                ↻ Regenerate report
              </button>
              <div className="ml-auto flex items-center gap-1.5 text-[9px] font-mono text-text-muted/60">
                <div className="w-2 h-2 rounded-full bg-teal/60" />
                Powered by Perplexity
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
