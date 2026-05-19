"""
dex_scanner/base_agent.py
─────────────────────────
ChainAgent base class — shared logic for all chain agents.

Each chain agent (BSC, BASE, ETH, SOL, ARB) inherits from this class
and provides chain-specific config. The scan() and analyse() methods
are identical for every chain — only the config differs.

Data sources (all free, no API key):
  DexScreener  — pair discovery, market data, buy/sell pressure, price changes
  GoPlus       — honeypot, contract risk, holder concentration

Scoring: VPRT-inspired 4-factor score from DexScreener market fields.
  V — Volume score   (0–5): relative vol, buy/sell ratio, txn count
  P — Momentum score (0–3): price change 1h + 24h
  R — Range score    (0–2): above vs below key levels
  T — Trend score    (0–3): multi-timeframe momentum alignment

Total: 0–13 (same scale as CEX VPRT). STRONG BUY >= 9.

NOTE: GeckoTerminal OHLCV endpoint is rate-limited on the free tier and
unreliable for continuous sweeps. We score directly from DexScreener
market fields — faster, more reliable, zero rate-limit risk.
"""

import asyncio
import aiohttp
import logging
import time

logger = logging.getLogger(__name__)

# ── API base URLs ─────────────────────────────────────────────────────────────
DEXSCREENER = "https://api.dexscreener.com"
GOPLUS      = "https://api.gopluslabs.io/api/v1"

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
        gecko_net    str   e.g. "bsc"         (GeckoTerminal network slug — for trending pools)
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
    MIN_SCORE = 4  # gate-based: BUY needs V+T+ADX (score ~4+), STRONG BUY ~6+


    # ── Per-instance candidate cache (5 min TTL) ──────────────────────────
    _CANDIDATES_TTL: float = 300.0

    def __init__(self):
        """Initialise per-instance candidate cache."""
        self._candidates_cache: list = []
        self._candidates_ts: float = 0.0

    # ────────────────────────────────────────────────────────────────────────
    # PUBLIC: sweep the chain, return list of blackboard entries
    # ────────────────────────────────────────────────────────────────────────
    async def scan(self, session: aiohttp.ClientSession, top_n: int = 5) -> list[dict]:
        """
        Full chain sweep:
        1. Fetch trending pools from GeckoTerminal (trending pools endpoint works fine)
        2. Apply universe filter
        3. Enrich via DexScreener + GoPlus risk
        4. Score using VPRT-from-market-data
        5. Return hits that pass score + risk thresholds
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
            if r.get("signal", "NO SIGNAL") in ("BUY", "STRONG BUY") and \
               r.get("risk", {}).get("level") not in ("CRITICAL",):
                hits.append(r)

        hits.sort(key=lambda x: (x["score"], x.get("change_1h", 0)), reverse=True)
        logger.info(f"[{self.chain_id.upper()}] {len(hits)} hits above threshold")
        return hits[:top_n]

    # ────────────────────────────────────────────────────────────────────────
    # PUBLIC: vol-first scan — returns ALL pairs with rel_vol >= 1.8x
    # Used for the vol radar watch report when no BUY/STRONG BUY fires
    # ────────────────────────────────────────────────────────────────────────
    async def scan_vol_hits(self, session: aiohttp.ClientSession) -> list[dict]:
        """
        Returns all scored pairs with rel_vol >= 1.8x regardless of signal tier.
        Used to populate the DEX vol radar when no gems fire.
        Reuses the same _get_candidates() pipeline — no extra DexScreener calls.
        """
        pairs = await self._get_candidates(session)
        if not pairs:
            return []

        sem = asyncio.Semaphore(3)

        async def bounded(pair):
            async with sem:
                return await self.analyse(session, pair)

        results = await asyncio.gather(
            *[bounded(p) for p in pairs[:30]],
            return_exceptions=True
        )

        vol_hits = []
        for r in results:
            if isinstance(r, Exception) or r is None:
                continue
            # Include anything with unusual vol, skip CRITICAL risk
            if r.get("rel_vol", 0) >= 1.8 and                r.get("risk", {}).get("level") not in ("CRITICAL",):
                vol_hits.append(r)

        vol_hits.sort(key=lambda x: x.get("rel_vol", 0), reverse=True)
        return vol_hits[:15]

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
        address      = pair.get("base_address", "")
        pool_address = pair.get("pool_address", "")
        symbol       = pair.get("symbol", "?")

        try:
            # Run market refresh and risk check in parallel
            market_task = self._enrich_market(session, pair)
            risk_task   = self._check_risk(session, address)

            market, risk = await asyncio.gather(
                market_task, risk_task,
                return_exceptions=True
            )

            if isinstance(market, Exception):
                market = pair  # fallback to raw pair data
            if isinstance(risk, Exception):
                risk = _unknown_risk()

            # Score from market data (no OHLCV needed)
            signal = _score_market(market)

            setup = _build_trade_setup(market, signal)

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
                "score":        signal["score"],
                "signal":       signal["label"],
                "rsi":          signal.get("rsi_proxy", 0),
                "adx":          signal.get("trend_strength", 0),
                "rel_vol":      signal.get("rel_vol", 0),
                "trade_setup":  setup,
                "risk":         risk if isinstance(risk, dict) else _unknown_risk(),
                "agent":        self.chain_id.upper(),
                "scanned_at":   int(time.time()),
                # Z-score Phase 1 (display only — not blocking signals)
                "z_price":      signal.get("z_price", 0.0),
                "z_vol":        signal.get("z_vol", 0.0),
                "z_return":     signal.get("z_return", 0.0),
                "z_quality":    signal.get("z_quality", "UNKNOWN"),
                "z_detail":     signal.get("z_detail", ""),
            }
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] analyse failed for {symbol}: {e}")
            return None

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL: fetch trending pools from GeckoTerminal + DexScreener fallback
    # ────────────────────────────────────────────────────────────────────────
    async def _get_candidates(self, session: aiohttp.ClientSession) -> list[dict]:
        """
        Volume-first discovery using GeckoTerminal + DexScreener enrichment.

        Strategy:
          1. Fetch trending + top pools from GeckoTerminal for this chain
             (GeckoTerminal returns actual on-chain pool data with volume breakdown)
          2. Normalise each pool to our standard pair dict format
          3. Apply vol_spike screen: vol_h1 / (vol_h6/6) >= 1.8x
             + liquidity >= min_liq  + vol_24h >= min_vol  + age >= min_age_h
          4. Sort survivors by vol_spike descending
          5. Cap at 25 candidates for scoring
        """
        # Return cached candidates if fresh (avoids double GeckoTerminal hit when
        # scan() and scan_vol_hits() are both called in the same _run_agent cycle)
        now = time.monotonic()
        if self._candidates_cache and (now - self._candidates_ts) < self._CANDIDATES_TTL:
            logger.debug(f"[{self.chain_id.upper()}] Using cached candidates ({len(self._candidates_cache)})")
            return self._candidates_cache

        GECKO_BASE = "https://api.geckoterminal.com/api/v2"
        raw_pairs: list[dict] = []

        async def _fetch_gecko(endpoint: str) -> list[dict]:
            try:
                url = f"{GECKO_BASE}{endpoint}"
                async with session.get(
                    url,
                    headers={"Accept": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        return data.get("data") or []
            except Exception as e:
                logger.debug(f"[{self.chain_id.upper()}] GeckoTerminal {endpoint} failed: {e}")
            return []

        # Fetch trending pools and top volume pools in parallel
        results = await asyncio.gather(
            _fetch_gecko(f"/networks/{self.gecko_net}/trending_pools"),
            _fetch_gecko(f"/networks/{self.gecko_net}/pools?page=1&sort=h24_volume_desc"),
            return_exceptions=True
        )
        for res in results:
            if isinstance(res, list):
                raw_pairs.extend(res)

        # Normalise GeckoTerminal pool format to our pair dict
        seen_pools: set[str] = set()
        candidates: list[dict] = []

        for pool in raw_pairs:
            attrs   = pool.get("attributes", {})
            address = attrs.get("address", "").lower()
            name    = attrs.get("name", "")

            # Extract base token symbol from name (e.g. "CAKE / WBNB 0.25%" -> "CAKE")
            sym = name.split("/")[0].strip().split()[0].upper() if name else "?"
            if sym in SKIP_SYMBOLS:
                continue
            if not address or address in seen_pools:
                continue
            seen_pools.add(address)

            # Volume breakdown
            vol_usd  = attrs.get("volume_usd", {})
            vol_h24  = float(vol_usd.get("h24", 0) or 0)
            vol_h6   = float(vol_usd.get("h6",  0) or 0)
            vol_h1   = float(vol_usd.get("h1",  0) or 0)

            # Price changes
            chg      = attrs.get("price_change_percentage", {})
            chg_5m   = float(chg.get("m5",  0) or 0)
            chg_1h   = float(chg.get("h1",  0) or 0)
            chg_6h   = float(chg.get("h6",  0) or 0)
            chg_24h  = float(chg.get("h24", 0) or 0)

            # Transaction counts
            txns    = attrs.get("transactions", {})
            txns_1h = txns.get("h1", {})
            txns_24h = txns.get("h24", {})
            buys_1h  = int(txns_1h.get("buys",  0) or 0)
            sells_1h = int(txns_1h.get("sells", 0) or 0)
            buys_24h = int(txns_24h.get("buys",  0) or 0)
            sells_24h = int(txns_24h.get("sells", 0) or 0)

            # Liquidity + age
            liq      = float(attrs.get("reserve_in_usd", 0) or 0)
            created  = attrs.get("pool_created_at", "")
            age_h    = 0.0
            if created:
                try:
                    from datetime import datetime, timezone
                    ct = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    age_h = (datetime.now(timezone.utc) - ct).total_seconds() / 3600
                except Exception:
                    age_h = 999  # assume old if parse fails

            price = float(attrs.get("base_token_price_usd", 0) or 0)

            # Need base token address — available via relationships if included
            # For GoPlus risk check we use the pool address as fallback
            rels    = pool.get("relationships", {})
            base_tk = rels.get("base_token", {}).get("data", {})
            base_id = base_tk.get("id", "")  # format: "network_id/0xaddr"
            base_address = base_id.split("/")[-1] if "/" in base_id else address

            candidates.append({
                "symbol":       sym,
                "base_address": base_address,
                "pool_address": address,
                "dex_id":       self.dex_name,
                "price":        price,
                "change_5m":    chg_5m,
                "change_1h":    chg_1h,
                "change_6h":    chg_6h,
                "change_24h":   chg_24h,
                "volume_24h":   vol_h24,
                "vol_h6":       vol_h6,
                "vol_h1":       vol_h1,
                "liquidity":    liq,
                "pair_age_h":   round(age_h, 1),
                "buys_1h":      buys_1h,
                "sells_1h":     sells_1h,
                "buys_24h":     buys_24h,
                "sells_24h":    sells_24h,
            })

        logger.info(f"[{self.chain_id.upper()}] {len(candidates)} raw pools from GeckoTerminal")

        # ── Vol spike screen ─────────────────────────────────────────────────
        MIN_VOL_SPIKE = 1.8
        MIN_LIQ       = max(self.min_liq, 50_000)
        MIN_VOL_H1    = 5_000   # at least $5k in last 1h
        MIN_AGE_H     = self.min_age_h

        screened: list[tuple[float, dict]] = []
        for pair in candidates:
            vol_h6  = pair.get("vol_h6",  0)
            vol_h1  = pair.get("vol_h1",  0)
            vol_24h = pair.get("volume_24h", 0)
            liq     = pair.get("liquidity", 0)
            age_h   = pair.get("pair_age_h", 0)

            if liq < MIN_LIQ or vol_h1 < MIN_VOL_H1 or age_h < MIN_AGE_H:
                continue

            # Vol spike: 1h vs 6h hourly avg
            avg_hourly = vol_h6 / 6 if vol_h6 > 0 else (vol_24h / 24 if vol_24h > 0 else 0)
            if avg_hourly <= 0:
                continue
            vol_spike = vol_h1 / avg_hourly
            if vol_spike >= MIN_VOL_SPIKE:
                screened.append((vol_spike, pair))

        screened.sort(key=lambda x: x[0], reverse=True)
        filtered = [pair for _, pair in screened[:25]]

        logger.info(
            f"[{self.chain_id.upper()}] Vol screen: {len(candidates)} -> "
            f"{len(filtered)} passed {MIN_VOL_SPIKE}x gate"
        )

        # Cache the result for this scan cycle
        self._candidates_cache = filtered
        self._candidates_ts    = time.monotonic()

        # Fallback to DexScreener boosts if nothing cleared the vol gate
        if len(filtered) < 3:
            logger.info(f"[{self.chain_id.upper()}] Vol gate dry -- trying DexScreener boosts")
            boost_pairs: list[dict] = []
            for endpoint in ["/token-boosts/top/v1", "/token-boosts/latest/v1"]:
                try:
                    async with session.get(
                        f"{DEXSCREENER}{endpoint}",
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as r:
                        if r.status == 200:
                            data = await r.json()
                            for item in (data if isinstance(data, list) else []):
                                if item.get("chainId","").lower() == self.chain_id.lower():
                                    addr = item.get("tokenAddress","")
                                    if addr:
                                        resolved = await self._resolve_address(session, addr)
                                        if resolved and self._passes_filter(resolved):
                                            boost_pairs.append(resolved)
                            if boost_pairs:
                                break
                except Exception as e:
                    logger.debug(f"[{self.chain_id.upper()}] {endpoint} failed: {e}")
            filtered = (filtered + boost_pairs)[:25]

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
                data  = await r.json()
                pairs = data.get("pairs") or []

                # Prefer pairs on this chain
                chain_pairs = [
                    p for p in pairs
                    if p.get("chainId", "").lower() == self.chain_id.lower()
                ]

                # For /gem cross-chain lookup, fall back to any chain
                candidates = chain_pairs or pairs
                if not candidates:
                    return None

                best = max(
                    candidates,
                    key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0)
                )
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
                    data  = await r.json()
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
        contract verification, mint function, and more.
        """
        if not address:
            return _unknown_risk()
        try:
            url = f"{GOPLUS}/token_security/{self.goplus_id}?contract_addresses={address}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                if r.status != 200:
                    return _unknown_risk()
                data   = await r.json()
                result = (data.get("result") or {}).get(address.lower()) or \
                         (data.get("result") or {}).get(address) or {}
                if not result:
                    return _unknown_risk()

                honeypot     = result.get("is_honeypot",      "0") == "1"
                verified     = result.get("is_open_source",   "0") == "1"
                mintable     = result.get("is_mintable",       "0") == "1"
                blacklist    = result.get("is_blacklisted",    "0") == "1"
                hidden_owner = result.get("hidden_owner",      "0") == "1"
                renounced    = result.get("owner_address", "x") in (
                    "", "0x0000000000000000000000000000000000000000"
                )

                buy_tax  = float(result.get("buy_tax",  0) or 0) * 100
                sell_tax = float(result.get("sell_tax", 0) or 0) * 100

                holders   = result.get("holders") or []
                top10_pct = sum(float(h.get("percent", 0)) * 100 for h in holders[:10])

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
                    "level":     level,
                    "honeypot":  honeypot,
                    "verified":  verified,
                    "renounced": renounced,
                    "mintable":  mintable,
                    "buy_tax":   round(buy_tax,  1),
                    "sell_tax":  round(sell_tax, 1),
                    "top10_pct": round(top10_pct, 1),
                    "flags":     flags,
                    "source":    "GoPlus",
                }
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] GoPlus failed for {address}: {e}")
            return _unknown_risk()

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL: normalise a raw DexScreener pair dict
    # ────────────────────────────────────────────────────────────────────────
    def _normalise_pair(self, p: dict) -> dict:
        base    = p.get("baseToken",  {})
        liq     = p.get("liquidity")  or {}
        vol     = p.get("volume")     or {}
        txns    = p.get("txns")       or {}
        chg     = p.get("priceChange") or {}
        txns_1h = txns.get("h1") or {}

        created_at = p.get("pairCreatedAt", 0) or 0
        age_h      = (time.time() - created_at / 1000) / 3600 if created_at else 0

        symbol = (
            f"{base.get('symbol','?')}/"
            f"{(p.get('quoteToken') or {}).get('symbol','?')}"
        )

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
            "buys_24h":     int((txns.get("h24") or {}).get("buys",  0) or 0),
            "sells_24h":    int((txns.get("h24") or {}).get("sells", 0) or 0),
            "vol_h6":       float(vol.get("h6",  0) or 0),
            "vol_h1":       float(vol.get("h1",  0) or 0),
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
        "renounced": None,   "mintable": None,
        "buy_tax": None,     "sell_tax": None, "top10_pct": None,
        "flags": ["Risk data unavailable"], "source": "unavailable",
    }


def _score_market(market: dict) -> dict:
    """
    Gate-based VPRT signal from DexScreener market fields.
    No OHLCV available — trend proxied from multi-TF price alignment.

    V gate  (flat): rel_vol >= 1.8x  (1h vol vs 6h hourly avg)
                    Baseline: vol_h6/6  (responsive to recent activity)
                    Fallback: vol_24h/24 if vol_h6 unavailable

    T gate        : >= 2 of 3 short TFs rising (5m, 1h, 6h)
                    Requiring all 3 is too strict — normal oscillation
                    causes brief dips. 2/3 confirms real momentum.

    ADX proxy     : >= 3 of 4 TFs positive (5m/1h/6h/24h) = "trending"

    BUY        = V + T + ADX proxy all confirmed
    STRONG BUY = BUY + P confirmed (1h > 1% AND 24h > 3%)
                     + R confirmed (buy-dominated, buy_ratio > 0.55)
    NO SIGNAL  = any gate fails
    """
    vol_24h  = market.get("volume_24h",  0)
    vol_h6   = market.get("vol_h6",      0)
    vol_h1   = market.get("vol_h1",      0)
    buys_1h  = market.get("buys_1h",     0)
    sells_1h = market.get("sells_1h",    0)
    chg_5m   = market.get("change_5m",   0)
    chg_1h   = market.get("change_1h",   0)
    chg_6h   = market.get("change_6h",   0)
    chg_24h  = market.get("change_24h",  0)

    # ── Relative volume: 1h vs 6h hourly avg (fallback to 24h avg) ─────
    if vol_h6 > 0:
        avg_hourly = vol_h6 / 6
    elif vol_24h > 0:
        avg_hourly = vol_24h / 24
    else:
        avg_hourly = 1
    rel_vol = (vol_h1 / avg_hourly) if avg_hourly > 0 and vol_h1 > 0 else 1.0
    rel_vol = round(rel_vol, 2)

    # ── V gate: flat — rel_vol >= 1.8x (unusual volume required) ────────
    v_confirmed = rel_vol >= 1.8
    v_detail    = f"Vol: {rel_vol:.1f}x above average" if v_confirmed else f"Vol: {rel_vol:.1f}x (below 1.8x threshold)"

    # T gate: use ALL 4 TFs (5m/1h/6h/24h), need >= 2 positive to confirm trend
    # Including 24h means strong daily moves aren't killed by brief 5m/6h pullbacks
    tfs_label    = [("5m", chg_5m), ("1h", chg_1h), ("6h", chg_6h), ("24h", chg_24h)]
    all_tfs_up   = sum(1 for _, v in tfs_label if v > 0)
    t_confirmed  = all_tfs_up >= 2
    tfs_up   = [tf for tf, v in tfs_label if v > 0]
    tfs_down = [tf for tf, v in tfs_label if v <= 0]
    if t_confirmed:
        t_detail = f"Trend: rising {' / '.join(tfs_up)}" + (f" (down {' / '.join(tfs_down)})" if tfs_down else "")
    else:
        t_detail = f"Trend: only {all_tfs_up}/4 TFs rising -- weak"

    # ADX proxy: >= 3 of 4 TFs positive = strong directional trend
    tf_positive = all_tfs_up
    adx_proxy   = tf_positive >= 3
    adx_detail  = f"ADX proxy: {tf_positive}/4 TFs positive -- {'trending' if adx_proxy else 'sideways'}"
    # ── P confirmation: strong momentum ────────────────────────────────
    p_confirmed = chg_1h > 1.0 and chg_24h > 3.0
    p_detail    = f"Momentum: 1h {chg_1h:+.1f}% · 24h {chg_24h:+.1f}%"

    # ── R confirmation: buy-dominated txn flow ──────────────────────────
    total_txns  = buys_1h + sells_1h
    buy_ratio   = buys_1h / total_txns if total_txns > 0 else 0.5
    r_confirmed = buy_ratio > 0.55
    r_detail    = f"Range: {buy_ratio*100:.0f}% buys in last 1h"

    # ── Signal tier ─────────────────────────────────────────────────────
    buy_gates_met = v_confirmed and t_confirmed and adx_proxy
    if buy_gates_met and p_confirmed and r_confirmed:
        label = "STRONG BUY"
    elif buy_gates_met:
        label = "BUY"
    else:
        label = "NO SIGNAL"

    # ── Legacy score (0-13 scale for blackboard compat) ─────────────────
    v = 3 if rel_vol >= 3.5 else (2 if rel_vol >= 2.5 else (1 if v_confirmed else 0))
    t = 3 if t_confirmed and adx_proxy else (2 if t_confirmed else (1 if adx_proxy else 0))
    p = 2 if p_confirmed and chg_24h >= 5 else (1 if p_confirmed else 0)
    r = 1 if r_confirmed else 0
    score = v + t + p + r

    rsi_proxy      = 50 + min(chg_24h * 2, 40)
    rsi_proxy      = max(10, min(90, rsi_proxy))
    trend_strength = tf_positive * 25

    # ── Z-score proxies (Phase 1 — display only, no blocking) ───────────
    # DEX has no OHLCV candle data, so we use the 4-TF change array as a
    # distribution proxy. "Mean" = average of abs changes, "std" = spread.
    # z_price  : how far the 1h move is from the 24h mean move
    # z_vol    : how elevated current 1h vol is vs 6h hourly baseline
    # z_return : whether the 24h return is already exhausted vs historical
    changes = [chg_5m, chg_1h, chg_6h, chg_24h]
    mean_chg = sum(changes) / len(changes)
    std_chg  = (sum((c - mean_chg) ** 2 for c in changes) / len(changes)) ** 0.5
    z_price_dex  = round((chg_1h - mean_chg) / std_chg, 2) if std_chg > 0 else 0.0

    # z_vol: 1h vol vs 6h/6 baseline (rel_vol - 1) / 1  normalised
    z_vol_dex    = round((rel_vol - 1.0), 2)  # >0.5 = genuine spike, >1.5 = strong

    # z_return: 24h return vs mean of all TFs
    z_return_dex = round((chg_24h - mean_chg) / std_chg, 2) if std_chg > 0 else 0.0

    # Entry quality label
    good_z_price  = z_price_dex  <  2.0   # not extended
    good_z_vol    = z_vol_dex    >= 0.5   # genuine volume
    good_z_return = z_return_dex <  2.5   # not chasing
    quality_pts   = sum([good_z_price, good_z_vol, good_z_return])
    if quality_pts == 3:   z_quality_dex = "IDEAL"
    elif quality_pts == 2: z_quality_dex = "GOOD"
    elif quality_pts == 1: z_quality_dex = "CAUTION"
    else:                  z_quality_dex = "AVOID"

    z_detail_dex = f"PrZ {z_price_dex:+.1f} VolZ {z_vol_dex:+.1f} RetZ {z_return_dex:+.1f}"

    return {
        "score":          score,
        "label":          label,
        "gates": {
            "v":   v_confirmed,
            "t":   t_confirmed,
            "adx": adx_proxy,
        },
        "v_confirmed":    v_confirmed,
        "t_confirmed":    t_confirmed,
        "p_confirmed":    p_confirmed,
        "r_confirmed":    r_confirmed,
        "v_detail":       v_detail,
        "t_detail":       t_detail,
        "p_detail":       p_detail,
        "r_detail":       r_detail,
        "adx_detail":     adx_detail,
        "v_score":        v,
        "p_score":        p,
        "r_score":        r,
        "t_score":        t,
        "rsi_proxy":      round(rsi_proxy, 1),
        "trend_strength": trend_strength,
        "rel_vol":        rel_vol,
        # Z-score Phase 1 (display only)
        "z_price":        z_price_dex,
        "z_vol":          z_vol_dex,
        "z_return":       z_return_dex,
        "z_quality":      z_quality_dex,
        "z_detail":       z_detail_dex,
    }


def _build_trade_setup(market: dict, signal: dict) -> dict:
    """
    ATR-based trade setup.

    ATR proxy for DEX tokens = (high_24h - low_24h) / 4
    (conservative fraction of 24h range, analogous to 14-period ATR)

    Entry:  current price
    Stop:   entry - (1.5 x ATR)   capped at -15% max
    Target: entry + (2.5 x ATR)
    R:R:    target_dist / stop_dist
    """
    price  = market.get("price", 0)
    high   = market.get("high_24h", 0)
    low    = market.get("low_24h", 0)

    if not price or signal.get("label", "NO SIGNAL") == "NO SIGNAL":
        return {}

    # ATR proxy: use 24h range / 4 if both high and low are valid
    atr_proxy = 0.0
    if high > 0 and low > 0 and high > low:
        atr_proxy = (high - low) / 4.0

    if atr_proxy > 0 and atr_proxy < price * 0.40:   # sanity: ATR < 40% of price
        atr_stop   = price - 1.5 * atr_proxy
        atr_target = price + 2.5 * atr_proxy
        # Floor: stop never tighter than 10%, target never less than 20%
        stop   = round(max(atr_stop,   price * 0.90), 8)
        target = round(max(atr_target, price * 1.20), 8)
    else:
        # Fallback: 10% stop, 20% target (DEX tokens need room to breathe)
        stop   = round(price * 0.90, 8)
        target = round(price * 1.20, 8)

    risk   = price - stop
    reward = target - price
    rr     = round(reward / risk, 1) if risk > 0 else 2.0
    atr_pct = round(atr_proxy / price * 100, 2) if price > 0 else 0

    return {
        "entry":   price,
        "stop":    stop,
        "target":  target,
        "rr":      rr,
        "atr":     round(atr_proxy, 8),
        "atr_pct": atr_pct,
    }
