"""Tokenised upload links for hired drivers (no app, no login) and the public endpoints they open.

Security model: a link is a bearer secret scoped to ONE trip and ONE purpose (upload a POD photo). Only the SHA-256 of
the token is stored, so a database leak does not leak working links. Links expire, can be revoked, are rate limited,
reveal no personal data, and a new link revokes the older ones for that trip.
"""
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import AccessLink, AuditLog, LinkKind, Role, Trip, TripState, User, Vehicle
from app.notify.sms import MockSms, Sms, get_sms, mask_phone, render, send_sms
from app.phones import clean_phone
from app.pod.ingest import OPEN_STATUSES, UploadResult, ingest_pod
from app.ratelimit import RateLimiter
from app.security import link_hash, require_roles
from app.storage import Storage, get_storage

router = APIRouter(tags=["links"])
Session = Annotated[AsyncSession, Depends(get_session)]

bad_token_limiter = RateLimiter(max_hits=30, window_s=60)  # per client IP: guessing tokens
upload_limiter = RateLimiter(max_hits=12, window_s=3600)  # per link: photos per hour (retakes are capped at 2 anyway)


_hash = link_hash


class CreateLink(BaseModel):
    phone: str | None = Field(default=None, pattern=r"^\+?\d{10,15}$", description="driver's mobile; SMS is sent if given")
    driver_name: str | None = Field(default=None, max_length=120, description="a hired driver's name, for the record")
    lang: Literal["hi", "mr", "en"] = "hi"


class LinkOut(BaseModel):
    url: str
    expires_at: datetime
    sms_sent: bool
    sms_simulated: bool = False  # the sender is the simulated one: nothing really left the machine
    sms_error: str | None = None  # why the text did not go; the link itself is still good and can be shared by hand


class LinkInfo(BaseModel):
    """Everything the public page may know: no client, amount, consignee or other trips."""

    destination: str
    vehicle: str
    status: str
    retakes_left: int
    expires_at: datetime
    needs_code: bool = False  # the receiver's 4-digit code must be entered before the photo


async def _driver_for(session: AsyncSession, trip: Trip, vehicle: Vehicle | None, phone: str | None, name: str | None, lang: str) -> User:
    """The person the link signs in as. A trip with a driver keeps them; a hired trip with none gets a driver record (found by mobile number,
    so the same person on their next trip is the same record) who has no PIN and can only ever use a private link."""
    if trip.driver_id:
        return await session.get(User, trip.driver_id)
    person = await session.scalar(select(User).where(User.phone == phone)) if phone else None
    if person is not None and (person.role != Role.driver or not person.is_active):
        raise HTTPException(status.HTTP_409_CONFLICT, "That mobile number belongs to someone who cannot be a driver")
    if person is None:
        person = User(name=(name or "").strip() or f"Hired driver {vehicle.reg_no if vehicle else ''}".strip(), phone=phone, role=Role.driver, language=lang,
                      employment_type="hired", vendor_id=vehicle.vendor_id if vehicle else None)
        session.add(person)
        await session.flush()
    trip.driver_id = person.id
    return person


@router.post("/trips/{trip_id}/upload-link", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
async def create_link(
    trip_id: uuid.UUID, body: CreateLink, user: Annotated[User, Depends(require_roles(Role.ops, Role.billing))],
    session: Session, sms: Annotated[Sms, Depends(get_sms)],
) -> LinkOut:
    s = get_settings()
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    if trip.state == TripState.cancelled:
        raise HTTPException(status.HTTP_409_CONFLICT, "This trip is cancelled")
    if trip.pod_status not in OPEN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"POD already {trip.pod_status.value}; no upload needed")
    phone = clean_phone(body.phone) if body.phone else None
    await _driver_for(session, trip, await session.get(Vehicle, trip.vehicle_id), phone, body.driver_name, body.lang)

    await session.execute(update(AccessLink).where(AccessLink.trip_id == trip.id, AccessLink.kind == LinkKind.sms_upload,
                                                   AccessLink.revoked.is_(False)).values(revoked=True))
    raw = secrets.token_urlsafe(32)  # 256 bits
    # Long enough for the whole trip: the link must still work on the road and at the drop, days after it was sent.
    expires = max(datetime.now(UTC) + timedelta(hours=s.upload_link_ttl_hours), (trip.planned_end or datetime.now(UTC)) + timedelta(hours=48))
    session.add(AccessLink(token=_hash(raw), trip_id=trip.id, kind=LinkKind.sms_upload, expires_at=expires))
    url = f"{s.app_base_url.rstrip('/')}/u/{raw}?l={body.lang}"
    failure = await send_sms(session, sms, phone, render(body.lang, trip.destination, url), actor=user.id) if phone else None
    session.add(AuditLog(actor_id=user.id, action="link.create", entity="trip", entity_id=str(trip.id),
                         meta={"kind": "sms_upload", "sms_to": mask_phone(phone) if phone else None, "sms_failed": failure is not None}))
    await session.commit()
    return LinkOut(url=url, expires_at=expires, sms_sent=bool(phone) and failure is None, sms_simulated=isinstance(sms, MockSms), sms_error=failure)


@router.delete("/trips/{trip_id}/upload-link", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_links(trip_id: uuid.UUID, user: Annotated[User, Depends(require_roles(Role.ops, Role.billing))],
                       session: Session) -> Response:
    await session.execute(update(AccessLink).where(AccessLink.trip_id == trip_id, AccessLink.kind == LinkKind.sms_upload)
                          .values(revoked=True))
    session.add(AuditLog(actor_id=user.id, action="link.revoke", entity="trip", entity_id=str(trip_id)))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _resolve(token: str, request: Request, session: AsyncSession) -> tuple[AccessLink, Trip]:
    link = await session.get(AccessLink, _hash(token)) if 20 <= len(token) <= 128 else None
    if link is None or link.kind != LinkKind.sms_upload:
        # Throttle guessing, but ONLY for unknown tokens: carrier NAT puts many real drivers behind one IP, so a
        # blocked address must still be able to use its valid link. (Tokens are 256-bit; this limits load, not risk.)
        ip = request.client.host if request.client else "unknown"
        if bad_token_limiter.blocked(ip):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
        bad_token_limiter.record(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    if link.revoked or link.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "This link has expired. Ask the office for a new one.")
    trip = await session.get(Trip, link.trip_id)
    return link, trip


@router.get("/u/{token}", response_model=LinkInfo)
async def link_info(token: str, request: Request, session: Session) -> LinkInfo:
    link, trip = await _resolve(token, request, session)
    vehicle = await session.scalar(select(Vehicle.reg_no).where(Vehicle.id == trip.vehicle_id))
    return LinkInfo(destination=trip.destination, vehicle=vehicle or "", status=trip.pod_status.value,
                    retakes_left=max(0, get_settings().max_retakes - trip.retake_count), expires_at=link.expires_at,
                    needs_code=bool(trip.delivery_code) and trip.delivery_confirmed_at is None)


@router.post("/u/{token}/pod", response_model=UploadResult)
async def link_upload(
    token: str, request: Request, file: UploadFile, session: Session, storage: Annotated[Storage, Depends(get_storage)],
    client_upload_id: Annotated[str, Form(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    captured_at: Annotated[datetime, Form()],
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180)] = None,
) -> UploadResult:
    link, trip = await _resolve(token, request, session)
    if upload_limiter.blocked(link.token):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many photos for this link.")
    upload_limiter.record(link.token)
    return await ingest_pod(session, storage, trip=trip, file=file, client_upload_id=client_upload_id,
                            captured_at=captured_at, lat=lat, lng=lng, actor_id=None, source="sms_link")


class Handover(BaseModel):
    code: str = Field(pattern=r"^\d{4}$")
    shortage_or_damage: bool = False
    note: str | None = Field(default=None, max_length=300)


@router.post("/u/{token}/deliver")
async def link_deliver(token: str, body: Handover, request: Request, session: Session) -> dict:
    """A hired driver hands the goods over from the link: the receiver's code, and anything short or damaged."""
    from app.notify.service import safely
    from app.notify.shipment import tell_parties
    from app.routers.journey import confirm_delivery

    link, trip = await _resolve(token, request, session)
    if upload_limiter.blocked(f"code:{link.token}"):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many tries for this link.")
    upload_limiter.record(f"code:{link.token}")
    await confirm_delivery(session, trip, code=body.code, issue=body.shortage_or_damage, note=body.note, override=None, actor_id=None, office=False)
    await safely(session, tell_parties(session, trip, "delivered"))
    return {"delivered": True}
