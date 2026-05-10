"""replay tables: runs, retrain_events, equity_snapshots

Revision ID: 0003_replay
Revises: 0002_system_settings
Create Date: 2026-05-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_replay"
down_revision = "0002_system_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "replay_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("symbol", sa.String(32), nullable=False),
        sa.Column("config", postgresql.JSONB, nullable=False),
        sa.Column("current_simulated_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_equity", sa.Float, nullable=False, server_default="10000.0"),
        sa.Column("n_retrains", sa.Integer, nullable=False, server_default="0"),
        sa.Column("n_kill_switch_events", sa.Integer, nullable=False, server_default="0"),
        sa.Column("progress_pct", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("final_metrics", postgresql.JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_replay_runs_status", "replay_runs", ["status"])

    op.create_table(
        "replay_retrain_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("replay_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("replay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("t", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger", sa.String(32), nullable=False, server_default="scheduled"),
        sa.Column("organism", postgresql.JSONB, nullable=False),
        sa.Column("elapsed_seconds", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("equity_at_retrain", sa.Float, nullable=False, server_default="10000.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_replay_retrain_events_replay_id", "replay_retrain_events", ["replay_id"])

    op.create_table(
        "replay_equity_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("replay_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("replay_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("t", sa.DateTime(timezone=True), nullable=False),
        sa.Column("equity", sa.Float, nullable=False),
        sa.Column("position_size_pct", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("drawdown_pct", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("regime", sa.String(32), nullable=True),
        sa.Column("active_strategy", sa.String(64), nullable=True),
        sa.Column("n_trades_so_far", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_replay_equity_replay_id", "replay_equity_snapshots", ["replay_id"])
    op.create_index("ix_replay_equity_t", "replay_equity_snapshots", ["t"])


def downgrade() -> None:
    op.drop_table("replay_equity_snapshots")
    op.drop_table("replay_retrain_events")
    op.drop_table("replay_runs")
