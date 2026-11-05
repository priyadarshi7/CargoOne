"""fleet and driver onboarding: vehicle RC/PUC/availability, driver licence/employment/assigned truck, documents

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for col in (
        sa.Column("owner_name", sa.String(160)),
        sa.Column("rc_no", sa.String(30)),
        sa.Column("registration_date", sa.Date()),
        sa.Column("chassis_no", sa.String(30)),
        sa.Column("engine_no", sa.String(30)),
        sa.Column("insurance_no", sa.String(40)),
        sa.Column("puc_expiry", sa.Date()),
        sa.Column("availability", sa.String(16), nullable=False, server_default="available"),
        sa.Column("availability_note", sa.String(200)),
    ):
        op.add_column("vehicles", col)
    op.add_column("users", sa.Column("licence_no", sa.String(30)))
    op.add_column("users", sa.Column("licence_expiry", sa.Date()))
    op.add_column("users", sa.Column("employment_type", sa.String(16)))
    op.add_column("users", sa.Column("assigned_vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id")))
    op.execute("update users set employment_type = case when vendor_id is not null then 'hired' else 'company' end where role = 'driver'")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("owner_type", sa.String(16), nullable=False),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("mime", sa.String(40), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("owner_type", "owner_id", "kind", name="uq_document_slot"),
    )
    op.create_index("ix_documents_owner", "documents", ["owner_type", "owner_id"])


def downgrade() -> None:
    op.drop_table("documents")
    for c in ("assigned_vehicle_id", "employment_type", "licence_expiry", "licence_no"):
        op.drop_column("users", c)
    for c in ("availability_note", "availability", "puc_expiry", "insurance_no", "engine_no", "chassis_no", "registration_date", "rc_no", "owner_name"):
        op.drop_column("vehicles", c)
