from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST
from app.config import get_settings
from app.dashboard.digest import build_digest_pdf
from app.dashboard.metrics import Targets, TripFact, compute
from app.db import get_session
from app.models import AuditLog, Branch, Client, PodStatus, Role, Trip, TripState, User, Vehicle
from app.security import require_roles

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def build_dashboard(session: AsyncSession, days: int) -> dict:
    """Aggregates only: no consignee names or phone numbers."""
    now = datetime.now(UTC)
    rows = (await session.execute(
        select(Trip, Client.name, Vehicle.reg_no, func.coalesce(Branch.name, "Unassigned"), User.name)
        .join(Client, Client.id == Trip.client_id).join(Vehicle, Vehicle.id == Trip.vehicle_id)
        .outerjoin(Branch, Branch.id == Trip.branch_id).outerjoin(User, User.id == Trip.driver_id)
        .where(Trip.delivered_at >= now - timedelta(days=days), Trip.delivered_at.is_not(None))
        .limit(20000)
    )).all()
    def fact(t, client, reg, branch, driver) -> TripFact:
        return TripFact(
            trip_code=t.trip_code, client=client, branch=branch, vehicle=reg, status=t.pod_status.value, freight=t.freight_amount,
            delivered_at=t.delivered_at, first_pod_at=t.first_pod_at, verified_at=t.verified_at, invoiced_at=t.invoiced_at, driver=driver)

    facts = [fact(*r) for r in rows]
    waiting = (await session.execute(  # everything still waiting on a POD, a decision or an invoice, however long ago it was delivered
        select(Trip, Client.name, Vehicle.reg_no, func.coalesce(Branch.name, "Unassigned"), User.name)
        .join(Client, Client.id == Trip.client_id).join(Vehicle, Vehicle.id == Trip.vehicle_id)
        .outerjoin(Branch, Branch.id == Trip.branch_id).outerjoin(User, User.id == Trip.driver_id)
        .where(Trip.state != TripState.cancelled,  # (no delivery date needed: a POD in review or a verified one may not have it yet; "missing" still only counts delivered trips)
               Trip.pod_status.in_((PodStatus.pending, PodStatus.retake_requested, PodStatus.uploaded, PodStatus.needs_review, PodStatus.verified)))
        .limit(20000)
    )).all()

    s = get_settings()
    out = compute(facts, now=now, window_days=days, open_facts=[fact(*r) for r in waiting], targets=Targets(
        baseline_days=s.baseline_pod_to_invoice_days, target_days=s.target_pod_to_invoice_days,
        target_within_24h_pct=s.target_pod_within_24h_pct, baseline_lost_pct=s.baseline_lost_pct,
        target_lost_pct=s.target_lost_pct, interest_rate=s.interest_rate))
    return out


@router.get("")
async def dashboard(
    _: Annotated[User, Depends(require_roles(Role.ops, Role.md))],
    session: Annotated[AsyncSession, Depends(get_session)],
    days: Annotated[int, Query(ge=7, le=365)] = 90,
) -> dict:
    """Executive + operations view."""
    return await build_dashboard(session, days)


@router.get("/digest.pdf")
async def digest(
    user: Annotated[User, Depends(require_roles(Role.ops, Role.md))],
    session: Annotated[AsyncSession, Depends(get_session)],
    days: Annotated[int, Query(ge=7, le=90)] = 30,
) -> Response:
    """The MD's weekly digest as a printable PDF: the same numbers as the dashboard, one page, plain language."""
    data = await build_dashboard(session, days)
    pdf = build_digest_pdf(data, company=get_settings().company_name)
    session.add(AuditLog(actor_id=user.id, action="digest.download", entity="dashboard", meta={"days": days}))
    await session.commit()
    name = f"cargoone-digest-{datetime.now(UTC).astimezone(IST):%Y-%m-%d}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})
