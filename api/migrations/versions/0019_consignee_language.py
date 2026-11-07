"""the language the receiver's messages are written in

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("consignee_language", sa.String(2), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "consignee_language")
