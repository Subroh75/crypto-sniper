// âââ Custom Hooks for Crypto Sniper V2 ââââââââââââââââââââââââââââââââââââââ
import { useState, useEffect, useCallback, useRef } from "react";
import {
  analyse, kronos, deepResearch,
  getMarketOverview, getTrending, getGainers,
  getNews, getMacro, getWatchlistScores,
  getHitRate, getScannerPerformance, createAlert, getAlerts, deleteAlert,
} from "@/lib/api";
import type {
  AnalyseResponse, KronosResponse, DeepResearchResponse,
  MarketOverview, TrendingCoin, NewsArticle,
  MacroData, WatchlistScore, HitRateData, ScannerPerformance, AlertItem,
} from "@/types/api";

// ââ Generic async hook ââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
  immediate = true,
) {
  const [data, setData]       = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const abortRef              = useRef<AbortController | null>(null);

  const run = useCallback(async () => {
    abortRef.current?.abort();
    abortRef.current = new AbortController();
    setLoading(true);
    setError(null);
    try {
      const result = await fn();
      setData(result);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      if (!msg.includes("abort")) setError(msg);
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (immediate) run();
    return () => abortRef.current?.abort();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run]);

  return { data, loading, error, refetch: run };
}

// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
// ANALYSIS HOOKS
// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

/** Full V/P/R/T/S analysis â called on demand (not on mount) */
export function useAnalyse() {
  const [data, setData]       = useState<AnalyseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const run = useCallback(async (symbol: string, interval: string) => {
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const result = await analyse({ symbol: symbol.toUpperCase(), interval });
      if (result.error) throw new Error(result.error);
      setData(result);
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Analysis failed";
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, run };
}

/** Kronos AI forecast + agent debate â called after analyse */
export function useKronos() {
  const [data, setData]       = useState<KronosResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const run = useCallback(async (
    symbol: string,
    interval: string,
    signalCtx?: Record<string, unknown>,
  ) => {
    setLoading(true);
    setError(null);
    try {
      const result = await kronos(symbol, interval, signalCtx);
      if (result.error) throw new Error(result.error);
      setData(result);
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Forecast failed";
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, run };
}

/** Perplexity deep research */
export function useDeepResearch() {
  const [data, setData]       = useState<DeepResearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const run = useCallback(async (
    symbol: string,
    depth: "quick" | "deep" | "max" = "deep",
    context: Record<string, unknown> = {},
  ) => {
    setLoading(true);
    setError(null);
    try {
      const result = await deepResearch(symbol, depth, context);
      if (result.error) throw new Error(result.error);
      setData(result);
      return result;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Research failed";
      setError(msg);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const reset = useCallback(() => {
    setData(null);
    setError(null);
  }, []);

  return { data, loading, error, run, reset };
}

// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
// MARKET DATA HOOKS (auto-refresh)
// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

/** Market overview â refreshes every 60s */
export function useMarketOverview() {
  return useAsync<MarketOverview>(getMarketOverview, [], true);
}

/** Trending coins â refreshes every 5 min */
export function useTrending() {
  const { data, loading, error, refetch } = useAsync(
    getTrending,
    [],
    true,
  );
  const coins = data?.coins ?? [];

  useEffect(() => {
    const id = setInterval(refetch, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [refetch]);

  return { coins, loading, error, refetch };
}

/** Top gainers + losers */
export function useGainers() {
  const { data, loading, error, refetch } = useAsync(getGainers, [], true);

  useEffect(() => {
    const id = setInterval(refetch, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [refetch]);

  return {
    gainers: data?.gainers ?? [],
    losers:  data?.losers  ?? [],
    loading, error, refetch,
  };
}

/** News for a symbol */
export function useNews(symbol: string | null) {
  return useAsync<{ symbol: string; articles: NewsArticle[] }>(
    () => getNews(symbol ?? "BTC"),
    [symbol],
    !!symbol,
  );
}

/** Macro data */
export function useMacro() {
  return useAsync<MacroData>(getMacro, [], true);
}

/** Watchlist scores */
export function useWatchlist(symbols: string[]) {
  const [scores, setScores]   = useState<WatchlistScore[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!symbols.length) return;
    setLoading(true);
    try {
      const res = await getWatchlistScores(symbols);
      setScores(res.scores);
    } catch {
      // silent fail for watchlist
    } finally {
      setLoading(false);
    }
  }, [symbols.join(",")]); // eslint-disable-line

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 60 * 1000);
    return () => clearInterval(id);
  }, [refresh]);

  return { scores, loading, refresh };
}

// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ
// COINCAP WEBSOCKET â Live price ticker
// âââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââââ

const DEFAULT_TICKERS = ["bitcoin", "ethereum", "solana", "bnb", "dogecoin", "pepe"];

export interface LivePrice {
  symbol: string;
  price:  number;
  prev:   number;
}

// CoinGecko symbol → CoinGecko coin ID map for REST fallback
const CG_IDS: Record<string, string> = {
  BTC:  "bitcoin",   ETH: "ethereum",  SOL: "solana",
  BNB:  "binancecoin", DOGE: "dogecoin", PEPE: "pepe",
  WIF:  "dogwifcoin",  HYPE: "hyperliquid", XRP: "ripple",
  ADA:  "cardano",
};

export function useLivePrices() {
  const [prices, setPrices] = useState<Record<string, { price: number; change: number }>>({});
  const wsAlive = useRef(false);

  // CoinGecko REST fallback — polls every 30s
  const pollCoinGecko = useCallback(async () => {
    try {
      const ids = Object.values(CG_IDS).join(",");
      const res = await fetch(
        `https://api.coingecko.com/api/v3/simple/price?ids=${ids}&vs_currencies=usd&include_24hr_change=true`,
        { signal: AbortSignal.timeout(8000) },
      );
      if (!res.ok) return;
      const data = await res.json();
      const update: Record<string, { price: number; change: number }> = {};
      for (const [sym, cgId] of Object.entries(CG_IDS)) {
        const entry = data[cgId];
        if (entry) {
          update[sym] = { price: entry.usd ?? 0, change: entry.usd_24h_change ?? 0 };
        }
      }
      if (Object.keys(update).length > 0) setPrices(prev => ({ ...prev, ...update }));
    } catch { /* silent — best effort */ }
  }, []);

  useEffect(() => {
    const COINS = ["BTC","ETH","SOL","BNB","DOGE","PEPE","WIF","HYPE","XRP","ADA"];
    const streams = COINS.map(c => c.toLowerCase() + "usdt@miniTicker").join("/");
    let ws: WebSocket | null = null;
    let fallbackTimer: ReturnType<typeof setInterval> | null = null;

    const startFallback = () => {
      if (fallbackTimer) return; // already running
      pollCoinGecko();           // immediate first poll
      fallbackTimer = setInterval(pollCoinGecko, 30_000);
    };

    try {
      ws = new WebSocket("wss://stream.binance.com:9443/stream?streams=" + streams);

      // Give WS 5s to connect — if it hasn't by then, start REST fallback
      const wsTimeout = setTimeout(() => {
        if (!wsAlive.current) startFallback();
      }, 5000);

      ws.onopen = () => {
        wsAlive.current = true;
        clearTimeout(wsTimeout);
      };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          const d = msg.data;
          if (!d || !d.s) return;
          const sym = d.s.replace("USDT","").toUpperCase();
          const price = parseFloat(d.c);
          const open = parseFloat(d.o);
          const change = open > 0 ? ((price - open) / open) * 100 : 0;
          setPrices(prev => ({ ...prev, [sym]: { price, change } }));
        } catch {}
      };

      ws.onerror = () => {
        wsAlive.current = false;
        startFallback();
      };

      ws.onclose = () => {
        if (!wsAlive.current) startFallback();
      };
    } catch {
      startFallback();
    }

    return () => {
      try { ws?.close(); } catch {}
      if (fallbackTimer) clearInterval(fallbackTimer);
    };
  }, [pollCoinGecko]);

  return prices;
}


// ─────────────────────────────────────────────────────────────────────────────
// NEW HOOKS — Hit Rate, Scanner Performance, Alerts
// ─────────────────────────────────────────────────────────────────────────────

/** STRONG BUY hit rate from history DB */
export function useHitRate(symbol?: string | null, days = 30) {
  return useAsync<HitRateData>(
    () => getHitRate(symbol ?? undefined, days),
    [symbol, days],
    true,
  );
}

/** Scanner picks + % return over last N days */
export function useScannerPerformance(days = 7) {
  return useAsync<ScannerPerformance>(
    () => getScannerPerformance(days),
    [days],
    true,
  );
}

/** Alerts for a given email */
export function useAlerts(email: string | null) {
  const [alerts, setAlerts]   = useState<AlertItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!email) return;
    setLoading(true);
    try {
      const res = await getAlerts(email);
      setAlerts(res.alerts ?? []);
    } catch { /* silent */ }
    finally { setLoading(false); }
  }, [email]);

  useEffect(() => { refresh(); }, [refresh]);

  const create = useCallback(async (payload: {
    symbol: string; alert_type: "score" | "price";
    threshold: number; direction: "above" | "below";
  }) => {
    if (!email) return null;
    const res = await createAlert({ email, ...payload });
    refresh();
    return res;
  }, [email, refresh]);

  const remove = useCallback(async (id: number) => {
    await deleteAlert(id);
    refresh();
  }, [refresh]);

  return { alerts, loading, refresh, create, remove };
}

export function usePdfExport() {
  const [exporting, setExporting] = useState(false);

  const exportPdf = useCallback(async (elementId: string, filename = "crypto-sniper-report.pdf") => {
    setExporting(true);
    try {
      const [{ default: jsPDF }, { default: html2canvas }] = await Promise.all([
        import("jspdf"),
        import("html2canvas"),
      ]);

      const el = document.getElementById(elementId);
      if (!el) throw new Error("Element not found");

      const canvas = await html2canvas(el, {
        scale: 2,
        useCORS: true,
        backgroundColor: "#060912",
      });

      const imgData = canvas.toDataURL("image/png");
      const pdf     = new jsPDF("p", "mm", "a4");
      const w       = pdf.internal.pageSize.getWidth();
      const h       = (canvas.height * w) / canvas.width;

      pdf.addImage(imgData, "PNG", 0, 0, w, h);
      pdf.save(filename);
    } catch (e) {
      console.error("PDF export failed:", e);
    } finally {
      setExporting(false);
    }
  }, []);

  return { exporting, exportPdf };
}
