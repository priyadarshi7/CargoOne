"""live GPS pings, driver tracking consent, client tracking links

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("tracking_consent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "location_pings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("trip_id", sa.UUID(), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("driver_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("accuracy_m", sa.Float(), nullable=True),
        sa.Column("speed_kmh", sa.Float(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("trip_id", "recorded_at", name="uq_ping_trip_time"),
    )
    op.create_index("ix_pings_trip_time", "location_pings", ["trip_id", "recorded_at"])


def downgrade() -> None:
    op.drop_index("ix_pings_trip_time", table_name="location_pings")
    op.drop_table("location_pings")
    op.drop_column("users", "tracking_consent_at")
