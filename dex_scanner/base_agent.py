"""
dex_scanner/base_agent.py
─────────────────────────
ChainAgent base class — shared logic for all chain agents.

Each chain agent (BSC, BASE, ETH, SOL, ARB) inherits from this class
and provides chain-specific config. The scan() and analyse() methods
are identical for every chain — only the config differs.

Data sources (all free, no API key):
  DexScreener  — pair discovery, market data, buy/sell pressure
  GoPlus       — honeypot, contract risk, holder concentration
  GeckoTerminal — OHLCV candles for technical scoring
  calculate_signals() — existing VPRT scoring engine
"""

import asyncio
import aiohttp
import logging
import time
import sys
import os

# Allow importing from parent directory (signals.py, data.py etc.)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# ── API base URLs ─────────────────────────────────────────────────────────────
DEXSCREENER   = "https://api.dexscreener.com"
GOPLUS        = "https://api.gopluslabs.io/api/v1"
GECKOTERM     = "https://api.geckoterminal.com/api/v2"

# ── Stablecoin / wrapped token symbols to skip ────────────────────────────────
SKIP_SYMBOLS = {
    "USDT","USDC","BUSD","DAI","TUSD","FDUSD","USDP","USDD","FRAX","LUSD",
    "WBTC","WETH","WBNB","WBASE","WSOL","WMATIC","WAVAX",
    "STETH","CBETH","RETH","EZETH","WEETH","WSTETH",
}


class ChainAgent:
    """
    Base class for a single-chain DEX scanner agent.

    Subclasses set class-level config:
        chain_id     str   e.g. "bsc"         (DexScreener network slug)
        chain_name   str   e.g. "BNB Chain"
        goplus_id    str   e.g. "56"          (GoPlus chain ID)
        gecko_net    str   e.g. "bsc"         (GeckoTerminal network slug)
        dex_name     str   e.g. "PancakeSwap" (display only)
        min_liq      float minimum liquidity USD
        min_vol      float minimum 24h volume USD
        min_age_h    int   minimum pair age in hours
        min_txns_1h  int   minimum buy txns in last 1h
    """

    # ── Override in subclass ─────────────────────────────────────────────────
    chain_id:    str   = "unknown"
    chain_name:  str   = "Unknown"
    goplus_id:   str   = "1"
    gecko_net:   str   = "eth"
    dex_name:    str   = "Unknown DEX"
    min_liq:     float = 75_000
    min_vol:     float = 150_000
    min_age_h:   int   = 48
    min_txns_1h: int   = 50

    # ── Scoring threshold ────────────────────────────────────────────────────
    MIN_SCORE = 9

    # ────────────────────────────────────────────────────────────────────────
    # PUBLIC: sweep the chain, return list of blackboard entries
    # ────────────────────────────────────────────────────────────────────────
    async def scan(self, session: aiohttp.ClientSession, top_n: int = 5) -> list[dict]:
        """
        Full chain sweep:
        1. Fetch trending/top pairs from DexScreener
        2. Apply universe filter
        3. Run analyse() on each candidate (parallel, semaphore-limited)
        4. Return hits that pass score + risk thresholds
        """
        logger.info(f"[{self.chain_id.upper()}] Starting scan")
        pairs = await self._get_candidates(session)
        if not pairs:
            logger.warning(f"[{self.chain_id.upper()}] No candidates returned")
            return []

        logger.info(f"[{self.chain_id.upper()}] {len(pairs)} candidates after filter")

        sem = asyncio.Semaphore(3)

        async def bounded(pair):
            async with sem:
                return await self.analyse(session, pair)

        results = await asyncio.gather(
            *[bounded(p) for p in pairs[:30]],  # cap at 30 per chain per sweep
            return_exceptions=True
        )

        hits = []
        for r in results:
            if isinstance(r, Exception) or r is None:
                continue
            if r.get("score", 0) >= self.MIN_SCORE and r.get("risk", {}).get("level") in ("LOW", "MEDIUM"):
                hits.append(r)

        hits.sort(key=lambda x: (x["score"], x.get("change_1h", 0)), reverse=True)
        logger.info(f"[{self.chain_id.upper()}] {len(hits)} hits above threshold")
        return hits[:top_n]

    # ────────────────────────────────────────────────────────────────────────
    # PUBLIC: analyse a single token by address (for /gem command)
    # ────────────────────────────────────────────────────────────────────────
    async def analyse_address(self, session: aiohttp.ClientSession, address: str) -> dict | None:
        """Targeted single-token analysis — used by /gem <address> command."""
        pair = await self._resolve_address(session, address)
        if not pair:
            return None
        return await self.analyse(session, pair)

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL: full analysis pipeline for one pair
    # ────────────────────────────────────────────────────────────────────────
    async def analyse(self, session: aiohttp.ClientSession, pair: dict) -> dict | None:
        address     = pair.get("base_address", "")
        pool_address = pair.get("pool_address", "")
        symbol      = pair.get("symbol", "?")

        try:
            # Run market enrichment, risk check, and OHLCV in parallel
            market_task   = self._enrich_market(session, pair)
            risk_task     = self._check_risk(session, address)
            ohlcv_task    = self._get_ohlcv(session, pool_address)

            market, risk, ohlcv = await asyncio.gather(
                market_task, risk_task, ohlcv_task,
                return_exceptions=True
            )

            if isinstance(market, Exception): market = pair  # fallback to raw pair data
            if isinstance(risk,   Exception): risk   = _unknown_risk()
            if isinstance(ohlcv,  Exception): ohlcv  = []

            # Technical scoring
            signal = _score_ohlcv(ohlcv, market) if ohlcv else _empty_signal()

            return {
                "chain":        self.chain_id,
                "chain_name":   self.chain_name,
                "dex":          market.get("dex_id", self.dex_name),
                "symbol":       symbol,
                "address":      address,
                "pool_address": pool_address,
                "price":        market.get("price", 0),
                "change_5m":    market.get("change_5m", 0),
                "change_1h":    market.get("change_1h", 0),
                "change_6h":    market.get("change_6h", 0),
                "change_24h":   market.get("change_24h", 0),
                "volume_24h":   market.get("volume_24h", 0),
                "liquidity":    market.get("liquidity", 0),
                "pair_age_h":   market.get("pair_age_h", 0),
                "buys_1h":      market.get("buys_1h", 0),
                "sells_1h":     market.get("sells_1h", 0),
                "score":        signal.get("score", 0),
                "signal":       signal.get("label", "NO SIGNAL"),
                "rsi":          signal.get("rsi", 0),
                "adx":          signal.get("adx", 0),
                "rel_vol":      signal.get("rel_vol", 0),
                "trade_setup":  signal.get("trade_setup", {}),
                "risk":         risk if isinstance(risk, dict) else _unknown_risk(),
                "agent":        self.chain_id.upper(),
                "scanned_at":   int(time.time()),
            }
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] analyse failed for {symbol}: {e}")
            return None

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL: fetch top trending pairs for this chain from DexScreener
    # ────────────────────────────────────────────────────────────────────────
    async def _get_candidates(self, session: aiohttp.ClientSession) -> list[dict]:
        """
        Fetches top pairs on this chain from DexScreener boosted/trending feed,
        applies universe filter, returns normalised pair dicts.
        """
        raw_pairs = []

        # Primary: token-boosts (trending/promoted tokens — high activity)
        try:
            async with session.get(
                f"{DEXSCREENER}/token-boosts/top/v1",
                timeout=aiohttp.ClientTimeout(total=12)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    for item in (data if isinstance(data, list) else []):
                        if item.get("chainId", "").lower() == self.chain_id.lower():
                            raw_pairs.append({"base_address": item.get("tokenAddress", "")})
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] boosts fetch failed: {e}")

        # Fallback: search top pairs by chain directly
        if len(raw_pairs) < 10:
            try:
                async with session.get(
                    f"{DEXSCREENER}/latest/dex/tokens/{self.chain_id}",
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        for p in (data.get("pairs") or []):
                            if p.get("chainId", "").lower() == self.chain_id.lower():
                                raw_pairs.append(self._normalise_pair(p))
            except Exception as e:
                logger.debug(f"[{self.chain_id.upper()}] chain pairs fetch failed: {e}")

        # Resolve any address-only entries to full pair data
        resolved = []
        for p in raw_pairs:
            if "price" not in p and p.get("base_address"):
                full = await self._resolve_address(session, p["base_address"])
                if full:
                    resolved.append(full)
            elif "price" in p:
                resolved.append(p)

        # Apply universe filter
        filtered = [p for p in resolved if self._passes_filter(p)]
        return filtered

    async def _resolve_address(self, session: aiohttp.ClientSession, address: str) -> dict | None:
        """Resolve a contract address to a full pair dict via DexScreener search."""
        try:
            async with session.get(
                f"{DEXSCREENER}/latest/dex/search?q={address}",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status != 200:
                    return None
                data = await r.json()
                pairs = data.get("pairs") or []
                # Find the pair on this chain with highest liquidity
                chain_pairs = [
                    p for p in pairs
                    if p.get("chainId", "").lower() == self.chain_id.lower()
                ]
                if not chain_pairs:
                    # Return best pair regardless of chain (for /gem cross-chain search)
                    chain_pairs = pairs
                if not chain_pairs:
                    return None
                best = max(chain_pairs, key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0))
                return self._normalise_pair(best)
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] resolve failed for {address}: {e}")
            return None

    async def _enrich_market(self, session: aiohttp.ClientSession, pair: dict) -> dict:
        """Re-fetch fresh market data for a specific pair (prices may have moved)."""
        pool = pair.get("pool_address", "")
        if not pool:
            return pair
        try:
            async with session.get(
                f"{DEXSCREENER}/latest/dex/pairs/{self.chain_id}/{pool}",
                timeout=aiohttp.ClientTimeout(total=8)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    pairs = data.get("pairs") or []
                    if pairs:
                        return self._normalise_pair(pairs[0])
        except Exception:
            pass
        return pair

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL: GoPlus risk check
    # ────────────────────────────────────────────────────────────────────────
    async def _check_risk(self, session: aiohttp.ClientSession, address: str) -> dict:
        """
        GoPlus Security API — checks honeypot, transfer tax, ownership,
        contract verification, mint function, proxy, and more.
        """
        if not address:
            return _unknown_risk()
        try:
            url = f"{GOPLUS}/token_security/{self.goplus_id}?contract_addresses={address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return _unknown_risk()
                data = await r.json()
                result = (data.get("result") or {}).get(address.lower()) or \
                         (data.get("result") or {}).get(address) or {}
                if not result:
                    return _unknown_risk()

                honeypot     = result.get("is_honeypot", "0") == "1"
                verified     = result.get("is_open_source", "0") == "1"
                mintable     = result.get("is_mintable", "0") == "1"
                proxy        = result.get("is_proxy", "0") == "1"
                blacklist    = result.get("is_blacklisted", "0") == "1"
                tax_pausable = result.get("trading_cooldown", "0") == "1"
                hidden_owner = result.get("hidden_owner", "0") == "1"
                renounced    = result.get("owner_address", "x") in ("", "0x0000000000000000000000000000000000000000")

                # Buy/sell tax
                buy_tax  = float(result.get("buy_tax",  0) or 0) * 100
                sell_tax = float(result.get("sell_tax", 0) or 0) * 100

                # Holder concentration
                holders = result.get("holders") or []
                top10_pct = sum(float(h.get("percent", 0)) * 100 for h in holders[:10])

                # Risk scoring
                flags = []
                if honeypot:          flags.append("HONEYPOT")
                if sell_tax > 10:     flags.append(f"HIGH SELL TAX {sell_tax:.0f}%")
                if buy_tax  > 10:     flags.append(f"HIGH BUY TAX {buy_tax:.0f}%")
                if mintable:          flags.append("MINTABLE")
                if hidden_owner:      flags.append("HIDDEN OWNER")
                if blacklist:         flags.append("BLACKLIST FUNCTION")
                if top10_pct > 80:    flags.append(f"TOP 10 HOLD {top10_pct:.0f}%")
                if not verified:      flags.append("UNVERIFIED CONTRACT")

                if honeypot or sell_tax > 20 or hidden_owner:
                    level = "CRITICAL"
                elif len(flags) >= 3 or top10_pct > 70 or sell_tax > 10:
                    level = "HIGH"
                elif len(flags) >= 1 or top10_pct > 50 or not renounced:
                    level = "MEDIUM"
                else:
                    level = "LOW"

                return {
                    "level":      level,
                    "honeypot":   honeypot,
                    "verified":   verified,
                    "renounced":  renounced,
                    "mintable":   mintable,
                    "buy_tax":    round(buy_tax, 1),
                    "sell_tax":   round(sell_tax, 1),
                    "top10_pct":  round(top10_pct, 1),
                    "flags":      flags,
                    "source":     "GoPlus",
                }
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] GoPlus failed for {address}: {e}")
            return _unknown_risk()

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL: GeckoTerminal OHLCV
    # ────────────────────────────────────────────────────────────────────────
    async def _get_ohlcv(self, session: aiohttp.ClientSession, pool_address: str) -> list:
        """Fetch 1h OHLCV candles from GeckoTerminal for a pool address."""
        if not pool_address:
            return []
        try:
            url = f"{GECKOTERM}/networks/{self.gecko_net}/pools/{pool_address}/ohlcv/hour"
            async with session.get(
                url,
                params={"limit": 100, "currency": "usd"},
                timeout=aiohttp.ClientTimeout(total=10)
            ) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                raw = (data.get("data") or {}).get("attributes", {}).get("ohlcv_list", [])
                # GeckoTerminal format: [ts, open, high, low, close, volume]
                # Reformat to match calculate_signals() expectation: [ts, o, h, l, c, v]
                return [[c[0], c[1], c[2], c[3], c[4], c[5]] for c in raw]
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] OHLCV failed for pool {pool_address}: {e}")
            return []

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL: normalise a raw DexScreener pair dict
    # ────────────────────────────────────────────────────────────────────────
    def _normalise_pair(self, p: dict) -> dict:
        base    = p.get("baseToken", {})
        liq     = p.get("liquidity") or {}
        vol     = p.get("volume")    or {}
        txns    = p.get("txns")      or {}
        chg     = p.get("priceChange") or {}
        txns_1h = txns.get("h1") or {}

        # Pair age in hours
        created_at = p.get("pairCreatedAt", 0) or 0
        age_h = (time.time() - created_at / 1000) / 3600 if created_at else 0

        symbol = f"{base.get('symbol','?')}/{(p.get('quoteToken') or {}).get('symbol','?')}"

        return {
            "symbol":       symbol,
            "base_address": base.get("address", ""),
            "pool_address": p.get("pairAddress", ""),
            "dex_id":       p.get("dexId", self.dex_name),
            "price":        float(p.get("priceUsd", 0) or 0),
            "change_5m":    float(chg.get("m5",  0) or 0),
            "change_1h":    float(chg.get("h1",  0) or 0),
            "change_6h":    float(chg.get("h6",  0) or 0),
            "change_24h":   float(chg.get("h24", 0) or 0),
            "volume_24h":   float(vol.get("h24", 0) or 0),
            "liquidity":    float(liq.get("usd",  0) or 0),
            "pair_age_h":   round(age_h, 1),
            "buys_1h":      int(txns_1h.get("buys",  0) or 0),
            "sells_1h":     int(txns_1h.get("sells", 0) or 0),
        }

    def _passes_filter(self, pair: dict) -> bool:
        sym = pair.get("symbol", "").split("/")[0].upper()
        if sym in SKIP_SYMBOLS:
            return False
        if pair.get("liquidity",  0) < self.min_liq:
            return False
        if pair.get("volume_24h", 0) < self.min_vol:
            return False
        if pair.get("pair_age_h", 0) < self.min_age_h:
            return False
        if pair.get("buys_1h",    0) < self.min_txns_1h:
            return False
        return True


# ── Helpers ────────────────────────────────────────────────────────────────────

def _unknown_risk() -> dict:
    return {
        "level": "UNKNOWN", "honeypot": None, "verified": None,
        "renounced": None, "mintable": None,
        "buy_tax": None, "sell_tax": None, "top10_pct": None,
        "flags": ["Risk data unavailable"], "source": "unavailable",
    }


def _empty_signal() -> dict:
    return {"score": 0, "label": "NO SIGNAL", "rsi": 0, "adx": 0, "rel_vol": 0, "trade_setup": {}}


def _score_ohlcv(ohlcv: list, market: dict) -> dict:
    """
    Run VPRT scoring on GeckoTerminal OHLCV candles using the existing
    calculate_signals() engine from signals.py.
    """
    try:
        from signals import calculate_signals

        # Build a minimal quote dict from market data
        quote = {
            "price":      market.get("price", 0),
            "change_24h": market.get("change_24h", 0),
            "volume_24h": market.get("volume_24h", 0),
            "high_24h":   0,
            "low_24h":    0,
        }

        # calculate_signals expects [[ts, o, h, l, c, v], ...]
        sig = calculate_signals(ohlcv, quote, {})

        # Trade setup
        setup = {}
        if sig.entry and sig.stop and sig.target:
            setup = {
                "entry":  sig.entry,
                "stop":   sig.stop,
                "target": sig.target,
                "rr":     sig.rr_ratio,
            }

        return {
            "score":      sig.total,
            "label":      sig.signal_label,
            "rsi":        sig.rsi,
            "adx":        sig.adx,
            "rel_vol":    sig.rel_volume,
            "trade_setup": setup,
        }
    except Exception as e:
        logger.debug(f"calculate_signals failed: {e}")
        return _empty_signal()
