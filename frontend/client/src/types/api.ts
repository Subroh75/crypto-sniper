// ─── API Types for Crypto Sniper V2 ─────────────────────────────────────────
// Matches backend api.py response shapes exactly

export interface AnalyseRequest {
  symbol:   string;
  interval: string; // "1m"|"5m"|"15m"|"30m"|"1H"|"4H"|"1D"
}

// ── Signal ────────────────────────────────────────────────────────────────────
export interface SignalOutput {
  label:     string;  // "STRONG BUY" | "MODERATE" | "NO SIGNAL"
  total:     number;
  max:       number;
  direction: string;  // "LONG" | "SHORT" | "NEUTRAL"
}

export interface Component {
  score:  number;
  max:    number;
  label:  string;
  detail: string;
}

export interface SignalComponents {
  V: Component;
  P: Component;
  R: Component;
  T: Component;
  S: Component;
}

// ── Market Structure ──────────────────────────────────────────────────────────
export interface MarketStructure {
  close:    number;
  ema20:    number;
  ema50:    number;
  ema200:   number;
  vwap:     number;
  bb_upper: number;
  bb_lower: number;
}

// ── Timing ────────────────────────────────────────────────────────────────────
export interface TimingQuality {
  rsi:        number;
  adx:        number;
  atr:        number;
  rel_volume: number;
}

// ── Quote ─────────────────────────────────────────────────────────────────────
export interface Quote {
  price:      number;
  change_24h: number;
  volume_24h: number;
  high_24h:   number;
  low_24h:    number;
}

// ── Trade Setup ───────────────────────────────────────────────────────────────
export interface TradeSetup {
  direction:     string;
  entry:         number | null;
  stop:          number | null;
  target:        number | null;
  rr_ratio:      number | null;
  atr:           number;
  stop_dist_pct: number | null;
}

// ── Conviction ────────────────────────────────────────────────────────────────
export interface Conviction {
  bull_pct:     number;
  bear_pct:     number;
  bull_signals: string[];
  bear_signals: string[];
}

// ── Key Level ─────────────────────────────────────────────────────────────────
export interface KeyLevel {
  label:    string;
  price:    number;
  kind:     "resistance" | "dynamic" | "current" | "support" | "stop" | "target";
  dist_pct: number;
}

// ── OHLCV ─────────────────────────────────────────────────────────────────────
export type OHLCVBar = [number, number, number, number, number]; // [ts, o, h, l, c]

// ── Full Analyse Response ─────────────────────────────────────────────────────
export interface AnalyseResponse {
  symbol:     string;
  interval:   string;
  timestamp:  number;
  latency_ms: number;
  signal:     SignalOutput;
  components: SignalComponents;
  structure:  MarketStructure;
  timing:     TimingQuality;
  quote:      Quote;
  trade_setup: TradeSetup;
  conviction: Conviction;
  key_levels:  KeyLevel[];
  ohlcv:       OHLCVBar[];
  fear_greed?: { value: number; label: string } | null;
  cp_news?:    unknown;
  error?:      string;
}

// ── Kronos Forecast ───────────────────────────────────────────────────────────
export interface KronosCandle {
  h:     number;
  open:  number;
  high:  number;
  low:   number;
  close: number;
}

export interface KronosForecast {
  direction:         string;  // "Rising" | "Falling" | "Sideways"
  expected_move_pct: number;
  target_price:      number;
  high_24h:          number;
  low_24h:           number;
  momentum:          string;
  green_candle_pct:  number;
  trade_quality:     string;
  bull_case:         string;
  bear_case:         string;
  bull_conviction:   string;
  bear_conviction:   string;
  predicted_ohlcv:   KronosCandle[];
}

export interface Agent {
  key:     string;
  name:    string;
  icon:    string;
  text:    string;
  verdict: string;
}

export interface KronosResponse {
  symbol:    string;
  timestamp: number;
  forecast:  KronosForecast;
  agents:    Agent[];
  error?:    string;
}

// ── Deep Research ─────────────────────────────────────────────────────────────
export interface Finding {
  text: string;
  type: "bull" | "bear" | "neutral";
}

export interface ResearchSections {
  market_context:      string;
  narrative_sentiment: string;
  risk_factors:        string;
  outlook_30d:         string;
}

export interface ResearchReport {
  verdict_headline: string;
  confidence:       string;
  consensus:        string;
  sources_count:    number;
  findings:         Finding[];
  sections:         ResearchSections;
  sources:          string[];
  model:            string;
  generation_time_s: number;
}

export interface DeepResearchResponse {
  symbol:  string;
  depth:   string;
  report:  ResearchReport;
  error?:  string;
}

// ── Market Overview ───────────────────────────────────────────────────────────
export interface MarketOverview {
  total_market_cap_usd:  number;
  market_cap_change_24h: number;
  btc_dominance:         number;
  active_coins:          number;
  btc_mempool_fees:      number;
  btc_halfhour_fee:      number;
  timestamp:             number;
}

// ── Trending Coin ─────────────────────────────────────────────────────────────
export interface TrendingCoin {
  rank:       number;
  symbol:     string;
  name:       string;
  price:      number;
  change_24h: number;
}

// ── News Article ──────────────────────────────────────────────────────────────
export interface NewsArticle {
  title:     string;
  source:    string;
  url:       string;
  published: string;
  sentiment: "bullish" | "bearish" | "neutral";
}

// ── Macro Data ────────────────────────────────────────────────────────────────
export interface MacroData {
  fed_rate:  number | null;
  us_cpi:    number | null;
  us_gdp:    number | null;
  dxy:       number | null;
  gold:      number | null;
  timestamp: number;
}

// ── Watchlist Score ───────────────────────────────────────────────────────────
export interface WatchlistScore {
  symbol:     string;
  price:      number;
  change_24h: number;
  score:      number;
  signal:     "BUY" | "HOLD" | "WATCH";
}

// ── Health ────────────────────────────────────────────────────────────────────
export interface HealthStatus {
  status:     string;
  version:    string;
  latency_ms: number;
  sources:    Record<string, string>;
}
