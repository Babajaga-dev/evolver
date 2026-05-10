"""Endpoint /api/v1/live/* — live trading skeleton (no execution)."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.logging import get_logger
from app.live import get_live_state, preflight_order
from app.schemas.live import (
    LiveStateResponse,
    PreflightRequest,
    PreflightResponse,
)

router = APIRouter(tags=["live"], prefix="/live")
log = get_logger(__name__)


@router.get("/state", response_model=LiveStateResponse)
async def live_state() -> LiveStateResponse:
    """Snapshot config live trading + safety status."""
    state = await get_live_state()
    return LiveStateResponse(**state)


@router.post("/preflight", response_model=PreflightResponse)
async def live_preflight(body: PreflightRequest) -> PreflightResponse:
    """Simula un ordine: calcola fees/notional + safety checks. NO execution."""
    result = await preflight_order(
        side=body.side,
        symbol=body.symbol,
        quantity=body.quantity,
        estimated_price=body.estimated_price,
    )
    return PreflightResponse(
        side=result.side,
        symbol=result.symbol,
        quantity=result.quantity,
        estimated_price=result.estimated_price,
        estimated_notional=result.estimated_notional,
        estimated_fees=result.estimated_fees,
        safety_checks=result.safety_checks,
        blocked_by=result.blocked_by,
        timestamp=result.timestamp,
        message=result.message,
    )
