"""Schemi Pydantic per gli indicatori tecnici."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IndicatorParamInfo(BaseModel):
    """Metadati su un parametro di un indicatore (per UI auto-generata)."""

    name: str
    type: str
    default: Any
    min: float | int | None = None
    max: float | int | None = None
    choices: list[str] | None = None
    description: str = ""


class IndicatorInfo(BaseModel):
    """Schema completo di un indicatore (per /indicators/registry)."""

    id: str
    label: str
    kind: str  # "overlay" | "panel"
    description: str
    params: list[IndicatorParamInfo]
    output_keys: list[str]


class IndicatorPoint(BaseModel):
    """Un punto della serie di un indicatore.

    ``values`` è un dict perché alcuni indicatori (MACD, BBands, Stoch, ADX)
    restituiscono più serie correlate. Valori ``None`` per i primi N punti
    (warm-up del calcolo).
    """

    timestamp: datetime
    values: dict[str, float | None]


class IndicatorResponse(BaseModel):
    """Output di /api/v1/indicators/{symbol}/{timeframe}."""

    symbol: str
    timeframe: str
    indicator: str
    params: dict[str, Any]
    output_keys: list[str]
    count: int
    points: list[IndicatorPoint]
    label: str = ""
    kind: str = "panel"  # "overlay" | "panel"


class IndicatorsRegistryResponse(BaseModel):
    indicators: list[IndicatorInfo]
