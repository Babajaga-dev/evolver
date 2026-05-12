"""Modello Sentiment Fear & Greed Index.

Source: alternative.me/crypto/fear-and-greed-index/
Endpoint pubblico free: https://api.alternative.me/fng/

History 2018-02-01 → today, daily entries.

Scala 0-100:
- 0-24:  Extreme Fear
- 25-49: Fear
- 50:    Neutral
- 51-74: Greed
- 75-100: Extreme Greed

Trading idea: EMA-24w del F&G batte i predittori endogeni (return realized, volatility)
nel forecasting di crypto returns OOS 1-3 anni. Shock di 1-std-dev sentiment riduce
top-quartile returns di 15-22 pp, mediana di 6-10 pp.
Ref: Zhang & Watts "HODL Strategy or Fantasy? 480M Crypto Sim + Macro-Sentiment"
     arXiv 2512.02029 (Nov 2025)
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class FngIndex(Base):
    """Fear & Greed Index entry (daily)."""
    __tablename__ = "fng_index"
    fng_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True
    )
    value: Mapped[int] = mapped_column(Integer, nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False)
