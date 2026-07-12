// ScanAlertPoller.tsx
// Background hourly scanner — hits /scan every N minutes, fires a native
// push notification via the service worker when qualifying coins are found.
// No server VAPID needed: the SW receives a postMessage and calls showNotification().
//
// Settings are persisted in localStorage:
//   scan_alert_enabled    "true" | "false"
//   scan_alert_tier       "buy" | "strong_buy"
//   scan_alert_interval   "60" (minutes)
//   scan_alert_last_ts    unix seconds of last scan
//
// Filtering by signal.label instead of a raw score threshold — under the
// current tier system (signals.py) a plain BUY only needs Trend+ADX
// confirmed and can legitimately score as low as 3/13, while STRONG BUY's
// minimum possible score is 6 (one point on each of V/P/R/T). A raw score
// cutoff can no longer reliably distinguish the two tiers, and a 5+ floor
// was silently excluding real BUY signals entirely — see CSOVerdict.tsx
// for the same underlying bug, fixed the same way.
//
// Note: fetches go through the shared scanCache (fetchScanShared), so if
// TopSignals/VolRadar have just fetched the same params, this poller
// reuses that cached result instead of issuing its own request. We always
// request min_score: 1 from the backend so a plain BUY scoring 3-5 isn't
// excluded server-side before this component's own tier filter runs.

import { useEffect, useRef, useCallback } from "react";
import { fetchScanShared, type ScanResponse } from "@/lib/scanCache";

const STORAGE_ENABLED = "scan_alert_enabled";
const STORAGE_TIER = "scan_alert_tier";
const STORAGE_INTERVAL = "scan_alert_interval";
const STORAGE_LAST_TS = "scan_alert_last_ts";
const STORAGE_LAST_HITS = "scan_alert_last_hits";

function load(key: string, fallback: string) {
  try { return localStorage.getItem(key) ?? fallback; } catch { return fallback; }
}
function save(key: string, val: string) {
  try { localStorage.setItem(key, val); } catch {}
}

export type SignalTier = "buy" | "strong_buy";

interface ScanSignal {
  symbol: string;
  score: number;
  signal: string;
  change: number;
  rsi: number;
}

function _tierMatches(signal: string, tier: SignalTier): boolean {
  if (tier === "strong_buy") return signal === "STRONG BUY";
  return signal === "BUY" || signal === "STRONG BUY";
}

// ── Shared state — lets PriceAlertCard read/write poller settings ──────────
type SettingsListener = (s: ScanAlertSettings) => void;
const _settingsListeners = new Set<SettingsListener>();

export interface ScanAlertSettings {
  enabled: boolean;
  tier: SignalTier;
  interval: number;    // minutes
  lastTs: number;      // unix seconds
  lastHits: ScanSignal[];
}

function _readSettings(): ScanAlertSettings {
  const rawTier = load(STORAGE_TIER, "buy");
  return {
    enabled: load(STORAGE_ENABLED, "false") === "true",
    tier: (rawTier === "strong_buy" ? "strong_buy" : "buy") as SignalTier,
    interval: parseInt(load(STORAGE_INTERVAL, "60"), 10),
    lastTs: parseInt(load(STORAGE_LAST_TS, "0"), 10),
    lastHits: JSON.parse(load(STORAGE_LAST_HITS, "[]")),
  };
}

export function subscribeScanSettings(fn: SettingsListener) {
  _settingsListeners.add(fn);
  fn(_readSettings());
  return () => _settingsListeners.delete(fn);
}

export function updateScanSettings(patch: Partial<Omit<ScanAlertSettings, "lastTs" | "lastHits">>) {
  if (patch.enabled !== undefined) save(STORAGE_ENABLED, String(patch.enabled));
  if (patch.tier !== undefined) save(STORAGE_TIER, patch.tier);
  if (patch.interval !== undefined) save(STORAGE_INTERVAL, String(patch.interval));
  _settingsListeners.forEach(fn => fn(_readSettings()));
}

// ── Notification helper ───────────────────────────────────────────────────────
async function showScanNotification(hits: ScanSignal[], tier: SignalTier) {
  // First try SW postMessage (works when app is backgrounded/locked screen)
  if ("serviceWorker" in navigator) {
    try {
      const reg = await navigator.serviceWorker.ready;
      if (reg.active) {
        const top = hits[0];
        const title = `Crypto Sniper — ${hits.length} signal${hits.length > 1 ? "s" : ""} found`;
        const body = hits.length === 1
          ? `${top.symbol} ${top.score}/16 ${top.signal} | RSI ${top.rsi?.toFixed(0)} | ${top.change >= 0 ? "+" : ""}${top.change?.toFixed(1)}%`
          : `Top: ${hits.slice(0,3).map(h => `${h.symbol} ${h.score}/16`).join(", ")}${hits.length > 3 ? ` +${hits.length-3} more` : ""}`;
        reg.active.postMessage({
          type: "SHOW_NOTIFICATION",
          title,
          body,
          url: "https://crypto-sniper.app",
        });
        return;
      }
    } catch {}
  }
  // Fallback: direct Notification API (only works when app is in foreground)
  if ("Notification" in window && Notification.permission === "granted") {
    const top = hits[0];
    const title = `Crypto Sniper — ${hits.length} signal${hits.length > 1 ? "s" : ""} found`;
    const body = hits.length === 1
      ? `${top.symbol} ${top.score}/16 ${top.signal}`
      : hits.slice(0,3).map(h => `${h.symbol} ${h.score}/16`).join(", ");
    new Notification(title, { body, icon: "/pwa-192.png" });
  }
}

// ── The poller (rendered once at app root) ────────────────────────────────────
export function ScanAlertPoller() {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const runningRef = useRef(false);

  const runScan = useCallback(async () => {
    if (runningRef.current) return;
    const s = _readSettings();
    if (!s.enabled) return;
    if (Notification.permission !== "granted") return;

    runningRef.current = true;
    try {
      // min_score: 1 — do NOT pre-filter server-side by raw score. A plain
      // BUY can legitimately score as low as 3/13; filtering here happens
      // by signal.label below instead, which is what actually reflects the
      // current BUY/STRONG BUY tier logic.
      const data: ScanResponse = await fetchScanShared({
        interval: "1d",
        min_score: 1,
        max_coins: 200,
        min_volume: 500000,
      });
      const signals: ScanSignal[] = ((data.signals ?? []) as unknown as ScanSignal[]).filter(
        (sig) => _tierMatches(sig.signal, _readSettings().tier)
      );

      // Save last scan results
      const now = Math.floor(Date.now() / 1000);
      save(STORAGE_LAST_TS, String(now));
      save(STORAGE_LAST_HITS, JSON.stringify(signals.slice(0, 10)));
      _settingsListeners.forEach(fn => fn(_readSettings()));

      if (signals.length > 0) {
        await showScanNotification(signals, s.tier);
      }
    } catch (e) {
      console.warn("[ScanAlertPoller] scan failed:", e);
    } finally {
      runningRef.current = false;
    }
  }, []);

  const schedulePoller = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    const s = _readSettings();
    const intervalMs = s.interval * 60 * 1000;
    timerRef.current = setInterval(runScan, intervalMs);

    // Run immediately if it's been longer than the interval since last scan
    const msSinceLastScan = (Math.floor(Date.now() / 1000) - s.lastTs) * 1000;
    if (msSinceLastScan >= intervalMs) {
      setTimeout(runScan, 2000); // slight delay so app finishes loading
    }
  }, [runScan]);

  useEffect(() => {
    // Re-schedule whenever settings change
    const unsub = subscribeScanSettings(() => schedulePoller());
    schedulePoller();
    return () => {
      unsub();
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [schedulePoller]);

  return null; // no UI — purely background
}
