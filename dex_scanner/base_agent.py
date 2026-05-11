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
            if r.get("label", "NO SIGNAL") in ("BUY", "STRONG BUY") and \
               r.get("risk", {}).get("level") in ("LOW", "MEDIUM"):
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
            }
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] analyse failed for {symbol}: {e}")
            return None

    # ────────────────────────────────────────────────────────────────────────
    # INTERNAL: fetch trending pools from GeckoTerminal + DexScreener fallback
    # ────────────────────────────────────────────────────────────────────────
    async def _get_candidates(self, session: aiohttp.ClientSession) -> list[dict]:
        """
        Primary:  GeckoTerminal trending_pools per network (no rate limit on this endpoint)
        Fallback: DexScreener token-boosts/top/v1 (cross-chain, filter by chain)

        Both routes resolve to normalised pair dicts via DexScreener for
        consistent market data fields.
        """
        raw_addresses: list[str] = []

        # ── Primary: GeckoTerminal trending pools ──────────────────────────
        try:
            url = f"https://api.geckoterminal.com/api/v2/networks/{self.gecko_net}/trending_pools?page=1"
            async with session.get(
                url,
                headers={"Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=12)
            ) as r:
                if r.status == 200:
                    data = await r.json()
                    for pool in (data.get("data") or []):
                        attrs   = pool.get("attributes", {})
                        address = attrs.get("address", "")
                        # We want the base token address, not the pool address
                        # Get it from pool relationships
                        rels = pool.get("relationships", {})
                        base_token = rels.get("base_token", {}).get("data", {})
                        # GeckoTerminal token IDs are like "bsc_0xABCD..."
                        token_id = base_token.get("id", "")
                        if "_" in token_id:
                            raw_addresses.append(token_id.split("_", 1)[1])
                        elif address:
                            raw_addresses.append(address)
                    logger.debug(f"[{self.chain_id.upper()}] GeckoTerminal trending: {len(raw_addresses)} addresses")
        except Exception as e:
            logger.debug(f"[{self.chain_id.upper()}] GeckoTerminal trending failed: {e}")

        # ── Fallback: DexScreener token boosts ────────────────────────────
        if len(raw_addresses) < 5:
            try:
                async with session.get(
                    f"{DEXSCREENER}/token-boosts/top/v1",
                    timeout=aiohttp.ClientTimeout(total=12)
                ) as r:
                    if r.status == 200:
                        data = await r.json()
                        for item in (data if isinstance(data, list) else []):
                            if item.get("chainId", "").lower() == self.chain_id.lower():
                                addr = item.get("tokenAddress", "")
                                if addr and addr not in raw_addresses:
                                    raw_addresses.append(addr)
                        logger.debug(f"[{self.chain_id.upper()}] DexScreener boosts added — total {len(raw_addresses)}")
            except Exception as e:
                logger.debug(f"[{self.chain_id.upper()}] DexScreener boosts failed: {e}")

        if not raw_addresses:
            return []

        # ── Resolve addresses to full DexScreener pair data ───────────────
        sem = asyncio.Semaphore(4)

        async def resolve(addr):
            async with sem:
                await asyncio.sleep(0.1)
                return await self._resolve_address(session, addr)

        resolved_raw = await asyncio.gather(
            *[resolve(a) for a in raw_addresses[:25]],
            return_exceptions=True
        )

        resolved = [r for r in resolved_raw if isinstance(r, dict) and r is not None]

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
    No OHLCV available, so trend is proxied from multi-TF price alignment.

    V gate  (flat): rel_vol >= 1.2x  (1h vol vs hourly avg)
    T gate        : price rising across 3 TFs — 5m > 0, 1h > 0, 6h > 0
    ADX proxy     : >= 3 of 4 TFs positive (5m/1h/6h/24h) = "trending"

    BUY        = V + T + ADX proxy all confirmed
    STRONG BUY = BUY + P confirmed (1h > 1% AND 24h > 3%)
                     + R confirmed (buy-dominated, buy_ratio > 0.55)
    NO SIGNAL  = any gate fails
    """
    vol_24h  = market.get("volume_24h",  0)
    liq      = max(market.get("liquidity", 1), 1)
    buys_1h  = market.get("buys_1h",     0)
    sells_1h = market.get("sells_1h",    0)
    chg_5m   = market.get("change_5m",   0)
    chg_1h   = market.get("change_1h",   0)
    chg_6h   = market.get("change_6h",   0)
    chg_24h  = market.get("change_24h",  0)
    vol_h1   = market.get("vol_h1",      0)

    # ── Relative volume proxy (1h vol / hourly avg) ─────────────────────
    avg_hourly = vol_24h / 24 if vol_24h else 1
    rel_vol    = (vol_h1 / avg_hourly) if avg_hourly > 0 and vol_h1 > 0 else 1.0
    rel_vol    = round(rel_vol, 2)

    # ── V gate: flat — rel_vol >= 1.2x ─────────────────────────────────
    v_confirmed = rel_vol >= 1.2
    v_detail    = f"Vol: {rel_vol:.1f}x above average" if v_confirmed else f"Vol: {rel_vol:.1f}x — below threshold"

    # ── T gate: multi-TF trend alignment ───────────────────────────────
    # DEX has no EMAs — proxy: price rising in 5m, 1h, AND 6h
    t_confirmed = chg_5m > 0 and chg_1h > 0 and chg_6h > 0
    if t_confirmed:
        t_detail = "Trend: rising 5m · 1h · 6h"
    else:
        tfs_up   = [tf for tf, v in [("5m", chg_5m), ("1h", chg_1h), ("6h", chg_6h), ("24h", chg_24h)] if v > 0]
        tfs_down = [tf for tf, v in [("5m", chg_5m), ("1h", chg_1h), ("6h", chg_6h), ("24h", chg_24h)] if v <= 0]
        if tfs_up:
            t_detail = f"Trend: up on {' · '.join(tfs_up)} — down on {' · '.join(tfs_down)}"
        else:
            t_detail = "Trend: falling across all TFs"

    # ── ADX proxy: >= 3 of 4 TFs positive ──────────────────────────────
    tf_positive = sum(1 for v in [chg_5m, chg_1h, chg_6h, chg_24h] if v > 0)
    adx_proxy   = tf_positive >= 3
    adx_detail  = f"ADX proxy: {tf_positive}/4 TFs positive — {'trending' if adx_proxy else 'sideways'}"

    # ── P confirmation: strong momentum ────────────────────────────────
    p_confirmed = chg_1h > 1.0 and chg_24h > 3.0
    p_detail    = f"Momentum: 1h {chg_1h:+.1f}% · 24h {chg_24h:+.1f}%"

    # ── R confirmation: buy-dominated ──────────────────────────────────
    total_txns  = buys_1h + sells_1h
    buy_ratio   = buys_1h / total_txns if total_txns > 0 else 0.5
    r_confirmed = buy_ratio > 0.55
    r_detail    = f"Range: {buy_ratio*100:.0f}% buys in last 1h"

    # ── Signal tier ────────────────────────────────────────────────────
    buy_gates_met = v_confirmed and t_confirmed and adx_proxy
    if buy_gates_met and p_confirmed and r_confirmed:
        label = "STRONG BUY"
    elif buy_gates_met:
        label = "BUY"
    else:
        label = "NO SIGNAL"

    # ── Legacy score fields (kept for blackboard compat) ────────────────
    # Score reflects gates met: V(1) + T(1) + ADX(1) + P(1) + R(1) mapped to 0-13
    v = 3 if rel_vol >= 2.0 else (2 if rel_vol >= 1.5 else (1 if v_confirmed else 0))
    t = 3 if t_confirmed and adx_proxy else (2 if t_confirmed else (1 if adx_proxy else 0))
    p = 2 if p_confirmed and chg_24h >= 5 else (1 if p_confirmed else 0)
    r = 1 if r_confirmed else 0
    score = v + t + p + r

    # ── RSI / trend proxies (kept for blackboard display) ───────────────
    rsi_proxy = 50 + min(chg_24h * 2, 40)
    rsi_proxy = max(10, min(90, rsi_proxy))
    trend_strength = tf_positive * 25  # 0/25/50/75/100

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
    }


def _build_trade_setup(market: dict, signal: dict) -> dict:
    """
    Simple trade setup from current price + ATR-estimated range.
    Uses 24h high/low swing as ATR proxy.

    Entry:  current price
    Stop:   entry × (1 - 0.05)  (5% stop)
    Target: entry × (1 + 0.10)  (10% target, 2:1 R:R)
    """
    price = market.get("price", 0)
    if not price or signal.get("label", "NO SIGNAL") == "NO SIGNAL":
        return {}

    stop   = round(price * 0.95, 8)
    target = round(price * 1.10, 8)
    rr     = round((target - price) / (price - stop), 1) if price > stop else 2.0

    return {"entry": price, "stop": stop, "target": target, "rr": rr}
