"""who closed a request and why, so the office sees a client's "no"

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("transport_requests", sa.Column("declined_by", sa.String(8), nullable=True))  # office | client
    op.add_column("transport_requests", sa.Column("decline_reason", sa.String(300), nullable=True))
    op.add_column("transport_requests", sa.Column("decline_seen_at", sa.DateTime(timezone=True), nullable=True))  # the office has looked at a client's "no"
    op.add_column("transport_requests", sa.Column("quote_sent_at", sa.DateTime(timezone=True), nullable=True))  # when the current quote went to the client
    op.execute("update transport_requests set declined_by = 'office', decline_reason = ops_note where status = 'declined'")
    op.execute("update transport_requests set quote_sent_at = decided_at where quote_amount is not null")


def downgrade() -> None:
    for c in ("quote_sent_at", "decline_seen_at", "decline_reason", "declined_by"):
        op.drop_column("transport_requests", c)
