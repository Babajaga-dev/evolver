"""Schemi Pydantic per Fear & Greed sentiment endpoint."""
from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel, Field


class FngPoint(BaseModel):
    """Singolo punto Fear & Greed Index."""
    date: datetime
    value: int = Field(..., ge=0, le=100, description="Fear&Greed value 0-100")
    classification: str
    ema_24w: float | None = Field(
        None,
        description="EMA con span 24 settimane (168 daily samples). "
                    "Predictor stabile per ritorni crypto OOS 1-3y (Zhang-Watts arXiv 2512.02029)",
    )
    zone: str = Field(
        ...,
        description="Estrema Greed/Fear basata su EMA threshold",
    )


class FngSeriesResponse(BaseModel):
    """Serie storica Fear & Greed."""
    start_date: datetime
    end_date: datetime
    n_points: int
    points: list[FngPoint]
    summary: dict


class FngBackfillRequest(BaseModel):
    """Request per triggerare backfill F&G."""
    limit: int = Field(
        default=0,
        ge=0,
        le=10000,
        description="0 = tutta la storia disponibile (da 2018-02-01)",
    )


class FngBackfillResponse(BaseModel):
    started: bool
    job_id: str
    message: str
