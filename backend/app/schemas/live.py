"""Schemi Pydantic per /api/v1/live/*."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class LiveStateResponse(BaseModel):
    live_trading_enabled: bool
    exchange: str
    use_testnet: bool
    api_key_configured: bool
    safety_gates: dict[str, bool]
    status: str
    message: str
    timestamp: str


class PreflightRequest(BaseModel):
    side: str = Field(description="'buy' or 'sell'")
    symbol: str = Field(default="BTC/USDT")
    quantity: float = Field(gt=0)
    estimated_price: float = Field(gt=0)


class PreflightResponse(BaseModel):
    side: str
    symbol: str
    quantity: float
    estimated_price: float
    estimated_notional: float
    estimated_fees: float
    safety_checks: dict[str, bool]
    blocked_by: list[str]
    timestamp: datetime
    message: str
