"""trip lifecycle (planned / in transit / delivered / cancelled), planning window, trip code sequence

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trips", sa.Column("state", sa.String(length=24), nullable=False, server_default="in_transit"))
    op.add_column("trips", sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True))
    op.add_column("trips", sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True))
    op.add_column("trips", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    # Existing trips are already in motion or finished: anything with a POD photo is delivered, the rest are on the road.
    op.execute("UPDATE trips SET state = CASE WHEN first_pod_at IS NOT NULL OR pod_status NOT IN ('pending', 'retake_requested') "
               "THEN 'delivered' ELSE 'in_transit' END")
    op.create_index("ix_trips_state", "trips", ["state"])
    op.execute("CREATE SEQUENCE trip_code_seq START 70001")


def downgrade() -> None:
    op.execute("DROP SEQUENCE trip_code_seq")
    op.drop_index("ix_trips_state", table_name="trips")
    for c in ("started_at", "planned_end", "planned_start", "state"):
        op.drop_column("trips", c)
