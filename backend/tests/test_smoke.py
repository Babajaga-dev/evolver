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


def test_timeframe_constants() -> None:
    """I timeframe ammessi includono quelli usati nelle settings."""
    from app.exchanges.binance import TIMEFRAME_MS
    from app.models.market import ALLOWED_TIMEFRAMES

    for tf in ("15m", "1h", "4h", "1d"):
        assert tf in TIMEFRAME_MS
        assert tf in ALLOWED_TIMEFRAMES
