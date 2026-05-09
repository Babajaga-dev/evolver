"""Ingester news raw — bulk insert con dedup su (source, external_id).

Pipeline:
    sources.fetch_all_rss() → list[RawNewsItem] → ingest_news() → DB

La dedup intra-source è già fatta in ``sources.fetch_all_rss``. Qui
gestiamo:
    - dedup persistente (riesecuzione idempotente) via ON CONFLICT DO NOTHING
    - cross-source dedup tramite il campo ``hash`` (sha256(url+title))
      filtrato in Python prima dell'insert per evitare conflitti su due
      news diverse con stesso contenuto da fonti diverse.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.news import NewsRaw
from app.news.sources import RawNewsItem, fetch_all_rss

log = get_logger(__name__)


async def ingest_news(
    session: AsyncSession,
    items: list[RawNewsItem],
) -> int:
    """Bulk insert di news raw con dedup su (source, external_id) e hash.

    Strategy:
        1. Filtra cross-source via ``hash``: se un hash esiste già in DB,
           skippa l'item (anche se ha source/external_id diversi).
        2. Bulk insert con ``ON CONFLICT (source, external_id) DO NOTHING``
           per gestire ri-esecuzione idempotente.

    Args:
        session: AsyncSession aperta — caller gestisce commit.
        items: lista di RawNewsItem (già deduplicata intra-source).

    Returns:
        Numero di righe nuove effettivamente inserite.
    """
    if not items:
        return 0

    # 1. Cross-source dedup via hash
    hashes = [it.hash for it in items]
    existing_q = await session.execute(
        select(NewsRaw.hash).where(NewsRaw.hash.in_(hashes))
    )
    existing_hashes: set[str] = {row[0] for row in existing_q.all()}

    fresh_items = [it for it in items if it.hash not in existing_hashes]
    if not fresh_items:
        log.info(
            "news.ingest.all_duplicates",
            total=len(items),
            existing_hashes=len(existing_hashes),
        )
        return 0

    # 2. Bulk insert con ON CONFLICT DO NOTHING su (source, external_id)
    rows = [
        {
            "source": it.source,
            "external_id": it.external_id,
            "url": it.url,
            "title": it.title,
            "body": it.body,
            "published_at": it.published_at,
            "hash": it.hash,
        }
        for it in fresh_items
    ]

    stmt = pg_insert(NewsRaw).values(rows).on_conflict_do_nothing(
        index_elements=["source", "external_id"]
    )
    result = await session.execute(stmt)
    inserted = result.rowcount or 0

    log.info(
        "news.ingest.done",
        total=len(items),
        cross_source_skipped=len(items) - len(fresh_items),
        inserted=inserted,
        conflict_skipped=len(fresh_items) - inserted,
    )
    return inserted


async def fetch_and_ingest(session: AsyncSession) -> dict[str, int]:
    """Pipeline completa: fetch tutti i feed RSS + ingest in DB.

    Convenience wrapper per scheduler / endpoint manuali.

    Returns:
        {"fetched": N, "inserted": M}
    """
    items = await fetch_all_rss()
    inserted = await ingest_news(session, items)
    await session.commit()
    return {"fetched": len(items), "inserted": inserted}
