"""
keyboards.py — Persistent reply keyboard + inline button builders for Crypto Sniper bot.
"""
from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton


# ─────────────────────────────────────────────
#  Main persistent reply keyboard
#  Always visible at bottom of chat
# ─────────────────────────────────────────────

def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Persistent 2-column tap menu shown after every major interaction."""
    buttons = [
        ["📡 Live Signal",    "💎 DEX Gem Scan"],
        ["📊 Last Sweep",     "📈 Track Record"],
        ["⚙️ My Account",     "❓ Help"],
    ]
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Tap a menu item or type a question...",
    )


def remove_keyboard():
    """Import ReplyKeyboardRemove where needed — convenience re-export."""
    from telegram import ReplyKeyboardRemove
    return ReplyKeyboardRemove()


# ─────────────────────────────────────────────
#  Onboarding inline buttons (/start)
# ─────────────────────────────────────────────

def onboarding_keyboard() -> InlineKeyboardMarkup:
    """What do you want to do? — shown on first /start."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 Get a live signal",    callback_data="ob:signal")],
        [InlineKeyboardButton("💎 Scan a DEX token",     callback_data="ob:dex")],
        [InlineKeyboardButton("📊 See today's sweeps",   callback_data="ob:sweep")],
        [InlineKeyboardButton("❓ What is Crypto Sniper?", callback_data="ob:about")],
    ])


# ─────────────────────────────────────────────
#  Signal result inline buttons (/analyse)
# ─────────────────────────────────────────────

def signal_inline_keyboard(symbol: str, interval: str) -> InlineKeyboardMarkup:
    """Buttons attached to a CEX signal card."""
    next_tf = {"1M": "5M", "5M": "15M", "15M": "1H", "30M": "1H",
               "1H": "4H", "4H": "1D", "1D": "1D"}.get(interval.upper(), "4H")
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh",        callback_data=f"sig:refresh:{symbol}:{interval}"),
            InlineKeyboardButton(f"📊 {next_tf}",      callback_data=f"sig:tf:{symbol}:{next_tf}"),
            InlineKeyboardButton("📡 1D",              callback_data=f"sig:tf:{symbol}:1D"),
        ],
        [
            InlineKeyboardButton("💎 DEX scan this",  callback_data=f"sig:dex:{symbol}"),
            InlineKeyboardButton("📈 Track Record",   callback_data="rec:show:all"),
        ],
    ])


# ─────────────────────────────────────────────
#  DEX gem result inline buttons (/gem)
# ─────────────────────────────────────────────

def gem_inline_keyboard(address: str, symbol: str) -> InlineKeyboardMarkup:
    """Buttons attached to a DEX gem scan result."""
    short = address[:8] if address else ""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Refresh",        callback_data=f"gem:refresh:{address}"),
            InlineKeyboardButton("👀 Watch token",    callback_data=f"gem:watch:{address}:{symbol}"),
        ],
        [
            InlineKeyboardButton("📊 Last Sweep",     callback_data="sweep:show"),
            InlineKeyboardButton("📈 Track Record",   callback_data="rec:show:dex"),
        ],
    ])


# ─────────────────────────────────────────────
#  Track record inline buttons (/record)
# ─────────────────────────────────────────────

def record_inline_keyboard(current: str = "all") -> InlineKeyboardMarkup:
    """Toggle filter on /record results."""
    def _btn(label, cd, active_key):
        tick = " ✓" if current == active_key else ""
        return InlineKeyboardButton(f"{label}{tick}", callback_data=cd)

    return InlineKeyboardMarkup([
        [
            _btn("All",  "rec:show:all", "all"),
            _btn("CEX",  "rec:show:cex", "cex"),
            _btn("DEX",  "rec:show:dex", "dex"),
        ],
        [
            InlineKeyboardButton("📡 Live Signal",  callback_data="ob:signal"),
            InlineKeyboardButton("💎 DEX Gem Scan", callback_data="ob:dex"),
        ],
    ])


# ─────────────────────────────────────────────
#  Sweep results inline buttons (/gems)
# ─────────────────────────────────────────────

def sweep_inline_keyboard() -> InlineKeyboardMarkup:
    """Buttons attached to the DEX sweep results."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💎 Scan a token",   callback_data="ob:dex"),
            InlineKeyboardButton("🔄 Refresh sweep",  callback_data="sweep:show"),
        ],
        [
            InlineKeyboardButton("📈 Track Record",   callback_data="rec:show:all"),
            InlineKeyboardButton("📡 Live Signal",    callback_data="ob:signal"),
        ],
    ])


# ─────────────────────────────────────────────
#  Account inline buttons (/status)
# ─────────────────────────────────────────────

def account_inline_keyboard(has_email: bool) -> InlineKeyboardMarkup:
    rows = []
    if not has_email:
        rows.append([InlineKeyboardButton("🔗 Link my email", callback_data="acct:link")])
    rows.append([
        InlineKeyboardButton("📡 Get a signal",    callback_data="ob:signal"),
        InlineKeyboardButton("💎 DEX Gem Scan",    callback_data="ob:dex"),
    ])
    return InlineKeyboardMarkup(rows)
