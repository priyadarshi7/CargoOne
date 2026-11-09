"""Numbers for the role home screens (ops desk, billing desk). Counts only: the detail lives on the pages they link to.
Freight amounts are shown to ops and billing, never to anyone else."""
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import (
    Expense,
    ExpenseStatus,
    PodStatus,
    Role,
    TransportRequest,
    Trip,
    TripState,
    User,
    Vehicle,
)
from app.security import require_roles

router = APIRouter(prefix="/home", tags=["home"])
Session = Annotated[AsyncSession, Depends(get_session)]
Viewer = Annotated[User, Depends(require_roles(Role.ops, Role.billing, Role.md))]


@router.get("")
async def home(user: Viewer, session: Session) -> dict:
    async def count(*where) -> int:
        return await session.scalar(select(func.count()).select_from(Trip).where(*where)) or 0

    live = Trip.state != TripState.cancelled
    out: dict = {
        "planned": await count(Trip.state == TripState.planned),
        "in_transit": await count(Trip.state == TripState.in_transit),
        # delivered over a day ago and still no usable POD: the same rule as the dashboard's "trips without POD", so both say the same number
        "pod_missing": await count(live, Trip.pod_status.in_((PodStatus.pending, PodStatus.retake_requested)), Trip.delivered_at <= datetime.now(UTC) - timedelta(days=1)),
        "awaiting_review": await count(Trip.pod_status == PodStatus.needs_review),  # exactly what the Review queue lists
        "requests_new": await session.scalar(select(func.count()).select_from(TransportRequest).where(TransportRequest.status == "new")) or 0,
        # everything about requests that waits for a person: new ones, a yes nobody has booked, a client's no nobody has read
        "requests_attention": await session.scalar(select(func.count()).select_from(TransportRequest).where(or_(
            TransportRequest.status == "new",
            (TransportRequest.status == "accepted") & (TransportRequest.quote_amount.is_(None) | TransportRequest.quote_accepted_at.is_not(None)),
            (TransportRequest.status == "declined") & (TransportRequest.declined_by == "client") & TransportRequest.decline_seen_at.is_(None)))) or 0,
        # free to be booked: in working order and not on a trip right now
        "trucks_available": await session.scalar(select(func.count()).select_from(Vehicle).where(
            Vehicle.availability == "available", Vehicle.is_active.is_(True),
            Vehicle.id.not_in(select(Trip.vehicle_id).where(Trip.state == TripState.in_transit)))) or 0,
        "expenses_pending": await session.scalar(select(func.count()).select_from(Expense).where(Expense.status == ExpenseStatus.pending)) or 0,
    }
    ready = (Trip.pod_status == PodStatus.verified, Trip.invoice_id.is_(None))
    out["ready_to_bill"] = await count(*ready)
    out["ready_amount"] = float(await session.scalar(select(func.coalesce(func.sum(Trip.freight_amount), 0)).where(*ready)) or 0) if user.role != Role.md else None
    return out
