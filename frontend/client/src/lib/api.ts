// âââ API Client for Crypto Sniper V2 ââââââââââââââââââââââââââââââââââââââââ
// All calls go to the Render backend via environment variable

import type {
  AnalyseRequest, AnalyseResponse,
  KronosResponse, DeepResearchResponse,
  MarketOverview, TrendingCoin, NewsArticle,
  MacroData, WatchlistScore, HealthStatus,
  HitRateData, ScannerPerformance, AlertItem,
} from "@/types/api";

const BASE_URL =
  (import.meta as Record<string, unknown> & { env?: Record<string, string> })
    .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

// ââ Core fetch wrapper ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  retries = 1,
): Promise<T> {
  const url = `${BASE_URL}${path}`;
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(url, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      if (!res.ok) {
        const text = await res.text().catch(() => res.statusText);
        throw new Error(`API ${res.status}: ${text}`);
      }
      return res.json() as Promise<T>;
    } catch (err) {
      if (attempt === retries) throw err;
      await new Promise((r) => setTimeout(r, 800 * (attempt + 1)));
    }
  }
  throw new Error("Max retries exceeded");
}

// ââ POST helper âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
function post<T>(path: string, body: unknown, retries = 1): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) }, retries);
}

// ââ GET helper ââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
function get<T>(path: string, retries = 1): Promise<T> {
  return apiFetch<T>(path, { method: "GET" }, retries);
}

// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
// ENDPOINTS
// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

/** Full V/P/R/T/S analysis for a coin + interval */
export function analyse(req: AnalyseRequest): Promise<AnalyseResponse> {
  return post<AnalyseResponse>("/analyse", req, 1);
}

/** Kronos AI forecast + 4-agent debate */
export function kronos(
  symbol: string,
  interval: string,
  signalData?: Record<string, unknown>,
): Promise<KronosResponse> {
  return post<KronosResponse>("/kronos", { symbol, interval, signal_data: signalData }, 1);
}

/** Perplexity deep research */
export function deepResearch(
  symbol: string,
  depth: "quick" | "deep" | "max" = "deep",
  context: Record<string, unknown> = {},
): Promise<DeepResearchResponse> {
  return post<DeepResearchResponse>("/deep-research", { symbol, depth, context }, 0);
}

/** Market overview bar (total cap, BTC dom, mempool fees) */
export function getMarketOverview(): Promise<MarketOverview> {
  return get<MarketOverview>("/market", 2);
}

/** Top 10 trending coins */
export function getTrending(): Promise<{ coins: TrendingCoin[]; timestamp: number }> {
  return get("/trending", 2);
}

/** Top 5 gainers + losers */
export function getGainers(): Promise<{
  gainers: TrendingCoin[];
  losers: TrendingCoin[];
  timestamp: number;
}> {
  return get("/gainers", 2);
}

/** Live news for a symbol */
export function getNews(symbol: string): Promise<{ symbol: string; articles: NewsArticle[] }> {
  return get(`/news/${encodeURIComponent(symbol)}`, 2);
}

/** Macro context: Fed rate, CPI, Gold, DXY */
export function getMacro(): Promise<MacroData> {
  return get<MacroData>("/macro", 2);
}

/** Batch signal scores for watchlist */
export function getWatchlistScores(
  symbols: string[],
): Promise<{ scores: WatchlistScore[] }> {
  return post("/watchlist", { symbols }, 1);
}

/** Health check */
export function healthCheck(): Promise<HealthStatus> {
  return get<HealthStatus>("/health", 0);
}

/** STRONG BUY hit rate from signal history */
export function getHitRate(symbol?: string, days = 30): Promise<HitRateData> {
  const qs = new URLSearchParams({ days: String(days) });
  if (symbol) qs.set("symbol", symbol);
  return get<HitRateData>(`/hit-rate?${qs}`, 1);
}

/** Scanner performance (yesterday's picks + % return) */
export function getScannerPerformance(days = 7): Promise<ScannerPerformance> {
  return get<ScannerPerformance>(`/scanner-performance?days=${days}`, 1);
}

/** Create a price/score alert */
export function createAlert(payload: {
  email: string; symbol: string; alert_type: "score" | "price";
  threshold: number; direction: "above" | "below";
}): Promise<{ alert_id: number; message: string; error?: string }> {
  return post("/alerts", payload, 0);
}

/** List active alerts for an email */
export function getAlerts(email: string): Promise<{ alerts: AlertItem[] }> {
  return get(`/alerts?email=${encodeURIComponent(email)}`, 0);
}

/** Delete an alert */
export async function deleteAlert(id: number): Promise<void> {
  await apiFetch(`/alerts/${id}`, { method: "DELETE" }, 0);
}

// ââ Utility: format numbers âââââââââââââââââââââââââââââââââââââââââââââââââââ
export function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null || isNaN(n)) return "-";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function fmtPrice(n: number | null | undefined): string {
  if (n == null || isNaN(n) || n === 0) return "-";
  if (n < 0.001) return `$${n.toFixed(8)}`;
  if (n < 1)     return `$${n.toFixed(4)}`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtPct(n: number | null | undefined, showPlus = true): string {
  if (n == null || isNaN(n)) return "-";
  const sign = showPlus && n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export function fmtBigNum(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "-";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `$${(n / 1e9).toFixed(2)}B`;
  if (n >= 1e6)  return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

export function timeAgo(ts: string | number): string {
  const date = typeof ts === "number" ? new Date(ts * 1000) : new Date(ts);
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60)   return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ── New endpoints ─────────────────────────────────────────────────────────────

/** Backtest: STRONG BUY signals and their outcomes */
export function getBacktest(symbol?: string | null, days = 30): Promise<import("@/types/api").BacktestData> {
  const qs = new URLSearchParams({ days: String(days) });
  if (symbol) qs.set("symbol", symbol);
  return get(`/backtest?${qs}`, 1);
}

/** Multi-timeframe confluence for a symbol */
export function getConfluence(symbol: string, intervals = "1H,4H,1D"): Promise<import("@/types/api").ConfluenceData> {
  return get(`/confluence/${encodeURIComponent(symbol)}?intervals=${encodeURIComponent(intervals)}`, 1);
}

/** Get persisted watchlist symbols */
export function getWatchlistItems(userId: string): Promise<import("@/types/api").WatchlistItemsResponse> {
  return get(`/watchlist-items?user_id=${encodeURIComponent(userId)}`, 1);
}

/** Add a symbol to watchlist */
export function addWatchlistItem(userId: string, symbol: string): Promise<{ added: boolean; symbol: string }> {
  return post(`/watchlist-items`, { user_id: userId, symbol }, 0);
}

/** Remove a symbol from watchlist */
export function removeWatchlistItem(userId: string, symbol: string): Promise<{ deleted: boolean; symbol: string }> {
  return apiFetch(`/watchlist-items/${encodeURIComponent(symbol)}?user_id=${encodeURIComponent(userId)}`, { method: "DELETE" }, 0);
}

/** Request magic-link login email */
export function requestMagicLink(email: string): Promise<import("@/types/api").MagicLinkResult> {
  return post(`/auth/magic-link`, { email }, 0);
}

/** Verify magic-link token */
export function verifyMagicLink(token: string): Promise<import("@/types/api").VerifyResult> {
  return get(`/auth/verify?token=${encodeURIComponent(token)}`, 0);
}

/** Get current user from session token */
export function getMe(sessionToken: string): Promise<import("@/types/api").AuthUser & { timestamp: number }> {
  return get(`/auth/me?session_token=${encodeURIComponent(sessionToken)}`, 0);
}

/** On-chain intelligence for a symbol */
export function getOnchain(symbol: string): Promise<import("@/types/api").OnChainData> {
  return get(`/onchain/${encodeURIComponent(symbol.toUpperCase())}`, 1);
}

/** Internal signal backtest - replays scoring engine on 1D OHLCV history */
export function getBacktestInternal(symbol: string): Promise<import("@/types/api").BacktestInternalData> {
  return get(`/backtest-internal/${encodeURIComponent(symbol.toUpperCase())}`, 1);
}

// ── Score Performance ──────────────────────────────────────────────────────
export interface ScoreBand {
  label:    string;
  color:    string;
  min:      number;
  max:      number;
  n:        number;
  avg_1d:   number;
  avg_3d:   number | null;
  avg_7d:   number | null;
  win_rate: number;
  wins:     number;
  equity:   number;  // compounded $100
}

export interface ScorePerformanceData {
  bands:       ScoreBand[];
  coins_used:  string[];
  total_bars:  number;
  timestamp:   number;
  error?:      string;
}

export function getScorePerformance(topN = 15): Promise<ScorePerformanceData> {
  return get(`/score-performance?top_n=${topN}`, 1);
}

