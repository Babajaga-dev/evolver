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
        "news_raw",
        "news_scored",
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
