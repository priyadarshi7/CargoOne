"""exact map coordinates for trip and request origin and destination

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

COLUMNS = ("origin_lat", "origin_lng", "destination_lat", "destination_lng")


def upgrade() -> None:
    for table in ("trips", "transport_requests"):
        for col in COLUMNS:
            op.add_column(table, sa.Column(col, sa.Float, nullable=True))


def downgrade() -> None:
    for table in ("trips", "transport_requests"):
        for col in COLUMNS:
            op.drop_column(table, col)
