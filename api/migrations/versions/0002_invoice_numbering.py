"""invoice numbering sequence and period label

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A database sequence gives gap-tolerant, race-free invoice numbers even with concurrent billing users.
    op.execute("CREATE SEQUENCE invoice_no_seq START 1")
    op.add_column("invoices", sa.Column("period_label", sa.String(length=80), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "period_label")
    op.execute("DROP SEQUENCE invoice_no_seq")
