import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST
from app.config import get_settings
from app.db import get_session
from app.events import record
from app.lrdoc import LrData, build_lr_pdf
from app.models import AuditLog, Branch, Client, Role, Trip, TripState, User, Vehicle
from app.notify.service import safely
from app.notify.shipment import tell_parties
from app.security import link_trip_id, require_roles

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


class DriverTripOut(TripOut):
    """What the trip's own driver may see: the load, and who receives it (they have to find and call them)."""

    material: str | None
    weight_tonnes: float | None
    packages: int | None
    consignee_name: str | None
    consignee_phone: str | None
    destination_lat: float | None  # exact drop point when it was picked from the map suggestions: Navigate uses it
    destination_lng: float | None
    acknowledged_at: datetime | None
    loaded_at: datetime | None  # the truck is loaded (with a photo): until then the driver cannot start
    delivery_confirmed_at: datetime | None
    arrived_at: datetime | None
    needs_code: bool  # the receiver's 4-digit code is still to be entered before the proof-of-delivery photo


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


@router.get("/mine", response_model=list[DriverTripOut])
async def my_trips(
    request: Request,
    user: Annotated[User, Depends(require_roles(Role.driver))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[DriverTripOut]:
    query = _query().where(Trip.driver_id == user.id)
    if (only := link_trip_id(request)) is not None:
        query = query.where(Trip.id == only)  # a private link shows its one trip
    rows = (await session.execute(query)).all()
    return [DriverTripOut(**_out(r).model_dump(), material=r[0].material, weight_tonnes=float(r[0].weight_tonnes) if r[0].weight_tonnes is not None else None,
                          packages=r[0].packages, consignee_name=r[0].consignee_name, consignee_phone=r[0].consignee_phone,
                          destination_lat=r[0].destination_lat, destination_lng=r[0].destination_lng, acknowledged_at=r[0].acknowledged_at,
                          loaded_at=r[0].loaded_at, delivery_confirmed_at=r[0].delivery_confirmed_at, arrived_at=r[0].arrived_at,
                          needs_code=bool(r[0].delivery_code) and r[0].delivery_confirmed_at is None) for r in rows]


@router.get("/office-contact")
async def office_contact(_: Annotated[User, Depends(require_roles(Role.driver))]) -> dict:
    """The number a driver rings when something goes wrong (OFFICE_PHONE in the settings); empty until it is set."""
    return {"phone": get_settings().office_phone or None}


@router.get("/{trip_id}/lr.pdf")
async def lr_pdf(
    trip_id: uuid.UUID, user: Annotated[User, Depends(require_roles(Role.ops, Role.billing, Role.driver))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    """The lorry receipt for this trip as a printable PDF. A driver can only get their own trip's."""
    trip = await session.get(Trip, trip_id)
    if trip is None or (user.role == Role.driver and trip.driver_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    client = await session.get(Client, trip.client_id)
    vehicle = await session.get(Vehicle, trip.vehicle_id)
    branch = await session.get(Branch, trip.branch_id) if trip.branch_id else None
    driver = await session.get(User, trip.driver_id) if trip.driver_id else None
    pdf = build_lr_pdf(LrData(
        company=get_settings().company_name, lr_no=trip.lr_no, trip_code=trip.trip_code, issued_at=trip.created_at, branch=branch.name if branch else None,
        origin=trip.origin, destination=trip.destination, consignor=client.name if client else "", consignee=trip.consignee_name, vehicle=vehicle.reg_no if vehicle else "",
        driver=driver.name if driver else None, driver_phone=driver.phone if driver else None, material=trip.material, packages=trip.packages,
        weight_tonnes=trip.weight_tonnes, eway_bill_no=trip.eway_bill_no, planned_start=trip.planned_start))
    session.add(AuditLog(actor_id=user.id, action="lr.download", entity="trip", entity_id=trip.trip_code))
    await session.commit()
    name = trip.lr_no.replace("/", "-")
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}.pdf"', "Cache-Control": "private, no-store"})


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
        now = datetime.now(UTC)
        early = get_settings().start_early_hours
        if user.role == Role.driver and trip.planned_start and now < trip.planned_start - timedelta(hours=early):
            raise HTTPException(status.HTTP_409_CONFLICT, f"This trip is planned for {trip.planned_start.astimezone(IST):%d %b, %H:%M}. You can start it up to {early} hours before.")
        if user.role == Role.driver and trip.loaded_at is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Confirm that the truck is loaded (with a photo) before starting")
        busy = await session.execute(select(Trip.trip_code).where(Trip.state == TripState.in_transit, Trip.id != trip.id, (Trip.vehicle_id == trip.vehicle_id) | (Trip.driver_id == trip.driver_id if trip.driver_id else False)).limit(1))
        if (other := busy.scalar()) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"The truck or driver is still on {other}. Finish that trip first.")
        trip.state, trip.started_at = TripState.in_transit, now
        session.add(AuditLog(actor_id=user.id, action="trip.start", entity="trip", entity_id=trip.trip_code))
        record(session, trip, "started", actor=user.id, public=True)
        await session.commit()
        await safely(session, tell_parties(session, trip, "started"))
    elif trip.state != TripState.in_transit:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This trip is {trip.state.value}; it cannot be started")
    return _out((await session.execute(_query().where(Trip.id == trip.id))).one())
