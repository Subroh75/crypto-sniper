// ── AuthModal.tsx — Magic-link login flow ─────────────────────────────────────
import { useState, useEffect } from "react";
import type { AuthUser } from "@/types/api";

interface Props {
  open: boolean;
  onClose: () => void;
  onLogin:  (email: string) => Promise<{ sent?: boolean; error?: string; dev_link?: string | null; message: string }>;
  onVerify: (token: string) => Promise<{ verified?: boolean; error?: string; message?: string }>;
  user:     AuthUser | null;
  loading:  boolean;
  error:    string | null;
  linkSent: boolean;
  onLogout: () => void;
}

export function AuthModal({
  open, onClose,
  onLogin, onVerify,
  user, loading, error, linkSent, onLogout,
}: Props) {
  const [email,   setEmail]   = useState("");
  const [devLink, setDevLink] = useState<string | null>(null);
  const [sent,    setSent]    = useState(false);

  // Check URL for ?token= on mount (for magic-link redirect) — runs regardless of open state
  useEffect(() => {
    const hash   = window.location.hash; // e.g. #/auth?token=XXX
    const search = hash.split("?")[1];
    if (!search) return;
    const params = new URLSearchParams(search);
    const token  = params.get("token");
    if (token) {
      // Clean the token from the URL immediately
      window.history.replaceState(null, "", window.location.pathname + "#/");
      onVerify(token);
    }
  }, []); // eslint-disable-line

  if (!open) return null;

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    const res = await onLogin(email);
    if (res.sent) {
      setSent(true);
      if (res.dev_link) setDevLink(res.dev_link);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        className="relative w-full max-w-sm mx-4 rounded-2xl overflow-hidden border border-border/60"
        style={{ background: "var(--color-surface-card)" }}
      >
        {/* Top bar */}
        <div className="h-[3px]" style={{ background: "linear-gradient(90deg, #7c5cfc, #00d4aa)" }} />

        {/* Close */}
        <button
          onClick={onClose}
          className="absolute top-3 right-3 text-text-muted/60 hover:text-text-muted text-lg leading-none transition-colors"
        >
          ×
        </button>

        <div className="p-6">
          {user ? (
            /* ── Logged in ── */
            <div className="text-center">
              <div className="text-3xl mb-3">✅</div>
              <div className="text-[15px] font-black text-text mb-1">Logged in</div>
              <div className="text-[12px] font-mono text-text-muted mb-5">{user.email}</div>
              <div className="text-[10px] font-mono text-text-muted/60 leading-relaxed mb-6">
                Your watchlist and alerts are synced across sessions.
              </div>
              <button
                onClick={onLogout}
                className="w-full py-2.5 rounded-lg text-[12px] font-mono text-red border border-red/30 hover:bg-red/8 transition-all"
              >
                Log out
              </button>
            </div>
          ) : sent ? (
            /* ── Link sent ── */
            <div className="text-center">
              <div className="text-4xl mb-4">📬</div>
              <div className="text-[15px] font-black text-text mb-2">Check your inbox</div>
              <div className="text-[12px] font-mono text-text-muted mb-5">
                We sent a login link to <span className="text-purple">{email}</span>.
                It expires in 15 minutes.
              </div>
              {devLink && (
                <div className="mb-4 p-3 rounded-lg bg-amber/8 border border-amber/20">
                  <div className="text-[9px] font-mono text-amber/80 uppercase tracking-wide mb-1">
                    Dev mode — no SMTP configured
                  </div>
                  <a
                    href={devLink}
                    className="text-[10px] font-mono text-purple break-all hover:underline"
                  >
                    {devLink}
                  </a>
                </div>
              )}
              <button
                onClick={() => { setSent(false); setDevLink(null); }}
                className="text-[10px] font-mono text-text-muted/60 hover:text-text-muted"
              >
                Wrong email? Try again
              </button>
            </div>
          ) : (
            /* ── Login form ── */
            <>
              <div className="text-center mb-5">
                <div className="text-[11px] font-mono font-bold text-purple uppercase tracking-widest mb-2">
                  CRYPTO SNIPER
                </div>
                <div className="text-[17px] font-black text-text mb-1">Log in with email</div>
                <div className="text-[11px] font-mono text-text-muted leading-relaxed">
                  No password — we'll email you a magic link.
                  One click and you're in.
                </div>
              </div>

              <form onSubmit={handleSend} className="space-y-3">
                <input
                  type="email"
                  placeholder="your@email.com"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  required
                  className="w-full px-4 py-3 rounded-xl border border-border/50 bg-surface-2 text-text text-[13px] font-mono
                             placeholder:text-text-muted/40 focus:outline-none focus:border-purple/60 transition-colors"
                />
                {error && (
                  <div className="text-[10px] font-mono text-red px-3 py-2 rounded-lg bg-red/8 border border-red/20">
                    {error}
                  </div>
                )}
                <button
                  type="submit"
                  disabled={loading || !email}
                  className="w-full py-3 rounded-xl font-mono font-black text-[13px] text-white flex items-center justify-center gap-2 disabled:opacity-60 transition-all"
                  style={{
                    background: "linear-gradient(135deg, #7c5cfc, #5b3fd4)",
                    boxShadow: "0 4px 16px rgba(124,92,252,0.3)",
                  }}
                >
                  {loading ? "Sending…" : "✉ Send Login Link"}
                </button>
              </form>

              <div className="mt-5 pt-4 border-t border-border/30 flex items-center justify-center gap-4 flex-wrap">
                {[["🔒","No password"],["⚡","Instant access"],["🌍","No KYC"]].map(([ic,txt]) => (
                  <div key={txt} className="flex items-center gap-1 text-[9px] font-mono text-text-muted/50">
                    <span>{ic}</span><span>{txt}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── AuthButton — compact inline trigger ───────────────────────────────────────
export function AuthButton({
  user,
  onClick,
}: {
  user: AuthUser | null;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[10px] font-mono font-bold transition-all ${
        user
          ? "border-teal/30 bg-teal/8 text-teal hover:bg-teal/14"
          : "border-purple/30 bg-purple/8 text-purple hover:bg-purple/14"
      }`}
    >
      {user ? (
        <>
          <span className="text-xs">●</span>
          <span className="max-w-[100px] truncate">{user.email.split("@")[0]}</span>
        </>
      ) : (
        <>
          <span>⚡</span>
          <span>Log in</span>
        </>
      )}
    </button>
  );
}
