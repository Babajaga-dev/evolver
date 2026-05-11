"""Connector Binance via ccxt — backfill storico + skeleton websocket live.

Strategy:
    - **Backfill**: paginazione REST a chunk di 1000 candele (limite Binance).
      Idempotente: usa ``ON CONFLICT DO NOTHING`` per ri-runabilità.
    - **Live**: skeleton websocket pronto per Fase 4 (non ancora attivo).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import ccxt.async_support as ccxt
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.market import OHLCV

log = get_logger(__name__)

# Binance permette max 1000 candele per richiesta REST
KLINES_BATCH_LIMIT = 1000

# Conversione timeframe → ms
TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


class BinanceConnector:
    """Wrapper async su ccxt.binance.

    Usato in context manager per garantire la chiusura della sessione HTTP:

        async with BinanceConnector() as binance:
            await binance.backfill_ohlcv(...)
    """

    def __init__(self, *, use_testnet: bool | None = None) -> None:
        settings = get_settings()
        if use_testnet is None:
            use_testnet = settings.binance_use_testnet

        self._client: ccxt.binance = ccxt.binance(
            {
                "apiKey": (
                    settings.binance_api_key.get_secret_value()
                    if settings.binance_api_key
                    else None
                ),
                "secret": (
                    settings.binance_api_secret.get_secret_value()
                    if settings.binance_api_secret
                    else None
                ),
                "enableRateLimit": True,
                "options": {
                    "defaultType": "spot",
                },
            }
        )
        if use_testnet:
            self._client.set_sandbox_mode(True)

    async def __aenter__(self) -> BinanceConnector:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.close()

    # ------------------------------------------------------------------
    # Backfill storico
    # ------------------------------------------------------------------

    async def fetch_ohlcv_chunk(
        self,
        symbol: str,
        timeframe: str,
        since_ms: int,
        limit: int = KLINES_BATCH_LIMIT,
    ) -> list[list[Any]]:
        """Fetch di una pagina di candele.

        Returns:
            Lista di [timestamp_ms, open, high, low, close, volume].
        """
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=1, max=30),
            retry=retry_if_exception_type(
                (ccxt.NetworkError, ccxt.RequestTimeout, ccxt.ExchangeNotAvailable)
            ),
            reraise=True,
        ):
            with attempt:
                klines = await self._client.fetch_ohlcv(
                    symbol, timeframe, since=since_ms, limit=limit
                )
                return klines  # type: ignore[no-any-return]
        return []  # unreachable, ma soddisfa mypy

    async def fetch_funding_rate_chunk(
        self,
        symbol: str,
        *,
        since_ms: int,
        limit: int = 1000,
    ) -> list[dict]:
        """Fetch funding rate batch da Binance USDS-M perpetual via ccxt.

        ccxt: fetch_funding_rate_history(symbol, since, limit, params).
        Symbol format: "BTC/USDT:USDT" per perp swap.
        """
        # Convert spot symbol to perp swap symbol
        swap_symbol = symbol if ":USDT" in symbol else f"{symbol}:USDT"
        # Force defaultType=swap
        original_type = self.exchange.options.get("defaultType")
        self.exchange.options["defaultType"] = "swap"
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(5),
                wait=wait_exponential(multiplier=1, min=1, max=30),
                retry=retry_if_exception_type((ccxt.NetworkError, ccxt.ExchangeError)),
            ):
                with attempt:
                    raw = await self.exchange.fetch_funding_rate_history(
                        swap_symbol, since=since_ms, limit=limit,
                    )
                    return raw
        finally:
            if original_type is not None:
                self.exchange.options["defaultType"] = original_type
        return []

    async def backfill_funding_rates(
        self,
        session: AsyncSession,
        symbol: str,
        start: datetime,
        end: datetime | None = None,
        *,
        sleep_between_chunks_s: float = 0.3,
    ) -> int:
        """Backfill funding rate storico per un symbol Binance perpetual."""
        from app.repositories import funding as funding_repo
        if end is None:
            end = datetime.now(timezone.utc)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        cursor_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        total_inserted = 0
        FUNDING_INTERVAL_MS = 8 * 3600 * 1000  # 8h

        log.info("backfill.funding.start", symbol=symbol, start=start.isoformat(), end=end.isoformat())
        while cursor_ms < end_ms:
            batch = await self.fetch_funding_rate_chunk(
                symbol=symbol, since_ms=cursor_ms, limit=1000,
            )
            if not batch:
                log.info("backfill.funding.empty", symbol=symbol, cursor_ms=cursor_ms)
                break
            rows = []
            for item in batch:
                ts = item.get("timestamp") or 0
                if ts >= end_ms:
                    continue
                rows.append({
                    "symbol": symbol,
                    "funding_time": datetime.fromtimestamp(ts / 1000, tz=timezone.utc),
                    "funding_rate": float(item.get("fundingRate") or 0.0),
                    "mark_price": float(item.get("markPrice")) if item.get("markPrice") else None,
                })
            if not rows:
                break
            n = await funding_repo.upsert_funding(session, rows=rows)
            total_inserted += n
            # Advance cursor to last funding_time + 1 step
            last_ts = batch[-1].get("timestamp") or cursor_ms
            cursor_ms = last_ts + FUNDING_INTERVAL_MS
            if sleep_between_chunks_s > 0:
                await asyncio.sleep(sleep_between_chunks_s)
        log.info("backfill.funding.done", symbol=symbol, inserted=total_inserted)
        return total_inserted

    async def backfill_ohlcv(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime | None = None,
        *,
        sleep_between_chunks_s: float = 0.25,
    ) -> int:
        """Backfill candele OHLCV in DB tra ``start`` e ``end``.

        Args:
            session: Sessione SQLAlchemy async (commit gestito dal chiamante).
            symbol: es. "BTC/USDT".
            timeframe: es. "1h" — deve essere in ``TIMEFRAME_MS``.
            start: Inizio range (UTC).
            end: Fine range (UTC). Default ``now``.
            sleep_between_chunks_s: Throttle per evitare rate limiting.

        Returns:
            Numero di candele inserite (esclusi duplicati).
        """
        if timeframe not in TIMEFRAME_MS:
            raise ValueError(f"Timeframe non supportato: {timeframe}")

        if end is None:
            end = datetime.now(timezone.utc)

        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        tf_ms = TIMEFRAME_MS[timeframe]
        cursor_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        total_inserted = 0
        chunks_fetched = 0

        log.info(
            "backfill.start",
            symbol=symbol,
            timeframe=timeframe,
            start=start.isoformat(),
            end=end.isoformat(),
        )

        while cursor_ms < end_ms:
            klines = await self.fetch_ohlcv_chunk(
                symbol=symbol,
                timeframe=timeframe,
                since_ms=cursor_ms,
                limit=KLINES_BATCH_LIMIT,
            )
            if not klines:
                log.warning(
                    "backfill.empty_chunk",
                    symbol=symbol,
                    timeframe=timeframe,
                    cursor_ms=cursor_ms,
                )
                break

            # Filtra candele oltre end_ms
            klines = [k for k in klines if k[0] < end_ms]
            if not klines:
                break

            inserted = await self._upsert_ohlcv(
                session=session,
                symbol=symbol,
                timeframe=timeframe,
                klines=klines,
            )
            total_inserted += inserted
            chunks_fetched += 1

            # Avanza il cursore: prossimo timestamp è dopo l'ultima candela
            last_ts_ms = klines[-1][0]
            cursor_ms = last_ts_ms + tf_ms

            # Log progresso ogni 10 chunk
            if chunks_fetched % 10 == 0:
                pct = (cursor_ms - int(start.timestamp() * 1000)) / max(
                    end_ms - int(start.timestamp() * 1000), 1
                )
                log.info(
                    "backfill.progress",
                    symbol=symbol,
                    timeframe=timeframe,
                    chunks=chunks_fetched,
                    inserted=total_inserted,
                    progress_pct=round(pct * 100, 1),
                )

            await asyncio.sleep(sleep_between_chunks_s)

        log.info(
            "backfill.done",
            symbol=symbol,
            timeframe=timeframe,
            chunks=chunks_fetched,
            total_inserted=total_inserted,
        )
        return total_inserted

    async def _upsert_ohlcv(
        self,
        session: AsyncSession,
        symbol: str,
        timeframe: str,
        klines: list[list[Any]],
    ) -> int:
        """Inserisce candele in DB con ON CONFLICT DO NOTHING (idempotenza).

        Returns:
            Numero di righe nuove (esclusi duplicati).
        """
        if not klines:
            return 0

        rows: list[dict[str, Any]] = []
        for kl in klines:
            ts_ms, o, h, low_v, c, v = kl[:6]
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            rows.append(
                {
                    "timestamp": ts,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "open": Decimal(str(o)),
                    "high": Decimal(str(h)),
                    "low": Decimal(str(low_v)),
                    "close": Decimal(str(c)),
                    "volume": Decimal(str(v)),
                    "quote_volume": None,
                    "trades_count": None,
                    "is_closed": True,
                }
            )

        stmt = pg_insert(OHLCV).values(rows).on_conflict_do_nothing(
            index_elements=["symbol", "timeframe", "timestamp"]
        )
        result = await session.execute(stmt)
        # rowcount riporta gli inseriti effettivi su Postgres
        return result.rowcount or 0

    # ------------------------------------------------------------------
    # Live websocket — skeleton, implementazione completa in Fase 4
    # ------------------------------------------------------------------

    async def stream_ohlcv_live(
        self,
        symbol: str,
        timeframe: str,
    ) -> None:
        """Skeleton: websocket per candele live.

        TODO Fase 4: usare ccxt.pro o websockets diretti su
        wss://stream.binance.com:9443/ws/{symbol}@kline_{interval}.
        """
        raise NotImplementedError(
            "Live streaming sarà implementato in Fase 4 — vedi roadmap"
        )


# ---------------------------------------------------------------------------
# Helper per uso da scripts/backfill.py
# ---------------------------------------------------------------------------


async def backfill_symbol_all_timeframes(
    session: AsyncSession,
    symbol: str,
    years: int = 5,
    timeframes: list[str] | None = None,
) -> dict[str, int]:
    """Backfill di tutti i timeframe configurati per un singolo symbol.

    Returns:
        Dict timeframe → num candele inserite.
    """
    settings = get_settings()
    timeframes = timeframes or settings.timeframes
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365 * years)

    results: dict[str, int] = {}
    async with BinanceConnector() as binance:
        for tf in timeframes:
            count = await binance.backfill_ohlcv(
                session=session,
                symbol=symbol,
                timeframe=tf,
                start=start,
                end=end,
            )
            results[tf] = count
            await session.commit()  # commit per timeframe per limitare lock
    return results
