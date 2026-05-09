"""Endpoint News — list, stats, refresh, score batch.

Pipeline manuale (Fase 3.0a):
    POST /api/v1/news/refresh   → fetch RSS + ingest in DB
    POST /api/v1/news/score     → batch score con Claude Haiku
    GET  /api/v1/news           → lista paginata + filtri
    GET  /api/v1/news/stats     → dashboard counters
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.news import (
    fetch_and_ingest,
    get_news_stats,
    list_recent_news,
    score_pending_news,
)
from app.schemas.news import (
    NewsItemOut,
    NewsListResponse,
    NewsRefreshResponse,
    NewsScoreBatchResponse,
    NewsScoreOut,
    NewsStatsResponse,
)

router = APIRouter(tags=["news"], prefix="/news")
log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=NewsListResponse)
async def list_news(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=50, ge=1, le=500),
    asset: str | None = Query(default=None, description="Filtro asset (es. BTC)"),
    event_type: str | None = Query(
        default=None,
        description="Filtro event type (es. regulation)",
    ),
    only_scored: bool = Query(default=True),
) -> NewsListResponse:
    """Lista news ordinate per published_at DESC.

    Default ``only_scored=True``: il frontend mostra solo news arricchite
    dall'LLM. Per debug si può passare ``false`` e vedere anche le raw
    in attesa di scoring.
    """
    rows = await list_recent_news(
        session,
        limit=limit,
        asset=asset,
        event_type=event_type,
        only_scored=only_scored,
    )

    items = [_to_item_out(r) for r in rows]
    return NewsListResponse(items=items, count=len(items))


@router.get("/stats", response_model=NewsStatsResponse)
async def news_stats(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NewsStatsResponse:
    """Counters per la dashboard frontend."""
    stats = await get_news_stats(session)
    return NewsStatsResponse(**stats)


# ---------------------------------------------------------------------------
# Trigger endpoints (manuali — in Fase 4 li sposteremo su scheduler)
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=NewsRefreshResponse)
async def refresh_news(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NewsRefreshResponse:
    """Fetch tutti i feed RSS e ingest le news nuove."""
    result = await fetch_and_ingest(session)
    log.info("news.api.refresh", **result)
    return NewsRefreshResponse(**result)


@router.post("/score", response_model=NewsScoreBatchResponse)
async def score_news_batch(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: int = Query(default=20, ge=1, le=100),
    concurrency: int = Query(default=4, ge=1, le=10),
) -> NewsScoreBatchResponse:
    """Pickup le news non scorate e processa con Claude Haiku.

    ``limit`` cap il numero di chiamate Claude per request, evitando
    burst di costo. Default 20 ≈ ~$0.005 per call.
    """
    result = await score_pending_news(
        session,
        limit=limit,
        concurrency=concurrency,
    )
    log.info("news.api.score_batch", **result)
    return NewsScoreBatchResponse(**result)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_item_out(news) -> NewsItemOut:  # type: ignore[no-untyped-def]
    """Mappa NewsRaw (con eager-load score) → NewsItemOut Pydantic."""
    score_out = None
    if news.score is not None:
        s = news.score
        score_out = NewsScoreOut(
            assets_mentioned=list(s.assets_mentioned or []),
            event_type=s.event_type,
            factual_impact=float(s.factual_impact),
            sentiment_score=float(s.sentiment_score),
            confidence=float(s.confidence),
            ttl_hours=int(s.ttl_hours),
            reasoning=s.reasoning,
            model=s.model,
            scored_at=s.scored_at,
        )
    return NewsItemOut(
        id=news.id,
        source=news.source,
        url=news.url,
        title=news.title,
        body=news.body,
        published_at=news.published_at,
        ingested_at=news.ingested_at,
        score=score_out,
    )
