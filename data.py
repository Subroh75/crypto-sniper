# ── data.py PATCH ─────────────────────────────────────────────────────────────
# FIND this block in data.py and REPLACE with the block below.
# Only CG_ID changes — CAP_ID and everything else stays exactly as is.
#
# ── FIND (current) ────────────────────────────────────────────────────────────

CG_ID = {
    "BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin",
    "DOGE":"dogecoin","KAVA":"kava","PEPE":"pepe","WIF":"dogwifhat",
    "HYPE":"hyperliquid","RENDER":"render-token","MATIC":"matic-network",
    "ADA":"cardano","AVAX":"avalanche-2","LINK":"chainlink","DOT":"polkadot",
    "UNI":"uniswap","ATOM":"cosmos","LTC":"litecoin","XRP":"ripple",
}

# ── REPLACE WITH ──────────────────────────────────────────────────────────────

CG_ID = {
    # Original coins
    "BTC":"bitcoin","ETH":"ethereum","SOL":"solana","BNB":"binancecoin",
    "DOGE":"dogecoin","KAVA":"kava","PEPE":"pepe","WIF":"dogwifhat",
    "HYPE":"hyperliquid","RENDER":"render-token","MATIC":"matic-network",
    "ADA":"cardano","AVAX":"avalanche-2","LINK":"chainlink","DOT":"polkadot",
    "UNI":"uniswap","ATOM":"cosmos","LTC":"litecoin","XRP":"ripple",
    # Swarm universe — coins the signal swarm picks up that need analyse support
    "POL":"matic-network",          # Polygon (rebranded from MATIC)
    "POLY":"polymath-network",      # Polymath
    "JST":"just",                   # JUST (TRON ecosystem)
    "SUI":"sui",                    # Sui
    "INJ":"injective-protocol",     # Injective
    "TIA":"celestia",               # Celestia
    "WLD":"worldcoin-wld",          # Worldcoin
    "GRT":"the-graph",              # The Graph
    "OCEAN":"ocean-protocol",       # Ocean Protocol
    "PENDLE":"pendle",              # Pendle
    "GMX":"gmx",                    # GMX
    "LDO":"lido-dao",               # Lido DAO
    "KAITO":"kaito",                # Kaito
    "ONDO":"ondo-finance",          # Ondo Finance
    "TON":"the-open-network",       # Toncoin
    "TAO":"bittensor",              # Bittensor
    "FET":"fetch-ai",               # Fetch.ai
    "AAVE":"aave",                  # Aave
    "MKR":"maker",                  # Maker
    "RPL":"rocket-pool",            # Rocket Pool
    "CFG":"centrifuge",             # Centrifuge
    "SEI":"sei-network",            # Sei
    "APT":"aptos",                  # Aptos
    "ARB":"arbitrum",               # Arbitrum
    "OP":"optimism",                # Optimism
    "STX":"blockstack",             # Stacks
    "IMX":"immutable-x",            # Immutable X
    "MANTA":"manta-network",        # Manta Network
    "JUP":"jupiter-ag",             # Jupiter
    "PYTH":"pyth-network",          # Pyth Network
    "W":"wormhole",                 # Wormhole
    "STRK":"starknet",              # StarkNet
    "ENA":"ethena",                 # Ethena
    "ETHFI":"ether-fi",             # ether.fi
}
