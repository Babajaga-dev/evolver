"""Pipeline orchestrator: fetch + ingest + scoring batch.

Pensato per essere chiamato:
    - da un endpoint manuale (POST /api/v1/news/refresh)
    - da uno scheduler (Fase 4) ogni N minuti

Filosofia: idempotente. Ri-eseguibile senza side effects negativi.
"""

from __future__ import annotations

import asyncio
from typing import Any

from anthropic import AsyncAnthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.news.repository import get_unscored_news, save_score
from app.news.scorer import ScoringError, score_news

log = get_logger(__name__)


async def score_pending_news(
    session: AsyncSession,
    *,
    limit: int = 30,
    concurrency: int = 4,
) -> dict[str, Any]:
    """Pickup unscored news + score con Claude Haiku in parallelo limitato.

    Args:
        session: AsyncSession (caller gestisce commit).
        limit: max news da processare in questo batch (cap costo).
        concurrency: chiamate Anthropic parallele simultanee.

    Returns:
        {
            "picked": N,        # quante news abbiamo preso
            "scored": M,        # quante scorate con successo
            "failed": K,        # quante hanno fallito (API/parse)
        }
    """
    settings = get_settings()

    pending = await get_unscored_news(session, limit=limit)
    if not pending:
        log.info("news.pipeline.nothing_to_score")
        return {"picked": 0, "scored": 0, "failed": 0}

    log.info("news.pipeline.batch_start", count=len(pending), limit=limit)

    # Riusiamo lo stesso AsyncAnthropic client per tutti gli items
    client = AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        timeout=settings.claude_timeout_s,
        max_retries=settings.claude_max_retries,
    )

    semaphore = asyncio.Semaphore(concurrency)

    async def _score_one(news: Any) -> tuple[Any, Any]:
        """Returns (news, ScoringResult|None)."""
        async with semaphore:
            try:
                result = await score_news(
                    title=news.title,
                    body=news.body,
                    url=news.url,
                    client=client,
                )
                return (news, result)
            except ScoringError as exc:
                log.warning(
                    "news.pipeline.score_failed",
                    news_id=str(news.id),
                    url=news.url,
                    error=str(exc),
                )
                return (news, None)

    pairs = await asyncio.gather(*[_score_one(n) for n in pending])

    scored = 0
    failed = 0
    for news, result in pairs:
        if result is None:
            failed += 1
            continue
        try:
            await save_score(session, news_id=news.id, score=result)
            scored += 1
        except Exception as exc:  # pragma: no cover — DB error
            log.warning(
                "news.pipeline.save_failed",
                news_id=str(news.id),
                error=str(exc),
            )
            failed += 1

    if scored:
        await session.commit()

    log.info(
        "news.pipeline.batch_done",
        picked=len(pending),
        scored=scored,
        failed=failed,
    )
    return {"picked": len(pending), "scored": scored, "failed": failed}
