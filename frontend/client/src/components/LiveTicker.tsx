// ─── LiveTicker.tsx — Scrolling price ticker in header ──────────────────────
import { useLivePrices } from "@/hooks/useApi";
import { fmtPrice, fmtPct } from "@/lib/api";

const SYMBOLS = ["BTC","ETH","SOL","BNB","DOGE","PEPE","WIF","HYPE"];

export function LiveTicker() {
  const prices = useLivePrices();

  return (
    <div className="flex-1 overflow-hidden mask-fade-x">
      <div className="flex gap-6 animate-ticker whitespace-nowrap">
        {/* Duplicate for seamless loop */}
        {[...SYMBOLS, ...SYMBOLS].map((sym, i) => {
          const p = prices[sym];
          const chg = 0; // change shown from quote, not WS
          const up  = p ? p.price >= p.prev : true;

          return (
            <span key={i} className="inline-flex items-center gap-1.5 text-[11px] font-mono">
              <span className="text-text-muted font-semibold">{sym}</span>
              <span className="text-text font-bold">
                {p ? fmtPrice(p.price) : "—"}
              </span>
              {p && p.price !== p.prev && (
                <span className={up ? "text-teal" : "text-red"}>
                  {up ? "▲" : "▼"}
                </span>
              )}
            </span>
          );
        })}
      </div>
    </div>
  );
}
