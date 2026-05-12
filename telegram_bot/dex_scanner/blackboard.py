"""
dex_scanner/blackboard.py
──────────────────────────
Shared blackboard state + Telegram message compositor.

The blackboard is a simple in-memory list of hit dicts written by chain
agents. The compositor reads from it and formats the Telegram message.

Usage:
    board = Blackboard()
    board.write(hits)           # called by each chain agent
    msg   = board.compose()     # called once all agents done
    board.clear()               # reset for next sweep
"""

import time
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Chain display emoji map
CHAIN_EMOJI = {
    "bsc":      "🟡",  # BNB Chain yellow
    "base":     "🔵",  # Base blue
    "ethereum": "⬡",   # ETH
    "arbitrum": "🔷",  # ARB blue
    "solana":   "🟣",  # SOL purple
}

RISK_EMOJI = {
    "LOW":      "✅",
    "MEDIUM":   "⚠️",
    "HIGH":     "🔴",
    "CRITICAL": "☠️",
    "UNKNOWN":  "❓",
}

SCORE_BAR_LEN = 10


class Blackboard:
    """Thread-safe-ish in-memory blackboard for a single scan cycle."""

    def __init__(self):
        self._hits: list[dict] = []
        self._started_at = time.time()
        self._chain_status: dict[str, str] = {}  # chain_id → "pending"|"done"|"failed"

    def register_chain(self, chain_id: str):
        self._chain_status[chain_id] = "pending"

    def write(self, chain_id: str, hits: list[dict]):
        """Called by each chain agent when it completes."""
        self._hits.extend(hits)
        self._chain_status[chain_id] = "done"
        logger.info(f"[Blackboard] {chain_id.upper()} wrote {len(hits)} hits")

    def fail(self, chain_id: str):
        self._chain_status[chain_id] = "failed"
        logger.warning(f"[Blackboard] {chain_id.upper()} failed")

    def clear(self):
        self._hits.clear()
        self._chain_status.clear()
        self._started_at = time.time()

    def all_hits(self, top_n: int = 10) -> list[dict]:
        """Returns top N hits sorted by score desc, then 1h change desc."""
        sorted_hits = sorted(
            self._hits,
            key=lambda x: (x.get("score", 0), x.get("change_1h", 0)),
            reverse=True
        )
        return sorted_hits[:top_n]

    def summary(self) -> dict:
        chains_done   = sum(1 for s in self._chain_status.values() if s == "done")
        chains_failed = sum(1 for s in self._chain_status.values() if s == "failed")
        total_pairs   = len(self._hits)
        elapsed       = round(time.time() - self._started_at, 1)
        return {
            "chains_done":   chains_done,
            "chains_failed": chains_failed,
            "total_hits":    total_pairs,
            "elapsed_s":     elapsed,
        }

    # ────────────────────────────────────────────────────────────────────────
    # Telegram message composers
    # ────────────────────────────────────────────────────────────────────────

    def compose_sweep(self, top_n: int = 10, mode: str = "HOURLY") -> str:
        """Full sweep message — posted by the scanner job."""
        hits = self.all_hits(top_n)
        s    = self.summary()
        scan_time = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

        chains_active = [c for c, st in self._chain_status.items() if st == "done"]
        chain_str = " · ".join(c.upper() for c in chains_active)

        prefix = "DAILY" if mode == "DAILY" else "HOURLY"
        tf     = "1D" if mode == "DAILY" else "1H"

        header = (
            f"🔍 DEX GEM SCAN  —  {prefix}\n"
            f"{scan_time}  |  {tf}  |  Score 9+/13\n"
            f"Chains: {chain_str}\n"
            f"{'─' * 32}\n"
        )

        if not hits:
            return (
                header +
                f"No gems found this {prefix.lower()} sweep.\n"
                "Nothing passed risk + signal thresholds.\n"
                f"{'─' * 32}\n"
                "https://crypto-sniper.app\n"
                "Not financial advice."
            )

        header += f"🏆 {len(hits)} gem{'s' if len(hits) > 1 else ''} found\n"

        blocks = [_format_hit(hit, i) for i, hit in enumerate(hits, 1)]

        footer = (
            f"\n{'─' * 32}\n"
            f"Scanned {len(chains_active)} chains  ·  "
            f"{s['total_hits']} pairs passed filters  ·  {s['elapsed_s']}s\n"
            "https://crypto-sniper.app\n"
            "Not financial advice."
        )

        return header + "\n".join(blocks) + footer

    def compose_single(self, hit: dict) -> str:
        """Single token report — used by /gem command."""
        chain_emoji = CHAIN_EMOJI.get(hit.get("chain", ""), "🔗")
        chain_name  = hit.get("chain_name", hit.get("chain", "?").upper())
        dex         = hit.get("dex", "DEX")
        symbol      = hit.get("symbol", "?")
        address     = hit.get("address", "")
        addr_short  = f"{address[:6]}...{address[-4:]}" if len(address) > 12 else address

        header = (
            f"🔍 GEM REPORT\n"
            f"{chain_emoji} {chain_name}  ·  {dex}\n"
            f"{'─' * 32}\n"
            f"TOKEN: {symbol}\n"
            f"{addr_short}\n"
        )

        return header + _format_hit_detail(hit) + (
            f"\n{'─' * 32}\n"
            "Not financial advice."
        )


def compose_no_pair(address: str, supported_chains: list[str]) -> str:
    chains = " · ".join(c.upper() for c in supported_chains)
    short  = f"{address[:8]}...{address[-6:]}" if len(address) > 16 else address
    return (
        f"⚠️ No tradeable pair found\n"
        f"{short}\n\n"
        f"Either too new, unlisted, or on an unsupported chain.\n"
        f"Supported: {chains}"
    )


def compose_rate_limited(remaining_resets_at: str) -> str:
    return (
        "⚡ Daily limit reached\n\n"
        "You've used your 2 free gem scans today.\n"
        f"Resets at midnight UTC.\n\n"
        "Upgrade to Pro for unlimited scans:\n"
        "👉 /subscribe"
    )


# ── Private formatters ─────────────────────────────────────────────────────────

def _fmt_price(p: float) -> str:
    if p == 0:       return "$0"
    if p < 0.000001: return f"${p:.2e}"
    if p < 0.0001:   return f"${p:.8f}"
    if p < 0.01:     return f"${p:.6f}"
    if p < 1:        return f"${p:.4f}"
    if p < 1000:     return f"${p:.2f}"
    return f"${p:,.0f}"

def _fmt_vol(v: float) -> str:
    if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
    if v >= 1_000:     return f"${v/1_000:.0f}K"
    return f"${v:.0f}"

def _fmt_age(h: float) -> str:
    if h < 24:  return f"{h:.0f}h"
    return f"{h/24:.0f}d"

def _score_bar(score: int, max_score: int = 13) -> str:
    filled = round(score / max_score * SCORE_BAR_LEN)
    return "[" + "#" * filled + "-" * (SCORE_BAR_LEN - filled) + "]"

def _format_hit(hit: dict, rank: int) -> str:
    """Compact row format for sweep message."""
    chain_emoji = CHAIN_EMOJI.get(hit.get("chain", ""), "🔗")
    chain_name  = hit.get("chain_name", hit.get("chain","?").upper())
    score       = hit.get("score", 0)
    signal      = hit.get("signal", "")
    symbol      = hit.get("symbol", "?")
    price       = hit.get("price", 0)
    chg_1h      = hit.get("change_1h", 0)
    chg_24h     = hit.get("change_24h", 0)
    vol         = hit.get("volume_24h", 0)
    liq         = hit.get("liquidity", 0)
    age_h       = hit.get("pair_age_h", 0)
    rsi         = hit.get("rsi", 0)
    adx         = hit.get("adx", 0)
    rv          = hit.get("rel_vol", 0)
    risk        = hit.get("risk", {})
    risk_level  = risk.get("level", "UNKNOWN")
    risk_emoji  = RISK_EMOJI.get(risk_level, "❓")
    setup       = hit.get("trade_setup", {})

    v_detail   = hit.get("v_detail", f"Vol: {rv:.1f}x")
    t_detail   = hit.get("t_detail", f"Trend: ADX {adx:.0f}")
    z_quality  = hit.get("z_quality", "")
    z_detail   = hit.get("z_detail", "")

    block  = f"\n#{rank}  {symbol}  {chain_emoji} {chain_name}\n"
    block += f"Signal: {signal}\n"
    block += f"Price:  {_fmt_price(price)}  ({chg_1h:+.1f}% 1h  /  {chg_24h:+.1f}% 24h)\n"
    block += f"Vol:    {_fmt_vol(vol)}  Liq: {_fmt_vol(liq)}  Age: {_fmt_age(age_h)}\n"
    block += f"V: {v_detail}\n"
    block += f"T: {t_detail}\n"
    if z_quality and z_quality not in ("", "UNKNOWN"):
        q_icon = {"IDEAL": "\u2705", "GOOD": "\U0001f7e1", "CAUTION": "\U0001f7e0", "AVOID": "\U0001f534"}.get(z_quality, "\u26aa")
        block += f"Entry Q: {q_icon} {z_quality}  {z_detail}\n"
    block += f"Risk:   {risk_emoji} {risk_level}"

    if risk.get("flags"):
        flags = [f for f in risk["flags"] if f != "Risk data unavailable"]
        if flags:
            block += f"  [{', '.join(flags[:2])}]"

    block += "\n"

    if setup.get("entry") and setup.get("stop") and setup.get("target"):
        rr = setup.get("rr", 0)
        block += (
            f"Setup:  E {_fmt_price(setup['entry'])}  "
            f"SL {_fmt_price(setup['stop'])}  "
            f"TP {_fmt_price(setup['target'])}"
        )
        if rr:
            block += f"  R:R {rr:.1f}"
        block += "\n"

    return block


def _format_hit_detail(hit: dict) -> str:
    """Full detail format for /gem single-token report."""
    score   = hit.get("score", 0)
    signal  = hit.get("signal", "")
    price   = hit.get("price", 0)
    chg_5m  = hit.get("change_5m",  0)
    chg_1h  = hit.get("change_1h",  0)
    chg_6h  = hit.get("change_6h",  0)
    chg_24h = hit.get("change_24h", 0)
    vol     = hit.get("volume_24h", 0)
    liq     = hit.get("liquidity",  0)
    age_h   = hit.get("pair_age_h", 0)
    buys    = hit.get("buys_1h",    0)
    sells   = hit.get("sells_1h",   0)
    rsi     = hit.get("rsi",  0)
    adx     = hit.get("adx",  0)
    rv      = hit.get("rel_vol", 0)
    risk    = hit.get("risk", {})
    setup   = hit.get("trade_setup", {})

    risk_level = risk.get("level", "UNKNOWN")
    risk_emoji = RISK_EMOJI.get(risk_level, "❓")
    pressure   = "buy pressure" if buys > sells * 1.2 else "sell pressure" if sells > buys * 1.2 else "balanced"
    v_detail   = hit.get("v_detail",   f"Vol: {rv:.1f}x")
    t_detail   = hit.get("t_detail",   f"Trend strength {adx:.0f}")
    p_detail   = hit.get("p_detail",   "")
    adx_detail = hit.get("adx_detail", "")
    z_quality  = hit.get("z_quality", "")
    z_detail   = hit.get("z_detail",  "")
    z_price    = hit.get("z_price",   0.0)
    z_vol      = hit.get("z_vol",     0.0)
    z_return   = hit.get("z_return",  0.0)

    out  = f"\n── MARKET ──────────────────\n"
    out += f"Price:    {_fmt_price(price)}\n"
    out += f"Change:   {chg_5m:+.1f}% 5m  {chg_1h:+.1f}% 1h  {chg_6h:+.1f}% 6h  {chg_24h:+.1f}% 24h\n"
    out += f"Volume:   {_fmt_vol(vol)} 24h\n"
    out += f"Liq:      {_fmt_vol(liq)}  Age: {_fmt_age(age_h)}\n"
    if buys or sells:
        out += f"Txns 1h:  {buys} buys / {sells} sells  ({pressure})\n"

    out += f"\n── RISK  {risk_emoji} {risk_level} ──────────────\n"
    out += f"Honeypot:  {'CLEAR ✓' if risk.get('honeypot') == False else 'DETECTED ✗' if risk.get('honeypot') else '?'}\n"
    out += f"Contract:  {'Verified ✓' if risk.get('verified') else 'Unverified ✗' if risk.get('verified') == False else '?'}\n"
    out += f"Ownership: {'Renounced ✓' if risk.get('renounced') else 'Active ⚠' if risk.get('renounced') == False else '?'}\n"
    if risk.get("top10_pct") is not None:
        out += f"Top 10:    {risk['top10_pct']:.0f}% of supply\n"
    if risk.get("sell_tax") is not None:
        out += f"Tax:       Buy {risk.get('buy_tax',0):.0f}%  Sell {risk.get('sell_tax',0):.0f}%\n"
    if risk.get("flags"):
        flags = [f for f in risk["flags"] if f != "Risk data unavailable"]
        if flags:
            out += f"Flags:     {', '.join(flags)}\n"

    out += f"\n── SIGNAL  {signal} ─────────────\n"
    out += f"V: {v_detail}\n"
    out += f"T: {t_detail}\n"
    if adx_detail: out += f"   {adx_detail}\n"
    if p_detail:   out += f"P: {p_detail}\n"
    # Z-score entry quality (Phase 1 — display only)
    if z_quality and z_quality not in ("", "UNKNOWN"):
        q_icon = {"IDEAL": "\u2705", "GOOD": "\U0001f7e1", "CAUTION": "\U0001f7e0", "AVOID": "\U0001f534"}.get(z_quality, "\u26aa")
        out += f"\n── ENTRY QUALITY ─────────────\n"
        out += f"{q_icon} {z_quality}  (Phase 1: observing — not blocking signals)\n"
        out += f"Price Z:  {z_price:+.2f}σ  {'\u2191 extended' if z_price > 1.5 else '\u2193 depressed' if z_price < -1.5 else 'in range'}\n"
        out += f"Vol Z:    {z_vol:+.2f}  {'\u2713 genuine spike' if z_vol >= 0.5 else '~ low volume'}\n"
        out += f"Return Z: {z_return:+.2f}σ  {'\u26a0 chasing' if z_return > 2.0 else '\u2713 not exhausted'}\n"

    if setup.get("entry") and setup.get("stop") and setup.get("target"):
        rr = setup.get("rr", 0)
        out += f"\nEntry:   {_fmt_price(setup['entry'])}\n"
        out += f"Stop:    {_fmt_price(setup['stop'])}\n"
        out += f"Target:  {_fmt_price(setup['target'])}\n"
        if rr:
            out += f"R:R      {rr:.1f}\n"

    verdict_parts = []
    if risk_level == "LOW":                          verdict_parts.append("Risk clear ✓")
    if signal in ("STRONG BUY", "BUY"):              verdict_parts.append("Signal confirmed ✓")
    if buys > sells:                                 verdict_parts.append("Buy pressure ✓")

    if len(verdict_parts) == 3:
        verdict = "ALL CHECKS PASSED ✓"
    elif risk_level in ("CRITICAL", "HIGH"):
        verdict = "HIGH RISK — PROCEED WITH CAUTION ⚠️"
    elif signal == "NO SIGNAL":
        verdict = "GATES NOT MET — NO SIGNAL"
    else:
        verdict = " · ".join(verdict_parts) if verdict_parts else "MIXED SIGNALS"

    out += f"\n VERDICT: {verdict}\n"
    return out
