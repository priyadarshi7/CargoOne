"""Trip planning: create a trip, assign a vehicle and driver for a time window, and see who is booked when.

Vehicle and driver clashes are detected (never silently allowed): the API answers 409 with the clashing trips, and the
planner can re-send with `force` if the overlap is deliberate (for example a driver changing trucks mid-day)."""
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import AuditLog, Branch, Client, PodStatus, Role, Trip, TripState, User, Vehicle
from app.planning import overlaps, window
from app.security import require_roles

router = APIRouter(prefix="/planning", tags=["planning"])
Planner = Annotated[User, Depends(require_roles(Role.ops))]
Viewer = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Session = Annotated[AsyncSession, Depends(get_session)]
ACTIVE = (TripState.planned, TripState.in_transit)


class Clash(BaseModel):
    kind: str  # vehicle | driver
    trip_code: str
    start: datetime | None
    end: datetime | None


class NewTrip(BaseModel):
    client_id: uuid.UUID
    vehicle_id: uuid.UUID
    driver_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    origin: str | None = Field(default=None, min_length=1, max_length=120)
    destination: str = Field(min_length=1, max_length=120)
    freight_amount: Decimal = Field(gt=0, le=10_000_000, decimal_places=2)
    lr_no: str = Field(min_length=1, max_length=40)
    eway_bill_no: str = Field(pattern=r"^\d{12}$")
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    force: bool = False

    @model_validator(mode="after")
    def _order(self) -> "NewTrip":
        if self.planned_start and self.planned_end and self.planned_end <= self.planned_start:
            raise ValueError("The end must be after the start")
        return self


class Reassign(BaseModel):
    vehicle_id: uuid.UUID | None = None
    driver_id: uuid.UUID | None = None  # explicit null un-assigns the driver
    planned_start: datetime | None = None
    planned_end: datetime | None = None
    force: bool = False


class BoardTrip(BaseModel):
    id: str
    trip_code: str
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


async def _check_people(session: AsyncSession, vehicle_id: uuid.UUID, driver_id: uuid.UUID | None) -> None:
    if await session.get(Vehicle, vehicle_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown vehicle")
    if driver_id:
        d = await session.get(User, driver_id)
        if d is None or d.role != Role.driver:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown driver")


@router.get("/refs", response_model=Refs)
async def refs(_: Viewer, session: Session) -> Refs:
    return Refs(
        clients=[{"id": str(c.id), "name": c.name} for c in (await session.scalars(select(Client).order_by(Client.name))).all()],
        vehicles=[{"id": str(v.id), "reg_no": v.reg_no, "is_hired": v.is_hired} for v in (await session.scalars(select(Vehicle).order_by(Vehicle.reg_no))).all()],
        drivers=[{"id": str(u.id), "name": u.name} for u in (await session.scalars(select(User).where(User.role == Role.driver).order_by(User.name))).all()],
        branches=[{"id": str(b.id), "name": b.name} for b in (await session.scalars(select(Branch).order_by(Branch.name))).all()],
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
    vehicles = (await session.scalars(select(Vehicle).order_by(Vehicle.reg_no))).all()
    return {
        "now": datetime.now(UTC).isoformat(),
        "vehicles": [{"id": str(v.id), "reg_no": v.reg_no, "is_hired": v.is_hired} for v in vehicles],
        "trips": [BoardTrip(id=str(t.id), trip_code=t.trip_code, client=c, vehicle_id=str(t.vehicle_id), driver_id=str(t.driver_id) if t.driver_id else None, driver=d, origin=t.origin,
                            destination=t.destination, state=t.state.value, planned_start=t.planned_start, planned_end=t.planned_end,
                            started_at=t.started_at).model_dump(mode="json") for t, c, d in rows],
    }


@router.post("/trips", status_code=status.HTTP_201_CREATED)
async def create_trip(body: NewTrip, user: Planner, session: Session) -> dict:
    if await session.get(Client, body.client_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown client")
    await _check_people(session, body.vehicle_id, body.driver_id)
    if not body.force:
        clashes = await find_clashes(session, vehicle_id=body.vehicle_id, driver_id=body.driver_id, start=body.planned_start, end=body.planned_end)
        if clashes:
            raise _clash_error(clashes)
    code = f"TRP-{await session.scalar(select(func.nextval('trip_code_seq')))}"
    trip = Trip(
        trip_code=code, client_id=body.client_id, vehicle_id=body.vehicle_id, driver_id=body.driver_id, branch_id=body.branch_id,
        lr_no=body.lr_no.strip(), eway_bill_no=body.eway_bill_no, origin=(body.origin or get_settings().default_origin).strip(),
        destination=body.destination.strip(), freight_amount=body.freight_amount, pod_status=PodStatus.pending, state=TripState.planned,
        planned_start=body.planned_start, planned_end=body.planned_end,
    )
    session.add(trip)
    session.add(AuditLog(actor_id=user.id, action="trip.create", entity="trip", entity_id=code, meta={"forced": body.force}))
    await session.commit()
    return {"id": str(trip.id), "trip_code": code}


async def _planned_trip(session: AsyncSession, trip_id: uuid.UUID) -> Trip:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
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
    await _check_people(session, vehicle_id, driver_id)
    if not body.force:
        clashes = await find_clashes(session, vehicle_id=vehicle_id, driver_id=driver_id, start=start, end=end, exclude=trip.id)
        if clashes:
            raise _clash_error(clashes)
    trip.vehicle_id, trip.driver_id, trip.planned_start, trip.planned_end = vehicle_id, driver_id, start, end
    session.add(AuditLog(actor_id=user.id, action="trip.replan", entity="trip", entity_id=trip.trip_code, meta={"forced": body.force}))
    await session.commit()
    return {"id": str(trip.id), "trip_code": trip.trip_code}


@router.post("/trips/{trip_id}/cancel")
async def cancel(trip_id: uuid.UUID, user: Planner, session: Session) -> dict:
    trip = await _planned_trip(session, trip_id)
    if trip.state not in ACTIVE or trip.pod_status != PodStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "This trip already has a POD or is finished; it cannot be cancelled")
    trip.state = TripState.cancelled
    session.add(AuditLog(actor_id=user.id, action="trip.cancel", entity="trip", entity_id=trip.trip_code))
    await session.commit()
    return {"id": str(trip.id), "state": trip.state.value}
