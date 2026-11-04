from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.dashboard.metrics import Targets, TripFact, compute
from app.db import get_session
from app.models import Branch, Client, Role, Trip, User, Vehicle
from app.security import require_roles

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def dashboard(
    _: Annotated[User, Depends(require_roles(Role.ops, Role.md))],
    session: Annotated[AsyncSession, Depends(get_session)],
    days: Annotated[int, Query(ge=7, le=365)] = 90,
) -> dict:
    """Executive + operations view. Aggregates only: no consignee names or phone numbers."""
    now = datetime.now(UTC)
    rows = (await session.execute(
        select(Trip, Client.name, Vehicle.reg_no, func.coalesce(Branch.name, "Unassigned"), User.name)
        .join(Client, Client.id == Trip.client_id).join(Vehicle, Vehicle.id == Trip.vehicle_id)
        .outerjoin(Branch, Branch.id == Trip.branch_id).outerjoin(User, User.id == Trip.driver_id)
        .where(Trip.delivered_at >= now - timedelta(days=days), Trip.delivered_at.is_not(None))
        .limit(20000)
    )).all()
    facts = [TripFact(
        trip_code=t.trip_code, client=client, branch=branch, vehicle=reg, status=t.pod_status.value, freight=t.freight_amount,
        delivered_at=t.delivered_at, first_pod_at=t.first_pod_at, verified_at=t.verified_at, invoiced_at=t.invoiced_at,
        driver=driver,
    ) for t, client, reg, branch, driver in rows]

    s = get_settings()
    out = compute(facts, now=now, window_days=days, targets=Targets(
        baseline_days=s.baseline_pod_to_invoice_days, target_days=s.target_pod_to_invoice_days,
        target_within_24h_pct=s.target_pod_within_24h_pct, baseline_lost_pct=s.baseline_lost_pct,
        target_lost_pct=s.target_lost_pct, interest_rate=s.interest_rate))
    out["includes_demo_data"] = any(f.trip_code.startswith("DEMO-") for f in facts)
    return out
