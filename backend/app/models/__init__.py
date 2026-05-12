"""SQLAlchemy ORM models.

Importare i modelli da qui per garantire la registrazione su Base.metadata
prima dell'autogenerate Alembic.
"""

from app.models.base import Base
from app.models.market import OHLCV
from app.models.funding import FundingRate
from app.models.sentiment import FngIndex
from app.models.replay import ReplayEquitySnapshot, ReplayRetrainEvent, ReplayRun
from app.models.system import SystemSetting

__all__ = [
    "Base",
    "FngIndex",
    "FundingRate",
    "OHLCV",
    "ReplayEquitySnapshot",
    "ReplayRetrainEvent",
    "ReplayRun",
    "SystemSetting",
]
