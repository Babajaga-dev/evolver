"""Indicator engine — wrapper su pandas-ta-classic.

Convenzioni:
    - Ogni indicatore implementa l'interfaccia ``Indicator``.
    - Input: DataFrame OHLCV indicizzato per timestamp UTC.
    - Output: dict[str, pd.Series] — chiavi sono nomi delle serie (es.
      ``"rsi"``, oppure per MACD ``{"macd", "signal", "histogram"}``).
    - I parametri sono validati contro ``ParamSpec`` (range numerico /
      categorica / default).
"""

from app.indicators.core import (
    INDICATOR_REGISTRY,
    Indicator,
    IndicatorOutput,
    IndicatorSpec,
    ParamSpec,
    available_indicators,
    compute,
    get_indicator,
)

__all__ = [
    "INDICATOR_REGISTRY",
    "Indicator",
    "IndicatorOutput",
    "IndicatorSpec",
    "ParamSpec",
    "available_indicators",
    "compute",
    "get_indicator",
]
