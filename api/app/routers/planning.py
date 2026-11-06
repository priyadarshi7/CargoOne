"""Trip planning: create a trip, assign a vehicle and driver for a time window, and see who is booked when.

Vehicle and driver clashes are detected (never silently allowed): the API answers 409 with the clashing trips, and the
planner can re-send with `force` if the overlap is deliberate (for example a driver changing trucks mid-day)."""
import secrets
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST
from app.config import get_settings
from app.db import get_session
from app.events import record
from app.lr import next_lr_no
from app.models import (
    AuditLog,
    Branch,
    Client,
    PodStatus,
    Role,
    TransportRequest,
    Trip,
    TripState,
    User,
    Vehicle,
)
from app.notify.service import safely, trip_assigned, trip_update, when_text
from app.notify.shipment import tell_parties
from app.phones import clean_phone
from app.places import Coords
from app.planning import overlaps, window
from app.routers.requests import book, tell_requester
from app.routers.setup import DOCS
from app.security import require_roles

router = APIRouter(prefix="/planning", tags=["planning"])
Planner = Annotated[User, Depends(require_roles(Role.ops))]
Viewer = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Session = Annotated[AsyncSession, Depends(get_session)]
ACTIVE = (TripState.planned, TripState.in_transit)
LATE_BY = timedelta(minutes=15)  # a trip may be booked "from now"; a start any earlier than this is the past
MAX_AHEAD = timedelta(days=365)
MAX_SPAN = timedelta(days=60)


def check_window(start: datetime | None, end: datetime | None, eway_until: datetime | None = None) -> None:
    """A trip cannot be booked into the past, absurdly far ahead, or for months on end."""
    now = datetime.now(UTC)
    aware = lambda d: d if d.tzinfo else d.replace(tzinfo=IST)  # a time sent without a zone is India time
    if start:
        if aware(start) < now - LATE_BY:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The start time has already passed. Pick a time from now onwards.")
        if aware(start) > now + MAX_AHEAD:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The start is more than a year away. Check the date.")
    if start and end and aware(end) - aware(start) > MAX_SPAN:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A trip cannot run for more than 60 days. Check the end date.")
    if eway_until:
        if aware(eway_until) <= now:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The e-way bill has already expired. Get a new one before booking the trip.")
        if start and aware(eway_until) <= aware(start):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The e-way bill expires before the trip starts.")
        if end and aware(eway_until) < aware(end):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The e-way bill expires before the trip is due to end. Extend it or shorten the trip.")
        if aware(eway_until) > now + MAX_AHEAD:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The e-way bill validity is more than a year away. Check the date.")


class Clash(BaseModel):
    kind: str  # vehicle | driver
    trip_code: str
    start: datetime | None
    end: datetime | None


class NewTrip(Coords):
    client_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    origin: str | None = Field(default=None, min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    freight_amount: Decimal = Field(gt=0, le=10_000_000, decimal_places=2)
    eway_bill_no: str = Field(pattern=r"^\d{12}$")
    planned_start: datetime  # a trip without a start never shows on the calendar
    planned_end: datetime | None = None
    eway_valid_until: datetime  # printed on the e-way bill
    material: str | None = Field(default=None, max_length=160)
    weight_tonnes: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    packages: int | None = Field(default=None, gt=0, le=1_000_000)
    consignee_name: str | None = Field(default=None, max_length=160)
    consignee_phone: str | None = None
    request_id: uuid.UUID | None = None  # the accepted transport request this trip fulfils
    force: bool = False

    @model_validator(mode="after")
    def _order(self) -> "NewTrip":
        if self.planned_end and self.planned_end <= self.planned_start:
            raise ValueError("The end must be after the start")
        return self


class Reassign(BaseModel):
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None  # explicit null un-assigns the driver
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    reason: str | None = Field(default=None, max_length=300)  # required whenever the truck, driver or time actually changes
    force: bool = False


class Cancel(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


class BoardTrip(BaseModel):
    id: str
    trip_code: str
    lr_no: str
    client: str
    vehicle_id: str
    driver_id: str | None
    driver: str | None
    origin: str
    destination: str
    state: str
    planned_start: datetime | None
    planned_end: datetime | None
    started_at: datetime | None


class Refs(BaseModel):
    clients: list[dict]
    vehicles: list[dict]
    drivers: list[dict]
    branches: list[dict]
    default_origin: str


def _slot(t: Trip) -> tuple[datetime, datetime] | None:
    return window(t.started_at or t.planned_start, t.planned_end)


async def find_clashes(session: AsyncSession, *, vehicle_id: uuid.UUID, driver_id: uuid.UUID | None,
                       start: datetime | None, end: datetime | None, exclude: uuid.UUID | None = None) -> list[Clash]:
    mine = window(start, end)
    if mine is None:
        return []
    conds = [Trip.vehicle_id == vehicle_id] + ([Trip.driver_id == driver_id] if driver_id else [])
    q = select(Trip).where(Trip.state.in_(ACTIVE), or_(*conds))
    if exclude:
        q = q.where(Trip.id != exclude)
    out: list[Clash] = []
    for t in (await session.scalars(q)).all():
        theirs = _slot(t)
        if not overlaps(mine, theirs):
            continue
        if t.vehicle_id == vehicle_id:
            out.append(Clash(kind="vehicle", trip_code=t.trip_code, start=theirs[0], end=theirs[1]))
        if driver_id and t.driver_id == driver_id:
            out.append(Clash(kind="driver", trip_code=t.trip_code, start=theirs[0], end=theirs[1]))
    return out


def _clash_error(clashes: list[Clash]) -> HTTPException:
    kinds = " and ".join(sorted({c.kind for c in clashes}))
    return HTTPException(status.HTTP_409_CONFLICT, {
        "message": f"The {kinds} is already booked at that time ({', '.join(dict.fromkeys(c.trip_code for c in clashes))}).",
        "clashes": [c.model_dump(mode="json") for c in clashes],
    })


async def _check_people(session: AsyncSession, vehicle_id: uuid.UUID, driver_id: uuid.UUID | None) -> Vehicle:
    v = await session.get(Vehicle, vehicle_id)
    if v is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown vehicle")
    today = date.today()
    if v.availability != "available":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{v.reg_no} is not available ({v.availability}). Mark it available in Setup first.")
    expired = [d.removesuffix("_expiry") for d in DOCS if getattr(v, d) and getattr(v, d) < today]
    if expired:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{v.reg_no} has an expired paper ({', '.join(expired)}). Renew it in Setup first.")
    if driver_id:
        d = await session.get(User, driver_id)
        if d is None or d.role != Role.driver:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown driver")
        if d.licence_expiry and d.licence_expiry < today:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{d.name}'s driving licence has expired. Update it in Setup first.")
    return v


@router.get("/refs", response_model=Refs)
async def refs(_: Viewer, session: Session) -> Refs:
    return Refs(
        clients=[{"id": str(c.id), "name": c.name} for c in (await session.scalars(select(Client).where(Client.is_active).order_by(Client.name))).all()],
        vehicles=[{"id": str(v.id), "reg_no": v.reg_no, "is_hired": v.is_hired, "availability": v.availability, "capacity_tonnes": float(v.capacity_tonnes) if v.capacity_tonnes else None,
                   "vehicle_type": v.vehicle_type} for v in (await session.scalars(select(Vehicle).where(Vehicle.is_active).order_by(Vehicle.reg_no))).all()],
        drivers=[{"id": str(u.id), "name": u.name, "assigned_vehicle_id": str(u.assigned_vehicle_id) if u.assigned_vehicle_id else None} for u in (await session.scalars(select(User).where(User.role == Role.driver, User.is_active).order_by(User.name))).all()],
        branches=[{"id": str(b.id), "name": b.name, "code": b.code} for b in (await session.scalars(select(Branch).order_by(Branch.name))).all()],
        default_origin=get_settings().default_origin,
    )


@router.get("/board")
async def board(_: Viewer, session: Session) -> dict:
    """Vehicles and their active trips, plus trips that started in the last 3 days for context."""
    since = datetime.now(UTC) - timedelta(days=3)
    rows = (await session.execute(
        select(Trip, Client.name, User.name).join(Client, Client.id == Trip.client_id).outerjoin(User, User.id == Trip.driver_id)
        .where(or_(Trip.state.in_(ACTIVE), (Trip.state == TripState.delivered) & (Trip.planned_start >= since)))
        .order_by(Trip.planned_start.nulls_last(), Trip.trip_code).limit(1000)
    )).all()
    vehicles = (await session.scalars(select(Vehicle).where(Vehicle.is_active).order_by(Vehicle.reg_no))).all()
    return {
        "now": datetime.now(UTC).isoformat(),
        "vehicles": [{"id": str(v.id), "reg_no": v.reg_no, "is_hired": v.is_hired} for v in vehicles],
        "trips": [BoardTrip(id=str(t.id), trip_code=t.trip_code, lr_no=t.lr_no, client=c, vehicle_id=str(t.vehicle_id), driver_id=str(t.driver_id) if t.driver_id else None, driver=d, origin=t.origin,
                            destination=t.destination, state=t.state.value, planned_start=t.planned_start, planned_end=t.planned_end,
                            started_at=t.started_at).model_dump(mode="json") for t, c, d in rows],
    }


@router.post("/trips", status_code=status.HTTP_201_CREATED)
async def create_trip(body: NewTrip, user: Planner, session: Session) -> dict:
    if await session.get(Client, body.client_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown client")
    check_window(body.planned_start, body.planned_end, body.eway_valid_until)
    used = await session.scalar(select(Trip.trip_code).where(Trip.eway_bill_no == body.eway_bill_no, Trip.state != TripState.cancelled).limit(1))
    if used:
        raise HTTPException(status.HTTP_409_CONFLICT, f"E-way bill {body.eway_bill_no} is already on trip {used}. One e-way bill covers one consignment.")
    vehicle = await _check_people(session, body.vehicle_id, body.driver_id)
    if body.weight_tonnes and vehicle.capacity_tonnes and body.weight_tonnes > vehicle.capacity_tonnes:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{body.weight_tonnes} tonnes is more than {vehicle.reg_no} can carry ({vehicle.capacity_tonnes} tonnes)")
    branch = await session.get(Branch, body.branch_id) if body.branch_id else None
    if not body.force:
        clashes = await find_clashes(session, vehicle_id=body.vehicle_id, driver_id=body.driver_id, start=body.planned_start, end=body.planned_end)
        if clashes:
            raise _clash_error(clashes)
    code = f"TRP-{await session.scalar(select(func.nextval('trip_code_seq')))}"
    lr_no = await next_lr_no(session, branch)  # taken last, so a refused request never uses up a number
    trip = Trip(
        trip_code=code, client_id=body.client_id, vehicle_id=body.vehicle_id, driver_id=body.driver_id, branch_id=body.branch_id,
        material=(body.material or "").strip() or None, weight_tonnes=body.weight_tonnes, packages=body.packages,
        consignee_name=(body.consignee_name or "").strip() or None, consignee_phone=clean_phone(body.consignee_phone) if body.consignee_phone else None,
        lr_no=lr_no, eway_bill_no=body.eway_bill_no, origin=(body.origin or get_settings().default_origin).strip(),
        destination=body.destination.strip(), freight_amount=body.freight_amount, pod_status=PodStatus.pending, state=TripState.planned,
        planned_start=body.planned_start, planned_end=body.planned_end, eway_valid_until=body.eway_valid_until,
        delivery_code=f"{secrets.randbelow(10_000):04d}",
        origin_lat=body.origin_lat, origin_lng=body.origin_lng, destination_lat=body.destination_lat, destination_lng=body.destination_lng,
    )
    session.add(trip)
    session.add(AuditLog(actor_id=user.id, action="trip.create", entity="trip", entity_id=code, meta={"forced": body.force}))
    await session.flush()
    record(session, trip, "booked", actor=user.id, public=True)
    if trip.driver_id:
        record(session, trip, "assigned", actor=user.id, public=True)
    booked = None
    if body.request_id:
        await session.flush()
        booked = await book(session, body.request_id, trip)  # 422 here undoes the whole trip: nothing is half-booked
    await session.commit()
    result = {"id": str(trip.id), "trip_code": code, "lr_no": lr_no}  # built first: a rollback in the notifier would expire `trip`
    if trip.driver_id:
        driver = await session.get(User, trip.driver_id)
        await safely(session, trip_assigned(session, trip, driver, vehicle))
    if booked:
        await safely(session, tell_requester(session, booked[0], "booked", **booked[1]))
    if trip.driver_id:
        await safely(session, tell_parties(session, trip, "assigned"))
    return result


async def _planned_trip(session: AsyncSession, trip_id: uuid.UUID) -> Trip:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    if trip.closed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This trip is closed (invoiced and paid). An admin must reopen it first.")
    return trip


@router.patch("/trips/{trip_id}")
async def reassign(trip_id: uuid.UUID, body: Reassign, user: Planner, session: Session) -> dict:
    trip = await _planned_trip(session, trip_id)
    if trip.state != TripState.planned:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only a trip that has not started can be re-planned")
    fields = body.model_fields_set
    vehicle_id = body.vehicle_id or trip.vehicle_id
    driver_id = body.driver_id if "driver_id" in fields else trip.driver_id
    start = body.planned_start if "planned_start" in fields else trip.planned_start
    end = body.planned_end if "planned_end" in fields else trip.planned_end
    if start and end and end <= start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The end must be after the start")
    changed = (vehicle_id, driver_id, start, end) != (trip.vehicle_id, trip.driver_id, trip.planned_start, trip.planned_end)
    reason = (body.reason or "").strip()
    if changed and len(reason) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say why the plan is changing (a few words): the driver and the audit trail will show it.")
    if start != trip.planned_start or end != trip.planned_end:  # only a changed time is checked, so an old trip can still get a new driver
        check_window(start if start != trip.planned_start else None, end, trip.eway_valid_until if trip.eway_valid_until and trip.eway_valid_until > datetime.now(UTC) else None)
    await _check_people(session, vehicle_id, driver_id)
    if not body.force:
        clashes = await find_clashes(session, vehicle_id=vehicle_id, driver_id=driver_id, start=start, end=end, exclude=trip.id)
        if clashes:
            raise _clash_error(clashes)
    before = (trip.vehicle_id, trip.driver_id, trip.planned_start, trip.planned_end)
    trip.vehicle_id, trip.driver_id, trip.planned_start, trip.planned_end = vehicle_id, driver_id, start, end
    session.add(AuditLog(actor_id=user.id, action="trip.replan", entity="trip", entity_id=trip.trip_code, meta={"forced": body.force, "reason": reason}))
    if changed:
        record(session, trip, "replanned", actor=user.id, note=reason, public=True)
        if trip.driver_id != before[1] and trip.driver_id:
            record(session, trip, "assigned", actor=user.id, public=True)
            trip.acknowledged_at = None  # the new driver has not seen it yet
    await session.commit()
    result = {"id": str(trip.id), "trip_code": trip.trip_code}
    await safely(session, _tell_drivers(session, trip, before, reason))
    if (trip.vehicle_id, trip.planned_start) != (before[0], before[2]):
        await safely(session, tell_parties(session, trip, "replanned"))
    return result


async def _tell_drivers(session: AsyncSession, trip: Trip, before: tuple, reason: str = "") -> None:
    """After a re-plan: the new driver gets the trip, the old one is told it is gone, an unchanged driver hears about a new truck or time."""
    old_vehicle, old_driver, old_start, old_end = before
    veh = await session.get(Vehicle, trip.vehicle_id)
    if old_driver != trip.driver_id:
        if old_driver and (gone := await session.get(User, old_driver)):
            await trip_update(session, trip, gone, f"has been given to another driver ({reason})" if reason else "has been given to another driver")
        if trip.driver_id and (new := await session.get(User, trip.driver_id)):
            await trip_assigned(session, trip, new, veh)
    elif trip.driver_id and (trip.vehicle_id != old_vehicle or trip.planned_start != old_start or trip.planned_end != old_end):
        parts = []
        if trip.vehicle_id != old_vehicle and veh:
            parts.append(f"truck is now {veh.reg_no}")
        if trip.planned_start != old_start or trip.planned_end != old_end:
            parts.append(f"start is now {when_text(trip.planned_start)}")
        if driver := await session.get(User, trip.driver_id):
            await trip_update(session, trip, driver, "has changed: " + ", ".join(parts) + (f" ({reason})" if reason else ""))


@router.post("/trips/{trip_id}/cancel")
async def cancel(trip_id: uuid.UUID, body: Cancel, user: Planner, session: Session) -> dict:
    trip = await _planned_trip(session, trip_id)
    if trip.state not in ACTIVE or trip.pod_status != PodStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This trip already has a POD or is finished; it cannot be cancelled")
    trip.state, trip.cancel_reason = TripState.cancelled, body.reason.strip()
    session.add(AuditLog(actor_id=user.id, action="trip.cancel", entity="trip", entity_id=trip.trip_code, meta={"reason": trip.cancel_reason}))
    record(session, trip, "cancelled", actor=user.id, note=trip.cancel_reason, public=True)
    # a trip made from a request: the request is open again (the agreed quote stands), so the office sees it must be booked again
    for req in (await session.scalars(select(TransportRequest).where(TransportRequest.trip_id == trip.id, TransportRequest.status == "booked"))).all():
        req.status, req.trip_id = "accepted", None
        session.add(AuditLog(actor_id=user.id, action="request.reopened", entity="request", entity_id=req.reference, meta={"trip": trip.trip_code, "why": "trip cancelled"}))
    await session.commit()
    result = {"id": str(trip.id), "state": trip.state.value}
    await safely(session, tell_parties(session, trip, "cancelled"))
    if trip.driver_id and (driver := await session.get(User, trip.driver_id)):
        await safely(session, trip_update(session, trip, driver, f"was cancelled ({trip.cancel_reason})"))
    return result
