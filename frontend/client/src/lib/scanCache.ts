// frontend/client/src/lib/scanCache.ts
//
// Shared /scan request cache + deduplication.
//
// Previously TopSignals, VolRadar, and ScanAlertPoller each ran their own
// independent fetch() against /scan on page load (and on their own poll
// timers). With default params (interval=1d, min_score=1, max_coins=200,
// min_volume=500000), TopSignals and VolRadar issue genuinely identical
// requests. The backend now coalesces concurrent identical requests with a
// per-cache-key lock, but the frontend still fired the redundant requests in
// the first place.
//
// This module is the single place that talks to /scan. It:
//  - dedupes concurrent requests for the same params (an in-flight request
//    is shared rather than duplicated)
//  - caches the most recent response per param-set for FRESH_MS, so a
//    component that mounts shortly after another with the same params gets
//    the cached result instantly with no network call
//  - notifies every subscriber (TopSignals, VolRadar, ScanAlertPoller, ...)
//    when fresh data arrives for params they care about

const API =
  (import.meta as Record<string, unknown> & { env?: Record<string, string> })
    .env?.VITE_API_BASE ?? "https://crypto-sniper.onrender.com";

// Matches backend _SCAN_TTL (api.py) — no point re-fetching sooner than this.
const FRESH_MS = 5 * 60 * 1000;

export interface ScanParams {
  interval: string;
  min_score: number;
  max_coins?: number;
  min_volume?: number;
}

export interface ScanResponse {
  signals: Record<string, unknown>[];
  universe?: number;
  scanned?: number;
  cached?: boolean;
  cached_age_mins?: number;
  [key: string]: unknown;
}

type Listener = (data: ScanResponse | null, error: string | null) => void;

interface CacheEntry {
  data: ScanResponse | null;
  error: string | null;
  timestamp: number;
  inflight: Promise<ScanResponse> | null;
  subscribers: Set<Listener>;
}

const cache = new Map<string, CacheEntry>();

function keyFor(p: ScanParams): string {
  return `${p.interval.toLowerCase()}:${p.min_score}:${p.max_coins ?? 200}:${p.min_volume ?? 500000}`;
}

function getEntry(key: string): CacheEntry {
  let e = cache.get(key);
  if (!e) {
    e = { data: null, error: null, timestamp: 0, inflight: null, subscribers: new Set() };
    cache.set(key, e);
  }
  return e;
}

function buildUrl(p: ScanParams): string {
  const qs = new URLSearchParams({
    interval: p.interval.toLowerCase(),
    min_score: String(p.min_score),
    max_coins: String(p.max_coins ?? 200),
    min_volume: String(p.min_volume ?? 500000),
  });
  return `${API}/scan?${qs.toString()}`;
}

function doFetch(key: string, params: ScanParams, signal?: AbortSignal): Promise<ScanResponse> {
  const entry = getEntry(key);
  const promise = (async (): Promise<ScanResponse> => {
    try {
      const res = await fetch(buildUrl(params), {
        signal: signal ?? AbortSignal.timeout(60_000),
      });
      if (!res.ok) throw new Error(`/scan returned ${res.status}`);
      const data = (await res.json()) as ScanResponse;
      entry.data = data;
      entry.error = null;
      entry.timestamp = Date.now();
      entry.subscribers.forEach((fn) => fn(data, null));
      return data;
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      entry.error = msg;
      entry.subscribers.forEach((fn) => fn(entry.data, msg));
      throw e;
    } finally {
      entry.inflight = null;
    }
  })();
  entry.inflight = promise;
  return promise;
}

/**
 * Fetch /scan for `params`, sharing in-flight requests and recent results
 * across every caller. Pass `force: true` to bypass the freshness window
 * (e.g. a manual "Scan" button) — this always issues a fresh request but
 * still coalesces with any other in-flight forced request for the same key.
 */
export function fetchScanShared(
  params: ScanParams,
  opts?: { force?: boolean; signal?: AbortSignal }
): Promise<ScanResponse> {
  const key = keyFor(params);
  const entry = getEntry(key);
  const fresh = entry.data !== null && Date.now() - entry.timestamp < FRESH_MS;
  if (!opts?.force && fresh) return Promise.resolve(entry.data!);
  if (entry.inflight) return entry.inflight;
  return doFetch(key, params, opts?.signal);
}

/** Synchronously read whatever's cached for `params`, without fetching. */
export function getCachedScan(params: ScanParams): { data: ScanResponse | null; ageMs: number } {
  const entry = getEntry(keyFor(params));
  return { data: entry.data, ageMs: entry.data ? Date.now() - entry.timestamp : Infinity };
}

/** Subscribe to updates for a given param-set. Returns an unsubscribe fn. */
export function subscribeScan(params: ScanParams, fn: Listener): () => void {
  const entry = getEntry(keyFor(params));
  entry.subscribers.add(fn);
  return () => entry.subscribers.delete(fn);
}
