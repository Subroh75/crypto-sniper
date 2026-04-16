import { useState } from "react";
import { Search, Loader2, AlertTriangle, ChevronDown, Crosshair } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { analyzeToken } from "@/lib/onchain-api";
import type { AnalysisResult, Chain } from "@/lib/onchain-api";
import { Logo } from "@/components/Logo";
import { RiskAlert } from "@/components/onchain/RiskAlert";
import { KpiCards } from "@/components/onchain/KpiCards";
import { HolderPieChart } from "@/components/onchain/HolderPieChart";
import { WalletAgeChart } from "@/components/onchain/WalletAgeChart";
import { HoldersTable } from "@/components/onchain/HoldersTable";
import { Link } from "wouter";

const DEMOS: { label: string; address: string; chain: Chain }[] = [
  { label: "USDC",   address: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", chain: "ethereum" },
  { label: "UNI",    address: "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", chain: "ethereum" },
  { label: "Random", address: "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9", chain: "ethereum" },
  { label: "SPL",    address: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", chain: "solana" },
];

function SectionLabel({ num, label }: { num: string; label: string }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <span className="text-xs font-bold text-purple-DEFAULT font-mono tracking-widest">{num}</span>
      <span className="w-px h-3 bg-border" />
      <span className="text-xs font-semibold uppercase tracking-widest text-text-muted">{label}</span>
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="h-16 bg-surface-2 rounded-xl" />
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5">
        {[...Array(6)].map((_, i) => <div key={i} className="h-24 bg-surface-2 rounded-xl" />)}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="h-72 bg-surface-2 rounded-xl" />
        <div className="h-72 bg-surface-2 rounded-xl" />
      </div>
      <div className="h-96 bg-surface-2 rounded-xl" />
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 text-center">
      <div className="w-16 h-16 mb-6 relative">
        <svg viewBox="0 0 64 64" fill="none" className="w-full h-full">
          <polygon points="32,4 56,18 56,46 32,60 8,46 8,18" stroke="rgba(124,58,237,0.3)" strokeWidth="1.5" fill="none" />
          <circle cx="32" cy="32" r="10" stroke="#38bdf8" strokeWidth="1.5" fill="none" opacity="0.7" />
          <line x1="32" y1="16" x2="32" y2="22" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
          <line x1="32" y1="42" x2="32" y2="48" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
          <line x1="16" y1="32" x2="22" y2="32" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
          <line x1="42" y1="32" x2="48" y2="32" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" opacity="0.7" />
          <circle cx="32" cy="32" r="2.5" fill="#38bdf8" opacity="0.9" />
        </svg>
      </div>
      <p className="text-sm font-semibold text-text mb-1">Paste a Token Contract Address</p>
      <p className="text-xs text-text-muted max-w-xs mb-6">
        Analyze holder concentration, wallet ages, first buy-in dates, and on-chain risk signals on Ethereum or Solana.
      </p>
      <div className="flex flex-wrap gap-2 justify-center max-w-md">
        {["Top 20 Holders", "Concentration Chart", "First Buy Dates", "Risk Flagging", "Wallet Age", "TX History"].map(f => (
          <span key={f} className="text-xs px-3 py-1.5 rounded-full border border-border/50 text-text-faint bg-surface-2">{f}</span>
        ))}
      </div>
    </div>
  );
}

export default function OnChain() {
  const [address, setAddress] = useState("");
  const [chain, setChain] = useState<Chain>("ethereum");

  const mutation = useMutation({
    mutationFn: ({ addr, ch }: { addr: string; ch: Chain }) => analyzeToken(addr, ch),
  });

  const handleAnalyze = () => {
    if (!address.trim()) return;
    mutation.mutate({ addr: address.trim(), ch: chain });
  };

  const runDemo = (addr: string, ch: Chain) => {
    setAddress(addr);
    setChain(ch);
    mutation.mutate({ addr, ch });
  };

  const result = mutation.data;

  return (
    <div className="min-h-screen bg-bg text-text">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-border/60 backdrop-blur-xl bg-bg/80">
        <div className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="flex items-center gap-2.5 hover:opacity-80 transition-opacity">
              <Logo size={28} />
              <span className="text-sm font-bold tracking-tight text-text">
                crypto<span className="gradient-text">.guru</span>
              </span>
            </Link>
            <span className="hidden sm:flex items-center gap-1.5 text-xs text-text-faint">
              <span className="w-px h-3 bg-border" />
              <Crosshair size={12} style={{ color: "#38bdf8" }} />
              <span style={{ color: "#38bdf8" }}>On-Chain</span>
            </span>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/" className="text-xs text-text-faint hover:text-text-muted transition-colors font-mono">
              ← Signal Engine
            </Link>
            <div className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-DEFAULT animate-pulse" />
              <span className="text-xs font-mono text-text-faint hidden sm:inline">API LIVE</span>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 pt-10 pb-16">
        {/* Hero */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold mb-2 gradient-text">On-Chain Analysis</h1>
          <p className="text-sm text-text-muted">
            Holder concentration · Wallet ages · First buy-in dates · Risk signals
          </p>
        </div>

        {/* Search bar */}
        <div className="max-w-3xl mx-auto mb-8">
          <div className="flex rounded-xl overflow-hidden border border-border bg-surface focus-within:border-purple-DEFAULT/50 transition-all">
            {/* Chain toggle */}
            <div className="flex border-r border-border shrink-0">
              <button
                data-testid="button-chain-ethereum"
                onClick={() => setChain("ethereum")}
                className={`flex items-center gap-1.5 px-3 py-3 text-xs font-semibold transition-colors ${
                  chain === "ethereum" ? "text-violet-DEFAULT bg-violet-DEFAULT/10" : "text-text-faint hover:text-text-muted"
                }`}>
                <span className="text-base">⬡</span>
                <span className="hidden sm:inline">ETH</span>
              </button>
              <button
                data-testid="button-chain-solana"
                onClick={() => setChain("solana")}
                className={`flex items-center gap-1.5 px-3 py-3 text-xs font-semibold transition-colors ${
                  chain === "solana" ? "text-purple-DEFAULT bg-purple-DEFAULT/10" : "text-text-faint hover:text-text-muted"
                }`}>
                <span className="text-base">◎</span>
                <span className="hidden sm:inline">SOL</span>
              </button>
            </div>

            <input
              data-testid="input-contract-address"
              type="text"
              value={address}
              onChange={e => setAddress(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleAnalyze()}
              placeholder={chain === "ethereum" ? "0x… Ethereum token contract address" : "Solana SPL token mint address"}
              className="flex-1 bg-transparent px-4 py-3 text-sm text-text placeholder:text-text-faint font-mono outline-none"
              autoComplete="off" spellCheck={false}
            />

            <button
              data-testid="button-analyze"
              onClick={handleAnalyze}
              disabled={!address.trim() || mutation.isPending}
              className="flex items-center gap-2 px-5 py-3 text-sm font-semibold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
              style={{ background: "linear-gradient(135deg, #7c3aed, #818cf8)" }}>
              {mutation.isPending
                ? <><Loader2 size={14} className="animate-spin" /><span className="hidden sm:inline">Scanning…</span></>
                : <><Search size={14} /><span className="hidden sm:inline">Analyze</span></>
              }
            </button>
          </div>

          {/* Demo pills */}
          <div className="mt-3 flex items-center gap-2 flex-wrap justify-center">
            <span className="text-xs text-text-faint">Try demo:</span>
            {DEMOS.map(d => (
              <button key={d.address}
                onClick={() => runDemo(d.address, d.chain)}
                className="text-xs px-2 py-1 rounded border border-border/50 text-text-faint hover:text-text-muted hover:border-purple-DEFAULT/30 transition-colors">
                {d.label}{d.chain === "solana" ? " (SOL)" : ""}
              </button>
            ))}
          </div>

          {mutation.isError && (
            <div className="mt-3 flex items-center gap-2 bg-red-DEFAULT/10 border border-red-DEFAULT/30 rounded-lg px-4 py-3">
              <AlertTriangle size={14} className="text-red-DEFAULT shrink-0" />
              <p className="text-xs text-red-DEFAULT">
                {mutation.error instanceof Error ? mutation.error.message : "Analysis failed. Check the address and try again."}
              </p>
            </div>
          )}
        </div>

        {/* Loading */}
        {mutation.isPending && <LoadingSkeleton />}

        {/* Results */}
        {result && !mutation.isPending && (
          <div className="space-y-4 animate-fadeIn">
            {/* Token identity */}
            <div className="section-card">
              <div className="flex items-center gap-3 flex-wrap">
                <div className="w-9 h-9 rounded-full border border-border/50 bg-surface-2 flex items-center justify-center font-bold text-sm gradient-text">
                  {result.tokenSymbol.slice(0, 2)}
                </div>
                <div>
                  <p className="text-sm font-bold text-text">{result.tokenName}</p>
                  <p className="text-xs font-mono text-text-faint">{result.contractAddress}</p>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  <span className="text-xs px-2 py-0.5 rounded-full border font-semibold uppercase tracking-wide"
                    style={result.chain === "ethereum"
                      ? { color: "#818cf8", borderColor: "rgba(129,140,248,0.3)", background: "rgba(129,140,248,0.08)" }
                      : { color: "#7c3aed", borderColor: "rgba(124,58,237,0.3)", background: "rgba(124,58,237,0.08)" }}>
                    {result.chain === "ethereum" ? "⬡ Ethereum" : "◎ Solana"}
                  </span>
                  <span className="text-xs text-text-faint font-mono">
                    {new Date(result.analysisTimestamp).toLocaleTimeString("en-AU")}
                  </span>
                </div>
              </div>
            </div>

            {/* Risk alert */}
            {result.top10Percentage > 40 && (
              <div className="section-card !p-0 overflow-hidden">
                <div className="p-5">
                  <SectionLabel num="01" label="Risk Alert" />
                  <RiskAlert result={result} />
                </div>
              </div>
            )}

            {/* KPIs */}
            <div className="section-card">
              <SectionLabel num={result.top10Percentage > 40 ? "02" : "01"} label="Key Metrics" />
              <KpiCards result={result} />
            </div>

            {/* Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <div className="section-card">
                <SectionLabel num={result.top10Percentage > 40 ? "03" : "02"} label="Holder Concentration" />
                <HolderPieChart result={result} />
              </div>
              <div className="section-card">
                <SectionLabel num={result.top10Percentage > 40 ? "04" : "03"} label="Wallet Age Distribution" />
                <WalletAgeChart result={result} />
              </div>
            </div>

            {/* Table */}
            <div className="section-card !p-0 overflow-hidden">
              <div className="p-5 pb-0">
                <SectionLabel num={result.top10Percentage > 40 ? "05" : "04"} label="Top 20 Holders" />
              </div>
              <HoldersTable result={result} />
            </div>
          </div>
        )}

        {!result && !mutation.isPending && <EmptyState />}
      </main>
    </div>
  );
}
