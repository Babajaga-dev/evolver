"""Live order router — skeleton con safety gate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class LiveTradingDisabledError(Exception):
    """Sollevato quando si tenta di eseguire un ordine ma il flag e' OFF."""


@dataclass
class PreflightResult:
    """Risultato di una simulazione di ordine."""

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


async def get_live_state() -> dict[str, Any]:
    """Snapshot corrente della config live trading + safety status."""
    settings = get_settings()
    return {
        "live_trading_enabled": False,
        "exchange": "binance",
        "use_testnet": bool(settings.binance_use_testnet),
        "api_key_configured": bool(settings.binance_api_key),
        "safety_gates": {
            "config_flag": False,
            "testnet_mode": bool(settings.binance_use_testnet),
            "kill_switch": False,
            "max_daily_loss_reached": False,
        },
        "status": "disabled",
        "message": (
            "Live trading scaffold in place but disabled. Implementation "
            "in slice 5.x. Use /api/v1/live/preflight to simulate orders."
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def preflight_order(
    *,
    side: str,
    symbol: str,
    quantity: float,
    estimated_price: float,
) -> PreflightResult:
    """Simula un ordine: calcola notional, fees, safety checks. NO execution."""
    settings = get_settings()
    notional = quantity * estimated_price
    fees = notional * float(settings.paper_fee_taker)

    checks = {
        "side_valid": side in ("buy", "sell"),
        "quantity_positive": quantity > 0,
        "price_positive": estimated_price > 0,
        "notional_below_max": notional < 100_000,
        "live_trading_enabled": False,
        "exchange_configured": bool(settings.binance_api_key),
        "testnet_mode": bool(settings.binance_use_testnet),
    }

    blocked: list[str] = []
    if not checks["side_valid"]:
        blocked.append(f"invalid side '{side}', must be buy/sell")
    if not checks["quantity_positive"]:
        blocked.append("quantity must be > 0")
    if not checks["price_positive"]:
        blocked.append("price must be > 0")
    if not checks["notional_below_max"]:
        blocked.append(f"notional {notional:.0f} > $100k cap")
    if not checks["live_trading_enabled"]:
        blocked.append("live_trading_enabled=False (slice in scaffold)")

    msg = (
        "PREFLIGHT OK - would execute"
        if not blocked
        else f"PREFLIGHT BLOCKED - {len(blocked)} check(s) failed"
    )

    log.info(
        "live.preflight",
        side=side,
        symbol=symbol,
        notional=notional,
        blocked=len(blocked),
    )

    return PreflightResult(
        side=side,
        symbol=symbol,
        quantity=quantity,
        estimated_price=estimated_price,
        estimated_notional=notional,
        estimated_fees=fees,
        safety_checks=checks,
        blocked_by=blocked,
        timestamp=datetime.now(timezone.utc),
        message=msg,
    )
