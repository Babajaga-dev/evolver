"""Modelli market data (OHLCV).

La tabella ``ohlcv`` viene convertita in TimescaleDB hypertable nella
migration iniziale. Una sola tabella con colonna ``timeframe`` invece di
una tabella per timeframe — più semplice da interrogare e da partizionare.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Numeric,
    PrimaryKeyConstraint,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# Timeframe ammessi (allineati a ccxt)
ALLOWED_TIMEFRAMES = ("1m", "5m", "15m", "30m", "1h", "4h", "1d")


class OHLCV(Base):
    """Una candela OHLCV per (symbol, timeframe, timestamp).

    Note:
        - ``timestamp`` rappresenta l'inizio della candela (UTC).
        - ``is_closed`` distingue candele storiche definitive (True) da
          candele live ancora in formazione (False).
        - ``Numeric(20, 8)`` è abbondante per qualsiasi prezzo crypto.
    """

    __tablename__ = "ohlcv"
    __table_args__ = (
        PrimaryKeyConstraint("symbol", "timeframe", "timestamp"),
        Index("ix_ohlcv_timestamp", "timestamp"),
        Index("ix_ohlcv_symbol_timeframe", "symbol", "timeframe"),
    )

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False)

    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False)
    quote_volume: Mapped[Decimal | None] = mapped_column(Numeric(28, 8))
    trades_count: Mapped[int | None] = mapped_column()

    is_closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return (
            f"<OHLCV {self.symbol} {self.timeframe} @ {self.timestamp.isoformat()} "
            f"close={self.close}>"
        )
