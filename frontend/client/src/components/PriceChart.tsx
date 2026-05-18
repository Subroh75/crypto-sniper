// PriceChart.tsx — lightweight-charts v5: candlestick + EMA 20/50/200 only
import { useEffect, useRef, useCallback } from "react";
import {
  createChart, CandlestickSeries, LineSeries,
  ColorType, CrosshairMode, LineStyle,
} from "lightweight-charts";
import type { UTCTimestamp } from "lightweight-charts";
import type { OHLCVBar, MarketStructure } from "@/types/api";
import { fmtPrice } from "@/lib/api";
import { useMobile } from "@/hooks/useMobile";

interface Props {
  ohlcv:      OHLCVBar[];
  structure:  MarketStructure | null;
  interval:   string;
  symbol:     string;
  onTfChange: (tf: string) => void;
}

function calcEMA(closes: number[], period: number): (number | null)[] {
  const out: (number | null)[] = new Array(closes.length).fill(null);
  if (closes.length < period) return out;
  const k = 2 / (period + 1);
  let ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  out[period - 1] = ema;
  for (let i = period; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k);
    out[i] = ema;
  }
  return out;
}

// Build a series data array — skip leading nulls, never emit nulls mid-series
// If client EMA couldn't compute (all null), fall back to backend flat value
function buildLineData(
  raw:        number[][],
  clientVals: (number | null)[],
  fallback?:  number
): { time: UTCTimestamp; value: number }[] {
  const hasClient = clientVals.some(v => v != null);

  if (hasClient) {
    // Only emit from first non-null point onward (no leading gap)
    const firstIdx = clientVals.findIndex(v => v != null);
    return clientVals
      .slice(firstIdx)
      .map((v, i) => ({
        time:  Math.floor(raw[firstIdx + i][0] / 1000) as UTCTimestamp,
        value: v as number,
      }))
      .filter(d => d.value != null && isFinite(d.value));
  }

  if (fallback && fallback > 0) {
    // Backend-calculated value — draw as flat dashed line across all bars
    return raw.map(([ts]) => ({
      time:  Math.floor(ts / 1000) as UTCTimestamp,
      value: fallback,
    }));
  }

  return [];
}

const TF = ["1m","5m","15m","30m","1H","4H","1D"];

export function PriceChart({ ohlcv, structure, interval, symbol, onTfChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<ReturnType<typeof createChart> | null>(null);
  const isMobile     = useMobile();

  const buildChart = useCallback(() => {
    if (!containerRef.current || !ohlcv || ohlcv.length < 2) return;

    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const raw    = ohlcv as number[][];
    const closes = raw.map(c => c[4]);

    const ema20vals  = calcEMA(closes, 20);
    const ema50vals  = calcEMA(closes, 50);
    const ema200vals = calcEMA(closes, 200);

    // Determine whether each EMA was fully client-computed
    const ema50fromBackend  = ema50vals.every(v => v == null);
    const ema200fromBackend = ema200vals.every(v => v == null);

    const ema20data  = buildLineData(raw, ema20vals);
    const ema50data  = buildLineData(raw, ema50vals,  structure?.ema50  ?? undefined);
    const ema200data = buildLineData(raw, ema200vals, structure?.ema200 ?? undefined);

    const height = isMobile ? 220 : 270;

    const chart = createChart(containerRef.current, {
      width:  containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor:  "#475569",
        fontSize:   10,
        fontFamily: "'Helvetica Neue', Helvetica, Arial, sans-serif",
      },
      grid: {
        vertLines: { color: "#0f172a" },
        horzLines: { color: "#1e293b", style: LineStyle.Dashed },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: "#334155", labelBackgroundColor: "#1e293b" },
        horzLine: { color: "#334155", labelBackgroundColor: "#1e293b" },
      },
      rightPriceScale: {
        borderColor:  "#1e293b",
        textColor:    "#475569",
        scaleMargins: { top: 0.08, bottom: 0.05 },
      },
      timeScale: {
        borderColor:    "#1e293b",
        timeVisible:    true,
        secondsVisible: false,
        rightOffset:    4,
        barSpacing:     isMobile ? 5 : 7,
        fixLeftEdge:    true,
        fixRightEdge:   true,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
      handleScale:  { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    // ── Candlesticks ──────────────────────────────────────────────────────
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:          "#22c55e",
      downColor:        "#ef4444",
      borderUpColor:    "#22c55e",
      borderDownColor:  "#ef4444",
      wickUpColor:      "#22c55e",
      wickDownColor:    "#ef4444",
      priceLineVisible: false,
      lastValueVisible: true,
    });
    candleSeries.setData(raw.map(([ts, o, h, l, c]) => ({
      time: Math.floor(ts / 1000) as UTCTimestamp,
      open: o, high: h, low: l, close: c,
    })));

    // ── EMA 20 ────────────────────────────────────────────────────────────
    if (ema20data.length > 1) {
      const s = chart.addSeries(LineSeries, {
        color: "#22c55e", lineWidth: 2,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(ema20data);
    }

    // ── EMA 50 ────────────────────────────────────────────────────────────
    if (ema50data.length > 1) {
      const s = chart.addSeries(LineSeries, {
        color:     "#f59e0b",
        lineWidth: 2,
        lineStyle: ema50fromBackend ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(ema50data);
    }

    // ── EMA 200 ───────────────────────────────────────────────────────────
    if (ema200data.length > 1) {
      const s = chart.addSeries(LineSeries, {
        color:     "#ef4444",
        lineWidth: 2,
        lineStyle: ema200fromBackend ? LineStyle.Dashed : LineStyle.Solid,
        priceLineVisible: false, lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(ema200data);
    }

    chart.timeScale().fitContent();

    // Resize observer
    const ro = new ResizeObserver(entries => {
      for (const e of entries) chart.applyOptions({ width: e.contentRect.width });
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [ohlcv, structure, isMobile]);

  useEffect(() => {
    const cleanup = buildChart();
    return () => {
      cleanup?.();
      if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
    };
  }, [buildChart]);

  if (!ohlcv || ohlcv.length < 2) {
    return (
      <div className="flex items-center justify-center h-48 text-text-muted text-sm">
        No chart data
      </div>
    );
  }

  // Legend values — prefer client-computed last value, fall back to structure
  const raw    = ohlcv as number[][];
  const closes = raw.map(c => c[4]);
  const last   = closes.length - 1;
  const e20    = calcEMA(closes, 20);
  const e50    = calcEMA(closes, 50);
  const e200   = calcEMA(closes, 200);

  const indicators = [
    { label: "MA 20",  color: "#22c55e", value: e20[last]  ?? null },
    { label: "MA 50",  color: "#f59e0b", value: e50[last]  ?? structure?.ema50  ?? null },
    { label: "MA 200", color: "#ef4444", value: e200[last] ?? structure?.ema200 ?? null },
  ].filter(i => i.value != null && (i.value as number) > 0);

  return (
    <div className="w-full select-none">
      {/* Timeframe pills */}
      <div className="flex items-center gap-1 mb-2 px-1">
        {TF.map(tf => (
          <button key={tf} onClick={() => onTfChange(tf)}
            className={`text-[11px] font-mono px-2 py-0.5 rounded transition-all ${
              interval === tf
                ? "text-purple bg-purple/10 font-bold border border-purple/30"
                : "text-text-muted hover:text-text"
            }`}>
            {tf}
          </button>
        ))}
      </div>

      {/* Legend */}
      {indicators.length > 0 && (
        <div className="flex gap-4 px-1 mb-2 flex-wrap">
          {indicators.map(ind => (
            <div key={ind.label} className="flex items-center gap-1.5">
              <div className="w-5 h-[2px] rounded-full" style={{ background: ind.color }} />
              <span className="text-[10px] font-mono text-text-muted">
                {ind.label}{" "}
                <span className="text-text font-semibold">{fmtPrice(ind.value as number)}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Chart canvas */}
      <div ref={containerRef} className="w-full rounded overflow-hidden" />
    </div>
  );
}
