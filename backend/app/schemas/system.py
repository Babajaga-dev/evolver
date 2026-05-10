"""Schemi Pydantic per /api/v1/system/* — feature flags, scheduler, maintenance."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class SettingOut(BaseModel):
    key: str
    value: dict[str, Any]
    description: str | None = None
    category: str = "automation"
    schema_hint: dict[str, str] = Field(default_factory=dict)
    updated_at: datetime | None = None


class SettingsListResponse(BaseModel):
    settings: list[SettingOut]


class SettingUpdateIn(BaseModel):
    """Body per PATCH: merge superficiale del value JSONB."""

    value: dict[str, Any]


# ---------------------------------------------------------------------------
# Scheduler / jobs
# ---------------------------------------------------------------------------


class JobStatusOut(BaseModel):
    id: str
    name: str
    next_run: str | None = None
    trigger: str
    last_run_at: str | None = None
    last_status: str | None = None  # "ok" | "error" | "skipped"
    last_message: str | None = None
    last_duration_s: float | None = None


class JobsListResponse(BaseModel):
    jobs: list[JobStatusOut]


class JobTriggerResponse(BaseModel):
    id: str
    triggered: bool
    message: str


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


class OhlcvStats(BaseModel):
    count: int
    oldest: str | None = None
    newest: str | None = None


class NewsCounts(BaseModel):
    raw: int
    scored: int
    pending: int


class GaPostgresCounts(BaseModel):
    populations: int
    generations: int
    strategies: int
    fitness_evaluations: int


class GaRedisCounts(BaseModel):
    total: int
    by_status: dict[str, int]


class MaintenanceStatsResponse(BaseModel):
    ohlcv: OhlcvStats
    news: NewsCounts
    ga_postgres: GaPostgresCounts
    ga_redis: GaRedisCounts


class CleanupRequest(BaseModel):
    """Request body per POST /maintenance/cleanup.

    ``confirm=False`` → dry-run, ritorna solo n_candidates.
    ``confirm=True``  → esegue la delete.
    """

    target: str = Field(
        description=(
            "Cosa pulire: ohlcv_old | "
            "ga_runs_failed | ga_runs_completed | ga_runs_all"
        )
    )
    older_than_days: int | None = Field(
        default=None,
        ge=1,
        le=3650,
        description="Soglia per cleanup time-based",
    )
    confirm: bool = Field(default=False)


class CleanupResponse(BaseModel):
    target: str
    deleted: int
    dry_run: bool
    details: dict[str, Any]
