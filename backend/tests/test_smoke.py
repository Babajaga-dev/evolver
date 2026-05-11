"""Smoke tests — verificano che il package si importi e i modelli siano sani.

Non richiedono DB o Redis live.
"""

from __future__ import annotations

import pytest


def test_app_imports() -> None:
    """Il pacchetto si importa senza errori."""
    import app

    assert app.__version__ == "0.1.0"


def test_settings_load_with_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings si caricano correttamente con env vars minime."""
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://test:test@localhost/test",
    )
    monkeypatch.setenv(
        "DATABASE_URL_SYNC",
        "postgresql+psycopg://test:test@localhost/test",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    # Reset cache singleton
    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.env == "dev"
    assert "BTC/USDT" in settings.symbols
    assert "ETH/USDT" in settings.symbols
    assert settings.claude_model_haiku.startswith("claude-haiku-4-5")
    assert settings.claude_model_opus.startswith("claude-opus-4-6")


def test_models_register_metadata() -> None:
    """Tutti i modelli sono registrati su Base.metadata."""
    from app.models import Base

    table_names = set(Base.metadata.tables.keys())
    expected = {
        "ohlcv",
        "populations",
        "generations",
        "strategies",
        "fitness_evaluations",
        "paper_trades",
        "equity_snapshots",
    }
    missing = expected - table_names
    assert not missing, f"Tabelle mancanti su metadata: {missing}"


def test_fastapi_app_creates() -> None:
    """L'app FastAPI si istanzia."""
    from app.main import create_app

    app = create_app()
    routes = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/health" in routes
    assert "/version" in routes


def test_v1_routes_registered() -> None:
    """I router v1 (markets, coverage, ohlcv) sono inclusi."""
    from app.main import create_app

    app = create_app()
    routes = {r.path for r in app.routes}  # type: ignore[attr-defined]
    assert "/api/v1/markets" in routes
    assert "/api/v1/coverage" in routes
    # FastAPI normalizza il path param ``{symbol:path}`` rimuovendo il modificatore
    assert any(
        path.startswith("/api/v1/ohlcv/") and path.endswith("/{timeframe}")
        for path in routes
    ), f"Route OHLCV mancante in: {routes}"


def test_indicators_registry_complete() -> None:
    """Tutti gli indicatori v1 sono registrati con params e output keys."""
    from app.indicators import INDICATOR_REGISTRY

    expected = {"rsi", "ema", "sma", "macd", "bbands", "atr", "adx", "stoch"}
    missing = expected - set(INDICATOR_REGISTRY.keys())
    assert not missing, f"Indicatori mancanti: {missing}"
    for spec in INDICATOR_REGISTRY.values():
        assert spec.params, f"Indicatore '{spec.id}' senza params"
        assert spec.output_keys, f"Indicatore '{spec.id}' senza output_keys"
        assert spec.kind in {"overlay", "panel"}


def test_indicator_compute_on_synthetic_data() -> None:
    """Computo RSI/EMA su dati sintetici — verifica end-to-end della pipeline."""
    import numpy as np
    import pandas as pd

    from app.indicators import compute

    rng = np.random.default_rng(42)
    n = 100
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

    rsi_out, rsi_params = compute("rsi", df, {"period": 14})
    assert "rsi" in rsi_out
    assert rsi_params["period"] == 14
    # RSI range 0-100 dopo warm-up
    valid = rsi_out["rsi"].dropna()
    assert len(valid) > 50
    assert (valid >= 0).all() and (valid <= 100).all()

    macd_out, _ = compute("macd", df, {})
    assert {"macd", "signal", "histogram"} <= set(macd_out.keys())


def test_indicator_param_validation() -> None:
    """Params fuori range → ValueError."""
    import pandas as pd

    from app.indicators import compute

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

    # period sotto il minimo
    try:
        compute("rsi", df, {"period": 1})
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("ValueError attesa per period=1")


def test_ohlcv_schemas_serialize() -> None:
    """OHLCVCandle accetta Decimal e mantiene precision via json_encoders."""
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.schemas.ohlcv import OHLCVCandle

    candle = OHLCVCandle(
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        symbol="BTC/USDT",
        timeframe="4h",
        open=Decimal("65432.12345678"),
        high=Decimal("65500.0"),
        low=Decimal("65400.0"),
        close=Decimal("65450.99"),
        volume=Decimal("123.456"),
    )
    dumped = candle.model_dump(mode="json")
    assert dumped["symbol"] == "BTC/USDT"
    # Decimal serializzato come stringa per preservare precision
    assert dumped["open"] == "65432.12345678"


def test_timeframe_constants() -> None:
    """I timeframe ammessi includono quelli usati nelle settings."""
    from app.exchanges.binance import TIMEFRAME_MS
    from app.models.market import ALLOWED_TIMEFRAMES

    for tf in ("15m", "1h", "4h", "1d"):
        assert tf in TIMEFRAME_MS
        assert tf in ALLOWED_TIMEFRAMES
