"""Endpoint /api/v1/data/* — gestione dati storici (universe + backfill smart).

Funzionalità:
- Lista universe top-150 con stato per ogni coppia (count, first, last, gap_days)
- Backfill smart: se data esiste già, parte da last_date+1, altrimenti dal 2020-01-01
- Status check per ogni simbolo
"""
from __future__ import annotations
import asyncio
import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session, session_scope
from app.core.logging import get_logger
from app.exchanges.binance import BinanceConnector
from app.models.market import OHLCV

router = APIRouter(prefix="/data", tags=["data"])
log = get_logger(__name__)

# Universe top-150 by liquidity (curato, no stables/wrapped/leveraged)
UNIVERSE_TOP150 = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "SAGA/USDT",
    "SUI/USDT", "DOGE/USDT", "TON/USDT", "ZEC/USDT", "PEPE/USDT", "TRX/USDT",
    "NEAR/USDT", "LINK/USDT", "ONDO/USDT", "SPK/USDT", "TAO/USDT", "ADA/USDT",
    "INJ/USDT", "PENDLE/USDT", "LTC/USDT", "CRV/USDT", "SAHARA/USDT", "AVAX/USDT",
    "LUNC/USDT", "SOLV/USDT", "AAVE/USDT", "PENGU/USDT", "DYM/USDT", "ENA/USDT",
    "SAPIEN/USDT", "UNI/USDT", "FF/USDT", "SEI/USDT", "RAD/USDT", "HBAR/USDT",
    "VIC/USDT", "KITE/USDT", "ASTER/USDT", "BCH/USDT", "FET/USDT", "WLD/USDT",
    "DASH/USDT", "DOGS/USDT", "GTC/USDT", "XLM/USDT", "FIL/USDT", "TRUMP/USDT",
    "OSMO/USDT", "ICP/USDT", "APT/USDT", "PARTI/USDT", "ATOM/USDT", "VIRTUAL/USDT",
    "GALA/USDT", "ORDI/USDT", "WLFI/USDT", "TIA/USDT", "XPL/USDT", "ARB/USDT",
    "BONK/USDT", "PUMP/USDT", "AI/USDT", "RIF/USDT", "DOT/USDT", "ZBT/USDT",
    "MANTA/USDT", "THETA/USDT", "MANTRA/USDT", "STRK/USDT", "BANANAS31/USDT",
    "LDO/USDT", "POL/USDT", "RUNE/USDT", "MOVR/USDT", "CHZ/USDT", "ETHFI/USDT",
    "ALGO/USDT", "W/USDT", "LAYER/USDT", "ROBO/USDT", "THE/USDT", "COS/USDT",
    "FLOKI/USDT", "ZEN/USDT", "AR/USDT", "EDU/USDT", "CFG/USDT", "ARPA/USDT",
    "HOLO/USDT", "SXT/USDT", "APE/USDT", "GRT/USDT", "OP/USDT", "C/USDT",
    "NIGHT/USDT", "ENJ/USDT", "JTO/USDT", "MOVE/USDT", "ZRO/USDT", "MUBARAK/USDT",
    "NEIRO/USDT", "TST/USDT", "PLUME/USDT", "CVX/USDT", "ETC/USDT", "CAKE/USDT",
    "MITO/USDT", "TNSR/USDT", "API3/USDT", "HEMI/USDT", "WIF/USDT", "S/USDT",
    "GMT/USDT", "HUMA/USDT", "TWT/USDT", "FORM/USDT", "PSG/USDT", "RARE/USDT",
    "JST/USDT", "RESOLV/USDT", "MAV/USDT", "OPEN/USDT", "BERA/USDT", "BANK/USDT",
    "MBL/USDT", "ACH/USDT", "ZK/USDT", "ZIG/USDT", "PORTAL/USDT", "RENDER/USDT",
    "U/USDT", "UMA/USDT", "ME/USDT", "JUP/USDT", "MEME/USDT", "PYTH/USDT",
    "FXS/USDT", "GMX/USDT", "EIGEN/USDT", "DRIFT/USDT", "RAY/USDT", "AERO/USDT",
    "KMNO/USDT", "AKT/USDT", "ETN/USDT", "BLUR/USDT", "ROSE/USDT", "MASK/USDT",
    "WOO/USDT", "FLOW/USDT",
]


class SymbolStatus(BaseModel):
    symbol: str
    count: int = 0
    first: datetime | None = None
    last: datetime | None = None
    gap_days: float = 0.0  # gap between last bar and now
    status: str = "missing"  # missing / partial / fresh / stale
    in_universe: bool = True


class UniverseStatusResponse(BaseModel):
    timeframe: str
    total_universe: int
    completed: int
    partial: int
    missing: int
    rows: list[SymbolStatus]


class SmartBackfillRequest(BaseModel):
    symbol: str
    timeframe: str = "1d"
    start_date_fallback: datetime = Field(
        default_factory=lambda: datetime(2020, 1, 1, tzinfo=timezone.utc),
        description="Usato solo se il simbolo non ha dati esistenti",
    )


class SmartBackfillResponse(BaseModel):
    symbol: str
    timeframe: str
    started: bool
    job_id: str
    fetch_from: datetime
    fetch_to: datetime
    reason: str  # "from_scratch" / "incremental" / "already_fresh"


class BulkBackfillRequest(BaseModel):
    timeframe: str = "1d"
    only_missing: bool = True  # se true, solo simboli con count==0
    max_concurrent: int = 5


class BulkBackfillResponse(BaseModel):
    started: bool
    job_id: str
    symbols: list[str]
    message: str


@router.get("/universe", response_model=UniverseStatusResponse)
async def get_universe_status(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    timeframe: str = "1d",
) -> UniverseStatusResponse:
    """Stato completo dell'universe top-150 per timeframe."""
    q = (
        select(
            OHLCV.symbol,
            func.count(OHLCV.timestamp).label("count"),
            func.min(OHLCV.timestamp).label("first"),
            func.max(OHLCV.timestamp).label("last"),
        )
        .where(OHLCV.timeframe == timeframe)
        .group_by(OHLCV.symbol)
    )
    result = await session.execute(q)
    by_symbol: dict[str, dict] = {row.symbol: {"count": row.count, "first": row.first, "last": row.last}
                                   for row in result}

    now = datetime.now(timezone.utc)
    rows: list[SymbolStatus] = []
    completed = partial = missing = 0
    for sym in UNIVERSE_TOP150:
        info = by_symbol.get(sym, {})
        cnt = info.get("count", 0)
        last = info.get("last")
        first = info.get("first")
        gap_days = 0.0
        status = "missing"
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            gap_days = (now - last).total_seconds() / 86400.0
            if cnt >= 800:
                if gap_days < 2.0:
                    status = "fresh"; completed += 1
                else:
                    status = "stale"; partial += 1
            elif cnt > 0:
                status = "partial"; partial += 1
            else:
                status = "missing"; missing += 1
        else:
            status = "missing"; missing += 1

        if first is not None and first.tzinfo is None:
            first = first.replace(tzinfo=timezone.utc)

        rows.append(SymbolStatus(
            symbol=sym, count=cnt, first=first, last=last,
            gap_days=round(gap_days, 1), status=status, in_universe=True,
        ))

    return UniverseStatusResponse(
        timeframe=timeframe,
        total_universe=len(UNIVERSE_TOP150),
        completed=completed,
        partial=partial,
        missing=missing,
        rows=rows,
    )


async def _smart_backfill_job(symbol: str, timeframe: str, start: datetime, end: datetime) -> None:
    try:
        async with BinanceConnector() as conn:
            async with session_scope() as s:
                n = await conn.backfill_ohlcv(
                    session=s, symbol=symbol, timeframe=timeframe,
                    start=start, end=end,
                )
        log.info("data.smart_backfill.done", symbol=symbol, timeframe=timeframe, inserted=n)
    except Exception as exc:
        log.exception("data.smart_backfill.failed", symbol=symbol, error=str(exc))


@router.post("/backfill-smart", response_model=SmartBackfillResponse)
async def smart_backfill(
    body: SmartBackfillRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SmartBackfillResponse:
    """Backfill intelligente: skip se dato fresco, altrimenti parte da last+1bar.

    Funziona solo OHLCV (non funding) per evitare retry pesanti su simboli non perpetual.
    """
    # Find last bar
    q = (
        select(func.max(OHLCV.timestamp))
        .where(OHLCV.symbol == body.symbol, OHLCV.timeframe == body.timeframe)
    )
    res = await session.execute(q)
    last_bar = res.scalar_one_or_none()
    now = datetime.now(timezone.utc)

    if last_bar is not None:
        if last_bar.tzinfo is None:
            last_bar = last_bar.replace(tzinfo=timezone.utc)
        gap_days = (now - last_bar).total_seconds() / 86400.0
        if gap_days < 1.0 and body.timeframe in ("1d", "4h", "1h"):
            return SmartBackfillResponse(
                symbol=body.symbol, timeframe=body.timeframe,
                started=False, job_id="",
                fetch_from=last_bar, fetch_to=now,
                reason="already_fresh",
            )
        start = last_bar + timedelta(seconds=1)
        reason = "incremental"
    else:
        start = body.start_date_fallback
        reason = "from_scratch"

    job_id = str(uuid.uuid4())
    asyncio.create_task(_smart_backfill_job(body.symbol, body.timeframe, start, now))

    return SmartBackfillResponse(
        symbol=body.symbol, timeframe=body.timeframe,
        started=True, job_id=job_id,
        fetch_from=start, fetch_to=now, reason=reason,
    )


async def _bulk_backfill_job(symbols: list[str], timeframe: str, max_concurrent: int) -> None:
    """Backfill OHLCV-only in parallelo bounded."""
    log.info("data.bulk_backfill.start", n_symbols=len(symbols), timeframe=timeframe)
    sem = asyncio.Semaphore(max_concurrent)

    async def one(sym: str) -> None:
        async with sem:
            try:
                async with BinanceConnector() as conn:
                    async with session_scope() as s:
                        # Find last bar for incremental
                        q = (
                            select(func.max(OHLCV.timestamp))
                            .where(OHLCV.symbol == sym, OHLCV.timeframe == timeframe)
                        )
                        res = await s.execute(q)
                        last_bar = res.scalar_one_or_none()
                        if last_bar is not None and last_bar.tzinfo is None:
                            last_bar = last_bar.replace(tzinfo=timezone.utc)
                        start = (last_bar + timedelta(seconds=1)) if last_bar else datetime(2020, 1, 1, tzinfo=timezone.utc)
                        end = datetime.now(timezone.utc)
                        if (end - start).total_seconds() < 86400:  # < 1 day gap
                            return
                        n = await conn.backfill_ohlcv(
                            session=s, symbol=sym, timeframe=timeframe,
                            start=start, end=end,
                        )
                log.info("data.bulk.one.done", symbol=sym, inserted=n)
            except Exception as exc:
                log.warning("data.bulk.one.failed", symbol=sym, error=str(exc))

    await asyncio.gather(*[one(s) for s in symbols])
    log.info("data.bulk_backfill.done")


@router.post("/backfill-universe", response_model=BulkBackfillResponse)
async def backfill_universe(
    body: BulkBackfillRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BulkBackfillResponse:
    """Backfill bulk dell'universe top-150. Intelligente: skip simboli già freschi."""
    # Determine which symbols need work
    q = (
        select(OHLCV.symbol, func.count(OHLCV.timestamp), func.max(OHLCV.timestamp))
        .where(OHLCV.timeframe == body.timeframe)
        .group_by(OHLCV.symbol)
    )
    result = await session.execute(q)
    by_sym = {row[0]: (row[1], row[2]) for row in result}

    now = datetime.now(timezone.utc)
    to_fetch = []
    for sym in UNIVERSE_TOP150:
        cnt, last = by_sym.get(sym, (0, None))
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if body.only_missing and cnt >= 800 and last is not None:
            gap = (now - last).total_seconds() / 86400.0
            if gap < 2.0:
                continue  # skip fresh
        to_fetch.append(sym)

    job_id = str(uuid.uuid4())
    asyncio.create_task(_bulk_backfill_job(to_fetch, body.timeframe, body.max_concurrent))

    return BulkBackfillResponse(
        started=True, job_id=job_id, symbols=to_fetch,
        message=f"Backfill avviato per {len(to_fetch)} simboli ({body.timeframe}, max_concurrent={body.max_concurrent})",
    )
