"""Regime detector — analisi multi-timeframe del contesto di mercato.

Output: RegimeSignal con label discreto + score continui.
"""

from app.regime.detector import (
    RegimeError,
    RegimeSignal,
    detect_regime,
)

__all__ = [
    "RegimeError",
    "RegimeSignal",
    "detect_regime",
]
