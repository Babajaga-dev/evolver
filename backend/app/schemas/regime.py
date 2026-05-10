"""Schemi Pydantic per /api/v1/regime/*."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RegimeResponse(BaseModel):
    symbol: str
    timestamp: datetime
    regime: str
    confidence: float
    adx: float
    atr_pct: float
    sma_slope_pct: float
    rsi: float
    notes: str
