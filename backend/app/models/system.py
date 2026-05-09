"""Modelli system-wide: feature flags, settings runtime, scheduler state."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SystemSetting(Base):
    """Key-value store per feature flags e parametri runtime.

    Esempi di key:
        - "news.auto_refresh"  → {"enabled": false, "interval_seconds": 300}
        - "news.auto_score"    → {"enabled": false, "interval_seconds": 600,
                                  "batch_limit": 20}
        - "ga.auto_run"        → {"enabled": false}

    Tutto JSONB così possiamo evolvere lo schema senza migrations.
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    description: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )
