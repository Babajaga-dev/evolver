"""Redis client async per cache, pub/sub, rate limiting."""

from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    """Redis client singleton (async)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
            health_check_interval=30,
        )
    return _client


async def dispose_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
