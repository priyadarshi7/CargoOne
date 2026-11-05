"""driver expenses (fuel, toll, repair...), advances

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("client_expense_id", sa.String(64), nullable=False, unique=True),
        sa.Column("trip_id", sa.UUID(), sa.ForeignKey("trips.id"), nullable=True),
        sa.Column("vehicle_id", sa.UUID(), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("driver_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("litres", sa.Numeric(8, 2), nullable=True),
        sa.Column("odometer_km", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("receipt_key", sa.String(255), nullable=True),
        sa.Column("flags", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("reviewed_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.String(200), nullable=True),
        sa.Column("incurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_expense_amount_positive"),
    )
    op.create_index("ix_expenses_trip", "expenses", ["trip_id"])
    op.create_index("ix_expenses_status", "expenses", ["status"])
    op.create_index("ix_expenses_vehicle_time", "expenses", ["vehicle_id", "incurred_at"])
    op.create_table(
        "advances",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("driver_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("trip_id", sa.UUID(), sa.ForeignKey("trips.id"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(200), nullable=True),
        sa.Column("given_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_advance_amount_positive"),
    )
    op.create_index("ix_advances_driver_id", "advances", ["driver_id"])


def downgrade() -> None:
    op.drop_table("advances")
    op.drop_table("expenses")
