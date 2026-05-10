"""Modelli per Replay engine — replay storico con organismo evolutivo adattivo.

Tre tabelle:
- ReplayRun: una corsa di replay (config + status + progress)
- ReplayRetrainEvent: snapshot dell'organismo a ogni ri-evoluzione
- ReplayEquitySnapshot: equity curve campionata
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, CreatedAt


class ReplayRun(Base):
    __tablename__ = "replay_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # status ∈ {pending, running, stopping, completed, failed, cancelled}

    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # config: {start_date, end_date, initial_cash, retrain_cadence_days,
    #          lookback_days, kill_switch_dd_pct, ga_pop_size, ga_generations,
    #          fee, slippage_bps, symbols, primary_tf, ...}

    # Progress
    current_simulated_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_equity: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)
    n_retrains: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_kill_switch_events: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Final metrics (popolati a completed)
    final_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # final_metrics: {sharpe, total_return, max_dd, n_trades, calmar, win_rate,
    #                 baselines: {buy_hold:{...}, textbook_rsi:{...}, ga_one_shot:{...}}}

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    created_at: Mapped[datetime] = CreatedAt

    retrain_events = relationship("ReplayRetrainEvent", back_populates="run", cascade="all, delete-orphan")
    equity_snapshots = relationship("ReplayEquitySnapshot", back_populates="run", cascade="all, delete-orphan")


class ReplayRetrainEvent(Base):
    __tablename__ = "replay_retrain_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    replay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("replay_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger: Mapped[str] = mapped_column(String(32), nullable=False, default="scheduled")
    # trigger ∈ {scheduled, kill_switch, initial}

    organism: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # organism: {chromosome: {...}, sharpe_train, max_dd_train, diversity, n_trades_train}

    elapsed_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    equity_at_retrain: Mapped[float] = mapped_column(Float, nullable=False, default=10000.0)

    created_at: Mapped[datetime] = CreatedAt

    run = relationship("ReplayRun", back_populates="retrain_events")


class ReplayEquitySnapshot(Base):
    __tablename__ = "replay_equity_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    replay_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("replay_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    t: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    equity: Mapped[float] = mapped_column(Float, nullable=False)
    position_size_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    drawdown_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    regime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    active_strategy: Mapped[str | None] = mapped_column(String(64), nullable=True)
    n_trades_so_far: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    run = relationship("ReplayRun", back_populates="equity_snapshots")
