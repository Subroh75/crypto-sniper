// ─── PriceChart.tsx — Candlestick chart with indicators ─────────────────────
// Uses Recharts ComposedChart with custom candle rendering
import {
  ComposedChart, XAxis, YAxis, CartesianGrid, Tooltip,
  Line, Bar, ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { OHLCVBar, MarketStructure } from "@/types/api";
import { fmtPrice } from "@/lib/api";

const TIMEFRAMES = ["5m", "15m", "1H", "4H", "1D"] as const;

interface Props {
  ohlcv:     OHLCVBar[];
  structure: MarketStructure | null;
  interval:  string;
  symbol:    string;
  onTfChange?: (tf: string) => void;
}

// Custom candle shape - uses Recharts yAxis.scale for pixel-accurate positioning
function CandleBar(props: any) {
  const { x, y, width, background, payload, yAxis } = props;
  if (!payload || !background || !yAxis?.scale) return null;

  const scale = yAxis.scale;
  const { open, high, low, close, isGreen } = payload;

  const yH  = scale(high);
  const yL  = scale(low);
  const yO  = scale(open);
  const yC  = scale(close);
  const top = Math.min(yO, yC);
  const bot = Math.max(yO, yC);
  const bH  = Math.max(bot - top, 1.5);
  const bW  = Math.max(width - 2, 2);
  const cx  = x + width / 2;
  const col = isGreen ? "#22c55e" : "#ef4444";

  return (
    <g>
      <line x1={cx} y1={yH} x2={cx} y2={top} stroke={col} strokeWidth={1} />
      <line x1={cx} y1={bot} x2={cx} y2={yL} stroke={col} strokeWidth={1} />
      <rect x={x + 1} y={top} width={bW} height={bH} fill={col} fillOpacity={0.9} />
    </g>
  );
}
function formatBarData(ohlcv: OHLCVBar[]) {
  return ohlcv.map(([ts, o, h, l, c]) => ({
    ts, open: o, high: h, low: l, close: c, isGreen: c >= o,
    bbU: 0, bbL: 0, vwap: 0, ema20: 0, ema50: 0,
  }));
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-surface-2 border border-border rounded-lg px-3 py-2 text-[10px] font-mono shadow-xl">
      <div className="flex gap-3">
        <div>
          <div className="text-text-muted">O</div>
          <div className="text-text">{fmtPrice(d.open)}</div>
        </div>
        <div>
          <div className="text-text-muted">H</div>
          <div className="text-teal">{fmtPrice(d.high)}</div>
        </div>
        <div>
          <div className="text-text-muted">L</div>
          <div className="text-red">{fmtPrice(d.low)}</div>
        </div>
        <div>
          <div className="text-text-muted">C</div>
          <div className={d.isUp ? "text-teal" : "text-red"}>{fmtPrice(d.close)}</div>
        </div>
      </div>
    </div>
  );
}

export function PriceChart({ ohlcv, structure, interval, symbol, onTfChange }: Props) {
  if (!ohlcv || ohlcv.length < 2) {
    return (
      <div className="card mb-3">
        <div className="card-header">
          <span className="section-num">02b</span>
          <span>PRICE CHART</span>
        </div>
        <div className="h-[260px] flex items-center justify-center text-text-muted text-sm font-mono">
          No chart data
        </div>
      </div>
    );
  }

  const prices = ohlcv.map(b => b[4]);
  const allPrices = ohlcv.flatMap(b => [b[2], b[3]]);
  const yMin = Math.min(...allPrices) * 0.998;
  const yMax = Math.max(...allPrices) * 1.002;

  const data   = formatBarData(ohlcv, yMin, yMax);
  const latest = ohlcv[ohlcv.length - 1];
  const close  = latest[4];
  const chg    = ohlcv.length > 1
    ? ((close - ohlcv[0][1]) / ohlcv[0][1]) * 100
    : 0;
  const high24h = Math.max(...ohlcv.map(b => b[2]));
  const low24h  = Math.min(...ohlcv.map(b => b[3]));

  // Build EMA20/50 overlay data
  const ema20 = structure?.ema20;
  const ema50 = structure?.ema50;
  const vwap  = structure?.vwap;
  const bbU   = structure?.bb_upper;
  const bbL   = structure?.bb_lower;

  // Inject indicator values into data (constant lines for now — real per-bar values need API upgrade)
  const chartData = data.map(d => ({
    ...d,
    ema20: ema20,
    ema50: ema50,
    vwap:  vwap,
    bbU:   bbU,
    bbL:   bbL,
  }));

  const indicators = [
    { key: "ema20", color: "#00d4aa", label: `EMA 20: ${fmtPrice(ema20)}` },
    { key: "ema50", color: "#f7c948", label: `EMA 50: ${fmtPrice(ema50)}` },
    { key: "vwap",  color: "#ff8c42", label: `VWAP: ${fmtPrice(vwap)}`, dash: "4 3" },
    { key: "bbU",   color: "#7c5cfc", label: "BB Upper", dash: "3 3" },
    { key: "bbL",   color: "#7c5cfc", label: "BB Lower", dash: "3 3" },
  ].filter(ind => !!structure?.[ind.key as keyof MarketStructure]);

  return (
    <div className="card mb-3">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/60">
        <div className="flex items-center gap-3">
          <span className="text-[15px] font-black font-mono text-text">{symbol}/USDT</span>
          <span className="text-[20px] font-mono font-bold text-text">
            {fmtPrice(close)}
          </span>
          <span className={`text-[11px] font-mono font-bold px-2 py-0.5 rounded ${
            chg >= 0
              ? "bg-teal/10 text-teal border border-teal/20"
              : "bg-red/10 text-red border border-red/20"
          }`}>
            {chg >= 0 ? "▲" : "▼"} {Math.abs(chg).toFixed(2)}%
          </span>
          <span className="text-[10px] font-mono text-text-muted hidden sm:inline">
            H: {fmtPrice(high24h)} · L: {fmtPrice(low24h)}
          </span>
        </div>
        {/* TF pills */}
        <div className="flex gap-1.5">
          {TIMEFRAMES.map(tf => (
            <button
              key={tf}
              onClick={() => onTfChange?.(tf)}
              className={`text-[10px] font-mono font-bold px-2.5 py-1 rounded-md border transition-all ${
                tf === interval || (tf === "1H" && interval === "1h")
                  ? "border-purple text-purple bg-purple/8"
                  : "border-border/60 text-text-muted hover:border-text-muted hover:text-text"
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
      </div>

      {/* Indicators legend */}
      <div className="flex items-center gap-4 px-4 py-1.5 border-b border-border/40 bg-surface/50">
        {indicators.map(ind => (
          <div key={ind.key} className="flex items-center gap-1.5">
            <div className="w-4 h-[2px] rounded" style={{ background: ind.color }} />
            <span className="text-[9px] font-mono font-bold text-text-muted">{ind.label}</span>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div className="px-1 py-2" style={{ height: 220 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 4, right: 40, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />

            <XAxis
              dataKey="ts"
              tickFormatter={(ts) => {
                const d = new Date(ts);
                return `${d.getHours().toString().padStart(2,"0")}:${d.getMinutes().toString().padStart(2,"0")}`;
              }}
              tick={{ fontSize: 9, fill: "#4a5470", fontFamily: "monospace" }}
              axisLine={false}
              tickLine={false}
              interval="preserveStartEnd"
            />

            <YAxis
              domain={([dataMin, dataMax]: number[]) => { const pad = (dataMax - dataMin) * 0.05 || dataMin * 0.01; return [dataMin - pad, dataMax + pad]; }}
              tickFormatter={(v) => fmtPrice(v).replace("$","")}
              tick={{ fontSize: 9, fill: "#4a5470", fontFamily: "monospace" }}
              axisLine={false}
              tickLine={false}
              width={55}
              orientation="right"
            />

            <Tooltip content={<CustomTooltip />} />

            {/* Current price reference line */}
            {close > 0 && (
              <ReferenceLine
                y={close}
                stroke="rgba(255,255,255,0.18)"
                strokeDasharray="4 4"
                label={{
                  value: fmtPrice(close),
                  position: "right",
                  fontSize: 9,
                  fill: "#b8c2dc",
                  fontFamily: "monospace",
                }}
              />
            )}

            {/* BB Upper/Lower */}
            {bbU && <Line dataKey="bbU" stroke="#7c5cfc" strokeWidth={1} dot={false} strokeDasharray="3 3" strokeOpacity={0.5} />}
            {bbL && <Line dataKey="bbL" stroke="#7c5cfc" strokeWidth={1} dot={false} strokeDasharray="3 3" strokeOpacity={0.5} />}

            {/* EMA/VWAP lines */}
            {vwap  && <Line dataKey="vwap" stroke="#ff8c42" strokeWidth={1.5} dot={false} strokeDasharray="4 3" strokeOpacity={0.75} />}
            {ema50 && <Line dataKey="ema50" stroke="#f7c948" strokeWidth={1.5} dot={false} strokeOpacity={0.75} />}
            {ema20 && <Line dataKey="ema20" stroke="#00d4aa" strokeWidth={1.5} dot={false} strokeOpacity={0.85} />}

            {/* Candles as bars — body */}
            <Bar
              dataKey="close"
              fill="transparent"
              stroke="none"
              isAnimationActive={false}
              shape={candleShape}
                const y1 = scale(Math.max(open, c));
                const y2 = scale(Math.min(open, c));
                const yHigh = scale(high);
                const yLow  = scale(low);
                const fill  = isUp ? "#00d4aa" : "#ff3d5a";
                const cx    = (x as number) + (width as number) / 2;
                return (
                  <g key={`candle-${(x as number)}`}>
                    <line x1={cx} y1={yHigh} x2={cx} y2={yLow} stroke={fill} strokeWidth={1} opacity={0.65} />
                    <rect
                      x={(x as number) + 1}
                      y={y1}
                      width={Math.max((width as number) - 2, 1)}
                      height={Math.max(y2 - y1, 1)}
                      fill={fill}
                      opacity={0.9}
                      rx={1}
                    />
                  </g>
                );
              }}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
