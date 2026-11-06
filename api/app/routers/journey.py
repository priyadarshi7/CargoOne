"""The driver's part of a shipment, step by step: accept the job, confirm the truck is loaded (with a photo), report a delay or breakdown on
the road, and hand the goods over (the receiver reads out a 4-digit code, which proves who received them). Each step lands on the trip's
timeline; the public ones are what the client and the receiver see on their shipment page."""
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST
from app.config import get_settings
from app.db import get_session
from app.events import record
from app.models import AuditLog, Role, Trip, TripEvent, TripState, User
from app.notify.service import safely
from app.notify.shipment import tell_parties
from app.pod.ingest import validate_image
from app.security import require_roles
from app.storage import Storage, get_storage

router = APIRouter(prefix="/trips", tags=["journey"])
Session = Annotated[AsyncSession, Depends(get_session)]
Driver = Annotated[User, Depends(require_roles(Role.driver))]
Mover = Annotated[User, Depends(require_roles(Role.driver, Role.ops))]
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing, Role.md))]
MAX_WRONG_CODES = 5
LOCK = timedelta(minutes=15)


async def _own(session: AsyncSession, trip_id: uuid.UUID, user: User) -> Trip:
    trip = await session.get(Trip, trip_id)
    if trip is None or (user.role == Role.driver and trip.driver_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    return trip


@router.post("/{trip_id}/ack")
async def acknowledge(trip_id: uuid.UUID, user: Driver, session: Session) -> dict:
    """The driver has seen the job and accepts it. The office sees this, so a trip nobody has opened does not surprise them at pickup time."""
    trip = await _own(session, trip_id, user)
    if trip.acknowledged_at is None and trip.state == TripState.planned:
        trip.acknowledged_at = datetime.now(UTC)
        record(session, trip, "acknowledged", actor=user.id)
        await session.commit()
    return {"acknowledged_at": trip.acknowledged_at}


@router.post("/{trip_id}/loaded")
async def loaded(
    trip_id: uuid.UUID, user: Mover, session: Session, storage: Annotated[Storage, Depends(get_storage)],
    file: UploadFile | None = None, note: Annotated[str | None, Form(max_length=200)] = None,
) -> dict:
    """The goods are on the truck. The driver must send a photo of the loaded truck and the LR; the office may confirm without one (and say why)."""
    trip = await _own(session, trip_id, user)
    if trip.state != TripState.planned:
        raise HTTPException(status.HTTP_409_CONFLICT, f"This trip is {trip.state.value}; loading cannot be confirmed now")
    if trip.loaded_at is not None:
        return {"loaded_at": trip.loaded_at}  # a retry from a phone that lost the answer
    key = None
    if file is not None:
        data = await file.read(get_settings().max_image_bytes + 1)
        if len(data) > get_settings().max_image_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Image must be under 300 KB")
        _mime, ext = validate_image(data)
        key = f"loading/{trip.id}/{uuid.uuid4()}.{ext}"
        await storage.put(key, data)
    elif user.role == Role.driver:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Take a photo of the loaded truck and the LR")
    elif not (note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say why there is no photo")
    trip.loaded_at, trip.loading_photo_key = datetime.now(UTC), key
    if trip.acknowledged_at is None and user.role == Role.driver:
        trip.acknowledged_at = trip.loaded_at
    record(session, trip, "loaded", actor=user.id, note=note, public=True, meta={"photo": key is not None})
    session.add(AuditLog(actor_id=user.id, action="trip.loaded", entity="trip", entity_id=trip.trip_code, meta={"photo": key is not None}))
    await session.commit()
    return {"loaded_at": trip.loaded_at}


@router.get("/{trip_id}/loading-photo")
async def loading_photo(trip_id: uuid.UUID, _: Office, session: Session, storage: Annotated[Storage, Depends(get_storage)]) -> Response:
    trip = await session.get(Trip, trip_id)
    if trip is None or not trip.loading_photo_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No loading photo")
    try:
        data = await storage.get(trip.loading_photo_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No loading photo") from None
    return Response(data, media_type="image/webp" if trip.loading_photo_key.endswith("webp") else "image/jpeg", headers={"Cache-Control": "private, no-store"})


class RoadEvent(BaseModel):
    kind: Literal["delay", "breakdown", "resolved"]
    reason: Literal["traffic", "weather", "police", "waiting", "rest", "tyre", "engine", "accident", "other"] = "other"
    minutes: int | None = Field(default=None, ge=5, le=720)
    note: str | None = Field(default=None, max_length=200)  # for the office only; the client sees the reason, not this


@router.post("/{trip_id}/events", status_code=status.HTTP_201_CREATED)
async def road_event(trip_id: uuid.UUID, body: RoadEvent, user: Mover, session: Session) -> dict:
    trip = await _own(session, trip_id, user)
    if trip.state != TripState.in_transit:
        raise HTTPException(status.HTTP_409_CONFLICT, "Delays and breakdowns are reported while the trip is on the road")
    if body.kind == "delay" and body.minutes is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "How long is the delay, roughly?")
    if body.kind == "breakdown" and body.reason not in ("tyre", "engine", "accident", "other"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Pick what went wrong with the truck")
    record(session, trip, body.kind, actor=user.id, note=body.note, public=True, meta={"reason": body.reason, "minutes": body.minutes})
    session.add(AuditLog(actor_id=user.id, action=f"trip.{body.kind}", entity="trip", entity_id=trip.trip_code, meta={"reason": body.reason, "minutes": body.minutes}))
    await session.commit()
    await safely(session, tell_parties(session, trip, body.kind, reason=body.reason, minutes=body.minutes or 0))
    return {"ok": True}


class Handover(BaseModel):
    code: str | None = Field(default=None, pattern=r"^\d{4}$")
    shortage_or_damage: bool = False
    note: str | None = Field(default=None, max_length=300)  # what was short or damaged: required when the box is ticked
    override_reason: str | None = Field(default=None, min_length=3, max_length=200)  # office only: the receiver could not give the code


async def confirm_delivery(session: AsyncSession, trip: Trip, *, code: str | None, issue: bool, note: str | None, override: str | None, actor_id: uuid.UUID | None, office: bool) -> None:
    """Shared by the driver's app, the hired driver's link and the office. Raises 4xx with a plain message; saves wrong-code counts before raising."""
    if trip.delivery_confirmed_at is not None:
        return  # already handed over: a retry changes nothing
    if trip.state not in (TripState.planned, TripState.in_transit):
        raise HTTPException(status.HTTP_409_CONFLICT, f"This trip is {trip.state.value}; it cannot be delivered")
    if issue and not (note or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say what was short or damaged")
    now = datetime.now(UTC)
    if override:
        if not office:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the office can confirm delivery without the receiver's code")
        trip.delivery_override = override.strip()
    elif trip.delivery_code:
        if trip.delivery_code_locked_until and now < trip.delivery_code_locked_until:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many wrong codes. Try again after {trip.delivery_code_locked_until.astimezone(IST):%H:%M} or ask the office.")
        if code is None or not hmac.compare_digest(code, trip.delivery_code):
            trip.delivery_code_tries += 1
            if trip.delivery_code_tries >= MAX_WRONG_CODES:
                trip.delivery_code_tries, trip.delivery_code_locked_until = 0, now + LOCK
            session.add(AuditLog(actor_id=actor_id, action="delivery.wrong_code", entity="trip", entity_id=trip.trip_code))
            await session.commit()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That code is not right. Ask the receiver to check the code on their shipment page.")
    trip.delivery_confirmed_at, trip.delivery_issue, trip.delivery_note = now, issue, (note or "").strip() or None
    trip.delivery_code_tries = 0
    if trip.delivered_at is None:
        trip.delivered_at = now
    trip.state = TripState.delivered
    record(session, trip, "delivered", actor=actor_id, note=f"Without the receiver's code: {override}" if override else None, public=True, meta={"override": bool(override)})
    if issue:
        record(session, trip, "issue", actor=actor_id, note=note, public=True)
    session.add(AuditLog(actor_id=actor_id, action="trip.deliver", entity="trip", entity_id=trip.trip_code, meta={"override": override, "issue": issue}))
    await session.commit()


@router.post("/{trip_id}/deliver")
async def deliver(trip_id: uuid.UUID, body: Handover, user: Mover, session: Session) -> dict:
    trip = await _own(session, trip_id, user)
    if user.role == Role.driver and trip.state == TripState.planned:
        raise HTTPException(status.HTTP_409_CONFLICT, "Start the trip first")
    await confirm_delivery(session, trip, code=body.code, issue=body.shortage_or_damage, note=body.note, override=body.override_reason,
                           actor_id=user.id, office=user.role == Role.ops)
    await safely(session, tell_parties(session, trip, "delivered"))
    return {"delivered_at": trip.delivered_at}


class TimelineRow(BaseModel):
    kind: str
    at: datetime
    note: str | None
    public: bool
    meta: dict | None


@router.get("/{trip_id}/timeline")
async def timeline(trip_id: uuid.UUID, _: Office, session: Session) -> dict:
    """For the office: every step of the trip in order, and where each driver-side step stands."""
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    rows = (await session.scalars(select(TripEvent).where(TripEvent.trip_id == trip.id).order_by(TripEvent.at, TripEvent.id))).all()
    return {
        "acknowledged_at": trip.acknowledged_at, "loaded_at": trip.loaded_at, "has_loading_photo": bool(trip.loading_photo_key), "started_at": trip.started_at,
        "delivery_confirmed_at": trip.delivery_confirmed_at, "delivery_override": trip.delivery_override, "delivery_issue": trip.delivery_issue, "delivery_note": trip.delivery_note,
        "eway_valid_until": trip.eway_valid_until, "closed_at": trip.closed_at,
        "events": [TimelineRow(kind=e.kind, at=e.at, note=e.note, public=e.public, meta=e.meta).model_dump() for e in rows],
    }
