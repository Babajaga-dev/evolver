"""Endpoint OHLCV + markets list.

Endpoints:
    GET /api/v1/markets
    GET /api/v1/coverage
    GET /api/v1/ohlcv/{symbol}/{timeframe}

``symbol`` nel path va URL-encoded (BTC%2FUSDT) perché contiene "/".
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.models.market import ALLOWED_TIMEFRAMES
from app.repositories import ohlcv as ohlcv_repo
from app.schemas.ohlcv import (
    MarketsResponse,
    OHLCVCandle,
    OHLCVResponse,
)

router = APIRouter(tags=["market-data"])


# ---------------------------------------------------------------------------
# Markets / Coverage
# ---------------------------------------------------------------------------


@router.get("/markets", response_model=MarketsResponse)
async def list_markets() -> MarketsResponse:
    """Universe di trading attivo (configurato via env)."""
    settings = get_settings()
    return MarketsResponse(
        symbols=settings.symbols,
        timeframes=settings.timeframes,
    )


@router.get("/coverage")
async def data_coverage(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[dict]:
    """Per ogni (symbol, timeframe) presente in DB: count + first/last ts.

    Permette al frontend di sapere quanto storico è disponibile prima di
    chiedere candele specifiche.
    """
    return await ohlcv_repo.coverage_summary(session)


# ---------------------------------------------------------------------------
# OHLCV range query
# ---------------------------------------------------------------------------


@router.get(
    "/ohlcv/{symbol:path}/{timeframe}",
    response_model=OHLCVResponse,
)
async def get_ohlcv(
    symbol: Annotated[
        str,
        Path(
            description="Symbol — usa URL-encoding per '/' (es. BTC%2FUSDT)",
            examples=["BTC/USDT"],
        ),
    ],
    timeframe: Annotated[
        str,
        Path(
            description="Timeframe candele",
            examples=["4h"],
        ),
    ],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: Annotated[
        datetime | None,
        Query(description="Lower bound (ISO 8601). Default: 30gg fa."),
    ] = None,
    end: Annotated[
        datetime | None,
        Query(description="Upper bound (ISO 8601). Default: ora."),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> OHLCVResponse:
    """Range di candele per ``(symbol, timeframe)``.

    Esempio:
        ``GET /api/v1/ohlcv/BTC%2FUSDT/4h?limit=200&order=desc``
    """
    # ``symbol:path`` non decodifica %2F; lo facciamo a mano.
    symbol_decoded = unquote(symbol)

    settings = get_settings()
    if symbol_decoded not in settings.symbols:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol_decoded}' non in universe attivo: {settings.symbols}",
        )
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeframe '{timeframe}' non supportato. Ammessi: {list(ALLOWED_TIMEFRAMES)}",
        )

    rows = await ohlcv_repo.fetch_ohlcv(
        session=session,
        symbol=symbol_decoded,
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
        order=order,
    )
    candles = [OHLCVCandle.model_validate(row) for row in rows]
    return OHLCVResponse(
        symbol=symbol_decoded,
        timeframe=timeframe,
        count=len(candles),
        candles=candles,
    )
