"""
Solana agent — Raydium / Orca primary DEXs.

Solana overrides:
  - GoPlus uses "solana" chain slug (not a numeric chain ID)
  - Contract addresses are base58 (not hex) — no normalisation needed,
    GoPlus handles both formats
  - GeckoTerminal network slug is "solana"
  - Lower liquidity floor — Solana retail is active at smaller pool sizes
"""
from dex_scanner.base_agent import ChainAgent

class SOLAgent(ChainAgent):
    chain_id    = "solana"
    chain_name  = "Solana"
    goplus_id   = "solana"
    gecko_net   = "solana"
    dex_name    = "Raydium"
    min_liq     = 50_000
    min_vol     = 100_000
    min_age_h   = 24        # Solana moves faster — 24h is sufficient seasoning
    min_txns_1h = 80        # Higher txn floor — Solana has many spam transactions
