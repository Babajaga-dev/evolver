"""SQLAlchemy declarative base + tipi comuni."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from sqlalchemy import DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, mapped_column

# Naming convention per indici/constraint — evita autogenerate caotici
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base ORM con metadata configurato."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Tipi annotati riusabili
TimestampTZ = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True)),
]

CreatedAt = Annotated[
    datetime,
    mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False),
]
