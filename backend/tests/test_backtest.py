"""Test backtest engine — unit + integration.

Test focus:
    - Metriche su returns sintetici con valori noti
    - Edge cases (0 trades, all losing)
    - Strategy registry completo
    - Endpoint registrato

Lasciamo fuori dal test in-process l'esecuzione di vectorbt vera (richiede
numba JIT 30s al primo import, rallenta i test) — la verifica end-to-end
è coperta dal browser test su /backtest.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Metriche
# ---------------------------------------------------------------------------


def test_metrics_zero_trades_no_crash() -> None:
    from app.backtest.metrics import compute_metrics

    initial = 10_000.0
    equity = pd.Series(
        [initial] * 10,
        index=pd.date_range("2026-01-01", periods=10, freq="4h", tz="UTC"),
    )
    m = compute_metrics(equity, [], "4h", initial)
    assert m.n_trades == 0
    assert m.total_return == 0.0
    assert m.max_drawdown == 0.0
    assert m.win_rate is None  # indefinito senza trade
    assert m.profit_factor is None


def test_metrics_total_return_correct() -> None:
    from app.backtest.metrics import compute_metrics

    initial = 10_000.0
    equity = pd.Series(
        [10_000.0, 10_500.0, 11_000.0],
        index=pd.date_range("2026-01-01", periods=3, freq="1d", tz="UTC"),
    )
    m = compute_metrics(equity, [500.0, 500.0], "1d", initial)
    assert m.total_return == pytest.approx(0.10, rel=1e-3)
    assert m.final_equity == 11_000.0
    assert m.n_trades == 2
    assert m.win_rate == 1.0  # tutti vincenti


def test_metrics_max_drawdown() -> None:
    """Equity peak 12000 → trough 9000 → drawdown -25%."""
    from app.backtest.metrics import compute_metrics

    initial = 10_000.0
    equity = pd.Series(
        [10_000.0, 12_000.0, 9_000.0, 11_000.0],
        index=pd.date_range("2026-01-01", periods=4, freq="1d", tz="UTC"),
    )
    m = compute_metrics(equity, [], "1d", initial)
    assert m.max_drawdown == pytest.approx(-0.25, rel=1e-3)


def test_metrics_all_losing_trades() -> None:
    from app.backtest.metrics import compute_metrics

    initial = 10_000.0
    equity = pd.Series(
        np.linspace(10_000.0, 7_000.0, 100),
        index=pd.date_range("2026-01-01", periods=100, freq="4h", tz="UTC"),
    )
    pnls = [-30.0] * 100
    m = compute_metrics(equity, pnls, "4h", initial)
    assert m.total_return == pytest.approx(-0.30, rel=1e-3)
    assert m.win_rate == 0.0
    # Solo loss → profit_factor None (no gains)
    assert m.profit_factor is None
    # Max drawdown coerente con perdita continua
    assert m.max_drawdown < 0


def test_metrics_sharpe_finite_for_positive_drift() -> None:
    """Returns positivi con noise contenuto → Sharpe > 0 finito."""
    from app.backtest.metrics import compute_metrics

    rng = np.random.default_rng(42)
    n = 500
    daily_returns = rng.normal(0.001, 0.01, n)  # 0.1% drift, 1% vol
    equity_vals = 10_000.0 * np.cumprod(1 + daily_returns)
    equity = pd.Series(
        equity_vals,
        index=pd.date_range("2024-01-01", periods=n, freq="1d", tz="UTC"),
    )
    m = compute_metrics(equity, [], "1d", 10_000.0)
    assert m.sharpe is not None
    assert math.isfinite(m.sharpe)
    assert m.sharpe > 0  # drift positivo


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------


def test_strategy_registry_complete() -> None:
    from app.backtest.strategies import STRATEGY_REGISTRY

    expected = {"rsi_mean_reversion", "ema_cross", "macd_cross", "bb_breakout"}
    assert expected <= set(STRATEGY_REGISTRY.keys())
    for spec in STRATEGY_REGISTRY.values():
        assert spec.params, f"Strategy '{spec.id}' senza params"
        assert spec.family in {
            "trend_follow",
            "mean_reversion",
            "breakout",
            "volatility",
        }


def test_strategy_validate_params_defaults() -> None:
    from app.backtest.strategies import get_strategy

    spec = get_strategy("rsi_mean_reversion")
    out = spec.validate_params({})
    assert out["rsi_period"] == 14
    assert out["buy_below"] == 30.0
    assert out["sell_above"] == 70.0


def test_strategy_signals_shape_match_input() -> None:
    """Le strategie restituiscono BoolSeries con stesso index dell'input."""
    from app.backtest.strategies import get_strategy

    rng = np.random.default_rng(7)
    n = 200
    base = 100.0 + rng.normal(0, 1, n).cumsum()
    df = pd.DataFrame(
        {
            "open": base,
            "high": base + 0.5,
            "low": base - 0.5,
            "close": base,
            "volume": rng.uniform(100, 1000, n),
        },
        index=pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC"),
    )

    spec = get_strategy("rsi_mean_reversion")
    params = spec.validate_params({})
    entries, exits = spec.fn(df, params)
    assert len(entries) == n
    assert len(exits) == n
    assert entries.dtype == bool
    assert exits.dtype == bool


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_backtest_routes_registered() -> None:
    from app.main import create_app

    app = create_app()
    routes = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/api/v1/strategies" in routes
    assert "/api/v1/backtest/run" in routes
    assert "/api/v1/backtest/walk-forward" in routes


# ---------------------------------------------------------------------------
# Walk-forward
# ---------------------------------------------------------------------------


def test_walkforward_verdict_robust() -> None:
    """4/5 finestre vincenti con mean Sharpe > 0.3 → robust."""
    from app.backtest.walk_forward import _verdict

    verdict, _ = _verdict(
        n_windows=5,
        n_winning=5,
        n_with_trades=5,
        mean_return=0.10,
        mean_sharpe=0.8,
    )
    assert verdict == "robust"


def test_walkforward_verdict_unstable() -> None:
    """0/5 finestre vincenti → unstable."""
    from app.backtest.walk_forward import _verdict

    verdict, _ = _verdict(
        n_windows=5,
        n_winning=1,
        n_with_trades=5,
        mean_return=-0.05,
        mean_sharpe=-0.3,
    )
    assert verdict == "unstable"


def test_walkforward_verdict_mixed() -> None:
    """3/5 finestre vincenti → mixed (40-79%)."""
    from app.backtest.walk_forward import _verdict

    verdict, _ = _verdict(
        n_windows=5,
        n_winning=3,
        n_with_trades=5,
        mean_return=0.02,
        mean_sharpe=0.1,
    )
    assert verdict == "mixed"


def test_walkforward_verdict_no_signal() -> None:
    """Solo 1/5 finestre con trade → no_signal."""
    from app.backtest.walk_forward import _verdict

    verdict, _ = _verdict(
        n_windows=5,
        n_winning=0,
        n_with_trades=1,
        mean_return=0.0,
        mean_sharpe=None,
    )
    assert verdict == "no_signal"


def test_walkforward_min_data_check() -> None:
    """Senza abbastanza candele deve fallire con ValueError."""
    import numpy as np
    import pandas as pd

    from app.backtest.walk_forward import run_walk_forward

    df = pd.DataFrame(
        {
            "open": [100.0] * 100,
            "high": [101.0] * 100,
            "low": [99.0] * 100,
            "close": [100.0] * 100,
            "volume": [1000.0] * 100,
        },
        index=pd.date_range("2026-01-01", periods=100, freq="1h", tz="UTC"),
    )
    # 100 candele / 5 windows = 20 per finestra → sotto minimo 50
    try:
        run_walk_forward(
            df=df,
            strategy_id="rsi_mean_reversion",
            params={},
            symbol="BTC/USDT",
            timeframe="1h",
            n_windows=5,
        )
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ValueError attesa per dati insufficienti")
