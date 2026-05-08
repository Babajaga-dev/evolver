"""initial schema with TimescaleDB hypertables

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-08 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Estensioni richieste
    # ------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "timescaledb"')

    # ------------------------------------------------------------------
    # ohlcv (sarà hypertable)
    # ------------------------------------------------------------------
    op.create_table(
        "ohlcv",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("open", sa.Numeric(20, 8), nullable=False),
        sa.Column("high", sa.Numeric(20, 8), nullable=False),
        sa.Column("low", sa.Numeric(20, 8), nullable=False),
        sa.Column("close", sa.Numeric(20, 8), nullable=False),
        sa.Column("volume", sa.Numeric(28, 8), nullable=False),
        sa.Column("quote_volume", sa.Numeric(28, 8), nullable=True),
        sa.Column("trades_count", sa.Integer(), nullable=True),
        sa.Column(
            "is_closed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.PrimaryKeyConstraint(
            "symbol", "timeframe", "timestamp", name="pk_ohlcv"
        ),
    )
    op.create_index("ix_ohlcv_timestamp", "ohlcv", ["timestamp"])
    op.create_index("ix_ohlcv_symbol_timeframe", "ohlcv", ["symbol", "timeframe"])

    # Conversione hypertable: chunk di 7 giorni — bilancia query speed e
    # numero di chunk per BTC+ETH × 4 timeframe
    op.execute(
        "SELECT create_hypertable('ohlcv', 'timestamp', "
        "chunk_time_interval => INTERVAL '7 days', "
        "if_not_exists => TRUE, migrate_data => TRUE)"
    )

    # Compression policy: candele più vecchie di 30 giorni vengono compresse
    op.execute(
        "ALTER TABLE ohlcv SET ("
        "timescaledb.compress, "
        "timescaledb.compress_segmentby = 'symbol, timeframe', "
        "timescaledb.compress_orderby = 'timestamp DESC')"
    )
    op.execute("SELECT add_compression_policy('ohlcv', INTERVAL '30 days')")

    # ------------------------------------------------------------------
    # news_raw
    # ------------------------------------------------------------------
    op.create_table(
        "news_raw",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=256), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_news_raw"),
        sa.UniqueConstraint("source", "external_id", name="uq_news_raw_source_external"),
    )
    op.create_index("ix_news_raw_published_at", "news_raw", ["published_at"])
    op.create_index("ix_news_raw_hash", "news_raw", ["hash"])

    # ------------------------------------------------------------------
    # news_scored
    # ------------------------------------------------------------------
    op.create_table(
        "news_scored",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("news_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "assets_mentioned",
            postgresql.ARRAY(sa.String(length=20)),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("factual_impact", sa.Float(), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "ttl_hours", sa.Integer(), nullable=False, server_default=sa.text("24")
        ),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "scored_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "factual_impact >= -1 AND factual_impact <= 1",
            name="ck_news_scored_factual_impact_range",
        ),
        sa.CheckConstraint(
            "sentiment_score >= -1 AND sentiment_score <= 1",
            name="ck_news_scored_sentiment_score_range",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_news_scored_confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["news_id"], ["news_raw.id"], ondelete="CASCADE",
            name="fk_news_scored_news_id_news_raw",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_news_scored"),
        sa.UniqueConstraint("news_id", name="uq_news_scored_news_id"),
    )
    op.create_index("ix_news_scored_scored_at", "news_scored", ["scored_at"])
    op.create_index(
        "ix_news_scored_assets",
        "news_scored",
        ["assets_mentioned"],
        postgresql_using="gin",
    )

    # ------------------------------------------------------------------
    # populations
    # ------------------------------------------------------------------
    op.create_table(
        "populations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("population_size", sa.Integer(), nullable=False),
        sa.Column(
            "config", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_populations"),
    )

    # ------------------------------------------------------------------
    # generations
    # ------------------------------------------------------------------
    op.create_table(
        "generations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("population_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("best_fitness", sa.Float(), nullable=True),
        sa.Column("mean_fitness", sa.Float(), nullable=True),
        sa.Column("std_fitness", sa.Float(), nullable=True),
        sa.Column("diversity_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["population_id"],
            ["populations.id"],
            ondelete="CASCADE",
            name="fk_generations_population_id_populations",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_generations"),
    )
    op.create_index(
        "ix_generations_population_number",
        "generations",
        ["population_id", "number"],
    )

    # ------------------------------------------------------------------
    # strategies
    # ------------------------------------------------------------------
    op.create_table(
        "strategies",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("generation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "chromosome", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "parent_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("ARRAY[]::uuid[]"),
        ),
        sa.Column("aggregate_fitness", sa.Float(), nullable=True),
        sa.Column(
            "is_elite",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["generation_id"],
            ["generations.id"],
            ondelete="CASCADE",
            name="fk_strategies_generation_id_generations",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_strategies"),
    )
    op.create_index("ix_strategies_generation", "strategies", ["generation_id"])
    op.create_index(
        "ix_strategies_chromosome",
        "strategies",
        ["chromosome"],
        postgresql_using="gin",
    )

    # ------------------------------------------------------------------
    # fitness_evaluations
    # ------------------------------------------------------------------
    op.create_table(
        "fitness_evaluations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("window_index", sa.Integer(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sharpe", sa.Float(), nullable=True),
        sa.Column("calmar", sa.Float(), nullable=True),
        sa.Column("sortino", sa.Float(), nullable=True),
        sa.Column("max_drawdown", sa.Float(), nullable=True),
        sa.Column("total_return", sa.Float(), nullable=True),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("profit_factor", sa.Float(), nullable=True),
        sa.Column(
            "n_trades",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("fitness", sa.Float(), nullable=True),
        sa.Column(
            "evaluated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "window_index >= 0", name="ck_fitness_evaluations_window_index_nonneg"
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            ondelete="CASCADE",
            name="fk_fitness_evaluations_strategy_id_strategies",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fitness_evaluations"),
    )
    op.create_index(
        "ix_fitness_strategy_window",
        "fitness_evaluations",
        ["strategy_id", "window_index"],
        unique=True,
    )

    # ------------------------------------------------------------------
    # paper_trades
    # ------------------------------------------------------------------
    op.create_table(
        "paper_trades",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("strategy_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("timeframe", sa.String(length=8), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("quantity", sa.Numeric(28, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=False),
        sa.Column("exit_price", sa.Numeric(20, 8), nullable=True),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fees",
            sa.Numeric(20, 8),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("pnl", sa.Numeric(20, 8), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Numeric(20, 8), nullable=True),
        sa.Column("take_profit", sa.Numeric(20, 8), nullable=True),
        sa.Column(
            "open_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "close_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["strategy_id"],
            ["strategies.id"],
            ondelete="SET NULL",
            name="fk_paper_trades_strategy_id_strategies",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paper_trades"),
    )
    op.create_index("ix_paper_trades_strategy", "paper_trades", ["strategy_id"])
    op.create_index("ix_paper_trades_entry_time", "paper_trades", ["entry_time"])
    op.create_index("ix_paper_trades_status", "paper_trades", ["status"])

    # ------------------------------------------------------------------
    # equity_snapshots (hypertable)
    # ------------------------------------------------------------------
    op.create_table(
        "equity_snapshots",
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "portfolio_id",
            sa.String(length=64),
            nullable=False,
            server_default=sa.text("'paper-v1'"),
        ),
        sa.Column("balance_quote", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "holdings",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("equity", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "drawdown_from_peak",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "open_positions_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.PrimaryKeyConstraint(
            "portfolio_id", "timestamp", name="pk_equity_snapshots"
        ),
    )
    op.create_index("ix_equity_timestamp", "equity_snapshots", ["timestamp"])
    op.execute(
        "SELECT create_hypertable('equity_snapshots', 'timestamp', "
        "chunk_time_interval => INTERVAL '30 days', "
        "if_not_exists => TRUE, migrate_data => TRUE)"
    )


def downgrade() -> None:
    op.drop_index("ix_equity_timestamp", table_name="equity_snapshots")
    op.drop_table("equity_snapshots")
    op.drop_index("ix_paper_trades_status", table_name="paper_trades")
    op.drop_index("ix_paper_trades_entry_time", table_name="paper_trades")
    op.drop_index("ix_paper_trades_strategy", table_name="paper_trades")
    op.drop_table("paper_trades")
    op.drop_index(
        "ix_fitness_strategy_window", table_name="fitness_evaluations"
    )
    op.drop_table("fitness_evaluations")
    op.drop_index("ix_strategies_chromosome", table_name="strategies")
    op.drop_index("ix_strategies_generation", table_name="strategies")
    op.drop_table("strategies")
    op.drop_index("ix_generations_population_number", table_name="generations")
    op.drop_table("generations")
    op.drop_table("populations")
    op.drop_index("ix_news_scored_assets", table_name="news_scored")
    op.drop_index("ix_news_scored_scored_at", table_name="news_scored")
    op.drop_table("news_scored")
    op.drop_index("ix_news_raw_hash", table_name="news_raw")
    op.drop_index("ix_news_raw_published_at", table_name="news_raw")
    op.drop_table("news_raw")
    op.drop_index("ix_ohlcv_symbol_timeframe", table_name="ohlcv")
    op.drop_index("ix_ohlcv_timestamp", table_name="ohlcv")
    op.drop_table("ohlcv")
