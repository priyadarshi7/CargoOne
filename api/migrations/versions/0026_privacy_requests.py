"""the register of people's requests about their own data

Revision ID: 0026
Revises: 0025
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "privacy_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference", sa.String(16), nullable=False, unique=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(120)),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("message", sa.String(500)),
        sa.Column("source", sa.String(8), nullable=False, server_default="public"),
        sa.Column("status", sa.String(8), nullable=False, server_default="open"),
        sa.Column("outcome", sa.String(300)),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_privacy_requests_status_time", "privacy_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_privacy_requests_status_time", table_name="privacy_requests")
    op.drop_table("privacy_requests")
