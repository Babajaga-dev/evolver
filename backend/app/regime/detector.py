"""Regime detector — calcolo regime macro su candele 1d."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timedelta, timezone

from app.core.logging import get_logger
from app.indicators.core import compute as compute_indicator
from app.repositories import ohlcv as ohlcv_repo

log = get_logger(__name__)


ADX_TREND_THRESHOLD = 25.0
ADX_RANGE_THRESHOLD = 20.0
ATR_HIGH_VOL = 4.0
ATR_LOW_VOL = 1.5
SMA_SLOPE_LOOKBACK = 10


@dataclass(frozen=True)
class RegimeSignal:
    """Output del regime detector."""

    symbol: str
    timestamp: datetime
    regime: str
    confidence: float
    adx: float
    atr_pct: float
    sma_slope_pct: float
    rsi: float
    notes: str


class RegimeError(Exception):
    """Sollevato quando il detector fallisce."""


async def detect_regime(
    session: AsyncSession,
    *,
    symbol: str,
    timeframe: str = "1d",
    lookback_candles: int = 120,
) -> RegimeSignal:
    """Calcola il regime corrente per un asset."""
    # Default fetch_ohlcv usa start=end-30d. Per 1d sarebbe solo 30
    # candele. Passiamo start esplicito calcolato dal lookback.
    tf_days_map = {"15m": 1/96, "1h": 1/24, "4h": 1/6, "1d": 1, "1w": 7}
    days_per_candle = tf_days_map.get(timeframe, 1)
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=int(lookback_candles * days_per_candle * 1.2))

    rows = await ohlcv_repo.fetch_ohlcv(
        session=session,
        symbol=symbol,
        timeframe=timeframe,
        start=start_dt,
        end=end_dt,
        limit=lookback_candles,
        order="asc",
    )
    if len(rows) < 60:
        raise RegimeError(
            f"Dati insufficienti per regime detector: {len(rows)} candele "
            f"(servono >=60 per ADX/SMA50)"
        )

    df = pd.DataFrame(
        [
            {
                "timestamp": r.timestamp,
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume),
            }
            for r in rows
        ]
    ).set_index("timestamp")

    adx_out, _ = compute_indicator("adx", df, {"period": 14})
    atr_out, _ = compute_indicator("atr", df, {"period": 14})
    sma_out, _ = compute_indicator("sma", df, {"period": 50})
    rsi_out, _ = compute_indicator("rsi", df, {"period": 14})

    last_close = float(df["close"].iloc[-1])
    last_adx = 0.0 if pd.isna(adx_out["adx"].iloc[-1]) else float(adx_out["adx"].iloc[-1])
    last_atr = 0.0 if pd.isna(atr_out["atr"].iloc[-1]) else float(atr_out["atr"].iloc[-1])
    atr_pct = (last_atr / last_close * 100) if last_close > 0 else 0.0

    sma_series = sma_out["sma"].dropna()
    if len(sma_series) >= SMA_SLOPE_LOOKBACK:
        sma_now = float(sma_series.iloc[-1])
        sma_prev = float(sma_series.iloc[-SMA_SLOPE_LOOKBACK])
        sma_slope_pct = ((sma_now - sma_prev) / sma_prev * 100) if sma_prev > 0 else 0.0
    else:
        sma_slope_pct = 0.0

    last_rsi = 50.0 if pd.isna(rsi_out["rsi"].iloc[-1]) else float(rsi_out["rsi"].iloc[-1])

    regime, confidence, notes = _classify(
        adx=last_adx,
        atr_pct=atr_pct,
        sma_slope_pct=sma_slope_pct,
        rsi=last_rsi,
    )

    return RegimeSignal(
        symbol=symbol,
        timestamp=df.index[-1].to_pydatetime(),
        regime=regime,
        confidence=confidence,
        adx=last_adx,
        atr_pct=atr_pct,
        sma_slope_pct=sma_slope_pct,
        rsi=last_rsi,
        notes=notes,
    )


def _classify(
    *,
    adx: float,
    atr_pct: float,
    sma_slope_pct: float,
    rsi: float,
) -> tuple[str, float, str]:
    """Classifica il regime in base ai 4 indicatori."""
    is_trend = adx > ADX_TREND_THRESHOLD
    is_range = adx < ADX_RANGE_THRESHOLD
    is_high_vol = atr_pct > ATR_HIGH_VOL
    is_low_vol = atr_pct < ATR_LOW_VOL
    is_bullish = sma_slope_pct > 1.0
    is_bearish = sma_slope_pct < -1.0

    if is_trend:
        if is_bullish:
            regime = "trend_bullish"
            confidence = min(1.0, (adx - ADX_TREND_THRESHOLD) / 25 + 0.5)
            notes = (
                f"Trend bullish forte: ADX={adx:.1f} (>{ADX_TREND_THRESHOLD}), "
                f"SMA50 slope +{sma_slope_pct:.1f}%/{SMA_SLOPE_LOOKBACK}d. "
                f"ATR={atr_pct:.2f}%."
            )
        elif is_bearish:
            regime = "trend_bearish"
            confidence = min(1.0, (adx - ADX_TREND_THRESHOLD) / 25 + 0.5)
            notes = (
                f"Trend bearish: ADX={adx:.1f} forte, "
                f"SMA50 slope {sma_slope_pct:.1f}%/{SMA_SLOPE_LOOKBACK}d."
            )
        else:
            regime = "trend_mixed"
            confidence = 0.4
            notes = (
                f"Trend ADX={adx:.1f} ma SMA slope ambiguo "
                f"({sma_slope_pct:+.1f}%). Possibile inversione."
            )
    elif is_range:
        if is_high_vol:
            regime = "range_high_vol"
            confidence = 0.7
            notes = f"Range volatile: ADX={adx:.1f}, ATR={atr_pct:.2f}%."
        elif is_low_vol:
            regime = "range_low_vol"
            confidence = 0.85
            notes = f"Range tranquillo: ADX={adx:.1f}, ATR={atr_pct:.2f}%."
        else:
            regime = "range"
            confidence = 0.6
            notes = f"Range standard: ADX={adx:.1f}, ATR={atr_pct:.2f}%."
    else:
        regime = "transition"
        confidence = 0.3
        notes = f"Transizione: ADX={adx:.1f} (zona grigia 20-25)."

    return regime, confidence, notes
