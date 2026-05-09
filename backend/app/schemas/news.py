"""Schemi Pydantic per il news pipeline."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Item — read model
# ---------------------------------------------------------------------------


class NewsScoreOut(BaseModel):
    """Score LLM associato a una news."""

    assets_mentioned: list[str] = Field(default_factory=list)
    event_type: str
    factual_impact: float
    sentiment_score: float
    confidence: float
    ttl_hours: int
    reasoning: str | None = None
    model: str
    scored_at: datetime


class NewsItemOut(BaseModel):
    """News raw + score (se presente) per il frontend."""

    id: uuid.UUID
    source: str
    url: str
    title: str
    body: str | None = None
    published_at: datetime
    ingested_at: datetime
    score: NewsScoreOut | None = None


class NewsListResponse(BaseModel):
    items: list[NewsItemOut]
    count: int


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


class NewsStatsResponse(BaseModel):
    total_raw: int
    total_scored: int
    scored_last_24h: int
    avg_sentiment_24h: float
    by_event_type_24h: dict[str, int]


class AssetSentimentResponse(BaseModel):
    """Sentiment aggregato per un singolo asset — feature regime per il GA."""

    asset: str
    hours: int
    n_news: int
    avg_sentiment: float
    avg_factual_impact: float
    avg_confidence: float
    weighted_signal: float
    by_event_type: dict[str, int]
    freshest_at: str | None = None


# ---------------------------------------------------------------------------
# Trigger responses
# -----