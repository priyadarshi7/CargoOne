"""Read-only POD view link for a client (consignor): they see the proof of delivery for ONE trip, nothing else.

Same security model as the hired-driver upload link (bearer secret, SHA-256 stored, expiry, revocation, throttled
guessing), with a smaller reach: it exposes no amounts, no consignee name/phone, no other trips, and no way to change
anything. Every open is written to the audit log, so the office can see whether the client looked."""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import AccessLink, AuditLog, LinkKind, PodStatus, PodSubmission, Role, Trip, User, Vehicle
from app.ratelimit import RateLimiter
from app.security import require_roles
from app.storage import Storage, get_storage

router = APIRouter(tags=["client-view"])
Session = Annotated[AsyncSession, Depends(get_session)]
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
SHAREABLE = (PodStatus.verified, PodStatus.billed)  # a client only ever sees a POD the company has accepted

bad_token_limiter = RateLimiter(max_hits=30, window_s=60)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ViewLinkOut(BaseModel):
    url: str
    expires_at: datetime


class ViewLinkRow(BaseModel):
    created_at: datetime
    expires_at: datetime
    revoked: bool
    views: int
    last_viewed_at: datetime | None


class PublicPod(BaseModel):
    """What a client may see. Deliberately small."""

    trip_code: str
    lr_no: str
    vehicle: str
    origin: str
    destination: str
    delivered_at: datetime | None
    verified_at: datetime | None
    expires_at: datetime
    company: str


@router.post("/trips/{trip_id}/view-link", response_model=ViewLinkOut, status_code=status.HTTP_201_CREATED)
async def create_view_link(trip_id: uuid.UUID, user: Office, session: Session) -> ViewLinkOut:
    s = get_settings()
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    if trip.pod_status not in SHAREABLE:
        raise HTTPException(status.HTTP_409_CONFLICT, "The POD is not verified yet, so there is nothing to share")
    await session.execute(update(AccessLink).where(AccessLink.trip_id == trip.id, AccessLink.kind == LinkKind.client_view,
                                                   AccessLink.revoked.is_(False)).values(revoked=True))
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(UTC) + timedelta(days=s.client_link_ttl_days)
    session.add(AccessLink(token=_hash(raw), trip_id=trip.id, kind=LinkKind.client_view, expires_at=expires))
    session.add(AuditLog(actor_id=user.id, action="client_link.create", entity="trip", entity_id=str(trip.id)))
    await session.commit()
    return ViewLinkOut(url=f"{s.app_base_url.rstrip('/')}/v/{raw}", expires_at=expires)


@router.get("/trips/{trip_id}/view-links", response_model=list[ViewLinkRow])
async def view_links(trip_id: uuid.UUID, _: Office, session: Session) -> list[ViewLinkRow]:
    """The access log: each link for this trip and how often the client opened it."""
    links = (await session.scalars(select(AccessLink).where(AccessLink.trip_id == trip_id, AccessLink.kind == LinkKind.client_view)
                                   .order_by(AccessLink.created_at.desc()))).all()
    out = []
    for link in links:
        views, last = (await session.execute(
            select(func.count(), func.max(AuditLog.at)).where(AuditLog.action == "client_link.view", AuditLog.entity_id == link.token[:16])
        )).one()
        out.append(ViewLinkRow(created_at=link.created_at, expires_at=link.expires_at, revoked=link.revoked, views=views, last_viewed_at=last))
    return out


@router.delete("/trips/{trip_id}/view-link", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_view_links(trip_id: uuid.UUID, user: Office, session: Session) -> Response:
    await session.execute(update(AccessLink).where(AccessLink.trip_id == trip_id, AccessLink.kind == LinkKind.client_view)
                          .values(revoked=True))
    session.add(AuditLog(actor_id=user.id, action="client_link.revoke", entity="trip", entity_id=str(trip_id)))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _resolve(token: str, request: Request, session: AsyncSession) -> tuple[AccessLink, Trip]:
    link = await session.get(AccessLink, _hash(token)) if 20 <= len(token) <= 128 else None
    if link is None or link.kind != LinkKind.client_view:
        ip = request.client.host if request.client else "unknown"
        if bad_token_limiter.blocked(ip):  # throttle unknown tokens only (shared carrier IPs), as for upload links
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
        bad_token_limiter.record(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    if link.revoked or link.expires_at <= datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "This link has expired. Ask the transporter for a new one.")
    trip = await session.get(Trip, link.trip_id)
    if trip is None or trip.pod_status not in SHAREABLE:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return link, trip


@router.get("/v/{token}", response_model=PublicPod)
async def public_pod(token: str, request: Request, session: Session) -> PublicPod:
    link, trip = await _resolve(token, request, session)
    vehicle = await session.scalar(select(Vehicle.reg_no).where(Vehicle.id == trip.vehicle_id))
    key = link.token[:16]  # a non-secret handle: enough to count views, useless to open the link
    session.add(AuditLog(actor_id=None, action="client_link.view", entity="access_link", entity_id=key, meta={"trip": str(trip.id)}))
    await session.commit()
    return PublicPod(trip_code=trip.trip_code, lr_no=trip.lr_no, vehicle=vehicle or "", origin=trip.origin,
                     destination=trip.destination, delivered_at=trip.delivered_at, verified_at=trip.verified_at,
                     expires_at=link.expires_at, company=get_settings().company_name)


@router.get("/v/{token}/image")
async def public_image(token: str, request: Request, session: Session, storage: Annotated[Storage, Depends(get_storage)]) -> Response:
    _, trip = await _resolve(token, request, session)
    sub = await session.scalar(select(PodSubmission).where(PodSubmission.trip_id == trip.id, PodSubmission.decision == PodStatus.verified)
                               .order_by(PodSubmission.created_at.desc()).limit(1))
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    try:
        data = await storage.get(sub.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image file is missing") from None
    media = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[sub.storage_key.rsplit(".", 1)[-1]]
    return Response(data, media_type=media, headers={"Cache-Control": "private, no-store"})
