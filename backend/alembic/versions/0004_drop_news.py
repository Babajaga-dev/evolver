"""drop news_raw + news_scored (cleanup news subsystem)

Revision ID: 0004_drop_news
Revises: 0003_replay
Create Date: 2026-05-11
"""

from __future__ import annotations

from alembic import op

revision = "0004_drop_news"
down_revision = "0003_replay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop news_scored FIRST (FK to news_raw)
    op.execute("DROP TABLE IF EXISTS news_scored CASCADE")
    op.execute("DROP TABLE IF EXISTS news_raw CASCADE")


def downgrade() -> None:
    # No-op: deliberato. Schema news rimosso definitivamente.
    pass
