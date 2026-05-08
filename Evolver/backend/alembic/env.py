"""Alembic environment.

Usa l'URL **sync** delle settings (psycopg) — Alembic non gira in event loop,
e mescolare async con migration online è una sorgente garantita di mal di
testa. L'app runtime usa l'URL async (asyncpg).
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Importa tutti i modelli per popolare Base.metadata
from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402, F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.database_url_sync)

target_metadata = Base.metadata


def include_object(
    obj: object,
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: FBT001
    compare_to: object,
) -> bool:
    """Esclude oggetti gestiti da TimescaleDB (chunk, indici interni)."""
    if type_ == "table" and name and name.startswith("_hyper"):
        return False
    if type_ == "schema" and name in ("_timescaledb_internal", "_timescaledb_catalog"):
        return False
    return True


def run_migrations_offline() -> None:
    """Genera SQL senza connettersi (per dump/review)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Esegue migration contro un DB live."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
