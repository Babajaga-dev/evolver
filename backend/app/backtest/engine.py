"""Backtest engine — facade su vectorbt.Portfolio.

Responsibility:
    1. Convertire OHLCV ORM rows → DataFrame numerico
    2. Far girare la strategia per ottenere ``entries`` e ``exits`` (BoolSeries)
    3. Costruire un ``vectorbt.Portfolio.from_signals`` con fee/slippage
    4. Estrarre equity curve, trades, metriche
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.metrics import Metrics, compute_metrics
from app.backtest.strategies import StrategySpec, get_strategy

# vectorbt è importato lazy per non rallentare l'avvio dell'app FastAPI
# (il primo import compila numba JIT ~30s).


@dataclass
class TradeRecord:
    """Singolo trade chiuso."""

    entry_time: datetime
    exit_time: datetime | None
    entry_price: float
    exit_price: float | None
    size: float
    direction: str  # "long" — short non supportato in v1
    pnl: float
    pnl_pct: float
    return_value: float


@dataclass
class EquityPoint:
    timestamp: datetime
    equity: float
    drawdown: float  # negativo, da peak corrente


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    strategy_id: str
    strategy_label: str
    params: dict[str, Any]
    initial_cash: float
    fee: float
    slippage: float
    start: datetime
    end: datetime
    equity_curve: list[EquityPoint]
    trades: list[TradeRecord]
    metrics: Metrics


class BacktestEngine:
    """Esegue un backtest single-asset, single-strategy.

    Default fee/slippage allineati a Binance spot taker (0.10% / 2bps).
    """

    def __init__(
        self,
        *,
        fee: float = 0.001,
        slippage_bps: float = 2.0,
        freq: str | None = None,
    ) -> None:
        self.fee = fee
        self.slippage = slippage_bps / 10_000  # 2bps → 0.0002
        self.freq = freq

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(
        self,
        df: pd.DataFrame,
        strategy_id: str,
        params: dict[str, Any],
        *,
        symbol: str,
        timeframe: str,
        initial_cash: float = 10_000.0,
        position_size_pct: float = 100.0,
    ) -> BacktestResult:
        """Esegue backtest e restituisce risultato strutturato.

        Args:
            position_size_pct: percentuale del cash da rischiare per entry (1-100).
                Default 100 = all-in (comportamento storico). Il GA passa
                questo dal cromosoma per esplorare il sizing.
        """
        spec = get_strategy(strategy_id)
        validated = spec.validate_params(params)

        df = self._prepare_df(df)
        if df.empty:
            return self._empty_result(spec, validated, symbol, timeframe, initial_cash)

        entries, exits = spec.fn(df, validated)
        # Riallinea booleane all'indice di df (paranoia)
        entries = entries.reindex(df.index, fill_value=False).astype(bool)
        exits = exits.reindex(df.index, fill_value=False).astype(bool)

        # Import lazy
        import vectorbt as vbt

        # position_size_pct: 4.83 → 0.0483 (frazione del cash). Clamp [0.01, 1.0].
        size_frac = max(0.0001, min(1.0, float(position_size_pct) / 100.0))

        pf = vbt.Portfolio.from_signals(
            close=df["close"],
            entries=entries,
            exits=exits,
            init_cash=initial_cash,
            fees=self.fee,
            slippage=self.slippage,
            freq=self.freq or _infer_freq(timeframe),
            size=size_frac,
            size_type="percent",
        )

        equity = pf.value()
        equity = equity.dropna()

        # Equity curve + drawdown
        peak = equity.cummax()
        dd_series = (equity - peak) / peak
        equity_points = [
            EquityPoint(
                timestamp=ts.to_pydatetime(),
                equity=float(equity.loc[ts]),
                drawdown=float(dd_series.loc[ts]),
            )
            for ts in equity.index
        ]

        # Trade list
        trades = self._extract_trades(pf, df)

        # Metrics
        pnls = [t.pnl for t in trades]
        metrics = compute_metrics(
            equity=equity,
            trade_pnls=pnls,
            timeframe=timeframe,
            initial_cash=initial_cash,
        )

        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy_id=strategy_id,
            strategy_label=spec.label,
            params=validated,
            initial_cash=initial_cash,
            fee=self.fee,
            slippage=self.slippage,
            start=df.index[0].to_pydatetime(),
            end=df.index[-1].to_pydatetime(),
            equity_curve=equity_points,
            trades=trades,
            metrics=metrics,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_df(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        # Normalizza colonne lowercase
        df = df.rename(columns={c: c.lower() for c in df.columns})
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame OHLCV manca colonne: {missing}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame deve avere DatetimeIndex")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        return df.sort_index()

    @staticmethod
    def _extract_trades(pf: Any, df: pd.DataFrame) -> list[TradeRecord]:
        """Estrae trade list da vectorbt portfolio."""
        try:
            records = pf.trades.records_readable
        except Exception:
            return []

        if records is None or len(records) == 0:
            return []

        trades: list[TradeRecord] = []
        for _, row in records.iterrows():
            # vectorbt usa nomi colonna leggibili tipo "Entry Index", "Exit Index"
            # ma per sicurezza tentiamo varianti
            entry_idx = _get_first(row, ["Entry Index", "Entry Timestamp", "Entry Idx"])
            exit_idx = _get_first(row, ["Exit Index", "Exit Timestamp", "Exit Idx"])
            entry_price = _get_first(row, ["Avg Entry Price", "Entry Price"])
            exit_price = _get_first(row, ["Avg Exit Price", "Exit Price"])
            size = _get_first(row, ["Size"])
            pnl = _get_first(row, ["PnL", "Pnl"])
            ret = _get_first(row, ["Return", "Return %"])
            direction = str(
                _get_first(row, ["Direction", "Side"], default="Long")
            ).lower()

            entry_ts = _to_dt(entry_idx, df)
            exit_ts = _to_dt(exit_idx, df) if exit_idx is not None else None

            trades.append(
                TradeRecord(
                    entry_time=entry_ts,
                    exit_time=exit_ts,
                    entry_price=float(entry_price) if entry_price is not None else 0.0,
                    exit_price=float(exit_price) if exit_price is not None and not _isnan(exit_price) else None,
                    size=float(size) if size is not None else 0.0,
                    direction="long" if "long" in direction else direction,
                    pnl=float(pnl) if pnl is not None and not _isnan(pnl) else 0.0,
                    pnl_pct=float(ret) if ret is not None and not _isnan(ret) else 0.0,
                    return_value=float(ret) if ret is not None and not _isnan(ret) else 0.0,
                )
            )
        return trades

    @staticmethod
    def _empty_result(
        spec: StrategySpec,
        validated: dict[str, Any],
        symbol: str,
        timeframe: str,
        initial_cash: float,
    ) -> BacktestResult:
        now = datetime.utcnow()
        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy_id=spec.id,
            strategy_label=spec.label,
            params=validated,
            initial_cash=initial_cash,
            fee=0.001,
            slippage=0.0002,
            start=now,
            end=now,
            equity_curve=[],
            trades=[],
            metrics=compute_metrics(
                equity=pd.Series([initial_cash], dtype=float),
                trade_pnls=[],
                timeframe=timeframe,
                initial_cash=initial_cash,
            ),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _infer_freq(timeframe: str) -> str:
    """Mapping timeframe → pandas freq string."""
    mapping = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1D",
    }
    return mapping.get(timeframe, "1h")


def _get_first(row: Any, keys: list[str], default: Any = None) -> Any:
    for k in keys:
        if k in row:
            return row[k]
    return default


def _to_dt(value: Any, df: pd.DataFrame) -> datetime:
    """Converte indice/posizione in datetime."""
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, (int, np.integer)):
        idx = int(value)
        if 0 <= idx < len(df):
            return df.index[idx].to_pydatetime()
    if isinstance(value, datetime):
        return value
    return df.index[0].to_pydatetime()


def _isnan(v: Any) -> bool:
    try:
        return bool(np.isnan(v))
    except (TypeError, ValueError):
        return False
