// ─── MarketBar.tsx — 6-stat strip: mkt cap, BTC dom, F&G, fees, Fed, DXY ────
import { useMarketOverview, useMacro } from "@/hooks/useApi";
import { fmtBigNum, fmtPct } from "@/lib/api";

interface StatProps {
  label: string;
  value: React.ReactNode;
  sub?:  React.ReactNode;
}

function Stat({ label, value, sub }: StatProps) {
  return (
    <div className="flex flex-col gap-[3px] px-4 py-2.5">
      <span className="text-[9px] font-mono uppercase tracking-[0.1em] text-text-muted/70">
        {label}
      </span>
      <span className="text-[14px] font-mono font-bold text-text leading-none">
        {value}
      </span>
      {sub && <span className="text-[10px] font-mono">{sub}</span>}
    </div>
  );
}

// Fear & Greed needle (placeholder — real index needs paid API)
function FearGreedMeter({ value = 62 }: { value?: number }) {
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
    <div className="flex flex-col gap-[3px] px-4 py-2.5">
      <span className="text-[9px] font-mono uppercase tracking-[0.1em] text-text-muted/70">
        Fear &amp; Greed
      </span>
      <span className="text-[14px] font-mono font-bold leading-none" style={{ color }}>
        {value} — {label}
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

  const capChange = market?.market_cap_change_24h ?? 0;
  const fees      = market?.btc_mempool_fees ?? 0;

  return (
    <div
      className="grid border-b border-border/60"
      style={{ gridTemplateColumns: "repeat(6, 1fr)" }}
    >
      {/* Dividers between cells */}
      <div className="border-r border-border/40">
        <Stat
          label="Total Mkt Cap"
          value={market ? fmtBigNum(market.total_market_cap_usd) : "Loading…"}
          sub={
            market ? (
              <span className={capChange >= 0 ? "text-teal" : "text-red"}>
                {capChange != null ? (capChange >= 0 ? "▲" : "▼") + " " + Math.abs(capChange).toFixed(2) + "% today" : ""}
              </span>
            ) : null
          }
        />
      </div>

      <div className="border-r border-border/40">
        <Stat
          label="BTC Dominance"
          value={market?.btc_dominance != null ? `${market.btc_dominance.toFixed(1)}%` : "—"}
          sub={<span className="text-text-muted/60">→ Holding</span>}
        />
      </div>

      <div className="border-r border-border/40">
        <FearGreedMeter value={62} />
      </div>

      <div className="border-r border-border/40">
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

      <div className="border-r border-border/40">
        <Stat
          label="Fed Rate"
          value={macro?.fed_rate != null ? `${macro.fed_rate}%` : "4.25%"}
          sub={<span className="text-text-muted/60">Next decision May 7</span>}
        />
      </div>

      <div>
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
  );
}
