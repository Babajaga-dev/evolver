"""Endpoint indicators — wrapper attorno a app.indicators."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from urllib.parse import unquote

import math
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.indicators import (
    available_indicators,
    compute,
    get_indicator,
)
from app.models.market import ALLOWED_TIMEFRAMES
from app.repositories import ohlcv as ohlcv_repo
from app.schemas.indicator import (
    IndicatorInfo,
    IndicatorParamInfo,
    IndicatorPoint,
    IndicatorResponse,
    IndicatorsRegistryResponse,
)

router = APIRouter(tags=["indicators"])


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@router.get("/indicators", response_model=IndicatorsRegistryResponse)
async def list_indicators() -> IndicatorsRegistryResponse:
    """Tutti gli indicatori registrati con i loro parametri.

    Il frontend usa questo endpoint per generare i form di configurazione
    automaticamente — niente UI hardcoded per indicatore.
    """
    return IndicatorsRegistryResponse(
        indicators=[
            IndicatorInfo(
                id=spec.id,
                label=spec.label,
                kind=spec.kind,
                description=spec.description,
                params=[
                    IndicatorParamInfo(
                        name=p.name,
                        type=p.type,
                        default=p.default,
                        min=p.min,
                        max=p.max,
                        choices=list(p.choices) if p.choices else None,
                        description=p.description,
                    )
                    for p in spec.params
                ],
                output_keys=list(spec.output_keys),
            )
            for spec in available_indicators()
        ]
    )


# ---------------------------------------------------------------------------
# Compute
# ---------------------------------------------------------------------------


@router.get(
    "/indicators/{symbol:path}/{timeframe}",
    response_model=IndicatorResponse,
)
async def compute_indicator(
    request: Request,
    symbol: Annotated[str, Path()],
    timeframe: Annotated[str, Path()],
    indicator: Annotated[str, Query(description="ID indicatore (es. rsi, macd)")],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=10, le=10000)] = 1000,
) -> IndicatorResponse:
    """Computa l'indicatore su candele OHLCV del DB.

    Tutti i parametri specifici dell'indicatore arrivano come query string
    (``?period=14`` o ``?fast=12&slow=26&signal=9``). Vengono validati
    contro il ``ParamSpec`` registrato.

    Esempio:
        ``GET /api/v1/indicators/BTC%2FUSDT/4h?indicator=rsi&period=14&limit=500``
    """
    symbol_decoded = unquote(symbol)

    settings = get_settings()
    if symbol_decoded not in settings.symbols:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol '{symbol_decoded}' non in universe attivo",
        )
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Timeframe '{timeframe}' non supportato",
        )

    try:
        spec = get_indicator(indicator)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # Estrai parametri specifici dell'indicatore dalla query string
    reserved = {"indicator", "start", "end", "limit"}
    raw_params: dict[str, Any] = {
        k: v for k, v in request.query_params.items() if k not in reserved
    }

    # Fetch OHLCV
    rows = await ohlcv_repo.fetch_ohlcv(
        session=session,
        symbol=symbol_decoded,
        timeframe=timeframe,
        start=start,
        end=end,
        limit=limit,
        order="asc",
    )
    if not rows:
        return IndicatorResponse(
            symbol=symbol_decoded,
            timeframe=timeframe,
            indicator=indicator,
            params={},
            output_keys=list(spec.output_keys),
            count=0,
            points=[],
            label=spec.label,
            kind=spec.kind,
        )

    # DataFrame OHLCV
    df = pd.DataFrame(
        [
            {
                "timestamp": r.timestamp,
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume),
            }
            for r in rows
        ]
    )
    df = df.set_index("timestamp")

    try:
        output, validated = compute(indicator, df, raw_params)
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # Allinea le serie sull'indice di df (potrebbero avere NaN nei primi N)
    timestamps = list(df.index)
    points: list[IndicatorPoint] = []
    output_keys = list(spec.output_keys)

    for i, ts in enumerate(timestamps):
        values: dict[str, float | None] = {}
        for key in output_keys:
            if key not in output:
                values[key] = None
                continue
            series = output[key]
            if i < len(series):
                v = series.iloc[i]
                values[key] = (
                    float(v) if pd.notna(v) and math.isfinite(v) else None
                )
            else:
                values[key] = None
        points.append(IndicatorPoint(timestamp=ts, values=values))

    return IndicatorResponse(
        symbol=symbol_decoded,
        timeframe=timeframe,
        indicator=indicator,
        params=validated,
        output_keys=output_keys,
        count=len(points),
        points=points,
        label=spec.label,
        kind=spec.kind,
    )
