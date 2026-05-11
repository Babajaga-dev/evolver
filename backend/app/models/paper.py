"""Modelli paper trading: trade simulati + snapshot equity."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, CreatedAt


class PaperTrade(Base):
    """Un trade simulato dal paper exchange."""

    __tablename__ = "paper_trades"
    __table_args__ = (
        Index("ix_paper_trades_strategy", "strategy_id"),
        Index("ix_paper_trades_entry_time", "entry_time"),
        Index("ix_paper_trades_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("strategies.id", ondelete="SET NULL"),
    )
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)  # long / short
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    # status ∈ {open, closed_tp, closed_sl, closed_signal, closed_manual}

    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    entry_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    fees: Mapped[Decimal] = mapped_column(
        Numeric(20, 8), nullable=False, default=Decimal("0")
    )
    pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    pnl_pct: Mapped[float | None] = mapped_column()

    stop_loss: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    take_profit: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))

    # Snapshot dei segnali al momento dell'apertura/chiusura — utile per analisi
    open_context: Mapped[dict | None] = mapped_column(JSONB)
    close_context: Mapped[dict | None] = mapped_column(JSONB)

    created_at: Mapped[CreatedAt]


class EquitySnapshot(Base):
    """Snapshot mark-to-market del portfolio paper trading.

    Hypertable in TimescaleDB — uno snapshot ogni N minuti per equity curve
    ad alta risoluzione.
    """

    __tablename__ = "equity_snapshots"
    __table_args__ = (
        PrimaryKeyConstraint("portfolio_id", "timestamp"),
        Index("ix_equity_timestamp", "timestamp"),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    portfolio_id: Mapped[str] = mapped_column(String(64), nullable=False, default="paper-v1")

    balance_quote: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    # quote = USDT
    holdings: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # holdings: {"BTC/USDT": {"qty": "0.05", "avg_price": "65000"}, ...}

    equity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    drawdown_from_peak: Mapped[float] = mapped_column(default=0.0)
    open_positions_count: Mapped[int] = mapped_column(default=0)
