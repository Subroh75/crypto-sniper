/// <reference lib="webworker" />
// Custom Service Worker — Crypto Sniper
// Handles: Workbox precaching + push notifications for scan alerts

import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching";

declare const self: ServiceWorkerGlobalScope;

// Injected by vite-plugin-pwa injectManifest mode
precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

// Skip waiting immediately so updates take effect without user reload
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

// ── Push handler ──────────────────────────────────────────────────────────────
// Payload shape: { title, body, url? }
self.addEventListener("push", (event) => {
  let data: { title?: string; body?: string; url?: string } = {};
  try {
    data = event.data?.json() ?? {};
  } catch {
    data = { title: "Crypto Sniper", body: event.data?.text() ?? "" };
  }

  const title = data.title ?? "Crypto Sniper";
  const body  = data.body  ?? "New signal detected.";
  const url   = data.url   ?? "https://crypto-sniper.app";

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon:  "/pwa-192.png",
      badge: "/pwa-192.png",
      data:  { url },
      tag:   "scan-alert",           // replaces previous notif instead of stacking
      renotify: true,
      vibrate: [200, 100, 200],
    })
  );
});

// ── Notification click — open/focus the app ───────────────────────────────────
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data as { url?: string })?.url ?? "https://crypto-sniper.app";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      // Focus existing tab if open
      for (const client of clients) {
        if (client.url.includes("crypto-sniper") && "focus" in client) {
          return client.focus();
        }
      }
      // Otherwise open new tab
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});

// ── Message from app → SW (e.g. trigger test notification) ───────────────────
self.addEventListener("message", (event) => {
  if (event.data?.type === "SHOW_NOTIFICATION") {
    const { title, body, url } = event.data;
    self.registration.showNotification(title ?? "Crypto Sniper", {
      body:     body ?? "",
      icon:     "/pwa-192.png",
      badge:    "/pwa-192.png",
      data:     { url: url ?? "https://crypto-sniper.app" },
      tag:      "scan-alert",
      renotify: true,
      vibrate:  [200, 100, 200],
    });
  }
});
