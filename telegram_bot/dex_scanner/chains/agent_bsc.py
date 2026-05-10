"""BSC / BNB Chain agent — PancakeSwap primary DEX."""
from dex_scanner.base_agent import ChainAgent

class BSCAgent(ChainAgent):
    chain_id    = "bsc"
    chain_name  = "BNB Chain"
    goplus_id   = "56"
    gecko_net   = "bsc"
    dex_name    = "PancakeSwap"
    min_liq     = 50_000
    min_vol     = 100_000
    min_age_h   = 48
    min_txns_1h = 50
