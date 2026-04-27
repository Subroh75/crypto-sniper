// Tooltip.tsx — hover tooltips for metric labels
// Usage: <MetricTooltip label="RSI 14">RSI 14</MetricTooltip>
// Or: <MetricTooltip id="RSI" /> — auto-looks up from METRIC_TIPS

import { useState, useRef } from "react";

export const METRIC_TIPS: Record<string, string> = {
  // V/P/R/T/S components
  "V": "Volume score (0–5): measures how much trading activity vs the 20-period average. High volume confirms conviction behind the move.",
  "P": "Momentum score (0–3): looks at recent price change relative to ATR. A big move backed by volatility scores higher.",
  "R": "Range Position score (0–2): where price sits within its recent high-low range. Top quartile = bullish positioning.",
  "T": "Trend Alignment score (0–3): checks ADX strength and whether EMAs are stacked bullishly. Strong trends score full marks.",
  "S": "Social score (0–3): LunarCrush social sentiment data. High positive chatter often precedes price moves.",

  // Timing Quality
  "RSI 14": "Relative Strength Index (14 periods): measures speed of price change. Above 70 = overbought (caution). Below 30 = oversold (opportunity). 40–60 = neutral zone.",
  "ADX 14": "Average Directional Index: measures trend strength, NOT direction. ADX > 25 = strong trend, worth trading. ADX < 20 = ranging market — signals are less reliable.",
  "ATR 14": "Average True Range: the average daily price swing over 14 candles. Larger ATR = more volatility. Used to set stop-loss distances. Shown as % of current price.",
  "Rel Vol": "Relative Volume: current candle volume divided by the 20-period average. 2x means double the normal activity — breakouts on high rel-vol are more credible.",
  "ADX": "Average Directional Index: measures trend strength, NOT direction. ADX > 25 = strong trend worth trading. ADX < 20 = market is ranging.",
  "RSI": "Relative Strength Index: momentum oscillator. >70 overbought, <30 oversold.",

  // Market Structure
  "EMA 20": "Exponential Moving Average (20 periods): short-term trend. Price above = bullish short-term bias.",
  "EMA 50": "Exponential Moving Average (50 periods): medium-term trend. Used by most swing traders. Price above = bullish.",
  "EMA 200": "Exponential Moving Average (200 periods): long-term trend. The most-watched MA by institutions. Price above = macro bullish.",
  "VWAP": "Volume-Weighted Average Price: average price weighted by volume. Acts as intraday support/resistance. Price above VWAP = buyers in control.",
  "BB Upper": "Bollinger Band Upper: 2 standard deviations above the 20-period MA. Price at or above = statistically extended — potential pullback zone.",
  "BB Lower": "Bollinger Band Lower: 2 standard deviations below the MA. Price at or below = potential bounce zone.",
  "Close": "Most recent closing price for the selected interval.",

  // Derivatives
  "Funding Rate": "Periodic payment between long and short perpetual contract holders. Positive = longs pay shorts (overleveraged bulls, slight bearish signal). Negative = shorts pay longs (fear in market, bullish contrarian signal).",
  "Open Interest": "Total USD value of all open perpetual futures contracts. Rising OI + rising price = trend is real. Rising OI + falling price = short squeeze risk or distribution.",
  "L/S Ratio": "% of accounts that are net long vs net short. Contrarian signal: >65% long = crowded trade, fade risk. <38% long = extreme fear, potential reversal.",

  // Signal
  "STRONG BUY": "Score ≥ 9/16: all major conditions aligned — volume surge, momentum, strong trend, bullish range position. Highest conviction setup.",
  "MODERATE": "Score 5–8/16: some bullish conditions present but not enough for high-conviction trade. Wait for confirmation.",
  "NO SIGNAL": "Score < 5/16: insufficient bullish conditions. Market may be ranging or bearish. No trade recommended.",

  // Hit Rate
  "Hit Rate": "% of STRONG BUY signals (score ≥ 9/16) that achieved a +2% price gain within 24 hours of the signal. Based on historical signal outcomes stored in the database.",

  // Trade Setup
  "R/R": "Risk/Reward ratio: how much you stand to gain vs lose. 2.0 means target is twice the distance from entry to stop. Above 1.5 is generally acceptable.",
  "Entry": "Suggested entry price based on current market structure and EMA positioning.",
  "Stop": "Stop-loss level: 1 ATR below entry for longs. Defines your maximum risk on the trade.",
  "Target": "Price target: 2× the stop distance above entry (2:1 R/R minimum). Based on nearby resistance and Bollinger Band.",
};

interface MetricTooltipProps {
  children: React.ReactNode;
  tip?: string;   // explicit tip text
  id?: string;    // key to look up in METRIC_TIPS
  className?: string;
}

export function MetricTooltip({ children, tip, id, className = "" }: MetricTooltipProps) {
  const [show, setShow] = useState(false);
  const [pos, setPos]   = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const ref = useRef<HTMLSpanElement>(null);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const tooltipText = tip ?? (id ? METRIC_TIPS[id] : undefined);
  if (!tooltipText) return <span className={className}>{children}</span>;

  const handleMouseEnter = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    if (ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setPos({
        top:  rect.top + window.scrollY - 8,
        left: rect.left + rect.width / 2,
      });
    }
    setShow(true);
  };

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => setShow(false), 100);
  };

  return (
    <>
      <span
        ref={ref}
        onMouseEnter={handleMouseEnter}
        onMouseLeave={handleMouseLeave}
        className={`cursor-help border-b border-dashed border-text-muted/40 hover:border-purple/60 transition-colors ${className}`}
      >
        {children}
      </span>
      {show && (
        <div
          className="fixed z-[9999] pointer-events-none"
          style={{ top: pos.top, left: pos.left, transform: "translate(-50%, -100%)" }}
          onMouseEnter={() => { if (timeoutRef.current) clearTimeout(timeoutRef.current); setShow(true); }}
          onMouseLeave={() => setShow(false)}
        >
          <div className="max-w-[260px] mb-2 px-3 py-2 rounded-lg bg-[#1e293b] border border-border/60 shadow-xl">
            <p className="text-[11px] text-text-muted leading-relaxed pointer-events-none">{tooltipText}</p>
          </div>
          {/* Arrow */}
          <div className="w-0 h-0 mx-auto"
            style={{
              borderLeft: "6px solid transparent",
              borderRight: "6px solid transparent",
              borderTop: "6px solid #1e293b",
              width: 0,
              height: 0,
            }}
          />
        </div>
      )}
    </>
  );
}
