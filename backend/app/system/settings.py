"""Repository per system_settings + definizioni di default.

Pattern: i settings sono JSONB key-value. Ogni feature dichiara qui le
sue chiavi e i valori di default — al boot facciamo upsert dei missing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.system import SystemSetting

log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Default settings catalog
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingDefinition:
    """Definizione di una feature flag / setting runtime."""

    key: str
    default_value: dict[str, Any]
    description: str
    category: str  # "automation" | "system" | "experimental"
    schema: dict[str, Any] = field(default_factory=dict)
    """JSON-schema-lite: hint sul tipo dei campi per UI dinamica.

    Esempio: {"enabled": "bool", "interval_seconds": "int"}
    """


DEFAULT_SETTINGS: list[SettingDefinition] = [
    SettingDefinition(
        key="news.auto_refresh",
        default_value={"enabled": False, "interval_seconds": 300},
        description="Fetch automatico dei feed RSS ogni N secondi",
        category="automation",
        schema={"enabled": "bool", "interval_seconds": "int"},
    ),
    SettingDefinition(
        key="news.auto_score",
        default_value={
            "enabled": False,
            "interval_seconds": 600,
            "batch_limit": 20,
            "concurrency": 4,
        },
        description="Scoring automatico via Claude Haiku delle news pending",
        category="automation",
        schema={
            "enabled": "bool",
            "interval_seconds": "int",
            "batch_limit": "int",
            "concurrency": "int",
        },
    ),
    SettingDefinition(
        key="ohlcv.auto_backfill",
        default_value={"enabled": False, "interval_seconds": 3600},
        description="Backfill automatico delle candele Binance",
        category="automation",
        schema={"enabled": "bool", "interval_seconds": "int"},
    ),
]


DEFAULT_BY_KEY: dict[str, SettingDefinition] = {d.key: d for d in DEFAULT_SETTINGS}


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


async def seed_defaults(session: AsyncSession) -> int:
    """Upsert dei DEFAULT_SETTINGS missing — chiamato al boot dell'app.

    Returns:
        Numero di settings nuovi inseriti.
    """
    rows = [
        {
            "key": d.key,
            "value": d.default_value,
            "description": d.description,
        }
        for d in DEFAULT_SETTINGS
    ]
    stmt = (
        pg_insert(SystemSetting)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["key"])
    )
    result = await session.execute(stmt)
    inserted = result.rowcount or 0
    if inserted:
        log.info("system.settings.seeded", count=inserted)
    return inserted


async def list_settings(session: AsyncSession) -> list[SystemSetting]:
    """Tutti i settings ordinati per key."""
    result = await session.execute(
        select(SystemSetting).order_by(SystemSetting.key)
    )
    return list(result.scalars().all())


async def get_setting(
    session: AsyncSession,
    key: str,
) -> SystemSetting | None:
    result = await session.execute(
        select(SystemSetting).where(SystemSetting.key == key)
    )
    return result.scalar_one_or_none()


async def get_value(
    session: AsyncSession,
    key: str,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Helper per leggere il value JSONB. Fallback su default catalog se assente."""
    row = await get_setting(session, key)
    if row is not None:
        return dict(row.value or {})
    if key in DEFAULT_BY_KEY:
        return dict(DEFAULT_BY_KEY[key].default_value)
    return default or {}


async def set_setting_value(
    session: AsyncSession,
    key: str,
    value: dict[str, Any],
) -> SystemSetting:
    """Upsert del value su una key esistente.

    Solleva ``KeyError`` se la key non è nel catalog dei DEFAULT_SETTINGS —
    evita typo che creerebbero settings orfani.
    """
    if key not in DEFAULT_BY_KEY:
        raise KeyError(f"Setting key '{key}' non riconosciuta")

    row = await get_setting(session, key)
    if row is None:
        # Creiamo la riga con merged value (default + override)
        defn = DEFAULT_BY_KEY[key]
        merged = {**defn.default_value, **value}
        row = SystemSetting(key=key, value=merged, description=defn.description)
        session.add(row)
    else:
        # Merge superficiale: i campi non specificati restano invariati
        merged = {**(row.value or {}), **value}
        row.value = merged

    await session.flush()
    log.info("system.settings.updated", key=key, value=merged)
    return row
