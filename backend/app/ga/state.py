"""Persistenza dello stato dei GA run su Redis.

Sostituisce il dict in-memory di ``api/v1/ga.py`` per:
    - Sopravvivere ai restart del container backend (deploy, OOM, ecc.)
    - Permettere multi-replica del backend in futuro
    - Polling client-friendly: get/set sub-millisecondo

Serializzazione: ``pickle`` perché ``RunState`` contiene dataclass nested,
``WalkForwardResult`` con timestamp e Pydantic fields. JSON richiederebbe
adapter custom; pickle è OK qui — i dati arrivano solo dal nostro backend,
mai da input untrusted (no deserialization gadget risk).

Nota: usiamo un client Redis **dedicato** con ``decode_responses=False``
perché pickle scrive bytes binari (magic byte 0x80) che il client default
(decode_responses=True per compatibilità con altri usi) tenterebbe di
decodificare come UTF-8 → UnicodeDecodeError.
"""

from __future__ import annotations

import pickle
import time

from redis.asyncio import Redis, from_url

from app.core.config import get_settings
from app.core.logging import get_logger
from app.ga.runner import RunState

log = get_logger(__name__)


# Client Redis dedicato per binary pickle data
_binary_client: Redis | None = None


def _get_binary_client() -> Redis:
    """Lazy-init di un client Redis con ``decode_responses=False`` per pickle."""
    global _binary_client
    if _binary_client is None:
        settings = get_settings()
        _binary_client = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=False,  # ← chiave: bytes raw, no UTF-8 decode
            max_connections=10,
            health_check_interval=30,
        )
    return _binary_client


async def dispose_binary_client() -> None:
    """Da chiamare a shutdown del processo (eventualmente)."""
    global _binary_client
    if _binary_client is not None:
        await _binary_client.aclose()
        _binary_client = None


# Prefix delle key Redis
_KEY_PREFIX = "evolver:ga:run:"
# TTL: i run completati restano 24h, poi vengono garbage-collected.
# In running state la TTL viene rinfrescata ad ogni save.
_TTL_SECONDS_RUNNING = 60 * 60 * 6  # 6h
_TTL_SECONDS_FINAL = 60 * 60 * 24  # 24h


def _key(population_id: str) -> str:
    return f"{_KEY_PREFIX}{population_id}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def save_state(state: RunState) -> None:
    """Pickle + persist su Redis. Idempotente, safe per chiamate frequenti."""
    redis = _get_binary_client()
    payload = pickle.dumps(state)
    ttl = (
        _TTL_SECONDS_FINAL
        if state.status in {"completed", "failed"}
        else _TTL_SECONDS_RUNNING
    )
    await redis.set(_key(state.population_id), payload, ex=ttl)


async def get_state(population_id: str) -> RunState | None:
    """Carica state. ``None`` se non esiste / scaduto."""
    redis = _get_binary_client()
    raw = await redis.get(_key(population_id))
    if raw is None:
        return None
    try:
        return pickle.loads(raw)  # noqa: S301 — input solo da nostro backend
    except Exception as exc:  # pragma: no cover
        log.warning("ga.state.unpickle_failed", population_id=population_id, error=str(exc))
        return None


async def list_states(limit: int = 50) -> list[RunState]:
    """Lista tutti i run state esistenti (max ``limit``).

    Usa Redis SCAN per non bloccare il server con KEYS.
    """
    redis = _get_binary_client()
    states: list[RunState] = []
    cursor = 0
    seen = 0
    while True:
        cursor, keys = await redis.scan(
            cursor=cursor, match=f"{_KEY_PREFIX}*".encode(), count=100
        )
        for k in keys:
            if seen >= limit:
                break
            raw = await redis.get(k)
            if raw is None:
                continue
            try:
                states.append(pickle.loads(raw))  # noqa: S301
                seen += 1
            except Exception:  # pragma: no cover
                continue
        if cursor == 0 or seen >= limit:
            break
    return states


async def delete_state(population_id: str) -> bool:
    """Cancella esplicitamente un run (es. user 'clear all')."""
    redis = _get_binary_client()
    n = await redis.delete(_key(population_id))
    return bool(n)


async def cleanup_stale_running(max_age_seconds: int = 60 * 60 * 24) -> int:
    """Marca come failed i run che dichiarano 'running' ma non si aggiornano
    da troppo tempo (es. backend killato durante run). Da chiamare al boot
    del backend.

    Returns:
        Numero di run marcati come 'failed/orphaned'.
    """
    states = await list_states(limit=200)
    now = time.time()
    n_fixed = 0
    for s in states:
        if s.status not in {"pending", "running"}:
            continue
        last_activity = s.completed_at or s.started_at or 0.0
        if last_activity == 0.0:
            continue
        if now - last_activity > max_age_seconds:
            s.status = "failed"
            s.error = "Run orphaned: backend restartato durante esecuzione"
            await save_state(s)
            n_fixed += 1
            log.warning(
                "ga.state.orphaned_run_marked_failed",
                population_id=s.population_id,
                last_activity_ago_s=now - last_activity,
            )
    return n_fixed
