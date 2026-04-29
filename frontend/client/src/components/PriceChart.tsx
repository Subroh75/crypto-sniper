// PriceChart.tsx
import {
  ComposedChart, XAxis, YAxis, CartesianGrid, Tooltip,
  Line, Bar, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
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

function calcBB(closes: number[], period = 20, mult = 2) {
  const upper: (number | null)[] = [], lower: (number | null)[] = [];
  for (let i = 0; i < closes.length; i++) {
    if (i < period - 1) { upper.push(null); lower.push(null); continue; }
    const slice = closes.slice(i - period + 1, i + 1);
    const mean  = slice.reduce((a, b) => a + b, 0) / period;
    const sd    = Math.sqrt(slice.reduce((a, b) => a + (b - mean) ** 2, 0) / period);
    upper.push(mean + sd * mult);
    lower.push(mean - sd * mult);
  }
  return { upper, lower };
}

function calcVWAP(raw: number[][]): (number | null)[] {
  let cumPV = 0, cumV = 0;
  return raw.map(([, o, h, l, c]) => {
    const typical = (h + l + c) / 3;
    const vol     = Math.abs(c - o) + 0.001;
    cumPV += typical * vol;
    cumV  += vol;
    return cumPV / cumV;
  });
}

// Normalise body size as a proxy volume for visual volume bars
function calcBodyVolume(raw: number[][]): number[] {
  const sizes = raw.map(([, o, , , c]) => Math.abs(c - o));
  const maxSize = Math.max(...sizes, 0.0001);
  return sizes.map(s => (s / maxSize) * 100); // 0–100 percentage
}

function Candle(props: any) {
  const { x, width, background, payload } = props;
  if (!payload || !background || background.height <= 0) return null;
  // Use the shared domain values pre-calculated in PriceChart (same as YAxis)
  const { open, high, low, close, isGreen, domMin, domRange } = payload;
  const py  = (p: number) => background.y + background.height - ((p - domMin) / domRange) * background.height;
  const yH  = py(high), yL = py(low), yO = py(open), yC = py(close);
  const top = Math.min(yO, yC), bot = Math.max(yO, yC);
  const bH  = Math.max(bot - top, 1.5), bW = Math.max(width - 2, 2);
  const cx  = x + width / 2;
  const col = isGreen ? "#22c55e" : "#ef4444";
  return (
    <g>
      <line x1={cx} y1={yH}  x2={cx} y2={top} stroke={col} strokeWidth={1} />
      <line x1={cx} y1={bot} x2={cx} y2={yL}  stroke={col} strokeWidth={1} />
      <rect x={x + 1} y={top} width={bW} height={bH} fill={col} fillOpacity={0.9} />
    </g>
  );
}

const TF = ["1m","5m","15m","30m","1H","4H","1D"];

export function PriceChart({ ohlcv, structure, interval, symbol, onTfChange }: Props) {
  const isMobile = useMobile();
  if (!ohlcv || ohlcv.length < 2) {
    return <div className="flex items-center justify-center h-48 text-text-muted text-sm">No data</div>;
  }

  const raw    = ohlcv as number[][];
  const closes = raw.map(c => c[4]);
  const allP   = raw.flatMap(([, o, h, l, c]) => [o, h, l, c]);
  const pMin   = Math.min(...allP);
  const pMax   = Math.max(...allP);
  // Price-aware padding: minimum 1.5% of price so low-price coins
  // (DOGE $0.10, XRP $0.50) produce visible candles
  const pad    = Math.max((pMax - pMin) * 0.08, pMin * 0.015);
  const domMin  = pMin - pad;
  const domMax  = pMax + pad;
  const domRange = domMax - domMin || pMin * 0.1 || 1;

  const ema20 = calcEMA(closes, 20);
  const ema50 = calcEMA(closes, 50);
  const bb    = calcBB(closes, 20, 2);
  const vwap  = calcVWAP(raw);

  const bodyVol = calcBodyVolume(raw);

  const data = raw.map(([ts, o, h, l, c], i) => ({
    ts, open: o, high: h, low: l, close: c,
    isGreen: c >= o,
    domMin, domRange,          // shared with Candle renderer
    ema20: ema20[i], ema50: ema50[i],
    bbU: bb.upper[i], bbL: bb.lower[i],
    vwap: vwap[i],
    vol: bodyVol[i],
  }));

  const last      = data[data.length - 1];
  const lastClose = last?.close ?? 0;

  const inds = [
    { key: "ema20", color: "#22c55e", label: "EMA 20", value: last?.ema20 },
    { key: "ema50", color: "#f59e0b", label: "EMA 50", value: last?.ema50 },
    { key: "vwap",  color: "#f97316", label: "VWAP",   value: last?.vwap  },
    { key: "bbU",   color: "#818cf8", label: "BB+",    value: last?.bbU   },
    { key: "bbL",   color: "#818cf8", label: "BB-",    value: last?.bbL   },
  ].filter(i => i.value != null && i.value > 0);

  return (
    <div className="w-full">
      {/* Timeframe selector */}
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
      {/* Indicator legend */}
      {inds.length > 0 && (
        <div className="flex gap-3 px-2 mb-2 flex-wrap">
          {inds.map(i => (
            <div key={i.key} className="flex items-center gap-1.5">
              <div className="w-6 h-[2px] rounded-full" style={{ background: i.color }} />
              <span className="text-[10px] font-mono text-text-muted">
                {i.label} <span className="text-text font-medium">{fmtPrice(i.value ?? 0)}</span>
              </span>
            </div>
          ))}
        </div>
      )}
      {/* Main candle chart */}
      <ResponsiveContainer width="100%" height={isMobile ? 200 : 230}>
        <ComposedChart data={data} margin={{ top: 4, right: isMobile ? 4 : 64, left: 0, bottom: 2 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="#1e293b" vertical={false} />
          <XAxis dataKey="ts"
            tickFormatter={v => {
              const d = new Date(v);
              return d.getHours() === 0
                ? d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit" })
                : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
            }}
            tick={{ fontSize: 9, fill: "#475569" }} tickLine={false} axisLine={false} minTickGap={48}
          />
          <YAxis
            domain={[domMin, domMax]}
            tickFormatter={v => fmtPrice(v)}
            tick={{ fontSize: 9, fill: "#475569" }} tickLine={false} axisLine={false}
            width={isMobile ? 48 : 72} orientation="right"
          />
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 11, padding: "6px 10px" }}
            formatter={(v: any, n: string) => {
              if (n === "vol") return null as any;
              return v != null ? [fmtPrice(v), n.toUpperCase()] : [null, n];
            }}
            labelFormatter={ts => new Date(ts as number).toLocaleString()}
            cursor={{ stroke: "#334155", strokeWidth: 1 }}
          />
          {/* Candle bars */}
          <Bar dataKey="close" fill="transparent" stroke="none"
            isAnimationActive={false}
            background={{ fill: "transparent" }}
            shape={(props: any) => <Candle {...props} />}
          />
          {/* EMA + VWAP + BB lines */}
          <Line type="monotone" dataKey="ema20" stroke="#22c55e" name="ema20"
            strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line type="monotone" dataKey="ema50" stroke="#f59e0b" name="ema50"
            strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line type="monotone" dataKey="vwap" stroke="#f97316" name="vwap"
            strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line type="monotone" dataKey="bbU" stroke="#818cf8" name="bbU"
            strokeWidth={1} dot={false} isAnimationActive={false} strokeDasharray="3 4" connectNulls={false} />
          <Line type="monotone" dataKey="bbL" stroke="#818cf8" name="bbL"
            strokeWidth={1} dot={false} isAnimationActive={false} strokeDasharray="3 4" connectNulls={false} />
          {/* Last price line */}
          {lastClose > 0 && (
            <ReferenceLine y={lastClose} stroke="#7c3aed" strokeDasharray="4 4" strokeWidth={1}
              label={{ value: fmtPrice(lastClose), position: "insideRight", fontSize: 9, fill: "#7c3aed", offset: 4 }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
      {/* Volume bars */}
      <ResponsiveContainer width="100%" height={40}>
        <ComposedChart data={data} margin={{ top: 0, right: isMobile ? 4 : 64, left: 0, bottom: 0 }}>
          <YAxis hide domain={[0, 100]} />
          <Bar dataKey="vol" isAnimationActive={false} maxBarSize={12}>
            {data.map((d, i) => (
              <Cell key={i} fill={d.isGreen ? "#22c55e" : "#ef4444"} fillOpacity={0.35} />
            ))}
          </Bar>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
