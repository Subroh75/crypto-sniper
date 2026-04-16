// API configuration — calls live Render backend
const API_BASE = import.meta.env.VITE_API_BASE ?? "https://crypto-sniper-api.onrender.com";

export interface AnalyseRequest {
  symbol: string;
  interval: string;
}

export interface ScoreComponent {
  volume_score: number;
  price_score: number;
  range_score: number;
  trend_score: number;
}

export interface MarketStructure {
  current_price: number;
  prev_close: number;
  atr: number;
  ema20: number;
  ema50: number;
  adx: number;
  relative_volume: number;
  range_position: number;
  atr_move: number;
}

export interface DebateAgent {
  role: string;
  view: string;
  argument: string;
}

export interface AnalyseResponse {
  symbol: string;
  interval: string;
  timestamp: string;
  signal: string;        // "STRONG BUY" | "MODERATE" | "NO SIGNAL"
  total_score: number;
  max_score: number;
  score_components: ScoreComponent;
  market_structure: MarketStructure;
  debate: DebateAgent[];
  error?: string;
}

export interface KronosCandle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface KronosResponse {
  symbol: string;
  interval: string;
  available: boolean;
  direction?: string;       // "UP" | "DOWN"
  predicted_change?: number;
  peak_price?: number;
  trough_price?: number;
  bull_pct?: number;        // % of predicted candles that are bullish
  candles?: number;         // number of forecast candles
  confidence?: number;      // 0–100 composite: range tightness + directional consensus
  forecast?: KronosCandle[];
  error?: string;
}

export async function analyse(req: AnalyseRequest): Promise<AnalyseResponse> {
  const res = await fetch(`${API_BASE}/analyse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

export async function kronos(req: AnalyseRequest): Promise<KronosResponse> {
  const res = await fetch(`${API_BASE}/kronos`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}
