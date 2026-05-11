"""Application settings loaded from environment variables.

Tutte le configurazioni passano da qui — niente os.environ sparsi nel codice.
Pydantic-settings valida i tipi e fallisce all'avvio se manca qualcosa di
obbligatorio.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Configurazione applicativa.

    Caricata da ``.env`` in dev, da Dokploy environment variables in prod.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Environment ---
    env: Literal["dev", "staging", "prod"] = Field(default="dev")
    debug: bool = Field(default=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(default="INFO")

    # --- API ---
    api_host: str = Field(default="0.0.0.0")  # noqa: S104 — intenzionale per container
    api_port: int = Field(default=8000)
    # NoDecode disabilita il parsing JSON automatico di pydantic-settings:
    # senza, "http://x,http://y" viene visto come JSON malformato e crasha
    # PRIMA che il field_validator possa intervenire.
    api_cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"],
    )

    # --- Database ---
    database_url: str = Field(
        description="PostgreSQL DSN, es. postgresql+asyncpg://user:pass@host:5432/db",
    )
    database_url_sync: str = Field(
        description="DSN sync per Alembic, es. postgresql+psycopg://user:pass@host:5432/db",
    )
    db_pool_size: int = Field(default=10)
    db_max_overflow: int = Field(default=20)
    db_pool_timeout: int = Field(default=30)
    db_echo: bool = Field(default=False)

    # --- Redis ---
    redis_url: str = Field(default="redis://localhost:6379/0")

    # --- Exchange ---
    binance_api_key: SecretStr | None = Field(default=None)  # opzionale per dati pubblici
    binance_api_secret: SecretStr | None = Field(default=None)
    binance_use_testnet: bool = Field(default=False)

    # --- Trading universe ---
    symbols: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["BTC/USDT", "ETH/USDT"]
    )
    timeframes: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["15m", "1h", "4h", "1d"],
    )

    # --- Paper trading ---
    paper_initial_balance_usdt: float = Field(default=10_000.0)
    paper_fee_maker: float = Field(default=0.001)  # 0.10% Binance default
    paper_fee_taker: float = Field(default=0.001)
    paper_slippage_bps: float = Field(default=2.0)  # 2 basis points = 0.02%

    # --- News ---
    cryptopanic_api_key: SecretStr | None = Field(default=None)

    @field_validator("api_cors_origins", "symbols", "timeframes", mode="before")
    @classmethod
    def _split_csv(cls, v: object) -> object:
        """Permette di passare liste come stringa CSV o JSON in env vars.

        Con ``NoDecode`` sui campi, pydantic-settings passa qui la stringa
        raw — siamo noi a decidere se è CSV o JSON.
        """
        if isinstance(v, str):
            stripped = v.strip()
            if stripped.startswith("["):
                # JSON list — delega al parser standard
                import json

                return json.loads(stripped)
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return v

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Singleton delle settings — caricato una volta sola all'avvio."""
    return Settings()  # type: ignore[call-arg]
