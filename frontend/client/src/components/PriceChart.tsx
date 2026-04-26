// PriceChart.tsx
import {
  ComposedChart, XAxis, YAxis, CartesianGrid, Tooltip,
  Line, Bar, ResponsiveContainer, ReferenceLine,
} from "recharts";
import type { OHLCVBar, MarketStructure } from "@/types/api";
import { fmtPrice } from "@/lib/api";

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

function Candle(props: any) {
  const { x, y, width, background, payload } = props;
  if (!payload || !background || background.height <= 0) return null;
  const { open, high, low, close, isGreen, pMin, pMax } = payload;
  const pad  = (pMax - pMin) * 0.08 || pMin * 0.01;
  const dMin = pMin - pad, dMax = pMax + pad, range = dMax - dMin || 1;
  const py   = (p: number) => background.y + background.height - ((p - dMin) / range) * background.height;
  const yH = py(high), yL = py(low), yO = py(open), yC = py(close);
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
  if (!ohlcv || ohlcv.length < 2) {
    return <div className="flex items-center justify-center h-48 text-text-muted text-sm">No data</div>;
  }

  const raw    = ohlcv as number[][];
  const closes = raw.map(c => c[4]);
  const allP   = raw.flatMap(([, o, h, l, c]) => [o, h, l, c]);
  const pMin   = Math.min(...allP);
  const pMax   = Math.max(...allP);
  const pad    = (pMax - pMin) * 0.08 || pMin * 0.01;

  const ema20 = calcEMA(closes, 20);
  const ema50 = calcEMA(closes, 50);
  const bb    = calcBB(closes, 20, 2);
  const vwap  = calcVWAP(raw);

  const data = raw.map(([ts, o, h, l, c], i) => ({
    ts, open: o, high: h, low: l, close: c,
    isGreen: c >= o, pMin, pMax,
    ema20: ema20[i], ema50: ema50[i],
    bbU: bb.upper[i], bbL: bb.lower[i],
    vwap: vwap[i],
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
      <div className="flex items-center gap-1 mb-2 px-1">
        {TF.map(tf => (
          <button key={tf} onClick={() => onTfChange(tf)}
            className={`text-[11px] font-mono px-2 py-0.5 rounded ${
              interval === tf ? "text-violet bg-violet/10 font-bold" : "text-text-muted"
            }`}>
            {tf}
          </button>
        ))}
      </div>
      {inds.length > 0 && (
        <div className="flex gap-3 px-2 mb-1 flex-wrap">
          {inds.map(i => (
            <div key={i.key} className="flex items-center gap-1">
              <div className="w-5 h-[1.5px]" style={{ background: i.color }} />
              <span className="text-[10px] font-mono text-text-muted">
                {i.label}: {fmtPrice(i.value ?? 0)}
              </span>
            </div>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data} margin={{ top: 4, right: 56, left: 0, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis dataKey="ts"
            tickFormatter={v => {
              const d = new Date(v);
              return d.getHours() === 0
                ? d.toLocaleDateString("en-GB", { day: "2-digit", month: "2-digit" })
                : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
            }}
            tick={{ fontSize: 9, fill: "#475569" }} tickLine={false} axisLine={false} minTickGap={40}
          />
          <YAxis
            domain={[pMin - pad, pMax + pad]}
            tickFormatter={v => fmtPrice(v)}
            tick={{ fontSize: 9, fill: "#475569" }} tickLine={false} axisLine={false}
            width={72} orientation="right"
          />
          <Tooltip
            contentStyle={{ background: "#0f172a", border: "1px solid #1e293b", borderRadius: 8, fontSize: 11 }}
            formatter={(v: any, n: string) => v != null ? [fmtPrice(v), n] : [null, n]}
            labelFormatter={ts => new Date(ts as number).toLocaleString()}
          />
          <Bar dataKey="close" fill="transparent" stroke="none"
            isAnimationActive={false}
            background={{ fill: "transparent" }}
            shape={(props: any) => <Candle {...props} />}
          />
          <Line type="monotone" dataKey="ema20" stroke="#22c55e"
            strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line type="monotone" dataKey="ema50" stroke="#f59e0b"
            strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line type="monotone" dataKey="vwap" stroke="#f97316"
            strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
          <Line type="monotone" dataKey="bbU" stroke="#818cf8"
            strokeWidth={1} dot={false} isAnimationActive={false} strokeDasharray="3 3" connectNulls={false} />
          <Line type="monotone" dataKey="bbL" stroke="#818cf8"
            strokeWidth={1} dot={false} isAnimationActive={false} strokeDasharray="3 3" connectNulls={false} />
          {lastClose > 0 && (
            <ReferenceLine y={lastClose} stroke="#7c3aed" strokeDasharray="4 4" strokeWidth={1}
              label={{ value: fmtPrice(lastClose), position: "right", fontSize: 10, fill: "#7c3aed" }}
            />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
