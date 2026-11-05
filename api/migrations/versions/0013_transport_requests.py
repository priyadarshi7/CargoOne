"""client transport requests, client GSTIN

Revision ID: 0013
Revises: 0012
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("clients", sa.Column("gstin", sa.String(15)))
    op.execute("create sequence if not exists request_ref_seq start 1001")
    op.create_table(
        "transport_requests",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("reference", sa.String(16), nullable=False, unique=True),
        sa.Column("company_name", sa.String(160), nullable=False),
        sa.Column("contact_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(160)),
        sa.Column("gstin", sa.String(15)),
        sa.Column("language", sa.String(2), nullable=False, server_default="en"),
        sa.Column("origin", sa.String(120), nullable=False),
        sa.Column("destination", sa.String(120), nullable=False),
        sa.Column("material", sa.String(160), nullable=False),
        sa.Column("weight_tonnes", sa.Numeric(8, 2)),
        sa.Column("truck_type", sa.String(60)),
        sa.Column("pickup_date", sa.Date(), nullable=False),
        sa.Column("notes", sa.String(500)),
        sa.Column("status", sa.String(12), nullable=False, server_default="new"),
        sa.Column("client_id", UUID, sa.ForeignKey("clients.id")),
        sa.Column("trip_id", UUID, sa.ForeignKey("trips.id", ondelete="SET NULL")),
        sa.Column("quote_amount", sa.Numeric(12, 2)),
        sa.Column("ops_note", sa.String(300)),
        sa.Column("decided_by", UUID, sa.ForeignKey("users.id")),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_requests_status_time", "transport_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_table("transport_requests")
    op.execute("drop sequence if exists request_ref_seq")
    op.drop_column("clients", "gstin")
