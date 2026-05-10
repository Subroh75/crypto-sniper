"""Arbitrum One agent — Camelot / Uniswap V3 primary DEX."""
from dex_scanner.base_agent import ChainAgent

class ARBAgent(ChainAgent):
    chain_id    = "arbitrum"
    chain_name  = "Arbitrum"
    goplus_id   = "42161"
    gecko_net   = "arbitrum"
    dex_name    = "Camelot"
    min_liq     = 75_000
    min_vol     = 150_000
    min_age_h   = 48
    min_txns_1h = 40
