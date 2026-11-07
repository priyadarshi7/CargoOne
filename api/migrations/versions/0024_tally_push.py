"""the invoice's voucher was pushed to Tally

Revision ID: 0024
Revises: 0023
"""
import sqlalchemy as sa
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("tally_pushed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("tally_voucher_no", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "tally_voucher_no")
    op.drop_column("invoices", "tally_pushed_at")
