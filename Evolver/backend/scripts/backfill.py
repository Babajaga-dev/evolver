"""CLI: backfill candele storiche per tutti i symbol/timeframe configurati.

Esempio:
    uv run python -m scripts.backfill --symbols BTC/USDT,ETH/USDT --years 5
    uv run python -m scripts.backfill --symbols BTC/USDT --timeframes 1h,4h --years 2
"""

from __future__ import annotations

import argparse
import asyncio

from app.core.config import get_settings
from app.core.db import session_scope
from app.core.logging import configure_logging, get_logger
from app.exchanges.binance import backfill_symbol_all_timeframes


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Evolver — backfill OHLCV")
    parser.add_argument(
        "--symbols",
        type=str,
        default=",".join(settings.symbols),
        help="CSV di symbol (default da settings)",
    )
    parser.add_argument(
        "--timeframes",
        type=str,
        default=",".join(settings.timeframes),
        help="CSV di timeframe (default da settings)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=5,
        help="Anni di storico da scaricare (default 5)",
    )
    return parser.parse_args()


async def main() -> None:
    configure_logging()
    log = get_logger("scripts.backfill")
    args = parse_args()

    symbols = [s.strip() for s in args.symbols.split(",") if s.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    log.info(
        "backfill.cli.start",
        symbols=symbols,
        timeframes=timeframes,
        years=args.years,
    )

    summary: dict[str, dict[str, int]] = {}
    for symbol in symbols:
        async with session_scope() as session:
            results = await backfill_symbol_all_timeframes(
                session=session,
                symbol=symbol,
                years=args.years,
                timeframes=timeframes,
            )
        summary[symbol] = results

    log.info("backfill.cli.done", summary=summary)


if __name__ == "__main__":
    asyncio.run(main())
