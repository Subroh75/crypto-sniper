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
  fear_greed?:  { value: number; label: string } | null;
  cp_news?:     unknown;
  derivatives?: DerivativesData;
  error?:       string;
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

// ── Derivatives (perp data) ───────────────────────────────────────────────────
export interface FundingRate {
  rate:             number;   // % e.g. 0.01
  rate_8h:          number;
  rate_annualised:  number;
  next_funding_ts:  number;
  sentiment:        "bullish" | "bearish" | "neutral";
  source:           string;
}

export interface OpenInterest {
  oi_usd:     number;
  oi_usd_fmt: string;
  change_24h: number;
  trend:      "rising" | "falling" | "flat";
  source:     string;
}

export interface LongShortRatio {
  long_pct:  number;
  short_pct: number;
  sentiment: "bullish" | "bearish" | "neutral";
  note:      string;
  source:    string;
}

export interface DerivativesData {
  funding:       FundingRate;
  open_interest: OpenInterest;
  long_short:    LongShortRatio;
  has_perp:      boolean;
}

// ── Signal History ───────────────────────────────────────────────────────────
export interface SignalHistoryRow {
  symbol:       string;
  interval:     string;
  score:        number;
  signal_label: string;
  close_price:  number;
  ts:           number;
  outcome_pct:  number | null;
}

// ── Hit Rate ─────────────────────────────────────────────────────────────────
export interface HitRateData {
  hit_rate_pct:   number | null;
  total_signals:  number;
  hits:           number;
  threshold_pct:  number;
  days:           number;
  symbol:         string | null;
  message:        string;
  timestamp:      number;
}

// ── Scanner Performance ──────────────────────────────────────────────────────
export interface ScannerPick {
  symbol:       string;
  score:        number;
  signal_label: string;
  close_price:  number;
  scan_date:    string;
  outcome_pct:  number | null;
}

export interface ScannerPerformance {
  picks:   ScannerPick[];
  summary: {
    total_picks:    number;
    checked:        number;
    avg_return_pct: number | null;
    win_rate_pct:   number | null;
    days:           number;
  };
  alltime?: {
    first_date:      string | null;
    total_picks:     number;
    checked:         number;
    cumulative_pct:  number | null;
    avg_return_pct:  number | null;
    win_rate_pct:    number | null;
  };
  timestamp: number;
}

// ── Alert ────────────────────────────────────────────────────────────────────
export interface AlertItem {
  id:         number;
  email:      string;
  symbol:     string;
  alert_type: "price" | "score";
  threshold:  number;
  direction:  "above" | "below";
  active:     boolean;
  created_ts: number;
  fired_ts:   number | null;
  fire_count: number;
}

// ── Backtest ──────────────────────────────────────────────────────────────────
export interface BacktestTrade {
  symbol:      string;
  interval:    string;
  entry_price: number;
  ts:          number;
  outcome_pct: number | null;
  resolved:    boolean;
}

export interface BacktestSummary {
  total:        number;
  resolved:     number;
  wins:         number;
  losses:       number;
  avg_return:   number | null;
  total_return: number | null;
  win_rate:     number | null;
  threshold_pct: number;
  days:         number;
  symbol:       string | null;
}

export interface BacktestData {
  trades:    BacktestTrade[];
  summary:   BacktestSummary;
  timestamp: number;
}

// ── Confluence ────────────────────────────────────────────────────────────────
export interface ConfluenceTF {
  interval:   string;
  score:      number;
  max_score:  number;
  signal:     string;
  direction:  string;
  close:      number;
  rsi:        number;
  adx:        number;
  ema_stack:  boolean;
  rel_volume: number;
  components: { V: number; P: number; R: number; T: number; S: number };
  error?:     string;
}

export interface ConfluenceData {
  symbol:           string;
  timeframes:       ConfluenceTF[];
  confluence_score: number;
  all_bullish:      boolean;
  any_strong_buy:   boolean;
  timestamp:        number;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface MagicLinkResult {
  sent?:        boolean;
  email?:       string;
  expires_in?:  number;
  message:      string;
  dev_link?:    string | null;
  error?:       string;
}

export interface VerifyResult {
  verified?:      boolean;
  email?:         string;
  session_token?: string;
  message?:       string;
  error?:         string;
}

export interface AuthUser {
  email: string;
}


// ── Internal Signal Backtest ───────────────────────────────────────────────
export interface BacktestTrade {
  date:        string;
  entry_price: number;
  exit_price:  number;
  score:       number;
  signal:      string;
  rsi:         number;
  adx:         number;
  ret_1d:      number;
  ret_3d:      number | null;
  ret_5d:      number | null;
  win_1d:      boolean;
  win_3d:      boolean | null;
  win_5d:      boolean | null;
}

export interface BacktestEquityPoint {
  date:   string;
  score:  number;
  signal: string;
  equity: number;
  close:  number;
}

export interface BacktestBarScore {
  date:      string;
  score:     number;
  signal:    string;
  close:     number;
  rsi:       number;
  adx:       number;
  ema_stack: boolean;
}

export interface BacktestInternalSummary {
  symbol:        string;
  bars_scanned:  number;
  total_trades:  number;
  wins_1d:       number;
  losses_1d:     number;
  win_rate_1d:   number | null;
  avg_ret_1d:    number | null;
  avg_ret_3d:    number | null;
  avg_ret_5d:    number | null;
  total_return:  number | null;
  max_drawdown:  number | null;
  sharpe_proxy:  number | null;
  threshold:     number;
  hold_days:     number;
  score_dist:    Record<string, number>;
  first_date:    string | null;
  last_date:     string | null;
}

export interface BacktestInternalData {
  symbol:     string;
  trades:     BacktestTrade[];
  equity:     BacktestEquityPoint[];
  bar_scores: BacktestBarScore[];
  summary:    BacktestInternalSummary;
  error?:     string;
}

// ── On-Chain Intelligence ─────────────────────────────────────────────────────
export interface OnChainSignal {
  type:   "positive" | "caution" | "risk";
  label:  string;
  detail: string;
}

export interface OnChainUnlockEvent {
  date:       number;      // unix timestamp
  amount_usd: number | null;
  label:      string;
}

export interface OnChainUnlock {
  total_locked_usd: number | null;
  next_unlock:      OnChainUnlockEvent | null;
}

export interface OnChainConcentration {
  top10_holders:  number;
  top10_quantity: number;
  source:         string;
}

export interface OnChainData {
  symbol:             string;
  source:             string[];
  // Supply
  circulating_supply: number | null;
  total_supply:       number | null;
  max_supply:         number | null;
  supply_pct:         number | null;
  // Valuation
  market_cap_usd:     number | null;
  fdv_usd:            number | null;
  mc_fdv_ratio:       number | null;
  // Activity
  volume_24h:         number | null;
  nvt_proxy:          number | null;
  // DeFi
  tvl_usd:            number | null;
  tvl_mc_ratio:       number | null;
  // Unlocks
  unlock:             OnChainUnlock | null;
  // Concentration
  concentration:      OnChainConcentration | null;
  // Signals
  signals:            OnChainSignal[];
  risk_score:         number | null;
  // Meta
  timestamp:          number;
  error?:             string;
}

// ── Editable Watchlist ────────────────────────────────────────────────────────
export interface WatchlistItemsResponse {
  user_id:  string;
  symbols:  string[];
  timestamp: number;
}
