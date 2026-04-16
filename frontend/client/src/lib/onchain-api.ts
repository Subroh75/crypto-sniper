// On-chain analysis API — calls the same Render backend as the rest of crypto.guru
const API_BASE = import.meta.env.VITE_API_BASE ?? "https://crypto-sniper-api.onrender.com";

export type Chain = "ethereum" | "solana";

export interface HolderData {
  rank: number;
  address: string;
  balance: number;
  percentage: number;
  firstBuyDate: string;
  lastActivityDate: string;
  transactions: number;
  walletAgeMonths: number;
  isContract: boolean;
  label?: string;
}

export interface AnalysisResult {
  tokenName: string;
  tokenSymbol: string;
  contractAddress: string;
  chain: Chain;
  totalHolders: number;
  totalSupply: number;
  top10Percentage: number;
  top20Percentage: number;
  riskLevel: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  holders: HolderData[];
  walletAgeDistribution: { label: string; count: number }[];
  concentrationScore: number;
  analysisTimestamp: string;
}

export async function analyzeToken(address: string, chain: Chain): Promise<AnalysisResult> {
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address, chain }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}
