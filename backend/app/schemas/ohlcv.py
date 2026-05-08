"""Schemi Pydantic per market data (OHLCV)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OHLCVCandle(BaseModel):
    """Una candela OHLCV serializzata per JSON.

    I prezzi sono ``Decimal`` ma vengono serializzati come stringa per
    preservare la precisione lato client (JS parsa numeri come float64).
    """

    model_config = ConfigDict(
        from_attributes=True,
        json_encoders={Decimal: str},
    )

    timestamp: datetime
    symbol: str
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class OHLCVResponse(BaseModel):
    """Response wrapper per range di candele."""

    symbol: str
    timeframe: str
    count: int
    candles: list[OHLCVCandle]


class MarketsResponse(BaseModel):
    """Lista universe di trading attivo (da settings)."""

    symbols: list[str]
    timeframes: list[str]


# ---------------------------------------------------------------------------
# Query params
# ---------------------------------------------------------------------------


class OHLCVQuery(BaseModel):
    """Validazione query string del GET /ohlcv."""

    start: datetime | None = Field(
        default=None, description="Filtro lower-bound (inclusive). Default: 30gg fa."
    )
    end: datetime | None = Field(
        default=None, description="Filtro upper-bound (inclusive). Default: ora."
    )
    limit: int = Field(default=500, ge=1, le=5000)
    order: str = Field(default="asc", pattern="^(asc|desc)$")
