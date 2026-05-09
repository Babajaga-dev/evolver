"""Endpoints /api/v1/system/* — control panel admin.

Sezioni:
    GET    /system/settings              feature flags
    PATCH  /system/settings/{key}        update a flag
    GET    /system/jobs                  scheduler jobs status
    POST   /system/jobs/{id}/run         trigger now
    GET    /system/maintenance/stats     DB counts
    POST   /system/maintenance/cleanup   wipe (con dry-run safety)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.logging import get_logger
from app.schemas.system import (
    CleanupRequest,
    CleanupResponse,
    JobStatusOut,
    JobTriggerResponse,
    JobsListResponse,
    MaintenanceStatsResponse,
    SettingOut,
    SettingUpdateIn,
    SettingsListResponse,
)
from app.system import maintenance
from app.system import settings as settings_repo
from app.system.scheduler import get_jobs_status, trigger_now

router = APIRouter(tags=["system"], prefix="/system")
log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@router.get("/settings", response_model=SettingsListResponse)
async def list_settings_endpoint(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SettingsListResponse:
    """Tutti i feature flags + metadati dal catalog."""
    rows = await settings_repo.list_settings(session)
    catalog = settings_repo.DEFAULT_BY_KEY

    out: list[SettingOut] = []
    seen_keys = set()
    for row in rows:
        seen_keys.add(row.key)
        defn = catalog.get(row.key)
        out.append(
            SettingOut(
                key=row.key,
                value=row.value,
                description=row.description or (defn.description if defn else None),
                category=defn.category if defn else "system",
                schema_hint=defn.schema if defn else {},
                updated_at=row.updated_at,
            )
        )

    # Aggiungi i settings del catalog non ancora persistiti (con default)
    for key, defn in catalog.items():
        if key in seen_keys:
            continue
        out.append(
            SettingOut(
                key=key,
                value=defn.default_value,
                description=defn.description,
                category=defn.category,
                schema_hint=defn.schema,
                updated_at=None,
            )
        )

    return SettingsListResponse(settings=out)


@router.patch("/settings/{key:path}", response_model=SettingOut)
async def update_setting(
    key: str,
    body: SettingUpdateIn,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SettingOut:
    """Merge superficiale del value JSONB (solo i campi forniti vengono cambiati)."""
    try:
        row = await settings_repo.set_setting_value(session, key, body.value)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    await session.commit()
    defn = settings_repo.DEFAULT_BY_KEY.get(key)
    return SettingOut(
        key=row.key,
        value=row.value,
        description=row.description or (defn.description if defn else None),
        category=defn.category if defn else "system",
        schema_hint=defn.schema if defn else {},
        updated_at=row.updated_at,
    )


# ---------------------------------------------------------------------------
# Jobs / scheduler
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=JobsListResponse)
async def list_jobs() -> JobsListResponse:
    """Snapshot di tutti i job APScheduler con next_run e last_run."""
    jobs = [JobStatusOut(**j) for j in get_jobs_status()]
    return JobsListResponse(jobs=jobs)


@router.post("/jobs/{job_id:path}/run", response_model=JobTriggerResponse)
async def run_job_now(job_id: str) -> JobTriggerResponse:
    """Esegue immediatamente un job, bypassando il flag enabled.

    Operazione admin manuale — non rispetta lo schedule e non altera lo
    stato del flag persistente (lo cambia solo per il tempo dell'esecuzione).
    """
    try:
        await trigger_now(job_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Job execution failed: {exc}",
        ) from exc

    return JobTriggerResponse(
        id=job_id, triggered=True, message="Job eseguito manualmente"
    )


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


@router.get("/maintenance/stats", response_model=MaintenanceStatsResponse)
async def maintenance_stats(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MaintenanceStatsResponse:
    """Counts per tabella + breakdown GA Redis."""
    stats = await maintenance.collect_stats(session)
    return MaintenanceStatsResponse(**stats)


@router.post("/maintenance/cleanup", response_model=CleanupResponse)
async def maintenance_cleanup(
    body: CleanupRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CleanupResponse:
    """Esegue una cleanup operation. ``confirm=false`` → dry-run."""
    try:
        result = await maintenance.cleanup(
            session,
            target=body.target,  # type: ignore[arg-type]
            older_than_days=body.older_than_days,
            confirm=body.confirm,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    if body.confirm and result.get("deleted", 0) > 0:
        await session.commit()

    return CleanupResponse(**result)
