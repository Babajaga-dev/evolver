"""SQLAlchemy ORM models.

Importare i modelli da qui per garantire la registrazione su Base.metadata
prima dell'autogenerate Alembic.
"""

from app.models.base import Base
from app.models.market import OHLCV
from app.models.news import NewsRaw, NewsScored
from app.models.paper import EquitySnapshot, PaperTrade
from app.models.strategy import (
    FitnessEvaluation,
    Generation,
    Population,
    Strategy,
)
from app.models.replay import ReplayEquitySnapshot, ReplayRetrainEvent, ReplayRun
from app.models.system import SystemSetting

__all__ = [
    "Base",
    "EquitySnapshot",
    "FitnessEvaluation",
    "Generation",
    "NewsRaw",
    "NewsScored",
    "OHLCV",
    "PaperTrade",
    "Population",
    "ReplayEquitySnapshot",
    "ReplayRetrainEvent",
    "ReplayRun",
    "Strategy",
    "SystemSetting",
]
