"""Live tracking. The driver's phone sends GPS fixes while a trip is on the road; ops and the MD watch a live map; a client
can be given a read-only link that shows roughly where their load is.

Privacy (DPDP): a driver's location is personal data. It is collected only after the driver has agreed (recorded with a
timestamp), only while a trip is in transit, shown to ops and the MD only (not billing), and old fixes are deleted after
`tracking_retention_days`. Client links show the last position rounded to ~100 m and never the driver's name."""
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.lateness import check_late
from app.models import AccessLink, AuditLog, LinkKind, LocationPing, Role, Trip, TripState, User, Vehicle
from app.notify.service import safely
from app.ratelimit import RateLimiter
from app.routers.client_view import _hash
from app.security import require_roles
from app.tracking import Fix, movement

router = APIRouter(tags=["tracking"])
Session = Annotated[AsyncSession, Depends(get_session)]
Driver = Annotated[User, Depends(require_roles(Role.driver))]
Watcher = Annotated[User, Depends(require_roles(Role.ops, Role.md))]
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
bad_token_limiter = RateLimiter(max_hits=30, window_s=60)


class Ping(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0, le=100_000)
    speed_kmh: float | None = Field(default=None, ge=0, le=250)
    recorded_at: datetime


class PingBatch(BaseModel):
    pings: list[Ping] = Field(min_length=1, max_length=50)


@router.post("/tracking/consent", status_code=status.HTTP_204_NO_CONTENT)
async def give_consent(user: Driver, session: Session) -> Response:
    if user.tracking_consent_at is None:
        user.tracking_consent_at = datetime.now(UTC)
        session.add(AuditLog(actor_id=user.id, action="tracking.consent", entity="user", entity_id=str(user.id)))
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/tracking/consent", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_consent(user: Driver, session: Session) -> Response:
    """Withdrawing stops collection immediately (pings are refused). Past fixes are removed by the retention job."""
    user.tracking_consent_at = None
    session.add(AuditLog(actor_id=user.id, action="tracking.withdraw", entity="user", entity_id=str(user.id)))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/trips/{trip_id}/pings")
async def add_pings(trip_id: uuid.UUID, body: PingBatch, user: Driver, session: Session) -> dict:
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.driver_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    if user.tracking_consent_at is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Location sharing has not been agreed")
    if trip.state != TripState.in_transit:
        raise HTTPException(status.HTTP_409_CONFLICT, "Location is only collected while the trip is on the road")
    now = datetime.now(UTC)
    rows = []
    for p in body.pings:
        if p.recorded_at > now + timedelta(minutes=2) or p.recorded_at < now - timedelta(hours=48):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A location time is not plausible")
        rows.append({"trip_id": trip.id, "driver_id": user.id, "lat": p.lat, "lng": p.lng, "accuracy_m": p.accuracy_m,
                     "speed_kmh": p.speed_kmh, "recorded_at": p.recorded_at})
    # Idempotent: the phone retries after a bad connection and the same fix must not be stored twice.
    result = await session.execute(pg_insert(LocationPing).values(rows).on_conflict_do_nothing(constraint="uq_ping_trip_time"))
    await session.commit()
    await safely(session, check_late(session, trip))
    return {"stored": result.rowcount, "received": len(rows)}


class LiveTrip(BaseModel):
    trip_id: str
    trip_code: str
    vehicle: str
    driver: str | None
    origin: str
    destination: str
    lat: float | None
    lng: float | None
    speed_kmh: float | None
    seen_at: datetime | None
    state: str  # moving | stopped | no_signal | unknown
    minutes: int
    alert: str | None  # stoppage | silent | None


@router.get("/tracking/live", response_model=list[LiveTrip])
async def live(_: Watcher, session: Session) -> list[LiveTrip]:
    s = get_settings()
    now = datetime.now(UTC)
    trips = (await session.execute(
        select(Trip, Vehicle.reg_no, User.name).join(Vehicle, Vehicle.id == Trip.vehicle_id).outerjoin(User, User.id == Trip.driver_id)
        .where(Trip.state == TripState.in_transit).order_by(Trip.trip_code)
    )).all()
    ids = [t.id for t, _, _ in trips]
    pings = (await session.scalars(
        select(LocationPing).where(LocationPing.trip_id.in_(ids), LocationPing.recorded_at >= now - timedelta(hours=6)).order_by(LocationPing.recorded_at)
    )).all() if ids else []
    by_trip: dict[uuid.UUID, list[LocationPing]] = {}
    for p in pings:
        by_trip.setdefault(p.trip_id, []).append(p)
    out = []
    for t, reg, driver in trips:
        mine = by_trip.get(t.id, [])
        state, minutes = movement([Fix(p.lat, p.lng, p.recorded_at) for p in mine], now,
                                  stale_after=timedelta(minutes=s.track_stale_min), stopped_after=timedelta(minutes=10))
        last = mine[-1] if mine else None
        alert = "silent" if state == "no_signal" else "stoppage" if state == "stopped" and minutes >= s.track_stopped_min else None
        out.append(LiveTrip(trip_id=str(t.id), trip_code=t.trip_code, vehicle=reg, driver=driver, origin=t.origin, destination=t.destination,
                            lat=last.lat if last else None, lng=last.lng if last else None, speed_kmh=last.speed_kmh if last else None,
                            seen_at=last.recorded_at if last else None, state=state, minutes=minutes, alert=alert))
    return out


@router.get("/tracking/trips/{trip_id}/track")
async def track(trip_id: uuid.UUID, user: Watcher, session: Session, hours: int = 24) -> dict:
    """The path a truck took, thinned to at most ~400 points so the map stays fast."""
    hours = max(1, min(hours, 72))
    rows = (await session.scalars(
        select(LocationPing).where(LocationPing.trip_id == trip_id, LocationPing.recorded_at >= datetime.now(UTC) - timedelta(hours=hours))
        .order_by(LocationPing.recorded_at)
    )).all()
    step = max(1, len(rows) // 400)
    session.add(AuditLog(actor_id=user.id, action="tracking.view", entity="trip", entity_id=str(trip_id)))
    await session.commit()
    return {"points": [{"lat": p.lat, "lng": p.lng, "at": p.recorded_at.isoformat()} for p in rows[::step]]}


# ---------------------------------------------------------------- client tracking link


class TrackLinkOut(BaseModel):
    url: str
    expires_at: datetime


class PublicTrack(BaseModel):
    """What a client sees: where the load roughly is, never who is driving."""

    trip_code: str
    vehicle: str
    origin: str
    destination: str
    state: str  # in_transit | delivered | planned
    lat: float | None
    lng: float | None
    seen_at: datetime | None
    expires_at: datetime
    company: str


@router.post("/trips/{trip_id}/track-link", response_model=TrackLinkOut, status_code=status.HTTP_201_CREATED)
async def create_track_link(trip_id: uuid.UUID, user: Office, session: Session) -> TrackLinkOut:
    s = get_settings()
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    if trip.state not in (TripState.planned, TripState.in_transit):
        raise HTTPException(status.HTTP_409_CONFLICT, "This trip is no longer on the road")
    await session.execute(update(AccessLink).where(AccessLink.trip_id == trip.id, AccessLink.kind == LinkKind.client_track,
                                                   AccessLink.revoked.is_(False)).values(revoked=True))
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(hours=s.track_link_ttl_hours)
    session.add(AccessLink(token=_hash(raw), trip_id=trip.id, kind=LinkKind.client_track, expires_at=expires))
    session.add(AuditLog(actor_id=user.id, action="track_link.create", entity="trip", entity_id=str(trip.id)))
    await session.commit()
    return TrackLinkOut(url=f"{s.app_base_url.rstrip('/')}/t/{raw}", expires_at=expires)


@router.delete("/trips/{trip_id}/track-link", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_track_links(trip_id: uuid.UUID, user: Office, session: Session) -> Response:
    await session.execute(update(AccessLink).where(AccessLink.trip_id == trip_id, AccessLink.kind == LinkKind.client_track).values(revoked=True))
    session.add(AuditLog(actor_id=user.id, action="track_link.revoke", entity="trip", entity_id=str(trip_id)))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/t/{token}", response_model=PublicTrack)
async def public_track(token: str, request: Request, session: Session) -> PublicTrack:
    link = await session.get(AccessLink, _hash(token)) if 20 <= len(token) <= 128 else None
    if link is None or link.kind != LinkKind.client_track:
        ip = request.client.host if request.client else "unknown"
        if bad_token_limiter.blocked(ip):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
        bad_token_limiter.record(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    if link.revoked or link.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "This link has expired. Ask the transporter for a new one.")
    trip = await session.get(Trip, link.trip_id)
    vehicle = await session.scalar(select(Vehicle.reg_no).where(Vehicle.id == trip.vehicle_id))
    last = None
    if trip.state == TripState.in_transit:  # no location is shown once the load has arrived
        last = await session.scalar(select(LocationPing).where(LocationPing.trip_id == trip.id).order_by(LocationPing.recorded_at.desc()).limit(1))
    return PublicTrack(
        trip_code=trip.trip_code, vehicle=vehicle or "", origin=trip.origin, destination=trip.destination, state=trip.state.value,
        lat=round(last.lat, 3) if last else None, lng=round(last.lng, 3) if last else None, seen_at=last.recorded_at if last else None,
        expires_at=link.expires_at, company=get_settings().company_name)


async def purge_old_pings(session: AsyncSession) -> int:
    """Retention: delete fixes older than the configured period. Run daily by the scheduler/cron in deployment."""
    cutoff = datetime.now(UTC) - timedelta(days=get_settings().tracking_retention_days)
    res = await session.execute(delete(LocationPing).where(LocationPing.recorded_at < cutoff))
    await session.commit()
    return res.rowcount or 0


