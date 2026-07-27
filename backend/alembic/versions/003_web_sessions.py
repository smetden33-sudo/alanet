"""Add protected Telegram web sessions.

Revision ID: 003
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("web_login_tokens", "web_sessions"):
        op.create_table(
            table,
            sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
            sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("token_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True) if table == "web_login_tokens" else sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("token_hash"),
        )
        op.create_index(f"ix_{table}_customer_id", table, ["customer_id"])


def downgrade():
    for table in ("web_sessions", "web_login_tokens"):
        op.drop_index(f"ix_{table}_customer_id", table_name=table)
        op.drop_table(table)
