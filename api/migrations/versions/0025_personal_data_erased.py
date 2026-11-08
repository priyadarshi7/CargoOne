"""a trip remembers when its personal data was erased

Revision ID: 0025
Revises: 0024
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("personal_data_erased_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("trips", "personal_data_erased_at")
