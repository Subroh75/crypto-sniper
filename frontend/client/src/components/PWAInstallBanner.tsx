import { useState, useEffect } from "react";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

// Detect platform
function isIOS() {
  return /iphone|ipad|ipod/i.test(navigator.userAgent);
}
function isAndroidChrome() {
  return /android/i.test(navigator.userAgent) && /chrome/i.test(navigator.userAgent);
}
function isStandalone() {
  return window.matchMedia("(display-mode: standalone)").matches
    || (navigator as unknown as { standalone?: boolean }).standalone === true;
}

export function PWAInstallBanner() {
  const [show, setShow] = useState(false);
  const [isIos, setIsIos] = useState(false);
  const [deferredPrompt, setDeferredPrompt] = useState<BeforeInstallPromptEvent | null>(null);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    // Already installed — never show
    if (isStandalone()) return;

    const ios = isIOS();
    const android = isAndroidChrome();

    if (ios) {
      setIsIos(true);
      setShow(true);
      return;
    }

    if (android) {
      const handler = (e: Event) => {
        e.preventDefault();
        setDeferredPrompt(e as BeforeInstallPromptEvent);
        setShow(true);
      };
      window.addEventListener("beforeinstallprompt", handler);
      return () => window.removeEventListener("beforeinstallprompt", handler);
    }
  }, []);

  if (!show) return null;

  async function handleInstall() {
    if (!deferredPrompt) return;
    setInstalling(true);
    await deferredPrompt.prompt();
    const { outcome } = await deferredPrompt.userChoice;
    if (outcome === "accepted") setShow(false);
    setInstalling(false);
    setDeferredPrompt(null);
  }

  return (
    <div style={{
      position: "fixed",
      bottom: "calc(56px + env(safe-area-inset-bottom, 0px) + 8px)",
      left: 12,
      right: 12,
      zIndex: 999,
      background: "linear-gradient(135deg, #1a0533 0%, #0c1225 100%)",
      border: "1px solid #7c3aed44",
      borderRadius: 14,
      padding: "14px 16px",
      boxShadow: "0 8px 32px rgba(124,58,237,0.25)",
      display: "flex",
      alignItems: "flex-start",
      gap: 12,
    }}>
      {/* Icon */}
      <div style={{
        width: 40, height: 40, borderRadius: 10, flexShrink: 0,
        background: "#7c3aed", display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 20,
      }}>
        ◎
      </div>

      {/* Text */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 800, color: "#f1f5f9", marginBottom: 3 }}>
          Add Crypto Sniper to your Home Screen
        </div>
        {isIos ? (
          <div style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.5 }}>
            Tap the <span style={{ color: "#7c3aed", fontWeight: 700 }}>Share</span> button in Safari, then{" "}
            <span style={{ color: "#7c3aed", fontWeight: 700 }}>Add to Home Screen</span> for the full app experience.
          </div>
        ) : (
          <div style={{ fontSize: 11, color: "#94a3b8", lineHeight: 1.5 }}>
            Install for instant access, offline support, and no browser chrome.
          </div>
        )}

        {/* Android install button */}
        {!isIos && deferredPrompt && (
          <button
            onClick={handleInstall}
            disabled={installing}
            style={{
              marginTop: 10,
              background: "#7c3aed",
              color: "#fff",
              border: "none",
              borderRadius: 8,
              padding: "7px 16px",
              fontSize: 12,
              fontWeight: 700,
              cursor: installing ? "not-allowed" : "pointer",
              opacity: installing ? 0.6 : 1,
              letterSpacing: "0.04em",
            }}
          >
            {installing ? "Installing..." : "Install App"}
          </button>
        )}
      </div>

      {/* Dismiss */}
      <button
        onClick={() => setShow(false)}
        style={{
          background: "none", border: "none", color: "#475569",
          fontSize: 18, cursor: "pointer", padding: "0 2px",
          lineHeight: 1, flexShrink: 0,
        }}
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}
