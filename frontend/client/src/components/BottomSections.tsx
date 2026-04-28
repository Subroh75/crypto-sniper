// ─── BottomSections.tsx — Trending · News · Macro ───────────────────────────
import { useTrending, useGainers, useNews, useMacro } from "@/hooks/useApi";
import { fmtPrice, fmtPct, timeAgo } from "@/lib/api";

// ── Section header ────────────────────────────────────────────────────────────
function SectionHeader({ num, icon, title, badge, src }: {
  num?: string; icon?: string; title: string; badge?: string; src?: string;
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
// TRENDING
// ════════════════════════════════════════════════════════════════════════════
export function TrendingSection({ onSelect }: { onSelect: (sym: string) => void }) {
  const { coins, loading } = useTrending();

  return (
    <div className="card mb-3">
      <SectionHeader icon="🔥" title="TRENDING NOW" />
      <div className="p-4">
        {loading ? (
          <div className="grid grid-cols-5 gap-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-20 bg-surface-2 rounded-lg animate-pulse border border-border/30" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-5 gap-2">
            {coins.slice(0, 5).map((coin) => (
              <button
                key={coin.symbol}
                onClick={() => onSelect(coin.symbol)}
                className="flex flex-col items-center gap-1.5 p-3 rounded-lg border border-border/50 bg-surface-2 hover:border-purple/40 transition-all text-center"
              >
                <span className="text-[9px] font-mono text-text-muted/60">#{coin.rank}</span>
                <span className={`text-[14px] font-mono font-black ${
                  coin.change_24h >= 0 ? "text-teal" : "text-red"
                }`}>{coin.symbol}</span>
                <span className="text-[8px] font-mono text-text-muted/60 truncate w-full">{coin.name}</span>
                {coin.price > 0 && (
                  <span className="text-[10px] font-mono font-bold text-text mt-0.5">{fmtPrice(coin.price)}</span>
                )}
                <span className={`text-[10px] font-mono font-bold ${
                  coin.change_24h >= 0 ? "text-teal" : "text-red"
                }`}>
                  {(coin.change_24h ?? 0) >= 0 ? "▲" : "▼"} {Math.abs(coin.change_24h ?? 0).toFixed(1)}%
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// NEWS
// ════════════════════════════════════════════════════════════════════════════
const SENTIMENT_STYLE = {
  bullish: { bar: "border-l-teal",    tag: "bg-teal/10 text-teal",   label: "Bullish" },
  bearish: { bar: "border-l-red",     tag: "bg-red/10 text-red",     label: "Bearish" },
  neutral: { bar: "border-l-amber",   tag: "bg-amber/10 text-amber", label: "Neutral" },
} as const;

export function NewsSection({ symbol }: { symbol: string }) {
  const { data, loading, error } = useNews(symbol);
  const articles = data?.articles ?? [];

  return (
    <div className="card mb-3">
      <SectionHeader icon="📰" title="LIVE NEWS" badge="NEW" />
      <div className="p-4">
        <div className="grid grid-cols-2 gap-2">
          {loading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-20 bg-surface-2 rounded-lg animate-pulse border border-border/30" />
            ))
          ) : articles.length > 0 ? (
            articles.slice(0, 4).map((article, i) => {
              const style = SENTIMENT_STYLE[article.sentiment] ?? SENTIMENT_STYLE.neutral;
              return (
                <a
                  key={i}
                  href={article.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`block p-3 rounded-lg border border-border/50 bg-surface-2 border-l-[3px] ${style.bar} hover:bg-surface-offset transition-all`}
                >
                  <div className="flex items-center gap-1.5 mb-2">
                    <span className={`text-[8px] font-mono font-bold px-1.5 py-0.5 rounded ${style.tag}`}>
                      {style.label} · {symbol}
                    </span>
                  </div>
                  <div className="text-[11px] text-text leading-snug mb-2 line-clamp-2">
                    {article.title}
                  </div>
                  <div className="flex gap-2 text-[9px] font-mono text-text-muted/60">
                    <span>{article.source}</span>
                    <span>{timeAgo(article.published)}</span>
                  </div>
                </a>
              );
            })
          ) : (
            <div className="col-span-2 py-8 text-center text-[11px] font-mono text-text-muted/50">
              {error ? `News unavailable — ${error}` : `No news found for ${symbol}`}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// MACRO
// ════════════════════════════════════════════════════════════════════════════
export function MacroSection() {
  const { data } = useMacro();

  const stats = [
    { label: "Fed Rate", value: data?.fed_rate != null ? `${data.fed_rate}%`    : "4.25%", color: "" },
    { label: "US CPI",   value: data?.us_cpi   != null ? `${data.us_cpi}%`     : "3.1%",  color: "" },
    { label: "DXY",      value: data?.dxy       != null ? data.dxy.toFixed(1)   : "101.4", color: "text-red" },
    { label: "10Y Yield",value: "4.38%",                                                    color: "" },
    { label: "Gold",     value: data?.gold      != null ? fmtPrice(data.gold)   : "$3,240", color: "text-teal" },
    { label: "S&P 500",  value: "5,241",                                                    color: "text-teal" },
  ];

  return (
    <div className="card mb-3">
      <SectionHeader icon="🌐" title="MACRO CONTEXT" badge="NEW" />
      <div className="p-4">
        <div className="grid grid-cols-6 gap-2">
          {stats.map(({ label, value, color }) => (
            <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-2.5">
              <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">{label}</div>
              <div className={`text-[13px] font-mono font-black ${color || "text-text"}`}>{value}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
