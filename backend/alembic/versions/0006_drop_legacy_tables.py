"""drop legacy tables (app/ga + app/paper removed)

Revision ID: 0006_drop_legacy
Revises: 0005_funding
Create Date: 2026-05-11
"""
from __future__ import annotations
from alembic import op

revision = "0006_drop_legacy"
down_revision = "0005_funding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Order matters: FKs cascade
    for tbl in ("fitness_evaluations", "paper_trades", "equity_snapshots",
                "strategies", "generations", "populations"):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")


def downgrade() -> None:
    # No-op: schema rimosso definitivamente
    pass
