"""automatic LR numbers: branch codes, per-branch yearly counters, goods details on a trip

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("code", sa.String(8)))
    op.create_index("uq_branches_code", "branches", ["code"], unique=True)
    op.execute("update branches set code = 'MH20' where name ilike 'Chhatrapati%' or name ilike 'Aurangabad%'")
    op.execute("update branches set code = 'MH12' where name ilike 'Pune%'")
    op.create_table(
        "lr_counters",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("fy", sa.String(5), primary_key=True),
        sa.Column("last_no", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("trips", sa.Column("material", sa.String(160)))
    op.add_column("trips", sa.Column("weight_tonnes", sa.Numeric(8, 2)))
    op.add_column("trips", sa.Column("packages", sa.Integer()))
    op.create_index("ix_trips_lr_no", "trips", ["lr_no"])


def downgrade() -> None:
    op.drop_index("ix_trips_lr_no", "trips")
    for c in ("packages", "weight_tonnes", "material"):
        op.drop_column("trips", c)
    op.drop_table("lr_counters")
    op.drop_index("uq_branches_code", "branches")
    op.drop_column("branches", "code")
