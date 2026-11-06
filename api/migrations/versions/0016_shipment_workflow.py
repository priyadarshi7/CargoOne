"""trip events, e-way validity, loading, delivery code, payments, client logins

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)
TRIP_COLUMNS = [
    ("eway_valid_until", TZ), ("cancel_reason", sa.String(300)), ("acknowledged_at", TZ), ("loaded_at", TZ), ("loading_photo_key", sa.String(255)),
    ("delivery_code", sa.String(4)), ("delivery_code_locked_until", TZ), ("delivery_confirmed_at", TZ), ("delivery_override", sa.String(200)),
    ("delivery_note", sa.String(300)), ("closed_at", TZ), ("late_alert_at", TZ),
]


def upgrade() -> None:
    for name, type_ in TRIP_COLUMNS:
        op.add_column("trips", sa.Column(name, type_, nullable=True))
    op.add_column("trips", sa.Column("delivery_code_tries", sa.Integer, nullable=False, server_default="0"))
    op.add_column("trips", sa.Column("delivery_issue", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("trips", sa.Column("link_epoch", sa.Integer, nullable=False, server_default="0"))

    op.create_table(
        "trip_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("at", TZ, server_default=sa.func.now(), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("note", sa.String(300)),
        sa.Column("public", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("meta", postgresql.JSONB),
    )
    op.create_index("ix_trip_events_trip_id", "trip_events", ["trip_id"])

    op.add_column("invoices", sa.Column("sent_at", TZ))
    op.add_column("invoices", sa.Column("sent_by", postgresql.UUID(as_uuid=True)))
    op.add_column("invoices", sa.Column("paid_at", TZ))
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("paid_on", sa.Date, nullable=False),
        sa.Column("reference", sa.String(80)),
        sa.Column("recorded_by", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", TZ, server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_payments_invoice_id", "payments", ["invoice_id"])

    op.add_column("clients", sa.Column("language", sa.String(2), nullable=False, server_default="en"))
    op.add_column("users", sa.Column("client_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("clients.id")))
    op.add_column("transport_requests", sa.Column("quote_accepted_at", TZ))
    op.add_column("transport_requests", sa.Column("quote_accepted_via", sa.String(12)))


def downgrade() -> None:
    op.drop_column("transport_requests", "quote_accepted_via")
    op.drop_column("transport_requests", "quote_accepted_at")
    op.drop_column("users", "client_id")
    op.drop_column("clients", "language")
    op.drop_table("payments")
    for c in ("paid_at", "sent_by", "sent_at"):
        op.drop_column("invoices", c)
    op.drop_table("trip_events")
    for c in ("link_epoch", "delivery_issue", "delivery_code_tries"):
        op.drop_column("trips", c)
    for name, _ in reversed(TRIP_COLUMNS):
        op.drop_column("trips", name)
