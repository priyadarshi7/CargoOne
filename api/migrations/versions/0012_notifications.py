"""in-app notifications, WhatsApp message log, one-time driver onboarding links

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("body", sa.String(600), nullable=False),
        sa.Column("link", sa.String(200)),
        sa.Column("trip_id", UUID, sa.ForeignKey("trips.id", ondelete="SET NULL")),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_time", "notifications", ["user_id", "created_at"])
    op.create_table(
        "messages",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("trip_id", UUID, sa.ForeignKey("trips.id", ondelete="SET NULL")),
        sa.Column("channel", sa.String(12), nullable=False, server_default="whatsapp"),
        sa.Column("template", sa.String(40), nullable=False),
        sa.Column("provider", sa.String(12), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("provider_id", sa.String(80)),
        sa.Column("error", sa.String(200)),
        sa.Column("to_masked", sa.String(20)),
        sa.Column("body", sa.String(1200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_messages_time", "messages", ["created_at"])
    op.create_table(
        "onboarding_links",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_onboarding_links_user_id", "onboarding_links", ["user_id"])


def downgrade() -> None:
    op.drop_table("onboarding_links")
    op.drop_table("messages")
    op.drop_table("notifications")
