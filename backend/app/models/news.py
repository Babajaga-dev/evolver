"""Modelli news raw + scoring LLM."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt


class NewsRaw(Base):
    """News come arrivano dal feed (CryptoPanic, RSS, ecc.)."""

    __tablename__ = "news_raw"
    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_news_raw_source_external"),
        Index("ix_news_raw_published_at", "published_at"),
        Index("ix_news_raw_hash", "hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(256), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[CreatedAt]

    # SHA-256 hex di (url + title) — per dedup cross-source
    hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relazione: una news può essere scorata da più modelli/run, ma in pratica
    # ne teniamo solo uno scoring "canonico"
    score: Mapped[NewsScored | None] = relationship(
        back_populates="news", uselist=False, cascade="all, delete-orphan"
    )


class NewsScored(Base):
    """Scoring LLM (Claude Haiku) di una news.

    Output strutturato: assets, event_type, factual_impact, sentiment, ecc.
    """

    __tablename__ = "news_scored"
    __table_args__ = (
        CheckConstraint(
            "factual_impact >= -1 AND factual_impact <= 1",
            name="factual_impact_range",
        ),
        CheckConstraint(
            "sentiment_score >= -1 AND sentiment_score <= 1",
            name="sentiment_score_range",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="confidence_range"
        ),
        Index("ix_news_scored_scored_at", "scored_at"),
        Index("ix_news_scored_assets", "assets_mentioned", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    news_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("news_raw.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Output strutturato dell'LLM
    assets_mentioned: Mapped[list[str]] = mapped_column(
        ARRAY(String(20)), nullable=False, default=list
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # event_type ∈ {hack, regulation, partnership, adoption, technology,
    #               opinion, market, macro, other}
    factual_impact: Mapped[float] = mapped_column(Float, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    ttl_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    reasoning: Mapped[str | None] = mapped_column(Text)

    model: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_response: Mapped[dict | None] = mapped_column(JSONB)
    scored_at: Mapped[CreatedAt]

    news: Mapped[NewsRaw] = relationship(back_populates="score")
