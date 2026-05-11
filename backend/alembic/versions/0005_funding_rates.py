"""funding_rates table

Revision ID: 0005_funding
Revises: 0004_drop_news
Create Date: 2026-05-11
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "0005_funding"
down_revision = "0004_drop_news"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "funding_rates",
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("funding_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("funding_rate", sa.Float, nullable=False),
        sa.Column("mark_price", sa.Float, nullable=True),
        sa.PrimaryKeyConstraint("symbol", "funding_time"),
    )
    op.create_index("ix_funding_rates_symbol_time", "funding_rates", ["symbol", "funding_time"])


def downgrade() -> None:
    op.drop_index("ix_funding_rates_symbol_time", table_name="funding_rates")
    op.drop_table("funding_rates")
