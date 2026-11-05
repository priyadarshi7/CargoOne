"""record when a POD first reached the system

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `pod_uploaded_at` is overwritten by every retake; the "POD within 24 h of delivery" KPI needs the FIRST arrival.
    op.add_column("trips", sa.Column("first_pod_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE trips SET first_pod_at = (SELECT min(created_at) FROM pod_submissions WHERE trip_id = trips.id)")
    op.create_index("ix_trips_delivered_at", "trips", ["delivered_at"])


def downgrade() -> None:
    op.drop_index("ix_trips_delivered_at", table_name="trips")
    op.drop_column("trips", "first_pod_at")
