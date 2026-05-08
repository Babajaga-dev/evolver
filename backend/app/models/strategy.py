"""Modelli per popolazione GA, generazioni, strategie, fitness."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt


class Population(Base):
    """Una popolazione GA — uno snapshot a un dato momento.

    Una nuova popolazione si crea quando si fa restart del GA o si esegue
    fork (es. cambio di regime → popolazione separata).
    """

    __tablename__ = "populations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # status ∈ {active, archived, paused}

    population_size: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # config: hyper-parameters GA (mutation_rate, crossover_rate, tournament_k, ecc.)

    created_at: Mapped[CreatedAt]

    generations: Mapped[list[Generation]] = relationship(
        back_populates="population", cascade="all, delete-orphan"
    )


class Generation(Base):
    """Una generazione del GA dentro una popolazione."""

    __tablename__ = "generations"
    __table_args__ = (
        Index("ix_generations_population_number", "population_id", "number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    population_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("populations.id", ondelete="CASCADE"),
        nullable=False,
    )
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Statistiche aggregate sulla generazione (calcolate a evoluzione completata)
    best_fitness: Mapped[float | None] = mapped_column(Float)
    mean_fitness: Mapped[float | None] = mapped_column(Float)
    std_fitness: Mapped[float | None] = mapped_column(Float)
    diversity_score: Mapped[float | None] = mapped_column(Float)

    population: Mapped[Population] = relationship(back_populates="generations")
    strategies: Mapped[list[Strategy]] = relationship(back_populates="generation")


class Strategy(Base):
    """Una strategia = un cromosoma in una generazione.

    Il cromosoma è ``JSONB`` per flessibilità: i geni cambieranno tra v1 e v2.
    Forma attuale (DNA vincolato):

        {
          "family": "trend_follow" | "mean_reversion" | "breakout" | "volatility",
          "entry_indicators": [{"name": "rsi", "params": {"period": 14, "buy_below": 30}}, ...],
          "entry_logic": "AND" | "OR",
          "exit_indicators": [...],
          "stop_atr_mult": 2.0,
          "tp_atr_mult": 3.5,
          "position_size_pct": 1.5,
          "news_sensitivity": 0.6,
          "regime_filter": ["bull", "range"]
        }
    """

    __tablename__ = "strategies"
    __table_args__ = (
        Index("ix_strategies_generation", "generation_id"),
        Index("ix_strategies_chromosome", "chromosome", postgresql_using="gin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    generation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("generations.id", ondelete="CASCADE"),
        nullable=False,
    )
    chromosome: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parent_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)), nullable=False, default=list
    )
    # parent_ids vuoto = strategia random nella gen 0; len=1 = mutazione asessuata;
    # len=2 = crossover; > 2 = riservato

    # Cache della fitness aggregata (per ranking veloce)
    aggregate_fitness: Mapped[float | None] = mapped_column(Float)
    is_elite: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[CreatedAt]

    generation: Mapped[Generation] = relationship(back_populates="strategies")
    fitness_evaluations: Mapped[list[FitnessEvaluation]] = relationship(
        back_populates="strategy", cascade="all, delete-orphan"
    )


class FitnessEvaluation(Base):
    """Risultato di una valutazione fitness su una finestra walk-forward.

    Una strategia viene valutata su N finestre — la fitness aggregata è una
    funzione (es. media + penalty per varianza) di queste valutazioni.
    """

    __tablename__ = "fitness_evaluations"
    __table_args__ = (
        CheckConstraint("window_index >= 0", name="window_index_nonneg"),
        Index(
            "ix_fitness_strategy_window", "strategy_id", "window_index", unique=True
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="CASCADE"),
        nullable=False,
    )
    window_index: Mapped[int] = mapped_column(Integer, nullable=False)
    window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Metriche risk-adjusted
    sharpe: Mapped[float | None] = mapped_column(Float)
    calmar: Mapped[float | None] = mapped_column(Float)
    sortino: Mapped[float | None] = mapped_column(Float)
    max_drawdown: Mapped[float | None] = mapped_column(Float)
    total_return: Mapped[float | None] = mapped_column(Float)
    win_rate: Mapped[float | None] = mapped_column(Float)
    profit_factor: Mapped[float | None] = mapped_column(Float)
    n_trades: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    fitness: Mapped[float | None] = mapped_column(Float)  # composita
    evaluated_at: Mapped[CreatedAt]

    strategy: Mapped[Strategy] = relationship(back_populates="fitness_evaluations")
