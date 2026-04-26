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

// Stacked bar candlestick approach:
// s1 = invisible base at low price (positions stack)
// s2 = lower wick (low -> body bottom)
// s3 = candle body (body bottom -> body top)
// s4 = upper wick (body top -> high)
function prepareData(ohlcv: OHLCVBar[]) {
  return ohlcv.map(([ts, o, h, l, c]) => {
    const bLow  = Math.min(o, c);
    const bHigh = Math.max(o, c);
    return {
      ts, open: o, high: h, low: l, close: c, isGreen: c >= o,
      s1: l,
      s2: bLow - l,
      s3: Math.max(bHigh - bLow, (h - l) * 0.005),
      s4: h - bHigh,
      ema20: 0, ema50: 0, bbU: 0, bbL: 0, vwap: 0,
    };
  });
}

function BodyBar(props: any) {
  const { x, y, width, height, payload } = props;
  if (!payload || height < 0.5) return null;
  const col = payload.isGreen ? "#22c55e" : "#ef4444";
  return <rect x={x + 1} y={y} width={Math.max(width - 2, 2)} height={Math.max(height, 1)} fill={col} fillOpacity={0.9} />;
}

function WickBar(props: any) {
  const { x, y, width, height } = props;
  if (height < 0.5) return null;
  const { payload } = props;
  const col = payload?.isGreen ? "#22c55e" : "#ef4444";
  return <line x1={x + width / 2} y1={y} x2={x + width / 2} y2={y + height} stroke={col} strokeWidth={1} />;
}

const TF = ["1m","5m","15m","30m","1H","4H","1D"];

export function PriceChart({ ohlcv, structure, interval, symbol, onTfChange }: Props) {
  if (!ohlcv || ohlcv.length < 2) {
    return <div className="flex items-center justify-center h-48 text-text-muted text-sm">No data</div>;
  }

  const data = prepareData(ohlcv as any);

  if (structure) {
    data.forEach(d => {
      d.ema20 = structure.ema20 ?? 0;
      d.ema50 = structure.ema50 ?? 0;
      d.bbU   = structure.bb_upper ?? 0;
      d.bbL   = structure.bb_lower ?? 0;
      d.vwap  = structure.vwap ?? 0;
    });
  }

  const allP = data.flatMap(d => [d.open, d.high, d.low, d.close]);
  const pMin = Math.min(...allP);
  const pMax = Math.max(...allP);
  const pad  = (pMax - pMin) * 0.08 || pMin * 0.01;

  const inds = [
    { key: "ema20", color: "#22c55e", label: "EMA 20" },
    { key: "ema50", color: "#f59e0b", label: "EMA 50" },
    { key: "vwap",  color: "#f97316", label: "VWAP"   },
    { key: "bbU",   color: "#6366f1", label: "BB+"    },
    { key: "bbL",   color: "#6366f1", label: "BB-"    },
  ].filter(i => data.some(d => (d as any)[i.key] > 0));

  const lastClose = data[data.length - 1]?.close ?? 0;

  return (
    <div className="w-full">
      <div className="flex items-center gap-1 mb-2 px-1">
        {TF.map(tf => (
          <button key={tf} onClick={() => onTfChange(tf)}
            className={`text-[11px] font-mono px-2 py-0.5 rounded ${interval===tf?"text-violet bg-violet/10 font-bold":"text-text-muted"}`}>
            {tf}
          </button>
        ))}
      </div>
      {inds.length > 0 && (
        <div className="flex gap-4 px-2 mb-1">
          {inds.map(i => (
            <div key={i.key} className="flex items-center gap-1">
              <div className="w-4 h-[2px]" style={{ background: i.color }} />
              <span className="text-[10px] font-mono text-text-muted">{i.label}: {fmtPrice((data[data.length-1] as any)[i.key])}</span>
            </div>
          ))}
        </div>
      )}
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={data} margin={{ top:4, right:56, left:0, bottom:4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
          <XAxis dataKey="ts"
            tickFormatter={v => {
              const d = new Date(v);
              return d.getHours()===0
                ? d.toLocaleDateString("en-GB",{day:"2-digit",month:"2-digit"})
                : d.toLocaleTimeString("en-GB",{hour:"2-digit",minute:"2-digit"});
            }}
            tick={{ fontSize:9, fill:"#475569" }} tickLine={false} axisLine={false} minTickGap={40}
          />
          <YAxis
            domain={[pMin - pad, pMax + pad]}
            tickFormatter={v => fmtPrice(v)}
            tick={{ fontSize:9, fill:"#475569" }} tickLine={false} axisLine={false}
            width={72} orientation="right"
          />
          <Tooltip
            contentStyle={{ background:"#0f172a", border:"1px solid #1e293b", borderRadius:8, fontSize:11 }}
            formatter={(v: any, n: string) => [fmtPrice(v), n]}
            labelFormatter={ts => new Date(ts).toLocaleString()}
          />
          <Bar dataKey="s1" stackId="c" fill="transparent" stroke="none" isAnimationActive={false} />
          <Bar dataKey="s2" stackId="c" fill="transparent" stroke="none" isAnimationActive={false}
            shape={(props: any) => <WickBar {...props} />} />
          <Bar dataKey="s3" stackId="c" fill="transparent" stroke="none" isAnimationActive={false}
            shape={(props: any) => <BodyBar {...props} />} />
          <Bar dataKey="s4" stackId="c" fill="transparent" stroke="none" isAnimationActive={false}
            shape={(props: any) => <WickBar {...props} />} />
          {inds.map(i => (
            <Line key={i.key} type="monotone" dataKey={i.key}
              stroke={i.color} strokeWidth={1} dot={false} isAnimationActive={false} />
          ))}
          {lastClose > 0 && (
            <ReferenceLine y={lastClose} stroke="#7c3aed" strokeDasharray="4 4" strokeWidth={1}
              label={{ value: fmtPrice(lastClose), position:"right", fontSize:10, fill:"#7c3aed" }} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
