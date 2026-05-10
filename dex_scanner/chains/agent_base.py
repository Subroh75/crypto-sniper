"""Base (Coinbase L2) agent — Aerodrome primary DEX."""
from dex_scanner.base_agent import ChainAgent

class BASEAgent(ChainAgent):
    chain_id    = "base"
    chain_name  = "Base"
    goplus_id   = "8453"
    gecko_net   = "base"
    dex_name    = "Aerodrome"
    min_liq     = 75_000
    min_vol     = 150_000
    min_age_h   = 48
    min_txns_1h = 50
