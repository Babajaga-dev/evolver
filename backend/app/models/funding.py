"""Modello FundingRate — funding rate storico dei perpetual futures.

Binance USDS-M perpetual: funding ogni 8h (00:00, 08:00, 16:00 UTC).
funding_rate è negativo se shorts pagano longs (perp prezzo < spot),
positivo se longs pagano shorts (perp prezzo > spot).

Trading idea documentata: cash-and-carry. Funding > +0.05%/8h sustained:
LONG spot + SHORT perp = catturi il funding senza esposizione direzionale.
Sharpe documentato 1.8 (retail fees) / 3.5 (market maker).
Ref: He & Manela "Fundamentals of Perpetual Futures" arXiv 2212.06888
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class FundingRate(Base):
    __tablename__ = "funding_rates"
    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    funding_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    funding_rate: Mapped[float] = mapped_column(Float, nullable=False)
    mark_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    __table_args__ = (Index("ix_funding_rates_symbol_time", "symbol", "funding_time"),)
