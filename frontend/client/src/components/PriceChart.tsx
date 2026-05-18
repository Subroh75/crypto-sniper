// PriceChart.tsx — lightweight-charts v5: candlestick + EMA 20/50/200 only
import { useEffect, useRef, useCallback } from "react";
import {
  createChart, CandlestickSeries, LineSeries,
  ColorType, CrosshairMode,
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
  const result: (number | null)[] = new Array(closes.length).fill(null);
  if (closes.length < period) return result;
  const k = 2 / (period + 1);
  let ema = closes.slice(0, period).reduce((a, b) => a + b, 0) / period;
  result[period - 1] = ema;
  for (let i = period; i < closes.length; i++) {
    ema = closes[i] * k + ema * (1 - k);
    result[i] = ema;
  }
  return result;
}

const TF = ["1m","5m","15m","30m","1H","4H","1D"];

export function PriceChart({ ohlcv, structure, interval, symbol, onTfChange }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<ReturnType<typeof createChart> | null>(null);
  const isMobile     = useMobile();

  const buildChart = useCallback(() => {
    if (!containerRef.current) return;
    if (!ohlcv || ohlcv.length < 2) return;

    // Destroy previous instance
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const raw    = ohlcv as number[][];
    const closes = raw.map(c => c[4]);
    const ema20  = calcEMA(closes, 20);
    const ema50  = calcEMA(closes, 50);
    const ema200 = calcEMA(closes, 200);

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
        vertLines:  { color: "#0f172a", style: 0 },
        horzLines:  { color: "#1e293b", style: 2 },
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
        borderColor:       "#1e293b",
        timeVisible:       true,
        secondsVisible:    false,
        rightOffset:       4,
        barSpacing:        isMobile ? 5 : 7,
        fixLeftEdge:       true,
        fixRightEdge:      true,
      },
      handleScroll:   { mouseWheel: true, pressedMouseMove: true, horzTouchDrag: true },
      handleScale:    { axisPressedMouseMove: true, mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    // ── Candlesticks ──────────────────────────────────────────────────────
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor:        "#22c55e",
      downColor:      "#ef4444",
      borderUpColor:  "#22c55e",
      borderDownColor:"#ef4444",
      wickUpColor:    "#22c55e",
      wickDownColor:  "#ef4444",
      priceLineVisible: false,
      lastValueVisible: true,
    });

    const candleData = raw.map(([ts, o, h, l, c]) => ({
      time: Math.floor(ts / 1000) as UTCTimestamp,
      open: o, high: h, low: l, close: c,
    }));
    candleSeries.setData(candleData);

    // ── EMA 20 ────────────────────────────────────────────────────────────
    const ema20Series = chart.addSeries(LineSeries, {
      color:            "#22c55e",
      lineWidth:        1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    ema20Series.setData(
      raw
        .map(([ts], i) => ({ time: Math.floor(ts / 1000) as UTCTimestamp, value: ema20[i] }))
        .filter(d => d.value != null) as { time: UTCTimestamp; value: number }[]
    );

    // ── EMA 50 ────────────────────────────────────────────────────────────
    const ema50Series = chart.addSeries(LineSeries, {
      color:            "#f59e0b",
      lineWidth:        1,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
    ema50Series.setData(
      raw
        .map(([ts], i) => ({ time: Math.floor(ts / 1000) as UTCTimestamp, value: ema50[i] }))
        .filter(d => d.value != null) as { time: UTCTimestamp; value: number }[]
    );

    // ── EMA 200 ───────────────────────────────────────────────────────────
    // Use client-computed if enough bars, else fall back to backend structure value
    const hasEma200 = ema200.some(v => v != null);
    const ema200Series = chart.addSeries(LineSeries, {
      color:            "#ef4444",
      lineWidth:        1,
      lineStyle:        hasEma200 ? 0 : 2,   // dashed when from backend
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });

    if (hasEma200) {
      ema200Series.setData(
        raw
          .map(([ts], i) => ({ time: Math.floor(ts / 1000) as UTCTimestamp, value: ema200[i] }))
          .filter(d => d.value != null) as { time: UTCTimestamp; value: number }[]
      );
    } else if (structure?.ema200 && structure.ema200 > 0) {
      // Fallback: flat line at backend value across all bars
      ema200Series.setData(
        raw.map(([ts]) => ({ time: Math.floor(ts / 1000) as UTCTimestamp, value: structure.ema200! }))
      );
    }

    // Fit all data on mount
    chart.timeScale().fitContent();

    // Resize observer
    const ro = new ResizeObserver(entries => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    ro.observe(containerRef.current);
    return () => ro.disconnect();
  }, [ohlcv, structure, isMobile]);

  useEffect(() => {
    const cleanup = buildChart();
    return () => {
      cleanup?.();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [buildChart]);

  // Symbol or interval change — just rebuild
  useEffect(() => {}, [symbol, interval]);

  if (!ohlcv || ohlcv.length < 2) {
    return (
      <div className="flex items-center justify-center h-48 text-text-muted text-sm">
        No chart data
      </div>
    );
  }

  const raw    = ohlcv as number[][];
  const closes = raw.map(c => c[4]);
  const ema20v = calcEMA(closes, 20);
  const ema50v = calcEMA(closes, 50);
  const ema200v= calcEMA(closes, 200);
  const last   = closes.length - 1;

  const indicators = [
    { label: "EMA 20",  color: "#22c55e", value: ema20v[last]  },
    { label: "EMA 50",  color: "#f59e0b", value: ema50v[last]  },
    { label: "EMA 200", color: "#ef4444", value: ema200v[last] ?? structure?.ema200 },
  ].filter(i => i.value != null && (i.value as number) > 0);

  return (
    <div className="w-full select-none">
      {/* Timeframe pills */}
      <div className="flex items-center gap-1 mb-2 px-1">
        {TF.map(tf => (
          <button
            key={tf}
            onClick={() => onTfChange(tf)}
            className={`text-[11px] font-mono px-2 py-0.5 rounded transition-all ${
              interval === tf
                ? "text-purple bg-purple/10 font-bold border border-purple/30"
                : "text-text-muted hover:text-text"
            }`}
          >
            {tf}
          </button>
        ))}
      </div>

      {/* EMA legend */}
      {indicators.length > 0 && (
        <div className="flex gap-4 px-1 mb-2 flex-wrap">
          {indicators.map(ind => (
            <div key={ind.label} className="flex items-center gap-1.5">
              <div className="w-5 h-[2px] rounded-full" style={{ background: ind.color }} />
              <span className="text-[10px] font-mono text-text-muted">
                {ind.label}{" "}
                <span className="text-text font-semibold">
                  {fmtPrice(ind.value as number)}
                </span>
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
