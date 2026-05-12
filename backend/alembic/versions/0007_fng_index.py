"""fng_index table — Fear & Greed Index storage

Revision ID: 0007_fng_index
Revises: 0006_drop_legacy
Create Date: 2026-05-12
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "0007_fng_index"
down_revision = "0006_drop_legacy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fng_index",
        sa.Column("fng_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Integer, nullable=False),
        sa.Column("classification", sa.String(24), nullable=False),
        sa.PrimaryKeyConstraint("fng_date"),
    )
    op.create_index("ix_fng_index_date", "fng_index", ["fng_date"])


def downgrade() -> None:
    op.drop_index("ix_fng_index_date", table_name="fng_index")
    op.drop_table("fng_index")
