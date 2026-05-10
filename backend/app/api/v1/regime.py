"""Endpoint /api/v1/regime/* — regime detector multi-timeframe."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.regime import RegimeError, detect_regime
from app.schemas.regime import RegimeResponse

router = APIRouter(tags=["regime"], prefix="/regime")
log = get_logger(__name__)


@router.get("/{symbol:path}", response_model=RegimeResponse)
async def regime_endpoint(
    symbol: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    timeframe: str = Query(default="1d"),
    lookback_candles: int = Query(default=120, ge=60, le=500),
) -> RegimeResponse:
    """Calcola regime macro per un asset su timeframe indicato."""
    try:
        signal = await detect_regime(
            session,
            symbol=symbol,
            timeframe=timeframe,
            lookback_candles=lookback_candles,
        )
    except RegimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    return RegimeResponse(
        symbol=signal.symbol,
        timestamp=signal.timestamp,
        regime=signal.regime,
        confidence=signal.confidence,
        adx=signal.adx,
        atr_pct=signal.atr_pct,
        sma_slope_pct=signal.sma_slope_pct,
        rsi=signal.rsi,
        notes=signal.notes,
    )
