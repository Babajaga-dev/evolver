"""Fetcher Fear & Greed Index da alternative.me API (gratis, no auth).

Endpoint: https://api.alternative.me/fng/
Params: limit=N (0 = all history), format=json
History: dal 2018-02-01 a oggi, daily.
"""
from __future__ import annotations
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logging import get_logger
from app.repositories import sentiment as sentiment_repo

log = get_logger(__name__)

FNG_API_URL = "https://api.alternative.me/fng/"


async def fetch_fng_history(*, limit: int = 0, timeout_s: float = 30.0) -> list[dict[str, Any]]:
    """Scarica FNG entries (limit=0 = full history dal 2018).

    Returns lista di {timestamp:int, value:str, value_classification:str}.
    """
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        reraise=True,
    ):
        with attempt:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.get(
                    FNG_API_URL,
                    params={"limit": str(limit), "format": "json"},
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("data", [])
    return []  # unreachable


async def backfill_fng(session: AsyncSession, *, limit: int = 0) -> int:
    """Fetch + upsert idempotente FNG history."""
    log.info("backfill.fng.start", limit=limit)
    raw = await fetch_fng_history(limit=limit)
    if not raw:
        log.warning("backfill.fng.empty")
        return 0

    rows = []
    for item in raw:
        try:
            ts = int(item["timestamp"])
            value = int(item["value"])
            classification = str(item.get("value_classification", "Unknown"))[:24]
            fng_date = datetime.fromtimestamp(ts, tz=timezone.utc)
            rows.append({
                "fng_date": fng_date,
                "value": value,
                "classification": classification,
            })
        except (KeyError, ValueError, TypeError) as exc:
            log.warning("backfill.fng.bad_row", item=item, error=str(exc))
            continue

    n = await sentiment_repo.upsert_fng(session, rows=rows)
    await session.commit()
    log.info("backfill.fng.done", inserted=n, total_rows=len(rows))
    return n
