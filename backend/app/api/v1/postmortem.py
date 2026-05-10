"""Endpoint /api/v1/postmortem — Claude Opus weekly review.

Triggerato manualmente dal pannello /control. Esegue il postmortem
synchronously (può durare 30-60s perché Opus ha latenza maggiore).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.postmortem import PostmortemError, generate_postmortem
from app.schemas.postmortem import PostmortemRequest, PostmortemResponse

router = APIRouter(tags=["postmortem"], prefix="/postmortem")
log = get_logger(__name__)


@router.post("/generate", response_model=PostmortemResponse)
async def postmortem_generate(
    body: PostmortemRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PostmortemResponse:
    """Genera il postmortem markdown chiamando Claude Opus.

    Costo stimato ~$0.50-1.00 per chiamata. Triggera manualmente dal
    pannello /control. Range temporale ``days`` (1-30).
    """
    if body.days < 1 or body.days > 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="days must be between 1 and 30",
        )
    try:
        report = await generate_postmortem(session=session, days=body.days)
    except PostmortemError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return PostmortemResponse(
        period_start=report.period_start,
        period_end=report.period_end,
        markdown=report.markdown,
        model=report.model,
        tokens_input=report.tokens_input,
        tokens_output=report.tokens_output,
        cost_usd_estimate=report.cost_usd_estimate,
    )
