// LiveTicker.tsx - scrolling price ticker with Binance WS live prices
import { useLivePrices } from "@/hooks/useApi";
import { fmtPct } from "@/lib/api";

const SYMBOLS = ["BTC","ETH","SOL","BNB","DOGE","PEPE","WIF","HYPE","XRP","ADA"];

function fmtP(p: number): string {
  if (!p || p === 0) return "--";
  if (p >= 1) return "$" + p.toLocaleString("en-US", {minimumFractionDigits:2,maximumFractionDigits:2});
  if (p >= 0.01) return "$" + p.toFixed(4);
  return "$" + p.toFixed(8);
}

export function LiveTicker() {
  const prices = useLivePrices();

  return (
    <div style={{ overflow: "hidden", flex: 1, position: "relative" }}>
      <style>{
        `@keyframes tickerScroll {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .ticker-track {
          display: flex;
          width: max-content;
          animation: tickerScroll 30s linear infinite;
        }
        .ticker-track:hover { animation-play-state: paused; }
        .ticker-item {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 0 20px;
          white-space: nowrap;
          font-family: monospace;
          font-size: 12px;
        }`
      }</style>
      <div className="ticker-track">
        {[...SYMBOLS, ...SYMBOLS].map((sym, i) => {
          const d = prices[sym];
          const up = d ? d.change >= 0 : true;
          return (
            <div key={i} className="ticker-item">
              <span style={{ color: "#64748b", fontWeight: 600 }}>{sym}</span>
              <span style={{ color: "#f1f5f9", fontWeight: 700 }}>
                {d ? fmtP(d.price) : "--"}
              </span>
              {d && (
                <span style={{ color: up ? "#22c55e" : "#ef4444", fontSize: 10 }}>
                  {up ? "+" : ""}{d.change.toFixed(2)}%
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
