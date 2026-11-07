"""a billing email on the client, and the client's own word that an invoice was paid (a claim billing confirms or rejects)

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("clients", sa.Column("email", sa.String(160), nullable=True))
    op.create_table(
        "payment_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(80), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="pending"),
        sa.Column("via", sa.String(8), nullable=False, server_default="portal"),
        sa.Column("claimed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reject_reason", sa.String(200), nullable=True),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_payment_claims_invoice_id", "payment_claims", ["invoice_id"])
    op.create_index("ix_payment_claims_status", "payment_claims", ["status"])


def downgrade() -> None:
    op.drop_table("payment_claims")
    op.drop_column("clients", "email")
