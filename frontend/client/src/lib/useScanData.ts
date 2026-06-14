// frontend/client/src/lib/useScanData.ts
import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchScanShared,
  subscribeScan,
  getCachedScan,
  type ScanParams,
  type ScanResponse,
} from "./scanCache";

export interface UseScanDataOptions {
  /** Re-run the fetch on this interval (ms). Polling re-runs go through the
   *  same shared/dedup/cache path as the initial fetch. */
  pollMs?: number;
  /** Set false to skip fetching entirely (e.g. ScanAlertPoller when alerts
   *  are disabled). */
  enabled?: boolean;
}

export interface UseScanDataResult {
  data: ScanResponse | null;
  error: string | null;
  loading: boolean;
  /** Manually re-run. `force` (default true) bypasses the freshness cache —
   *  use for a "Scan" / "Refresh" button. */
  refetch: (force?: boolean) => void;
}

/**
 * React hook over the shared /scan cache (see scanCache.ts). Any number of
 * components mounting with the same params share one underlying request and
 * one cached result instead of each firing their own — this is what
 * consolidates TopSignals / VolRadar / ScanAlertPoller's previously-separate
 * fetches.
 */
export function useScanData(params: ScanParams, opts: UseScanDataOptions = {}): UseScanDataResult {
  const { pollMs, enabled = true } = opts;
  const paramsKey = `${params.interval}:${params.min_score}:${params.max_coins ?? 200}:${params.min_volume ?? 500000}`;

  const initial = getCachedScan(params);
  const [data, setData] = useState<ScanResponse | null>(initial.data);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(enabled && initial.data === null);
  const hasDataRef = useRef<boolean>(initial.data !== null);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(
    (force = false) => {
      if (!enabled) return;
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(!hasDataRef.current);
      setError(null);
      fetchScanShared(params, { force, signal: ctrl.signal })
        .then((d) => {
          if (ctrl.signal.aborted) return;
          hasDataRef.current = true;
          setData(d);
          setLoading(false);
        })
        .catch((e: unknown) => {
          if (ctrl.signal.aborted) return;
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        });
    },
    // paramsKey captures everything in `params` that matters for the request
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [paramsKey, enabled]
  );

  useEffect(() => {
    if (!enabled) return;
    const unsub = subscribeScan(params, (d, err) => {
      if (d) {
        hasDataRef.current = true;
        setData(d);
      }
      setError(err);
    });

    run();

    let timer: ReturnType<typeof setInterval> | null = null;
    if (pollMs) timer = setInterval(() => run(), pollMs);

    return () => {
      unsub();
      if (timer) clearInterval(timer);
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey, enabled, pollMs]);

  return { data, error, loading, refetch: (force = true) => run(force) };
}
