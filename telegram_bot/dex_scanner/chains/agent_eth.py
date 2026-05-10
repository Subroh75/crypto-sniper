"""Ethereum mainnet agent — Uniswap V3 primary DEX."""
from dex_scanner.base_agent import ChainAgent

class ETHAgent(ChainAgent):
    chain_id    = "ethereum"
    chain_name  = "Ethereum"
    goplus_id   = "1"
    gecko_net   = "eth"
    dex_name    = "Uniswap V3"
    min_liq     = 150_000   # higher floor — gas cost filters small players
    min_vol     = 300_000
    min_age_h   = 48
    min_txns_1h = 30        # lower txn count — ETH trades are larger but fewer
