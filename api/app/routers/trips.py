import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AuditLog, Branch, Client, Role, Trip, TripState, User, Vehicle
from app.security import require_roles

router = APIRouter(prefix="/trips", tags=["trips"])


class TripOut(BaseModel):
    """List view. Consignee name/phone (personal data) are deliberately NOT included."""

    id: str
    trip_code: str
    client: str
    vehicle: str
    is_hired: bool
    branch: str | None
    lr_no: str
    eway_bill_no: str
    origin: str
    destination: str
    freight_amount: float
    pod_status: str
    retake_count: int
    delivered_at: datetime | None
    state: str
    planned_start: datetime | None
    planned_end: datetime | None
    started_at: datetime | None


_COLUMNS = (Trip, Client.name, Vehicle.reg_no, Vehicle.is_hired, Branch.name)


def _query():
    return (
        select(*_COLUMNS)
        .join(Client, Client.id == Trip.client_id)
        .join(Vehicle, Vehicle.id == Trip.vehicle_id)
        .outerjoin(Branch, Branch.id == Trip.branch_id)
        .where(Trip.state != TripState.cancelled)
        .order_by(Trip.delivered_at.desc().nullslast(), Trip.trip_code)
    )


def _out(row) -> TripOut:
    t, client, reg, hired, branch = row
    return TripOut(
        id=str(t.id), trip_code=t.trip_code, client=client, vehicle=reg, is_hired=hired, branch=branch,
        lr_no=t.lr_no, eway_bill_no=t.eway_bill_no, origin=t.origin, destination=t.destination,
        freight_amount=float(t.freight_amount), pod_status=t.pod_status.value,
        retake_count=t.retake_count, delivered_at=t.delivered_at, state=t.state.value,
        planned_start=t.planned_start, planned_end=t.planned_end, started_at=t.started_at,
    )


@router.get("", response_model=list[TripOut])
async def list_trips(
    _: Annotated[User, Depends(require_roles(Role.ops, Role.billing, Role.md))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TripOut]:
    return [_out(r) for r in (await session.execute(_query().limit(500))).all()]


@router.get("/mine", response_model=list[TripOut])
async def my_trips(
    user: Annotated[User, Depends(require_roles(Role.driver))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[TripOut]:
    rows = (await session.execute(_query().where(Trip.driver_id == user.id))).all()
    return [_out(r) for r in rows]


@router.post("/{trip_id}/start", response_model=TripOut)
async def start_trip(
    trip_id: uuid.UUID,
    user: Annotated[User, Depends(require_roles(Role.driver, Role.ops))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TripOut:
    """The driver (or ops on their behalf) marks the trip as on the road. Idempotent: starting twice changes nothing."""
    trip = await session.get(Trip, trip_id)
    if trip is None or (user.role == Role.driver and trip.driver_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    if trip.state == TripState.planned:
        trip.state, trip.started_at = TripState.in_transit, datetime.now(UTC)
        session.add(AuditLog(actor_id=user.id, action="trip.start", entity="trip", entity_id=trip.trip_code))
        await session.commit()
    elif trip.state != TripState.in_transit:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This trip is {trip.state.value}; it cannot be started")
    return _out((await session.execute(_query().where(Trip.id == trip.id))).one())
