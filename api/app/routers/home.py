"""Numbers for the role home screens (ops desk, billing desk). Counts only: the detail lives on the pages they link to.
Freight amounts are shown to ops and billing, never to anyone else."""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
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
        "pod_missing": await count(live, Trip.pod_status.in_((PodStatus.pending, PodStatus.retake_requested)), Trip.state != TripState.planned),
        "awaiting_review": await count(Trip.pod_status.in_((PodStatus.uploaded, PodStatus.needs_review))),
        "requests_new": await session.scalar(select(func.count()).select_from(TransportRequest).where(TransportRequest.status == "new")) or 0,
        "trucks_available": await session.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.availability == "available")) or 0,
        "expenses_pending": await session.scalar(select(func.count()).select_from(Expense).where(Expense.status == ExpenseStatus.pending)) or 0,
    }
    ready = (Trip.pod_status == PodStatus.verified, Trip.invoice_id.is_(None))
    out["ready_to_bill"] = await count(*ready)
    out["ready_amount"] = float(await session.scalar(select(func.coalesce(func.sum(Trip.freight_amount), 0)).where(*ready)) or 0) if user.role != Role.md else None
    return out
