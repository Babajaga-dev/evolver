"""system_settings table for runtime feature flags

Revision ID: 0002_system_settings
Revises: 0001_initial
Create Date: 2026-05-09 20:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_system_settings"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name="pk_system_settings"),
    )

    # Seed dei default — tutti disabilitati di default per safety.
    # La rotta admin /control li toggla a runtime.
    op.execute(
        """
        INSERT INTO system_settings (key, value, description) VALUES
        (
          'news.auto_refresh',
          '{"enabled": false, "interval_seconds": 300}'::jsonb,
          'Fetch automatico dei feed RSS ogni N secondi'
        ),
        (
          'news.auto_score',
          '{"enabled": false, "interval_seconds": 600, "batch_limit": 20, "concurrency": 4}'::jsonb,
          'Scoring automatico via Claude Haiku delle news in attesa'
        ),
        (
          'ohlcv.auto_backfill',
          '{"enabled": false, "interval_seconds": 3600}'::jsonb,
          'Backfill automatico delle candele Binance ogni N secondi'
        )
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("system_settings")
