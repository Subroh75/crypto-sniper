/**
 * ticker-contracts.ts
 * Maps common crypto ticker symbols to their canonical on-chain contract
 * addresses. Used to auto-populate the Fundamental panel contract input
 * when the user has searched a ticker in Technical mode.
 *
 * Rules:
 *  - Prefer the most liquid / widely-held contract for each ticker.
 *  - Native chains (ETH, SOL, BTC) map to their most common wrapped/pegged
 *    ERC-20 or SPL equivalent so holder analysis is meaningful.
 *  - Both uppercase and common variants are keyed.
 *  - chain: "ethereum" | "solana"
 */

export interface ContractInfo {
  address: string;
  chain: "ethereum" | "solana";
  /** Human-readable note shown in the pre-fill banner */
  label: string;
}

const TICKER_MAP: Record<string, ContractInfo> = {
  // ── Ethereum ERC-20s ────────────────────────────────────────────────────────
  USDC:  { address: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", chain: "ethereum", label: "USD Coin (USDC)" },
  USDT:  { address: "0xdac17f958d2ee523a2206206994597c13d831ec7", chain: "ethereum", label: "Tether (USDT)" },
  WBTC:  { address: "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", chain: "ethereum", label: "Wrapped BTC (WBTC)" },
  WETH:  { address: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", chain: "ethereum", label: "Wrapped Ether (WETH)" },
  UNI:   { address: "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", chain: "ethereum", label: "Uniswap (UNI)" },
  LINK:  { address: "0x514910771af9ca656af840dff83e8264ecf986ca", chain: "ethereum", label: "Chainlink (LINK)" },
  AAVE:  { address: "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9", chain: "ethereum", label: "Aave (AAVE)" },
  MKR:   { address: "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2", chain: "ethereum", label: "Maker (MKR)" },
  DAI:   { address: "0x6b175474e89094c44da98b954eedeac495271d0f", chain: "ethereum", label: "Dai (DAI)" },
  LDO:   { address: "0x5a98fcbea516cf06857215779fd812ca3bef1b32", chain: "ethereum", label: "Lido DAO (LDO)" },
  CRV:   { address: "0xd533a949740bb3306d119cc777fa900ba034cd52", chain: "ethereum", label: "Curve (CRV)" },
  COMP:  { address: "0xc00e94cb662c3520282e6f5717214004a7f26888", chain: "ethereum", label: "Compound (COMP)" },
  SNX:   { address: "0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f", chain: "ethereum", label: "Synthetix (SNX)" },
  BAL:   { address: "0xba100000625a3754423978a60c9317c58a424e3d", chain: "ethereum", label: "Balancer (BAL)" },
  SUSHI: { address: "0x6b3595068778dd592e39a122f4f5a5cf09c90fe2", chain: "ethereum", label: "SushiSwap (SUSHI)" },
  YFI:   { address: "0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e", chain: "ethereum", label: "Yearn Finance (YFI)" },
  GRT:   { address: "0xc944e90c64b2c07662a292be6244bdf05cda44a7", chain: "ethereum", label: "The Graph (GRT)" },
  ENS:   { address: "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72", chain: "ethereum", label: "Ethereum Name Service (ENS)" },
  APE:   { address: "0x4d224452801aced8b2f0aebe155379bb5d594381", chain: "ethereum", label: "ApeCoin (APE)" },
  SHIB:  { address: "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce", chain: "ethereum", label: "Shiba Inu (SHIB)" },
  PEPE:  { address: "0x6982508145454ce325ddbe47a25d4ec3d2311933", chain: "ethereum", label: "Pepe (PEPE)" },
  BLUR:  { address: "0x5283d291dbcf85356a21ba090e6db59121208b44", chain: "ethereum", label: "Blur (BLUR)" },
  IMX:   { address: "0xf57e7e7c23978c3caec3c3548e3d615c346e79ff", chain: "ethereum", label: "Immutable X (IMX)" },
  OP:    { address: "0x4200000000000000000000000000000000000042", chain: "ethereum", label: "Optimism (OP)" },
  ARB:   { address: "0xb50721bcf8d664c30412cfbc6cf7a15145234ad1", chain: "ethereum", label: "Arbitrum (ARB)" },

  // ── Native chains → best ERC-20 proxy for holder analysis ──────────────────
  // BTC: no ERC-20 native; use WBTC (most liquid wrapped version)
  BTC:   { address: "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", chain: "ethereum", label: "Wrapped BTC (WBTC) — proxy for BTC holders" },
  // ETH: use WETH (ERC-20 wrapper, meaningful holder distribution)
  ETH:   { address: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", chain: "ethereum", label: "Wrapped Ether (WETH) — proxy for ETH holders" },
  // BNB: BEP-20 on BSC; use ERC-20 pegged version
  BNB:   { address: "0xb8c77482e45f1f44de1745f52c74426c631bdd52", chain: "ethereum", label: "BNB (ERC-20)" },
  // XRP: use WXRP ERC-20
  XRP:   { address: "0x1d2f0da169ceb9fc7b3144628db156f3f6c60dbe", chain: "ethereum", label: "RXRP (ERC-20 pegged)" },

  // ── Solana SPL tokens ───────────────────────────────────────────────────────
  SOL:   { address: "So11111111111111111111111111111111111111112",  chain: "solana", label: "Wrapped SOL (wSOL)" },
  USDC_SOL: { address: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", chain: "solana", label: "USD Coin on Solana" },
  USDT_SOL: { address: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", chain: "solana", label: "Tether on Solana" },
  JUP:   { address: "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  chain: "solana", label: "Jupiter (JUP)" },
  BONK:  { address: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", chain: "solana", label: "Bonk (BONK)" },
  WIF:   { address: "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  chain: "solana", label: "dogwifhat (WIF)" },
  PYTH:  { address: "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3", chain: "solana", label: "Pyth Network (PYTH)" },
  JITO:  { address: "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn",  chain: "solana", label: "Jito Staked SOL (JitoSOL)" },
  RNDR:  { address: "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",   chain: "solana", label: "Render (RNDR) on Solana" },
  SAMO:  { address: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",  chain: "solana", label: "Samoyedcoin (SAMO)" },
  STEP:  { address: "StepAscQoEioFxxWGnh2sLBDFp9d8rvKz2Yp39iDpyT",   chain: "solana", label: "Step Finance (STEP)" },
  MNGO:  { address: "MangoCzJ36AjZyKwVj3VnYU4GTonjfVEnJmvvWaxLac",   chain: "solana", label: "Mango (MNGO)" },
};

/**
 * Look up a ticker symbol and return its canonical contract info, or null.
 * Case-insensitive. Strips common suffixes like /USDT, -USDT, USDT.
 */
export function lookupTicker(raw: string): ContractInfo | null {
  // Normalise: uppercase, strip exchange pair suffixes
  const sym = raw
    .toUpperCase()
    .replace(/[/\-_](USDT|USDC|BTC|ETH|BNB|BUSD|USD|PERP|SWAP)$/, "")
    .trim();

  return TICKER_MAP[sym] ?? null;
}
