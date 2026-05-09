"""Test smoke per il GA engine.

Test focus:
    - Chromosome encoding/decoding
    - Fitness function su DataFrame sintetico
    - Routes registered
    - Verdict (sentinel) per cromosoma muto

Lasciamo fuori il test "run completo" perché il pymoo+vectorbt richiede
warm-up JIT (~30s) e rallenta troppo. Verifica end-to-end è coperta dal
browser test.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Chromosome
# ---------------------------------------------------------------------------


def test_chromosome_spec_for_rsi() -> None:
    from app.ga.chromosome import build_chromosome_spec

    spec = build_chromosome_spec("rsi_mean_reversion")
    assert spec.strategy_id == "rsi_mean_reversion"
    # Params della strategia + universal position_size_pct
    assert "rsi_period" in spec.param_names
    assert "buy_below" in spec.param_names
    assert "sell_above" in spec.param_names
    assert "position_size_pct" in spec.param_names
    # pymoo vars dict popolato
    assert len(spec.pymoo_vars) == len(spec.param_names)


def test_chromosome_spec_for_ema_cross() -> None:
    from app.ga.chromosome import build_chromosome_spec

    spec = build_chromosome_spec("ema_cross")
    assert "fast" in spec.param_names
    assert "slow" in spec.param_names
    assert "position_size_pct" in spec.param_names


def test_chromosome_decode_filters_extras() -> None:
    """decode_chromosome deve droppare keys non in spec.param_names."""
    from app.ga.chromosome import build_chromosome_spec, decode_chromosome

    spec = build_chromosome_spec("rsi_mean_reversion")
    raw = {
        "rsi_period": 14,
        "buy_below": 30.0,
        "sell_above": 70.0,
        "position_size_pct": 1.5,
        "extra_meta": "ignored",
    }
    decoded = decode_chromosome(raw, spec)
    assert "extra_meta" not in decoded
    assert decoded["rsi_period"] == 14


# ---------------------------------------------------------------------------
# Fitness
# ---------------------------------------------------------------------------


def test_fitness_returns_three_objectives() -> None:
    from app.ga.fitness import FitnessConfig, compute_fitness

    rng = np.random.default_rng(7)
    n = 600
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
    cfg = FitnessConfig(n_windows=2)
    result = compute_fitness(
        chromosome_params={
            "rsi_period": 14,
            "buy_below": 30.0,
            "sell_above": 70.0,
            "position_size_pct": 1.0,
        },
        df=df,
        strategy_id="rsi_mean_reversion",
        symbol="BTC/USDT",
        timeframe="1h",
        config=cfg,
    )
    assert len(result.objectives) == 3
    # objectives finiti
    for o in result.objectives:
        assert o == o  # not NaN


def test_fitness_sentinel_on_invalid_data() -> None:
    """Su DataFrame troppo corto → walk_forward fallisce → fitness sentinel."""
    from app.ga.fitness import FitnessConfig, compute_fitness

    df = pd.DataFrame(
        {
            "open": [100.0] * 30,
            "high": [101.0] * 30,
            "low": [99.0] * 30,
            "close": [100.0] * 30,
            "volume": [1000.0] * 30,
        },
        index=pd.date_range("2026-01-01", periods=30, freq="1h", tz="UTC"),
    )
    cfg = FitnessConfig(n_windows=3, no_trade_sentinel=10.0)
    result = compute_fitness(
        chromosome_params={
            "rsi_period": 14,
            "buy_below": 30.0,
            "sell_above": 70.0,
            "position_size_pct": 1.0,
        },
        df=df,
        strategy_id="rsi_mean_reversion",
        symbol="BTC/USDT",
        timeframe="1h",
        config=cfg,
    )
    # Sentinel = penalty alta
    assert result.objectives[0] >= cfg.no_trade_sentinel - 0.1


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def test_ga_routes_registered() -> None:
    from app.main import create_app

    app = create_app()
    routes = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/api/v1/ga/runs" in routes
    assert "/api/v1/ga/runs/{population_id}" in routes
