// ─── MarketBar.tsx — 6-stat strip: mkt cap, BTC dom, F&G, fees, Fed, DXY ────
import { useState, useEffect } from "react";
import { useMarketOverview, useMacro } from "@/hooks/useApi";
import { fmtBigNum, fmtPct } from "@/lib/api";

interface StatProps {
  label: string;
  value: React.ReactNode;
  sub?:  React.ReactNode;
}

function Stat({ label, value, sub }: StatProps) {
  return (
    <div className="flex flex-col gap-[3px] px-3 md:px-4 py-2 md:py-2.5 min-w-[110px] md:min-w-0">
      <span className="text-[8px] md:text-[9px] font-mono uppercase tracking-[0.1em] text-text-muted/70 whitespace-nowrap">
        {label}
      </span>
      <span className="text-[12px] md:text-[14px] font-mono font-bold text-text leading-none whitespace-nowrap">
        {value}
      </span>
      {sub && <span className="text-[9px] md:text-[10px] font-mono">{sub}</span>}
    </div>
  );
}

// Fear & Greed needle — live from alternative.me (free, no key)
function FearGreedMeter({ value = 0, loading = false }: { value?: number; loading?: boolean }) {
  const label =
    value >= 75 ? "Extreme Greed"
    : value >= 55 ? "Greed"
    : value >= 45 ? "Neutral"
    : value >= 25 ? "Fear"
    : "Extreme Fear";

  const color =
    value >= 75 ? "#ff3d5a"
    : value >= 55 ? "#f7c948"
    : value >= 45 ? "#b8c2dc"
    : value >= 25 ? "#ff8c42"
    : "#ff3d5a";

  return (
    <div className="flex flex-col gap-[3px] px-3 md:px-4 py-2 md:py-2.5 min-w-[130px] md:min-w-0">
      <span className="text-[8px] md:text-[9px] font-mono uppercase tracking-[0.1em] text-text-muted/70 whitespace-nowrap">
        Fear &amp; Greed
      </span>
      <span className="text-[12px] md:text-[14px] font-mono font-bold leading-none whitespace-nowrap" style={{ color }}>
        {loading ? "…" : `${value} — ${label}`}
      </span>
      <div className="relative w-full h-[3px] rounded-full mt-1 overflow-visible"
           style={{ background: "linear-gradient(90deg,#ff3d5a 0%,#ff8c42 35%,#f7c948 60%,#00d4aa 100%)" }}>
        <div
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-[10px] h-[10px] rounded-full bg-white shadow"
          style={{ left: `${value}%` }}
        />
      </div>
    </div>
  );
}

export function MarketBar() {
  const { data: market } = useMarketOverview();
  const { data: macro }  = useMacro();

  // Live Fear & Greed from alternative.me (free, no key required)
  const [fng, setFng] = useState<{ value: number; loading: boolean }>({ value: 0, loading: true });
  useEffect(() => {
    fetch("https://api.alternative.me/fng/?limit=1&format=json", { signal: AbortSignal.timeout(8000) })
      .then(r => r.json())
      .then(j => {
        const v = parseInt(j?.data?.[0]?.value ?? "0", 10);
        if (v > 0) setFng({ value: v, loading: false });
        else setFng({ value: 0, loading: false });
      })
      .catch(() => setFng({ value: 0, loading: false }));
  }, []);

  // Fallback: fetch global data directly from CoinGecko if Render returns 0
  const [cgGlobal, setCgGlobal] = useState<{ cap: number; capChange: number; btcDom: number } | null>(null);
  useEffect(() => {
    if (market?.total_market_cap_usd && market.total_market_cap_usd > 0) return;
    fetch("https://api.coingecko.com/api/v3/global", { signal: AbortSignal.timeout(8000) })
      .then(r => r.json())
      .then(j => {
        const d = j?.data;
        if (!d) return;
        setCgGlobal({
          cap:       d.total_market_cap?.usd ?? 0,
          capChange: d.market_cap_change_percentage_24h_usd ?? 0,
          btcDom:    d.market_cap_percentage?.btc ?? 0,
        });
      })
      .catch(() => {});
  }, [market?.total_market_cap_usd]);

  const totalCap    = (market?.total_market_cap_usd && market.total_market_cap_usd > 0)
    ? market.total_market_cap_usd : (cgGlobal?.cap ?? 0);
  const capChange   = (market?.market_cap_change_24h && market.market_cap_change_24h !== 0)
    ? market.market_cap_change_24h : (cgGlobal?.capChange ?? 0);
  const btcDom      = (market?.btc_dominance && market.btc_dominance > 0)
    ? market.btc_dominance : (cgGlobal?.btcDom ?? 0);
  const fees        = market?.btc_mempool_fees ?? 0;

  return (
    <div className="border-b border-border/60 overflow-x-auto scrollbar-none">
    <div
      className="flex md:grid md:w-full"
      style={{ gridTemplateColumns: "repeat(6, 1fr)" }}
    >
      {/* Dividers between cells */}
      <div className="border-r border-border/40 flex-shrink-0">
        <Stat
          label="Total Mkt Cap"
          value={totalCap > 0 ? fmtBigNum(totalCap) : "Loading…"}
          sub={
            totalCap > 0 ? (
              <span className={capChange >= 0 ? "text-teal" : "text-red"}>
                {capChange >= 0 ? "▲" : "▼"} {Math.abs(capChange).toFixed(2)}% today
              </span>
            ) : null
          }
        />
      </div>

      <div className="border-r border-border/40 flex-shrink-0">
        <Stat
          label="BTC Dominance"
          value={btcDom > 0 ? `${btcDom.toFixed(1)}%` : "—"}
          sub={btcDom > 0 ? <span className="text-text-muted/60">→ {btcDom > 55 ? "Strong" : btcDom > 50 ? "Holding" : "Weakening"}</span> : null}
        />
      </div>

      <div className="border-r border-border/40 flex-shrink-0">
        <FearGreedMeter value={fng.value} loading={fng.loading} />
      </div>

      <div className="border-r border-border/40 flex-shrink-0">
        <Stat
          label="BTC Mempool"
          value={
            fees > 0 ? (
              <span className={fees > 30 ? "text-teal" : "text-text"}>
                {fees} sat/vB
              </span>
            ) : "—"
          }
          sub={
            fees > 0 ? (
              <span className={fees > 30 ? "text-teal" : "text-text-muted/60"}>
                {fees > 50 ? "Very high" : fees > 30 ? "High activity" : fees > 10 ? "Moderate" : "Low fees"}
              </span>
            ) : null
          }
        />
      </div>

      <div className="border-r border-border/40 flex-shrink-0">
        <Stat
          label="Fed Rate"
          value={macro?.fed_rate != null ? `${macro.fed_rate}%` : "4.25%"}
          sub={<span className="text-text-muted/60">Next decision May 7</span>}
        />
      </div>

      <div className="flex-shrink-0">
        <Stat
          label="DXY"
          value={
            <span className="text-red">
              {macro?.dxy != null ? macro.dxy.toFixed(1) : "101.4"}
            </span>
          }
          sub={<span className="text-red">▼ Weakening</span>}
        />
      </div>
    </div>
    </div>
  );
}
