"""Endpoint /api/v1/sentiment/* — Fear & Greed Index overlay.

Source: api.alternative.me/fng/ (free, no auth).
Storage: tabella fng_index (migration 0007).

Trading rationale: Zhang & Watts arXiv 2512.02029 (Nov 2025) dimostrano che
F&G EMA-24w è il predictor cross-basket stabile per crypto returns OOS 1-3y.
Shock 1-std-dev sentiment → top-quartile -15..-22 pp, median -6..-10 pp.
"""
from __future__ import annotations
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Annotated

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session, session_scope
from app.core.logging import get_logger
from app.repositories import sentiment as sentiment_repo
from app.schemas.sentiment import (
    FngBackfillRequest,
    FngBackfillResponse,
    FngPoint,
    FngSeriesResponse,
)
from app.sentiment.fng_fetcher import backfill_fng

router = APIRouter(prefix="/sentiment", tags=["sentiment"])
log = get_logger(__name__)

# Threshold paper-aligned. Extreme zones definiti su daily values.
EMA_SPAN_DAYS = 168  # 24 weeks = 168 days
ZONE_EXTREME_FEAR = 25
ZONE_FEAR = 45
ZONE_NEUTRAL_HIGH = 55
ZONE_GREED = 75


def _limit_display(limit: int) -> str:
    return "ALL history" if limit == 0 else str(limit)


def _classify_zone(ema_value: float) -> str:
    if ema_value < ZONE_EXTREME_FEAR:
        return "extreme_fear"
    if ema_value < ZONE_FEAR:
        return "fear"
    if ema_value < ZONE_NEUTRAL_HIGH:
        return "neutral"
    if ema_value < ZONE_GREED:
        return "greed"
    return "extreme_greed"


@router.get("/fng", response_model=FngSeriesResponse)
async def get_fng_series(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    limit: int = Query(default=5000, ge=10, le=10000),
) -> FngSeriesResponse:
    """Restituisce la serie F&G con EMA-24w e classificazione zona."""
    rows = await sentiment_repo.fetch_fng(
        session, start=start_date, end=end_date, limit=limit, order="asc",
    )
    if not rows:
        raise HTTPException(404, "Nessun dato F&G disponibile. Triggera /sentiment/backfill")

    # Compute EMA-24w via pandas
    df = pd.DataFrame(
        [{"date": r.fng_date, "value": r.value, "classification": r.classification} for r in rows]
    )
    df["ema_24w"] = df["value"].astype(float).ewm(span=EMA_SPAN_DAYS, adjust=False).mean()
    df["zone"] = df["ema_24w"].apply(_classify_zone)

    points = [
        FngPoint(
            date=row["date"],
            value=int(row["value"]),
            classification=row["classification"],
            ema_24w=round(float(row["ema_24w"]), 2),
            zone=row["zone"],
        )
        for _, row in df.iterrows()
    ]

    summary = {
        "current_value": int(df.iloc[-1]["value"]),
        "current_ema_24w": round(float(df.iloc[-1]["ema_24w"]), 2),
        "current_zone": df.iloc[-1]["zone"],
        "min_value": int(df["value"].min()),
        "max_value": int(df["value"].max()),
        "mean_value": round(float(df["value"].mean()), 2),
        "mean_ema_24w": round(float(df["ema_24w"].mean()), 2),
        "n_extreme_fear_days": int((df["ema_24w"] < ZONE_EXTREME_FEAR).sum()),
        "n_extreme_greed_days": int((df["ema_24w"] >= ZONE_GREED).sum()),
    }

    return FngSeriesResponse(
        start_date=df.iloc[0]["date"],
        end_date=df.iloc[-1]["date"],
        n_points=len(points),
        points=points,
        summary=summary,
    )


async def _backfill_job(req: FngBackfillRequest) -> None:
    """Background task: scarica + persistite F&G history."""
    log.info("admin.fng.backfill.start", limit=req.limit)
    try:
        async with session_scope() as s:
            n = await backfill_fng(s, limit=req.limit)
        log.info("admin.fng.backfill.done", inserted=n)
    except Exception as exc:
        log.exception("admin.fng.backfill.failed", error=str(exc))


@router.post("/backfill", response_model=FngBackfillResponse)
async def trigger_backfill(body: FngBackfillRequest) -> FngBackfillResponse:
    """Triggera backfill async F&G dalla API alternative.me."""
    job_id = str(uuid.uuid4())
    asyncio.create_task(_backfill_job(body))
    return FngBackfillResponse(
        started=True,
        job_id=job_id,
        message=f"Backfill F&G avviato (limit={_limit_display(body.limit)})",
    )


@router.get("/stats")
async def fng_stats(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict:
    """Quick health: count + ultime entries."""
    count = await sentiment_repo.count_fng(session)
    latest = await sentiment_repo.latest_fng(session)
    return {
        "total_entries": count,
        "latest_date": latest.fng_date.isoformat() if latest else None,
        "latest_value": latest.value if latest else None,
        "latest_classification": latest.classification if latest else None,
    }
