"""API v1 — endpoint pubblici versionati.

Convenzione: ogni router è in un file separato e viene aggregato in
``router_v1`` dal modulo ``api/v1.py``.
"""

from fastapi import APIRouter

from app.api.v1 import backtest, ga, indicators, ohlcv

router_v1 = APIRouter(prefix="/api/v1")
router_v1.include_router(ohlcv.router)
router_v1.include_router(indicators.router)
router_v1.include_router(backtest.router)
router_v1.include_router(ga.router)
