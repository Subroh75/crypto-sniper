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
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className={`h-20 bg-surface-2 rounded-lg animate-pulse border border-border/30${i === 5 ? " sm:hidden" : ""}`} />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-2">
            {coins.slice(0, 6).map((coin, idx) => (
              <button
                key={coin.symbol}
                onClick={() => onSelect(coin.symbol)}
                className={`flex flex-col items-center gap-1.5 p-3 rounded-lg border border-border/50 bg-surface-2 hover:border-purple/40 transition-all text-center${idx === 5 ? " sm:hidden" : ""}`}
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

  const sp500 = 5241; // static fallback

  // Each metric scores -1 (bearish for crypto), 0 (neutral), +1 (bullish)
  const fedScore  = fedRate <= 3.5 ? 1 : fedRate >= 5.0 ? -1 : 0;
  const cpiScore  = cpi <= 2.5 ? 1 : cpi >= 4.0 ? -1 : 0;
  const dxyScore  = dxy <= 99 ? 1 : dxy >= 104 ? -1 : 0;
  const yieldScore = yield10y <= 3.5 ? 1 : yield10y >= 4.5 ? -1 : 0;
  const goldScore  = gold >= 2500 ? 1 : gold <= 1800 ? -1 : 0; // gold up = risk-off but also inflation hedge
  const spScore   = sp500 >= 5000 ? 1 : sp500 <= 4000 ? -1 : 0;

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
    {
      label: "S&P 500",
      value: sp500.toLocaleString(),
      signal: spScore > 0 ? "Bullish" : spScore < 0 ? "Bearish" : "Neutral",
      color:  spScore > 0 ? "text-teal" : spScore < 0 ? "text-red" : "text-amber",
      note:   sp500 >= 5000 ? "Equities strong — risk-on environment supports crypto correlation"
            : sp500 <= 4000 ? "Equities weak — broad risk-off likely weighs on crypto"
            : "S&P range-bound — no decisive risk-on or risk-off signal",
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
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {stats.map(({ label, value, color }) => (
            <div key={label} className="bg-surface-2 rounded-lg border border-border/40 p-2.5">
              <div className="text-[9px] font-mono text-text-muted/70 uppercase tracking-wide mb-1">{label}</div>
              <div className={`text-[13px] font-mono font-black ${color || "text-text"}`}>{value}</div>
            </div>
          ))}
        </div>

        {/* Macro Regime verdict */}
        <div className={`rounded-lg border ${regime.bg} px-4 py-3 flex items-center gap-4`}>
          <div className="shrink-0 min-w-[110px]">
            <div className="text-[8px] font-mono text-text-muted/50 uppercase tracking-widest mb-1">Macro Regime</div>
            <div className={`text-[14px] font-mono font-black tracking-wide ${regime.color}`}>{regime.label}</div>
          </div>
          <div className="w-px self-stretch bg-border/30" />
          <p className="text-[11px] text-text-muted leading-relaxed">{regime.desc}</p>
        </div>

        {/* Per-metric crypto impact — 2-column card grid */}
        <div>
          <div className="text-[8px] font-mono font-bold text-text-muted/40 uppercase tracking-widest mb-2 px-0.5">Crypto Impact Breakdown</div>
          <div className="grid grid-cols-2 gap-2">
            {impacts.map((row) => {
              const pillCls =
                row.signal === "Bullish" ? "bg-teal/10 text-teal border-teal/25" :
                row.signal === "Bearish" ? "bg-red/10 text-red border-red/25" :
                "bg-amber/10 text-amber border-amber/25";
              const dotCls =
                row.signal === "Bullish" ? "bg-teal" :
                row.signal === "Bearish" ? "bg-red" :
                "bg-amber";
              return (
                <div
                  key={row.label}
                  className="bg-surface-2 rounded-lg border border-border/40 p-3 flex flex-col gap-2"
                >
                  {/* Top row: indicator name + signal pill */}
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[10px] font-mono font-bold text-text-muted/80 uppercase tracking-wide">
                      {row.label}
                    </span>
                    <span className={`inline-flex items-center gap-1 text-[8px] font-mono font-bold px-2 py-0.5 rounded-full border ${pillCls} shrink-0`}>
                      <span className={`w-1 h-1 rounded-full ${dotCls}`} />
                      {row.signal}
                    </span>
                  </div>
                  {/* Value */}
                  <div className={`text-[17px] font-mono font-black leading-none ${row.color}`}>
                    {row.value}
                  </div>
                  {/* Impact note */}
                  <div className="text-[10px] text-text-muted/60 leading-snug">
                    {row.note}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

      </div>
    </div>
  );
}

// ════════════════════════════════════════════════════════════════════════════
// MARKET OPTIONS INTELLIGENCE
// Deribit public API — BTC + ETH options. No auth required.
// Always rendered as market-wide sentiment, irrespective of analysed coin.
// ════════════════════════════════════════════════════════════════════════════

interface OptionsData {
  currency:       string;
  underlying:     number;
  nearest_expiry: string;
  atm_iv:         number | null;
  pc_ratio:       number | null;
  skew:           number | null;   // OTM put IV − OTM call IV
  max_pain:       number | null;
  exp_move_pct:   number | null;
  exp_move_usd:   number | null;
}

async function fetchDeribitOptions(currency: "BTC" | "ETH"): Promise<OptionsData | null> {
  try {
    const r = await fetch(
      `https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=${currency}&kind=option`,
      { signal: AbortSignal.timeout(12000) }
    );
    if (!r.ok) return null;
    const d = await r.json();
    const results: Array<Record<string, unknown>> = d.result ?? [];

    // Parse instruments
    interface Inst { expiry: string; strike: number; type: "C"|"P"; oi: number; mark_iv: number; underlying: number; }
    const instruments: Inst[] = [];
    for (const row of results) {
      const name = row.instrument_name as string;
      const parts = name.split("-");
      if (parts.length !== 4) continue;
      const [, expiry, strikeStr, optType] = parts;
      const strike = parseInt(strikeStr, 10);
      if (isNaN(strike)) continue;
      instruments.push({
        expiry,
        strike,
        type:       (optType as "C"|"P"),
        oi:         (row.open_interest as number) ?? 0,
        mark_iv:    (row.mark_iv       as number) ?? 0,
        underlying: (row.underlying_price as number) ?? 0,
      });
    }
    if (!instruments.length) return null;

    // Sort expiries chronologically — parse "28APR26" or "28APR2026"
    const parseExp = (e: string): number => {
      const months: Record<string,number> = {
        JAN:0,FEB:1,MAR:2,APR:3,MAY:4,JUN:5,JUL:6,AUG:7,SEP:8,OCT:9,NOV:10,DEC:11
      };
      const m = e.match(/^(\d{1,2})([A-Z]{3})(\d{2,4})$/);
      if (!m) return Infinity;
      const day = parseInt(m[1], 10);
      const mon = months[m[2]] ?? 0;
      const yr  = parseInt(m[3], 10) + (m[3].length === 2 ? 2000 : 0);
      return new Date(yr, mon, day).getTime();
    };
    const expiries = [...new Set(instruments.map(i => i.expiry))].sort((a,b) => parseExp(a)-parseExp(b));
    const nearest  = expiries[0];
    const near     = instruments.filter(i => i.expiry === nearest);
    const und      = near[0]?.underlying ?? 0;

    // Put/Call OI ratio
    const puts  = near.filter(i=>i.type==="P").reduce((s,i)=>s+i.oi,0);
    const calls = near.filter(i=>i.type==="C").reduce((s,i)=>s+i.oi,0);
    const pc_ratio = calls > 0 ? parseFloat((puts/calls).toFixed(3)) : null;

    // ATM IV (closest call strike to spot)
    const atmCall = near.filter(i=>i.type==="C").sort((a,b)=>Math.abs(a.strike-und)-Math.abs(b.strike-und))[0];
    const atm_iv  = atmCall?.mark_iv ?? null;

    // 25Δ skew proxy: OTM put (−10%) vs OTM call (+10%)
    const otmPut  = near.filter(i=>i.type==="P").sort((a,b)=>Math.abs(a.strike-und*0.90)-Math.abs(b.strike-und*0.90))[0];
    const otmCall = near.filter(i=>i.type==="C").sort((a,b)=>Math.abs(a.strike-und*1.10)-Math.abs(b.strike-und*1.10))[0];
    const skew = (otmPut && otmCall && otmCall.mark_iv > 0)
      ? parseFloat((otmPut.mark_iv - otmCall.mark_iv).toFixed(1))
      : null;

    // Max pain: strike minimising total option seller loss
    const strikes = [...new Set(near.map(i=>i.strike))].sort((a,b)=>a-b);
    let minLoss = Infinity, max_pain: number|null = null;
    for (const s of strikes) {
      const loss = near.reduce((acc, i) => {
        if (i.type==="C" && s > i.strike) return acc + i.oi*(s-i.strike);
        if (i.type==="P" && s < i.strike) return acc + i.oi*(i.strike-s);
        return acc;
      }, 0);
      if (loss < minLoss) { minLoss=loss; max_pain=s; }
    }

    // 1-week expected move (±1σ)
    const exp_move_pct = atm_iv != null
      ? parseFloat(((atm_iv/100)*Math.sqrt(7/365)*100).toFixed(1))
      : null;
    const exp_move_usd = atm_iv != null
      ? Math.round(und*(atm_iv/100)*Math.sqrt(7/365))
      : null;

    return { currency, underlying: und, nearest_expiry: nearest, atm_iv, pc_ratio, skew, max_pain, exp_move_pct, exp_move_usd };
  } catch {
    return null;
  }
}

function ivSentiment(iv: number|null): { label: string; color: string } {
  if (iv == null) return { label: "—",            color: "text-text-muted/40" };
  if (iv < 40)   return { label: "Low (calm)",    color: "text-teal" };
  if (iv < 70)   return { label: "Moderate",      color: "text-amber" };
  if (iv < 100)  return { label: "Elevated",      color: "text-orange" };
  return              { label: "Extreme",          color: "text-red" };
}

function pcSentiment(pc: number|null): { label: string; color: string } {
  if (pc == null) return { label: "—",               color: "text-text-muted/40" };
  if (pc < 0.7)   return { label: "Call bias",        color: "text-teal" };
  if (pc < 1.0)   return { label: "Slight hedge",     color: "text-amber" };
  if (pc < 1.3)   return { label: "Hedge bias",       color: "text-orange" };
  return               { label: "Fear / hedge heavy", color: "text-red" };
}

function skewSentiment(sk: number|null): { label: string; color: string } {
  if (sk == null)  return { label: "—",              color: "text-text-muted/40" };
  if (sk <= -5)    return { label: "Call premium",    color: "text-teal" };
  if (sk < 5)      return { label: "Neutral",         color: "text-text-muted" };
  if (sk < 15)     return { label: "Put premium",     color: "text-amber" };
  return                { label: "Strong fear skew",  color: "text-red" };
}

function OptionsCurrencyPanel({ data, loading }: { data: OptionsData|null; loading: boolean }) {
  if (loading) {
    return (
      <div className="space-y-2">
        {[1,2,3,4,5].map(i => (
          <div key={i} className="h-8 rounded-lg bg-surface-2 animate-pulse" />
        ))}
      </div>
    );
  }
  if (!data) {
    return (
      <div className="text-center py-4 text-[10px] font-mono text-text-muted/40">
        Deribit unavailable
      </div>
    );
  }

  const iv   = ivSentiment(data.atm_iv);
  const pc   = pcSentiment(data.pc_ratio);
  const sk   = skewSentiment(data.skew);

  const fmtPrice = (n: number) =>
    n >= 1000 ? `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : `$${n.toFixed(2)}`;

  const rows: Array<{ label: string; value: string; sub: string; color: string }> = [
    {
      label: "ATM IV",
      value: data.atm_iv != null ? `${data.atm_iv.toFixed(1)}%` : "—",
      sub:   iv.label,
      color: iv.color,
    },
    {
      label: "Put/Call",
      value: data.pc_ratio != null ? data.pc_ratio.toFixed(2) : "—",
      sub:   pc.label,
      color: pc.color,
    },
    {
      label: "25Δ Skew",
      value: data.skew != null ? `${data.skew > 0 ? "+" : ""}${data.skew}` : "—",
      sub:   sk.label,
      color: sk.color,
    },
    {
      label: "Max Pain",
      value: data.max_pain != null ? fmtPrice(data.max_pain) : "—",
      sub:   data.underlying > 0
        ? `spot ${fmtPrice(data.underlying)}`
        : "—",
      color: data.max_pain != null && data.underlying > 0
        ? data.max_pain > data.underlying ? "text-teal" : "text-red"
        : "text-text-muted/40",
    },
    {
      label: "1W Exp Move",
      value: data.exp_move_pct != null ? `±${data.exp_move_pct}%` : "—",
      sub:   data.exp_move_usd != null ? `±${fmtPrice(data.exp_move_usd)}` : "—",
      color: data.exp_move_pct != null
        ? data.exp_move_pct < 5 ? "text-teal" : data.exp_move_pct < 10 ? "text-amber" : "text-orange"
        : "text-text-muted/40",
    },
  ];

  return (
    <div className="space-y-1.5">
      {rows.map(row => (
        <div
          key={row.label}
          className="flex items-center justify-between py-1.5 px-2 rounded-lg bg-surface-2 border border-border/30"
        >
          <span className="text-[9px] font-mono text-text-muted/60 uppercase tracking-wide w-20 shrink-0">
            {row.label}
          </span>
          <div className="flex items-baseline gap-2 ml-auto">
            <span className={`text-[13px] font-mono font-black ${row.color}`}>
              {row.value}
            </span>
            <span className="text-[8px] font-mono text-text-muted/40 text-right min-w-[70px]">
              {row.sub}
            </span>
          </div>
        </div>
      ))}
      <div className="text-[8px] font-mono text-text-muted/25 text-right pt-0.5">
        expiry {data.nearest_expiry} · Deribit
      </div>
    </div>
  );
}

export function OptionsIntelligenceSection() {
  const [btc, setBtc] = useState<OptionsData|null>(null);
  const [eth, setEth] = useState<OptionsData|null>(null);
  const [loadingBtc, setLoadingBtc] = useState(true);
  const [loadingEth, setLoadingEth] = useState(true);
  const [tab, setTab] = useState<"BTC"|"ETH">("BTC");

  useEffect(() => {
    fetchDeribitOptions("BTC").then(d => { setBtc(d); setLoadingBtc(false); });
    fetchDeribitOptions("ETH").then(d => { setEth(d); setLoadingEth(false); });
  }, []);

  // Derive an overall market sentiment signal
  const btcSig = btc
    ? (btc.pc_ratio != null && btc.pc_ratio > 1.0 ? -1 : 1) +
      (btc.skew     != null && btc.skew     > 10   ? -1 : 1) +
      (btc.atm_iv   != null && btc.atm_iv   > 70   ? -1 : 1)
    : 0;
  const regimeLabel = !btc ? "Loading…"
    : btcSig >= 2  ? "Options Bullish"
    : btcSig <= -1 ? "Options Bearish"
    : "Options Neutral";
  const regimeColor = !btc ? "text-text-muted/40"
    : btcSig >= 2  ? "text-teal"
    : btcSig <= -1 ? "text-red"
    : "text-amber";
  const regimeBg = !btc ? "bg-surface-2 border-border/40"
    : btcSig >= 2  ? "bg-teal/5 border-teal/20"
    : btcSig <= -1 ? "bg-red/5 border-red/20"
    : "bg-amber/5 border-amber/20";

  return (
    <div className="card mb-3">
      <SectionHeader icon="📊" title="MARKET OPTIONS INTELLIGENCE" badge="LIVE" src="Deribit" />
      <div className="p-4 space-y-4">

        {/* Regime verdict */}
        <div className={`rounded-lg border ${regimeBg} px-4 py-3 flex items-center gap-4`}>
          <div className="shrink-0 min-w-[140px]">
            <div className="text-[8px] font-mono text-text-muted/50 uppercase tracking-widest mb-1">Options Regime</div>
            <div className={`text-[14px] font-mono font-black tracking-wide ${regimeColor}`}>{regimeLabel}</div>
          </div>
          <div className="w-px self-stretch bg-border/30" />
          <p className="text-[11px] text-text-muted leading-relaxed">
            {btcSig >= 2
              ? "Calls dominate OI, skew is flat, IV is calm — options market not pricing significant downside."
              : btcSig <= -1
              ? "Put/call elevated, negative skew and high IV — market paying up for downside protection."
              : "Mixed signals — hedging activity present but not decisive. Monitor IV direction."}
          </p>
        </div>

        {/* BTC / ETH tab switcher */}
        <div className="flex gap-1">
          {(["BTC","ETH"] as const).map(c => (
            <button
              key={c}
              onClick={() => setTab(c)}
              className={`text-[9px] font-mono font-bold px-3 py-1.5 rounded-lg border transition-all ${
                tab === c
                  ? "border-purple/50 bg-purple/10 text-purple"
                  : "border-border/40 bg-surface-2 text-text-muted/60 hover:border-purple/30"
              }`}
            >
              {c}
            </button>
          ))}
          <div className="ml-auto text-[8px] font-mono text-text-muted/30 self-center">
            nearest expiry · open interest
          </div>
        </div>

        {/* Panel */}
        {tab === "BTC"
          ? <OptionsCurrencyPanel data={btc} loading={loadingBtc} />
          : <OptionsCurrencyPanel data={eth} loading={loadingEth} />
        }

      </div>
    </div>
  );
}
