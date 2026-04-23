import re
from signals import calculate_signals, get_key_levels, SignalResult  # noqa

def clean_symbol(symbol: str) -> str:
    if not symbol: return "BTC"
    s = re.sub(r"[^A-Za-z0-9]", "", symbol.strip()).upper()
    return s if s else "BTC"
