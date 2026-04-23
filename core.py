"""
core.py — Backwards compatibility stub.
All logic moved to signals.py in V2.
"""
from signals import calculate_signals, get_key_levels, SignalResult  # noqa

__all__ = ["calculate_signals", "get_key_levels", "SignalResult"]
