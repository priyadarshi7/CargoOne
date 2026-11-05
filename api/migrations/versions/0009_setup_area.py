"""setup area: vendors, active flags, vehicle details, client contacts

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
        sa.Column("contact_name", sa.String(120)),
        sa.Column("phone", sa.String(20)),
        sa.Column("notes", sa.String(300)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column("users", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("users", sa.Column("vendor_id", sa.UUID(), sa.ForeignKey("vendors.id"), nullable=True))
    op.add_column("clients", sa.Column("contact_name", sa.String(120)))
    op.add_column("clients", sa.Column("contact_phone", sa.String(20)))
    op.add_column("clients", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("vehicles", sa.Column("vendor_id", sa.UUID(), sa.ForeignKey("vendors.id"), nullable=True))
    op.add_column("vehicles", sa.Column("vehicle_type", sa.String(40)))
    op.add_column("vehicles", sa.Column("capacity_tonnes", sa.Numeric(5, 1)))
    op.add_column("vehicles", sa.Column("insurance_expiry", sa.Date()))
    op.add_column("vehicles", sa.Column("fitness_expiry", sa.Date()))
    op.add_column("vehicles", sa.Column("permit_expiry", sa.Date()))
    op.add_column("vehicles", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"))


def downgrade() -> None:
    for c in ("is_active", "permit_expiry", "fitness_expiry", "insurance_expiry", "capacity_tonnes", "vehicle_type", "vendor_id"):
        op.drop_column("vehicles", c)
    for c in ("is_active", "contact_phone", "contact_name"):
        op.drop_column("clients", c)
    op.drop_column("users", "vendor_id")
    op.drop_column("users", "is_active")
    op.drop_table("vendors")
