"""Add durable admin action confirmations.

Revision ID: 004
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    tables = set(inspector.get_table_names())
    if "admin_actions" not in tables:
        op.create_table(
            "admin_actions",
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
            sa.Column("admin_telegram_id", sa.BigInteger(), nullable=False),
            sa.Column("action", sa.String(length=40), nullable=False),
            sa.Column("target", sa.String(length=120), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("result", sa.JSON(), nullable=False),
        )
    indexes = {item["name"] for item in inspector.get_indexes("admin_actions")} if "admin_actions" in set(inspector.get_table_names()) else set()
    if "ix_admin_actions_admin_telegram_id" not in indexes:
        op.create_index("ix_admin_actions_admin_telegram_id", "admin_actions", ["admin_telegram_id"])
    if "ix_admin_actions_status" not in indexes:
        op.create_index("ix_admin_actions_status", "admin_actions", ["status"])


def downgrade():
    op.drop_index("ix_admin_actions_status", table_name="admin_actions")
    op.drop_index("ix_admin_actions_admin_telegram_id", table_name="admin_actions")
    op.drop_table("admin_actions")
