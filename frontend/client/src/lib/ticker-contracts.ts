/**
 * ticker-contracts.ts
 * Maps common crypto ticker symbols to their canonical on-chain contract
 * addresses. Used to auto-populate the Fundamental panel contract input
 * when the user has searched a ticker in Technical mode.
 *
 * Sources:
 *  - Ethereum ERC-20: Etherscan verified contracts / CoinGecko platforms
 *  - Solana SPL: Jupiter strict token list (token.jup.ag/strict)
 *  - BEP-20 (BNB Chain): Binance / CoinGecko verified
 *
 * Rules:
 *  - Prefer the most liquid / most-held contract per ticker.
 *  - Native L1s (BTC, ETH, SOL) map to their most common wrapped/pegged
 *    ERC-20 or SPL so holder analysis is meaningful.
 *  - Prefer Ethereum over other chains unless the token is Solana-native.
 *  - All addresses lowercase for Ethereum; exact-case for Solana.
 */

export interface ContractInfo {
  address: string;
  chain: "ethereum" | "solana";
  /** Human-readable note shown in the pre-fill banner */
  label: string;
}

const TICKER_MAP: Record<string, ContractInfo> = {

  // ── Native L1s → wrapped proxy ──────────────────────────────────────────────
  BTC:   { address: "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", chain: "ethereum", label: "Wrapped BTC (WBTC) — proxy for BTC" },
  ETH:   { address: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", chain: "ethereum", label: "Wrapped Ether (WETH) — proxy for ETH" },
  SOL:   { address: "So11111111111111111111111111111111111111112",  chain: "solana",   label: "Wrapped SOL (wSOL)" },

  // ── Stablecoins ─────────────────────────────────────────────────────────────
  USDT:  { address: "0xdac17f958d2ee523a2206206994597c13d831ec7", chain: "ethereum", label: "Tether USD (USDT)" },
  USDC:  { address: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", chain: "ethereum", label: "USD Coin (USDC)" },
  DAI:   { address: "0x6b175474e89094c44da98b954eedeac495271d0f", chain: "ethereum", label: "Dai (DAI)" },
  PYUSD: { address: "0x6c3ea9036406852006290770bedfcaba0e23a0e8", chain: "ethereum", label: "PayPal USD (PYUSD)" },
  USDS:  { address: "0xdc035d45d973e3ec169d2276ddab16f1e407384f", chain: "ethereum", label: "USDS (Sky Dollar)" },
  FRAX:  { address: "0x853d955acef822db058eb8505911ed77f175b99e", chain: "ethereum", label: "Frax (FRAX)" },
  LUSD:  { address: "0x5f98805a4e8be255a32880fdec7f6728c6568ba0", chain: "ethereum", label: "Liquity USD (LUSD)" },

  // ── Top ERC-20s by market cap ────────────────────────────────────────────────
  WBTC:  { address: "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599", chain: "ethereum", label: "Wrapped Bitcoin (WBTC)" },
  WETH:  { address: "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2", chain: "ethereum", label: "Wrapped Ether (WETH)" },
  STETH: { address: "0xae7ab96520de3a18e5e111b5eaab095312d7fe84", chain: "ethereum", label: "Lido Staked Ether (stETH)" },
  BNB:   { address: "0xb8c77482e45f1f44de1745f52c74426c631bdd52", chain: "ethereum", label: "BNB (ERC-20)" },
  SHIB:  { address: "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce", chain: "ethereum", label: "Shiba Inu (SHIB)" },
  LINK:  { address: "0x514910771af9ca656af840dff83e8264ecf986ca", chain: "ethereum", label: "Chainlink (LINK)" },
  UNI:   { address: "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984", chain: "ethereum", label: "Uniswap (UNI)" },
  AAVE:  { address: "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9", chain: "ethereum", label: "Aave (AAVE)" },
  MKR:   { address: "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2", chain: "ethereum", label: "Maker (MKR)" },
  LDO:   { address: "0x5a98fcbea516cf06857215779fd812ca3bef1b32", chain: "ethereum", label: "Lido DAO (LDO)" },
  ARB:   { address: "0xb50721bcf8d664c30412cfbc6cf7a15145234ad1", chain: "ethereum", label: "Arbitrum (ARB)" },
  OP:    { address: "0x4200000000000000000000000000000000000042", chain: "ethereum", label: "Optimism (OP)" },
  PEPE:  { address: "0x6982508145454ce325ddbe47a25d4ec3d2311933", chain: "ethereum", label: "Pepe (PEPE)" },
  CRV:   { address: "0xd533a949740bb3306d119cc777fa900ba034cd52", chain: "ethereum", label: "Curve (CRV)" },
  GRT:   { address: "0xc944e90c64b2c07662a292be6244bdf05cda44a7", chain: "ethereum", label: "The Graph (GRT)" },
  LRC:   { address: "0xbbbbca6a901c926f240b89eacb641d8aec7aeafd", chain: "ethereum", label: "Loopring (LRC)" },
  SNX:   { address: "0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f", chain: "ethereum", label: "Synthetix (SNX)" },
  COMP:  { address: "0xc00e94cb662c3520282e6f5717214004a7f26888", chain: "ethereum", label: "Compound (COMP)" },
  BAL:   { address: "0xba100000625a3754423978a60c9317c58a424e3d", chain: "ethereum", label: "Balancer (BAL)" },
  SUSHI: { address: "0x6b3595068778dd592e39a122f4f5a5cf09c90fe2", chain: "ethereum", label: "SushiSwap (SUSHI)" },
  YFI:   { address: "0x0bc529c00c6401aef6d220be8c6ea1667f6ad93e", chain: "ethereum", label: "Yearn Finance (YFI)" },
  ENS:   { address: "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72", chain: "ethereum", label: "Ethereum Name Service (ENS)" },
  APE:   { address: "0x4d224452801aced8b2f0aebe155379bb5d594381", chain: "ethereum", label: "ApeCoin (APE)" },
  BLUR:  { address: "0x5283d291dbcf85356a21ba090e6db59121208b44", chain: "ethereum", label: "Blur (BLUR)" },
  IMX:   { address: "0xf57e7e7c23978c3caec3c3548e3d615c346e79ff", chain: "ethereum", label: "Immutable X (IMX)" },
  ONDO:  { address: "0xfaba6f8e4a5e8ab82f62fe7c39859fa577269be3", chain: "ethereum", label: "Ondo Finance (ONDO)" },
  MNT:   { address: "0x3c3a81e81dc49a522a592e7622a7e711c06bf354", chain: "ethereum", label: "Mantle (MNT)" },
  INJ:   { address: "0xe28b3b32b6c345a34ff64674606124dd5aceca30", chain: "ethereum", label: "Injective (INJ)" },
  FET:   { address: "0xaea46a60368a7bd060eec7df8cba43b7ef41ad85", chain: "ethereum", label: "Fetch.ai (FET)" },
  "1INCH": { address: "0x111111111117dc0aa78b770fa6a738034120c302", chain: "ethereum", label: "1inch (1INCH)" },
  WOO:   { address: "0x4691937a7508860f876c9c0a2a617e7d9e945d4b", chain: "ethereum", label: "WOO Network (WOO)" },
  CBBTC: { address: "0xcbb7c0000ab88b473b1f5afd9ef808440eed33bf", chain: "ethereum", label: "Coinbase Wrapped BTC (cbBTC)" },

  // ── BNB Chain BEP-20 tokens (using BSC addresses) ──────────────────────────
  // Note: BSC chain is not yet supported by the /analyze endpoint (Ethereum only).
  // These are mapped to their ERC-20 equivalents where available,
  // or omitted if no meaningful ERC-20 proxy exists.
  // BNB itself uses the ERC-20 above.
  CAKE:  { address: "0x152649ea73beab28c5b49b26eb48f7ead6d4c898", chain: "ethereum", label: "PancakeSwap (CAKE) — ERC-20" },

  // ── Solana SPL tokens (from Jupiter strict list) ────────────────────────────
  JUP:   { address: "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",  chain: "solana", label: "Jupiter (JUP)" },
  BONK:  { address: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263", chain: "solana", label: "Bonk (BONK)" },
  WIF:   { address: "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  chain: "solana", label: "dogwifhat (WIF)" },
  PYTH:  { address: "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",  chain: "solana", label: "Pyth Network (PYTH)" },
  JTO:   { address: "jtojtomepa8beP8AuQc6eXt5FriJwfFMwQx2v2f9mCL",   chain: "solana", label: "Jito (JTO)" },
  RAY:   { address: "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  chain: "solana", label: "Raydium (RAY)" },
  W:     { address: "85VBFQZC9TZkfaptBWjvUw7YbZjy52A6mjtPGjstQAmQ",  chain: "solana", label: "Wormhole (W)" },
  RNDR:  { address: "rndrizKT3MK1iimdxRdWabcF7Zg7AR5T4nud4EkHBof",   chain: "solana", label: "Render (RNDR) on Solana" },
  KMNO:  { address: "KMNo3nJsBXfcpJTVhZcXLW7RmTwTt4GVFE7suUBo9sS",  chain: "solana", label: "Kamino (KMNO)" },
  DRIFT: { address: "DriFtupJYLTosbwoN8koMbEYSx54aFAVLddWsbksjwg7",  chain: "solana", label: "Drift Protocol (DRIFT)" },
  HNT:   { address: "hntyVP6YFm1Hg25TN9WGLqM12b8TQmcknKrdu1oxWux",  chain: "solana", label: "Helium (HNT)" },
  MOBILE:{ address: "mb1eu7TzEc71KxDpsmsKoucSSuuoGLv1drys1oP2jh6",  chain: "solana", label: "Helium Mobile (MOBILE)" },
  SAMO:  { address: "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",  chain: "solana", label: "Samoyedcoin (SAMO)" },
  STEP:  { address: "StepAscQoEioFxxWGnh2sLBDFp9d8rvKz2Yp39iDpyT",  chain: "solana", label: "Step Finance (STEP)" },
  MNGO:  { address: "MangoCzJ36AjZyKwVj3VnYU4GTonjfVEnJmvvWaxLac",  chain: "solana", label: "Mango (MNGO)" },

  // Solana stablecoins (canonical SPL mints)
  USDC_SOL: { address: "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", chain: "solana", label: "USD Coin on Solana" },
  USDT_SOL: { address: "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  chain: "solana", label: "Tether on Solana" },
};

/**
 * Look up a ticker symbol and return its canonical contract info, or null.
 * Case-insensitive. Strips common exchange pair suffixes (/USDT, -USDT, etc.)
 * and CEX-style prefixes (1000SHIB → SHIB).
 */
export function lookupTicker(raw: string): ContractInfo | null {
  const sym = raw
    .toUpperCase()
    // Strip exchange pair suffixes
    .replace(/[/\-_](USDT|USDC|BTC|ETH|BNB|BUSD|USD|PERP|SWAP|FUTURES)$/, "")
    // Strip CEX multiplier prefixes like 1000SHIB → SHIB
    .replace(/^1000/, "")
    .trim();

  return TICKER_MAP[sym] ?? null;
}

/** Returns all entries as an array, useful for building suggestion lists. */
export function allContracts(): Array<{ symbol: string } & ContractInfo> {
  return Object.entries(TICKER_MAP).map(([symbol, info]) => ({ symbol, ...info }));
}
