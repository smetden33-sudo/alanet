"""Add one-time Telegram account binding tokens.

Revision ID: 002
"""
from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "telegram_bind_tokens",
        sa.Column("id", sa.UUID(), primary_key=True, nullable=False),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_telegram_bind_tokens_customer_id", "telegram_bind_tokens", ["customer_id"])
    op.create_index("uq_customers_email_lower", "customers", [sa.text("lower(email)")], unique=True)


def downgrade():
    op.drop_index("uq_customers_email_lower", table_name="customers")
    op.drop_index("ix_telegram_bind_tokens_customer_id", table_name="telegram_bind_tokens")
    op.drop_table("telegram_bind_tokens")
