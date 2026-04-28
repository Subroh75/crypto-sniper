// ─── BottomSections.tsx — Trending · News · Macro ───────────────────────────
import { useState, useEffect, useRef } from "react";
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

// Coin name map for news keyword matching
const NEWS_COIN_NAMES: Record<string, string[]> = {
  BTC: ["bitcoin", "btc"], ETH: ["ethereum", "eth"], SOL: ["solana", "sol"],
  BNB: ["bnb", "binance"], XRP: ["ripple", "xrp"], DOGE: ["dogecoin", "doge"],
  ADA: ["cardano", "ada"], AVAX: ["avalanche", "avax"], DOT: ["polkadot", "dot"],
  LINK: ["chainlink", "link"], MATIC: ["polygon", "matic"], UNI: ["uniswap", "uni"],
  ATOM: ["cosmos", "atom"], LTC: ["litecoin", "ltc"], NEAR: ["near", "near protocol"],
  APT: ["aptos", "apt"], ARB: ["arbitrum", "arb"], OP: ["optimism", "op"],
  SUI: ["sui"], INJ: ["injective", "inj"], TIA: ["celestia", "tia"],
  SEI: ["sei"], PEPE: ["pepe"], SHIB: ["shiba", "shib"], WIF: ["dogwifhat", "wif"],
};

const RSS_FEEDS = [
  { url: "https://cointelegraph.com/rss",                  source: "CoinTelegraph" },
  { url: "https://www.coindesk.com/arc/outboundfeeds/rss/", source: "CoinDesk" },
];

function scoreSentiment(title: string, desc: string): "bullish" | "bearish" | "neutral" {
  const text = (title + " " + desc).toLowerCase();
  const bull = ["surge","rally","bull","gain","rise","pump","breakout","hit high","all-time high","ath","recover","soar","jump","moon","up ","spike"];
  const bear = ["crash","drop","bear","fall","dump","collapse","plunge","tumble","slump","sell","loss","decline","warning","fear","hack","exploit","fraud","sec","ban"];
  const bs = bull.filter(w => text.includes(w)).length;
  const be = bear.filter(w => text.includes(w)).length;
  return bs > be ? "bullish" : be > bs ? "bearish" : "neutral";
}

function useClientNews(symbol: string) {
  const [articles, setArticles] = useState<Array<{title:string;source:string;url:string;published:string;sentiment:"bullish"|"bearish"|"neutral"}>>([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string|null>(null);
  const prevSymbol = useRef("");

  useEffect(() => {
    if (!symbol || symbol === prevSymbol.current) return;
    prevSymbol.current = symbol;
    setLoading(true);
    setError(null);
    setArticles([]);

    const keywords = [
      symbol.toLowerCase(),
      ...(NEWS_COIN_NAMES[symbol.toUpperCase()] ?? []),
    ];

    const fetches = RSS_FEEDS.map(feed =>
      fetch(`https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(feed.url)}`)
        .then(r => r.json())
        .then(d => (d.items ?? []).map((item: Record<string,string>) => ({ ...item, _source: feed.source })))
        .catch(() => [])
    );

    Promise.all(fetches).then(results => {
      const all = results.flat();
      const matched = all.filter((item: Record<string,string>) => {
        const text = ((item.title ?? "") + " " + (item.description ?? "") + " " + (item.categories ?? []).join(" ")).toLowerCase();
        return keywords.some(k => text.includes(k));
      });
      // Fallback to top 4 general crypto news if no match
      const pool = matched.length >= 2 ? matched : all.slice(0, 8);
      const seen = new Set<string>();
      const deduped = pool.filter((item: Record<string,string>) => {
        if (seen.has(item.title)) return false;
        seen.add(item.title); return true;
      });
      setArticles(deduped.slice(0, 4).map((item: Record<string,string>) => ({
        title:     item.title ?? "",
        source:    item._source ?? "Crypto News",
        url:       item.link ?? "",
        published: item.pubDate ?? "",
        sentiment: scoreSentiment(item.title ?? "", item.description ?? ""),
      })));
      setLoading(false);
    }).catch(e => { setError(String(e)); setLoading(false); });
  }, [symbol]);

  return { articles, loading, error };
}

export function NewsSection({ symbol }: { symbol: string }) {
  const { articles, loading, error } = useClientNews(symbol);

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
              {error ? `News unavailable` : `No news found for ${symbol}`}
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
// Derive a macro regime score (-3 to +3) and per-metric interpretation from live data
function buildMacroInsights(data: Record<string, number | null | undefined> | null) {
  const fedRate  = data?.fed_rate ?? 4.25;
  const cpi      = data?.us_cpi   ?? 3.1;
  const dxy      = data?.dxy      ?? 101.4;
  const gold     = data?.gold     ?? 3240;
  const yield10y = 4.38; // static fallback

  // Each metric scores -1 (bearish for crypto), 0 (neutral), +1 (bullish)
  const fedScore  = fedRate <= 3.5 ? 1 : fedRate >= 5.0 ? -1 : 0;
  const cpiScore  = cpi <= 2.5 ? 1 : cpi >= 4.0 ? -1 : 0;
  const dxyScore  = dxy <= 99 ? 1 : dxy >= 104 ? -1 : 0;
  const yieldScore = yield10y <= 3.5 ? 1 : yield10y >= 4.5 ? -1 : 0;
  const goldScore  = gold >= 2500 ? 1 : gold <= 1800 ? -1 : 0; // gold up = risk-off but also inflation hedge

  const total = fedScore + cpiScore + dxyScore + yieldScore + goldScore;

  const regime =
    total >= 3  ? { label: "RISK-ON",     color: "text-teal",  bg: "bg-teal/8 border-teal/20",    desc: "Macro tailwinds are strong. Low rates + weak dollar = ideal crypto environment." } :
    total >= 1  ? { label: "MILD BULLISH",color: "text-teal",  bg: "bg-teal/5 border-teal/15",    desc: "Conditions lean supportive. Most macro factors are not headwinds for crypto." } :
    total === 0 ? { label: "NEUTRAL",     color: "text-amber", bg: "bg-amber/8 border-amber/20",  desc: "Mixed signals. Bulls and bears have equal footing from a macro standpoint." } :
    total >= -2 ? { label: "MILD BEARISH",color: "text-red",   bg: "bg-red/5 border-red/15",      desc: "Some macro headwinds present. High rates or strong dollar compress risk appetite." } :
                  { label: "RISK-OFF",    color: "text-red",   bg: "bg-red/8 border-red/20",      desc: "Macro environment is hostile to risk assets. Capital preservation favoured." };

  const impacts = [
    {
      label: "Fed Rate",
      value: `${fedRate}%`,
      signal: fedScore > 0 ? "Bullish" : fedScore < 0 ? "Bearish" : "Neutral",
      color:  fedScore > 0 ? "text-teal" : fedScore < 0 ? "text-red" : "text-amber",
      note:   fedRate <= 3.5 ? "Accommodative — cheap capital flows into risk assets"
            : fedRate >= 5.0 ? "Restrictive — high cost of capital limits crypto upside"
            : "Moderate — neither stimulative nor restrictive for crypto",
    },
    {
      label: "US CPI",
      value: `${cpi}%`,
      signal: cpiScore > 0 ? "Bullish" : cpiScore < 0 ? "Bearish" : "Neutral",
      color:  cpiScore > 0 ? "text-teal" : cpiScore < 0 ? "text-red" : "text-amber",
      note:   cpi <= 2.5 ? "Inflation tamed — reduces pressure for rate hikes"
            : cpi >= 4.0 ? "Elevated inflation — forces Fed hawkishness, risk-asset drag"
            : "Within range — rate cut path remains open",
    },
    {
      label: "DXY",
      value: dxy > 0 ? dxy.toFixed(1) : "101.4",
      signal: dxyScore > 0 ? "Bullish" : dxyScore < 0 ? "Bearish" : "Neutral",
      color:  dxyScore > 0 ? "text-teal" : dxyScore < 0 ? "text-red" : "text-amber",
      note:   dxy <= 99  ? "Weak dollar — strong historical tailwind for BTC and alts"
            : dxy >= 104 ? "Strong dollar — inversely correlated with crypto rally potential"
            : "Dollar neutral — no significant FX headwind or tailwind",
    },
    {
      label: "10Y Yield",
      value: `${yield10y}%`,
      signal: yieldScore > 0 ? "Bullish" : yieldScore < 0 ? "Bearish" : "Neutral",
      color:  yieldScore > 0 ? "text-teal" : yieldScore < 0 ? "text-red" : "text-amber",
      note:   yield10y <= 3.5 ? "Low yields push capital toward higher-risk assets like crypto"
            : yield10y >= 4.5 ? "High yields make bonds competitive — reduces crypto appeal"
            : "Yields moderate — not a decisive factor either way",
    },
    {
      label: "Gold",
      value: gold > 0 ? fmtPrice(gold) : "$3,240",
      signal: goldScore > 0 ? "Bullish" : goldScore < 0 ? "Bearish" : "Neutral",
      color:  goldScore > 0 ? "text-teal" : goldScore < 0 ? "text-red" : "text-amber",
      note:   gold >= 2500 ? "Gold elevated — inflation hedge demand benefits BTC narrative"
            : gold <= 1800 ? "Gold weak — risk-off sentiment not yet driving store-of-value bids"
            : "Gold range-bound — neutral read on inflation and safe-haven flows",
    },
  ];

  return { regime, impacts, total };
}

export function MacroSection() {
  const { data } = useMacro();

  const macroData = data as Record<string, number | null | undefined> | null;
  const { regime, impacts } = buildMacroInsights(macroData);

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
      <div className="p-4 space-y-4">

        {/* Metric tiles */}
        <div className="grid grid-cols-6 gap-2">
          {stats.map(({ label, value, color }) => (
            <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-2.5">
              <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">{label}</div>
              <div className={`text-[13px] font-mono font-black ${color || "text-text"}`}>{value}</div>
            </div>
          ))}
        </div>

        {/* Macro Regime verdict */}
        <div className={`rounded-lg border ${regime.bg} px-4 py-3 flex items-start gap-4`}>
          <div className="shrink-0">
            <div className="text-[9px] font-mono text-text-muted/60 uppercase tracking-widest mb-1">Macro Regime</div>
            <div className={`text-[15px] font-mono font-black ${regime.color}`}>{regime.label}</div>
          </div>
          <div className="w-px self-stretch bg-border/30" />
          <p className="text-[11px] text-text-muted leading-relaxed pt-0.5">{regime.desc}</p>
        </div>

        {/* Per-metric crypto impact table */}
        <div className="rounded-lg border border-border/40 overflow-hidden">
          <div className="grid grid-cols-4 px-3 py-1.5 border-b border-border/30 bg-surface-2">
            <span className="text-[9px] font-mono font-bold text-text-muted/50 uppercase tracking-widest">Indicator</span>
            <span className="text-[9px] font-mono font-bold text-text-muted/50 uppercase tracking-widest">Value</span>
            <span className="text-[9px] font-mono font-bold text-text-muted/50 uppercase tracking-widest">Signal</span>
            <span className="text-[9px] font-mono font-bold text-text-muted/50 uppercase tracking-widest">Crypto Impact</span>
          </div>
          {impacts.map((row, i) => (
            <div
              key={row.label}
              className={`grid grid-cols-4 px-3 py-2.5 items-start gap-2 ${
                i < impacts.length - 1 ? "border-b border-border/20" : ""
              }`}
            >
              <span className="text-[10px] font-mono font-bold text-text-muted/80">{row.label}</span>
              <span className={`text-[10px] font-mono font-bold ${row.color}`}>{row.value}</span>
              <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded self-start ${
                row.signal === "Bullish" ? "bg-teal/10 text-teal" :
                row.signal === "Bearish" ? "bg-red/10 text-red" :
                "bg-amber/10 text-amber"
              }`}>{row.signal}</span>
              <span className="text-[10px] text-text-muted/70 leading-snug">{row.note}</span>
            </div>
          ))}
        </div>

      </div>
    </div>
  );
}
