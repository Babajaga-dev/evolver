"""Repository helpers per news_raw + news_scored.

Pattern: funzioni stateless che prendono ``AsyncSession`` come primo arg.
Niente ORM "Service objects" — minimizziamo l'astrazione.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.news import NewsRaw, NewsScored
from app.news.scorer import ScoringResult

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------


async def get_unscored_news(
    session: AsyncSession,
    *,
    limit: int = 50,
) -> list[NewsRaw]:
    """Ritorna le news raw che non hanno ancora uno NewsScored associato.

    Ordinate per ``published_at DESC`` (più recenti prima — privilegiamo
    notizie attuali se siamo in backlog).
    """
    stmt = (
        select(NewsRaw)
        .outerjoin(NewsScored, NewsScored.news_id == NewsRaw.id)
        .where(NewsScored.id.is_(None))
        .order_by(desc(NewsRaw.published_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_recent_news(
    session: AsyncSession,
    *,
    limit: int = 100,
    asset: str | None = None,
    event_type: str | None = None,
    only_scored: bool = True,
) -> list[NewsRaw]:
    """Lista news ordinate per published_at DESC con eager-load dello score.

    Filtri opzionali su asset (es. "BTC") ed event_type (es. "regulation").
    """
    stmt = (
        select(NewsRaw)
        .options(selectinload(NewsRaw.score))
        .order_by(desc(NewsRaw.published_at))
        .limit(limit)
    )

    conditions = []
    if only_scored or asset or event_type:
        # Joinato per filtrare su NewsScored
        stmt = stmt.join(NewsScored, NewsScored.news_id == NewsRaw.id)
        if asset:
            conditions.append(NewsScored.assets_mentioned.contains([asset.upper()]))
        if event_type:
            conditions.append(NewsScored.event_type == event_type.lower())

    if conditions:
        stmt = stmt.where(and_(*conditions))

    result = await session.execute(stmt)
    return list(result.scalars().unique().all())


async def get_news_stats(session: AsyncSession) -> dict[str, int | float]:
    """Statistiche aggregate per la dashboard.

    Returns:
        {
            "total_raw": N,
            "total_scored": M,
            "scored_last_24h": K,
            "avg_sentiment_24h": X,
            "by_event_type_24h": {...}
        }
    """
    now = datetime.now(timezone.utc)
    h24_ago = now - timedelta(hours=24)

    total_raw_q = await session.execute(select(func.count()).select_from(NewsRaw))
    total_raw = total_raw_q.scalar_one()

    total_scored_q = await session.execute(
        select(func.count()).select_from(NewsScored)
    )
    total_scored = total_scored_q.scalar_one()

    scored_24h_q = await session.execute(
        select(func.count())
        .select_from(NewsScored)
        .where(NewsScored.scored_at >= h24_ago)
    )
    scored_24h = scored_24h_q.scalar_one()

    # Avg sentiment 24h (peso uniforme)
    avg_sent_q = await session.execute(
        select(func.avg(NewsScored.sentiment_score))
        .select_from(NewsScored)
        .join(NewsRaw, NewsRaw.id == NewsScored.news_id)
        .where(NewsRaw.published_at >= h24_ago)
    )
    avg_sent = avg_sent_q.scalar()

    # Breakdown by event_type 24h
    by_event_q = await session.execute(
        select(NewsScored.event_type, func.count())
        .select_from(NewsScored)
        .join(NewsRaw, NewsRaw.id == NewsScored.news_id)
        .where(NewsRaw.published_at >= h24_ago)
        .group_by(NewsScored.event_type)
    )
    by_event = {row[0]: row[1] for row in by_event_q.all()}

    return {
        "total_raw": int(total_raw),
        "total_scored": int(total_scored),
        "scored_last_24h": int(scored_24h),
        "avg_sentiment_24h": float(avg_sent) if avg_sent is not None else 0.0,
        "by_event_type_24h": by_event,
    }


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------


async def save_score(
    session: AsyncSession,
    *,
    news_id: uuid.UUID,
    score: ScoringResult,
) -> NewsScored:
    """Crea uno NewsScored row dal risultato di score_news().

    Caller gestisce il commit. Solleva se uno score esiste già per
    questa news (uniqueness su news_id) — il chiamante deve filtrare con
    ``get_unscored_news``.
    """
    row = NewsScored(
        news_id=news_id,
        assets_mentioned=score.assets_mentioned,
        event_type=score.event_type,
        factual_impact=score.factual_impact,
        sentiment_score=score.sentiment_score,
        confidence=score.confidence,
        ttl_hours=score.ttl_hours,
        reasoning=score.reasoning,
        model=score.model,
        raw_response=score.raw_response,
    )
    session.add(row)
    await session.flush()  # popola row.id senza committare
    return row
