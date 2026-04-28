// ── On-Chain Intelligence Card ─────────────────────────────────────────────
// Section 13. Fetches supply/valuation data directly from CoinGecko's public
// API (CORS-open, no key required) so it works regardless of Render deploy
// state. DeFiLlama TVL is also fetched directly.

import { useState, useEffect, useRef } from "react";

// ── CoinGecko ID map ─────────────────────────────────────────────────────────
const CG_ID: Record<string, string> = {
  BTC:"bitcoin", ETH:"ethereum", SOL:"solana", BNB:"binancecoin",
  XRP:"ripple", ADA:"cardano", DOGE:"dogecoin", DOT:"polkadot",
  AVAX:"avalanche-2", LINK:"chainlink", UNI:"uniswap", ATOM:"cosmos",
  LTC:"litecoin", MATIC:"matic-network", PEPE:"pepe", WIF:"dogwifhat",
  HYPE:"hyperliquid", RENDER:"render-token", KAVA:"kava", SEI:"sei-network",
  SUI:"sui", APT:"aptos", ARB:"arbitrum", OP:"optimism",
  INJ:"injective-protocol", TIA:"celestia", BONK:"bonk", FET:"fetch-ai",
  NEAR:"near", ALGO:"algorand", ICP:"internet-computer", FIL:"filecoin",
  HBAR:"hedera-hashgraph", PENGU:"pudgy-penguins", TON:"the-open-network",
  SHIB:"shiba-inu", NOT:"notcoin", STRK:"starknet", LDO:"lido-dao",
  MKR:"maker", AAVE:"aave", CRV:"curve-dao-token", GMX:"gmx",
  JUP:"jupiter-exchange-solana", PYTH:"pyth-network", WLD:"worldcoin-wld",
  TAO:"bittensor", ENA:"ethena", COMP:"compound-governance-token",
  XMR:"monero", ETC:"ethereum-classic", BCH:"bitcoin-cash", TRX:"tron",
};

// ── DeFiLlama slug map ────────────────────────────────────────────────────────
const DFL_SLUG: Record<string, string> = {
  AAVE:"aave", UNI:"uniswap", COMP:"compound", MKR:"maker", CRV:"curve",
  LDO:"lido", ARB:"arbitrum", OP:"optimism", INJ:"injective", KAVA:"kava",
  JUP:"jupiter", ENA:"ethena", GMX:"gmx",
};

// ── Types ─────────────────────────────────────────────────────────────────────
interface OnChainSignal {
  type:   "positive" | "caution" | "risk";
  label:  string;
  detail: string;
}

interface OnChainState {
  loading:          boolean;
  error:            string | null;
  circulating:      number | null;
  total_supply:     number | null;
  max_supply:       number | null;
  supply_pct:       number | null;
  market_cap:       number | null;
  fdv:              number | null;
  mc_fdv_ratio:     number | null;
  volume_24h:       number | null;
  nvt:              number | null;
  tvl:              number | null;
  tvl_mc_ratio:     number | null;
  signals:          OnChainSignal[];
  risk_score:       number;
  sources:          string[];
}

const EMPTY: OnChainState = {
  loading: false, error: null,
  circulating: null, total_supply: null, max_supply: null, supply_pct: null,
  market_cap: null, fdv: null, mc_fdv_ratio: null,
  volume_24h: null, nvt: null, tvl: null, tvl_mc_ratio: null,
  signals: [], risk_score: 0, sources: [],
};

// ── Fetch helpers ─────────────────────────────────────────────────────────────
async function fetchCG(cgId: string): Promise<Record<string, unknown> | null> {
  try {
    const r = await fetch(
      `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=${cgId}&per_page=1&page=1&sparkline=false&price_change_percentage=24h`,
      { signal: AbortSignal.timeout(10000) }
    );
    if (!r.ok) return null;
    const data = await r.json();
    return Array.isArray(data) && data.length > 0 ? data[0] : null;
  } catch { return null; }
}

async function fetchDFL(slug: string): Promise<number | null> {
  try {
    const r = await fetch(`https://api.llama.fi/protocol/${slug}`, {
      signal: AbortSignal.timeout(8000),
    });
    if (!r.ok) return null;
    const data = await r.json();
    const tvl = data?.tvl;
    if (typeof tvl === "number") return tvl;
    if (Array.isArray(tvl) && tvl.length > 0) {
      return tvl[tvl.length - 1]?.totalLiquidityUSD ?? null;
    }
    return null;
  } catch { return null; }
}

// ── Derive signals ────────────────────────────────────────────────────────────
function deriveSignals(s: Partial<OnChainState>): { signals: OnChainSignal[]; risk_score: number } {
  const signals: OnChainSignal[] = [];
  let risk = 0;

  if (s.mc_fdv_ratio != null) {
    if (s.mc_fdv_ratio < 0.3) {
      signals.push({ type:"risk",     label:"High dilution risk",    detail:`MC/FDV = ${(s.mc_fdv_ratio*100).toFixed(0)}%` });
      risk += 2;
    } else if (s.mc_fdv_ratio < 0.6) {
      signals.push({ type:"caution",  label:"Moderate dilution",     detail:`MC/FDV = ${(s.mc_fdv_ratio*100).toFixed(0)}%` });
      risk += 1;
    } else {
      signals.push({ type:"positive", label:"Low dilution risk",     detail:`MC/FDV = ${(s.mc_fdv_ratio*100).toFixed(0)}%` });
    }
  }

  if (s.supply_pct != null) {
    if (s.supply_pct > 90) {
      signals.push({ type:"positive", label:"Supply mostly circulating", detail:`${s.supply_pct.toFixed(1)}% in circulation` });
    } else if (s.supply_pct < 40) {
      signals.push({ type:"risk",     label:"Large unreleased supply",   detail:`Only ${s.supply_pct.toFixed(1)}% circulating` });
      risk += 2;
    }
  }

  if (s.nvt != null) {
    if (s.nvt > 200) {
      signals.push({ type:"caution",  label:"Low on-chain activity",  detail:`NVT = ${s.nvt.toFixed(0)}x` });
      risk += 1;
    } else if (s.nvt < 30) {
      signals.push({ type:"positive", label:"High on-chain activity", detail:`NVT = ${s.nvt.toFixed(0)}x` });
    }
  }

  if (s.tvl_mc_ratio != null) {
    if (s.tvl_mc_ratio >= 1.0) {
      signals.push({ type:"positive", label:"TVL exceeds market cap", detail:`TVL/MC = ${s.tvl_mc_ratio.toFixed(2)}x — undervalued` });
    } else if (s.tvl_mc_ratio >= 0.3) {
      signals.push({ type:"positive", label:"Strong TVL backing",     detail:`TVL/MC = ${s.tvl_mc_ratio.toFixed(2)}x` });
    }
  }

  return { signals, risk_score: Math.min(100, risk * 20) };
}

// ── Shared card primitives (must match home.tsx exactly) ───────────────────
function Card({ children, className = "", id }: {
  children: React.ReactNode; className?: string; id?: string;
}) {
  return (
    <div id={id} className={`rounded-xl border border-border/60 bg-surface-card overflow-hidden mb-3 ${className}`}>
      {children}
    </div>
  );
}

function CardHeader({ num, icon, title, badge, src, right }: {
  num?: string; icon?: string; title: string; badge?: string;
  src?: string; right?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-border/50">
      <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.1em] text-text-muted">
        {num  && <span className="text-purple">{num}</span>}
        {icon && <span>{icon}</span>}
        <span>{title}</span>
        {badge && (
          <span className="text-[8px] font-bold px-1.5 py-0.5 rounded bg-orange/10 text-orange border border-orange/15 uppercase tracking-wide">
            {badge}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        {right}
        {src && (
          <span className="text-[9px] font-mono text-text-muted/60 px-2 py-0.5 rounded bg-surface-2 border border-border/40">
            {src}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────
function SignalBadge({ signal }: { signal: OnChainSignal }) {
  const cfg = {
    positive: { text:"text-teal",  bg:"bg-teal/8  border-teal/20"  },
    caution:  { text:"text-amber", bg:"bg-amber/8 border-amber/20" },
    risk:     { text:"text-red",   bg:"bg-red/8   border-red/20"   },
  }[signal.type];
  const icon = signal.type === "positive" ? "▲" : signal.type === "risk" ? "▼" : "●";
  return (
    <div className={`flex items-start gap-2 px-3 py-2 rounded-lg border ${cfg.bg}`}>
      <span className={`text-[10px] font-mono font-bold ${cfg.text} shrink-0 mt-[1px]`}>{icon}</span>
      <div className="min-w-0">
        <div className={`text-[11px] font-mono font-bold ${cfg.text}`}>{signal.label}</div>
        <div className="text-[10px] text-text-muted/70 leading-relaxed">{signal.detail}</div>
      </div>
    </div>
  );
}

function Row({ label, value, valueClass = "text-text" }: {
  label: string; value: React.ReactNode; valueClass?: string;
}) {
  return (
    <div className="flex items-center justify-between py-1.5 border-b border-border/20 last:border-none">
      <span className="text-[10px] font-mono text-text-muted/60 uppercase tracking-wide">{label}</span>
      <span className={`text-[11px] font-mono font-bold ${valueClass}`}>{value}</span>
    </div>
  );
}

function MiniBar({ pct, color }: { pct: number; color: string }) {
  return (
    <div className="w-full h-[3px] bg-surface-2 rounded-full overflow-hidden mt-1">
      <div className="h-full rounded-full transition-all duration-700" style={{ width:`${Math.min(100,pct)}%`, background:color }} />
    </div>
  );
}

function RiskGauge({ score }: { score: number }) {
  const color = score >= 60 ? "#ef4444" : score >= 40 ? "#f59e0b" : "#22c55e";
  const label = score >= 60 ? "HIGH RISK" : score >= 40 ? "MODERATE" : "LOW RISK";
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1">
        <div className="w-full h-2 bg-surface-2 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all duration-700" style={{ width:`${score}%`, background:color }} />
        </div>
      </div>
      <span className="text-[10px] font-mono font-bold whitespace-nowrap" style={{ color }}>{label}</span>
    </div>
  );
}

function fmtSupply(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1e12) return `${(n/1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `${(n/1e9).toFixed(2)}B`;
  if (n >= 1e6)  return `${(n/1e6).toFixed(2)}M`;
  if (n >= 1e3)  return `${(n/1e3).toFixed(2)}K`;
  return n.toFixed(0);
}

function fmtUsd(n: number | null): string {
  if (n == null) return "—";
  if (n >= 1e12) return `$${(n/1e12).toFixed(2)}T`;
  if (n >= 1e9)  return `$${(n/1e9).toFixed(2)}B`;
  if (n >= 1e6)  return `$${(n/1e6).toFixed(2)}M`;
  return `$${n.toFixed(0)}`;
}

// ── Main component ────────────────────────────────────────────────────────────
export function OnChainCard({ symbol }: { symbol: string | null }) {
  const [state, setState] = useState<OnChainState>({ ...EMPTY, loading: false });
  const prevSymbol = useRef<string | null>(null);

  useEffect(() => {
    if (!symbol || symbol === prevSymbol.current) return;
    prevSymbol.current = symbol;

    setState({ ...EMPTY, loading: true });

    const cgId = CG_ID[symbol.toUpperCase()];
    const dflSlug = DFL_SLUG[symbol.toUpperCase()];

    // Fire both fetches in parallel
    Promise.all([
      cgId ? fetchCG(cgId) : Promise.resolve(null),
      dflSlug ? fetchDFL(dflSlug) : Promise.resolve(null),
    ]).then(([cg, tvlRaw]) => {
      const partial: Partial<OnChainState> = { loading: false, error: null, sources: [] };

      if (cg) {
        partial.sources!.push("CoinGecko");
        partial.circulating  = (cg.circulating_supply as number) ?? null;
        partial.total_supply = (cg.total_supply as number) ?? null;
        partial.max_supply   = (cg.max_supply as number) ?? null;

        const circ = partial.circulating;
        const maxs = partial.max_supply ?? partial.total_supply;
        if (circ && maxs && maxs > 0) {
          partial.supply_pct = Math.round((circ / maxs) * 1000) / 10;
        }

        partial.market_cap  = (cg.market_cap as number) ?? null;
        partial.fdv         = (cg.fully_diluted_valuation as number) ?? null;
        const mc  = partial.market_cap;
        const fdv = partial.fdv;
        if (mc && fdv && fdv > 0) {
          partial.mc_fdv_ratio = Math.round((mc / fdv) * 1000) / 1000;
        }

        partial.volume_24h = (cg.total_volume as number) ?? null;
        if (mc && partial.volume_24h && partial.volume_24h > 0) {
          partial.nvt = Math.round(mc / partial.volume_24h * 10) / 10;
        }
      } else {
        partial.error = cgId ? "CoinGecko unavailable" : "Symbol not mapped";
      }

      if (tvlRaw != null) {
        partial.sources!.push("DeFiLlama");
        partial.tvl = tvlRaw;
        const mc = partial.market_cap;
        if (mc && mc > 0 && tvlRaw > 0) {
          partial.tvl_mc_ratio = Math.round((tvlRaw / mc) * 1000) / 1000;
        }
      }

      const { signals, risk_score } = deriveSignals(partial);
      partial.signals    = signals;
      partial.risk_score = risk_score;

      setState(s => ({ ...s, ...partial }));
    });
  }, [symbol]);

  const src = state.sources.join(" · ") || "CoinGecko · DeFiLlama";
  const riskColor = state.risk_score >= 60 ? "#ef4444" : state.risk_score >= 40 ? "#f59e0b" : "#22c55e";
  const riskBg    = state.risk_score >= 60 ? "rgba(239,68,68,0.08)" : state.risk_score >= 40 ? "rgba(245,158,11,0.08)" : "rgba(34,197,94,0.08)";
  const riskBdr   = state.risk_score >= 60 ? "rgba(239,68,68,0.20)" : state.risk_score >= 40 ? "rgba(245,158,11,0.20)" : "rgba(34,197,94,0.20)";

  return (
    <Card>
      <CardHeader
        num="13"
        icon="⬡"
        title="ON-CHAIN INTELLIGENCE"
        badge="LIVE"
        src={src}
        right={
          state.market_cap != null ? (
            <span className="text-[9px] font-mono font-bold px-2 py-0.5 rounded border"
              style={{ color: riskColor, background: riskBg, borderColor: riskBdr }}>
              Risk {state.risk_score}/100
            </span>
          ) : undefined
        }
      />

      <div className="p-4">
        {/* Loading skeletons */}
        {state.loading && (
          <div className="space-y-2">
            {[...Array(6)].map((_,i) => (
              <div key={i} className="h-6 bg-surface-2 rounded animate-pulse border border-border/20" />
            ))}
          </div>
        )}

        {/* Not mapped */}
        {!state.loading && !symbol && (
          <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
            Run analysis to load on-chain data
          </div>
        )}

        {/* Not in CG map */}
        {!state.loading && symbol && state.market_cap == null && !state.loading && (
          <div className="text-center py-6 text-[11px] font-mono text-text-muted/60">
            {state.error ?? "On-chain data not available for this symbol"}
          </div>
        )}

        {/* Data */}
        {!state.loading && state.market_cap != null && (
          <div className="space-y-4">

            {/* Risk gauge */}
            <div className="px-0.5">
              <RiskGauge score={state.risk_score} />
            </div>

            {/* Supply */}
            <div>
              <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">Supply</div>
              <div className="space-y-0">
                <Row label="Circulating" value={fmtSupply(state.circulating)} />
                {state.total_supply != null && (
                  <Row label="Total supply" value={fmtSupply(state.total_supply)} valueClass="text-text-muted" />
                )}
                {state.max_supply != null && (
                  <Row label="Max supply" value={fmtSupply(state.max_supply)} valueClass="text-text-muted" />
                )}
                {state.supply_pct != null && (
                  <div className="py-1.5">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[10px] font-mono text-text-muted/60 uppercase tracking-wide">% Circulating</span>
                      <span className={`text-[11px] font-mono font-bold ${
                        state.supply_pct > 80 ? "text-teal" : state.supply_pct < 40 ? "text-red" : "text-amber"
                      }`}>{state.supply_pct.toFixed(1)}%</span>
                    </div>
                    <MiniBar
                      pct={state.supply_pct}
                      color={state.supply_pct > 80 ? "#22c55e" : state.supply_pct < 40 ? "#ef4444" : "#f59e0b"}
                    />
                  </div>
                )}
              </div>
            </div>

            {/* Valuation */}
            <div>
              <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">Valuation</div>
              <div className="space-y-0">
                <Row label="Market cap" value={fmtUsd(state.market_cap)} />
                {state.fdv != null && (
                  <Row label="Fully diluted" value={fmtUsd(state.fdv)} valueClass="text-text-muted" />
                )}
                {state.mc_fdv_ratio != null && (
                  <Row
                    label="MC / FDV"
                    value={`${(state.mc_fdv_ratio * 100).toFixed(0)}%`}
                    valueClass={state.mc_fdv_ratio >= 0.8 ? "text-teal" : state.mc_fdv_ratio >= 0.5 ? "text-amber" : "text-red"}
                  />
                )}
                {state.nvt != null && (
                  <Row
                    label="NVT proxy"
                    value={`${state.nvt.toFixed(0)}x`}
                    valueClass={state.nvt < 50 ? "text-teal" : state.nvt < 150 ? "text-amber" : "text-red"}
                  />
                )}
                {state.volume_24h != null && (
                  <Row label="24h volume" value={fmtUsd(state.volume_24h)} valueClass="text-text-muted" />
                )}
              </div>
            </div>

            {/* TVL (DeFi only) */}
            {state.tvl != null && (
              <div>
                <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">DeFi TVL</div>
                <div className="space-y-0">
                  <Row label="Total value locked" value={fmtUsd(state.tvl)} />
                  {state.tvl_mc_ratio != null && (
                    <Row
                      label="TVL / Market cap"
                      value={`${state.tvl_mc_ratio.toFixed(2)}x`}
                      valueClass={state.tvl_mc_ratio >= 1 ? "text-teal" : state.tvl_mc_ratio >= 0.3 ? "text-amber" : "text-text-muted"}
                    />
                  )}
                </div>
              </div>
            )}

            {/* Signals */}
            {state.signals.length > 0 && (
              <div>
                <div className="text-[9px] font-mono font-bold uppercase tracking-[0.12em] text-text-muted/50 mb-2">On-Chain Signals</div>
                <div className="space-y-1.5">
                  {state.signals.map((sig, i) => <SignalBadge key={i} signal={sig} />)}
                </div>
              </div>
            )}

          </div>
        )}
      </div>
    </Card>
  );
}
