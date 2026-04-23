// ─── API Client for Crypto Sniper V2 ────────────────────────────────────────
// All calls go to the Render backend via environment variable

import type {
  AnalyseRequest, AnalyseResponse,
  KronosResponse, DeepResearchResponse,
  MarketOverview, TrendingCoin, NewsArticle,
  MacroData, WatchlistScore, HealthStatus,
} from "@/types/api";

const BASE_URL =
  (import.meta as Record<string, unknown> & { env?: Record<string, string> })
    .env?.VITE_API_BASE ?? "https://crypto-sniper-api.onrender.com";

// ── Core fetch wrapper ────────────────────────────────────────────────────────
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

// ── POST helper ───────────────────────────────────────────────────────────────
function post<T>(path: string, body: unknown, retries = 1): Promise<T> {
  return apiFetch<T>(path, { method: "POST", body: JSON.stringify(body) }, retries);
}

// ── GET helper ────────────────────────────────────────────────────────────────
function get<T>(path: string, retries = 1): Promise<T> {
  return apiFetch<T>(path, { method: "GET" }, retries);
}

// ═══════════════════════════════════════════════════════════════════════════════
// ENDPOINTS
// ═══════════════════════════════════════════════════════════════════════════════

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

// ── Utility: format numbers ───────────────────────────────────────────────────
export function fmt(n: number | null | undefined, decimals = 2): string {
  if (n == null || isNaN(n)) return "—";
  return n.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function fmtPrice(n: number | null | undefined): string {
  if (n == null || isNaN(n) || n === 0) return "—";
  if (n < 0.001) return `$${n.toFixed(8)}`;
  if (n < 1)     return `$${n.toFixed(4)}`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function fmtPct(n: number | null | undefined, showPlus = true): string {
  if (n == null || isNaN(n)) return "—";
  const sign = showPlus && n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}%`;
}

export function fmtBigNum(n: number | null | undefined): string {
  if (n == null || isNaN(n)) return "—";
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
