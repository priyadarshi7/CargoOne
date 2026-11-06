"""an optional email for the receiver, so the shipment link can go by email too

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("consignee_email", sa.String(160), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "consignee_email")
