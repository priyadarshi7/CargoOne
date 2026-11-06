"""The shipment page: one private address per trip for the client and one for the receiver, showing the same timeline.

The client sees the price, the proof of delivery and the invoice. The receiver sees how the delivery is going and the 4-digit code to read out
to the driver, never a price. Neither sees who is driving, other trips, or any contact detail. The position is rounded to about 100 m and only
shown while the truck is on the road. Every open is written to the audit log so the office can see whether the page was looked at."""
import uuid
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.lateness import arrival_estimate
from app.models import (
    AuditLog,
    Client,
    Invoice,
    LocationPing,
    Message,
    PodStatus,
    PodSubmission,
    Role,
    Trip,
    TripEvent,
    TripState,
    User,
    Vehicle,
)
from app.notify.shipment import UPDATES, tell_parties
from app.ratelimit import RateLimiter
from app.security import require_roles
from app.shipment import AUDIENCES, genuine, parse, shipment_url
from app.storage import Storage, get_storage

public = APIRouter(prefix="/public/shipments", tags=["shipment page"])
office = APIRouter(prefix="/trips", tags=["shipment links"])
Session = Annotated[AsyncSession, Depends(get_session)]
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
bad_token_limiter = RateLimiter(max_hits=30, window_s=60)

MONEY = {"verified", "invoiced", "paid", "closed"}  # steps the receiver is never told about
NOTES_FOR_CLIENT = {"issue", "cancelled", "replanned"}  # the office's wording is shown to the client only, and only for these


async def _resolve(token: str, request: Request, session: AsyncSession) -> tuple[Trip, str]:
    parsed = parse(token)
    trip = None
    if parsed:
        code, aud, epoch, sig = parsed
        trip = await session.scalar(select(Trip).where(Trip.trip_code == code))
        if trip is not None and not genuine(trip, aud, epoch, sig):
            trip = None
    if trip is None:
        ip = request.client.host if request.client else "unknown"
        if bad_token_limiter.blocked(ip):  # throttle unknown tokens only: carrier NAT puts many real people behind one address
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
        bad_token_limiter.record(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    return trip, AUDIENCES[parse(token)[1]]  # type: ignore[index]


async def _invoice(session: AsyncSession, trip: Trip) -> Invoice | None:
    return await session.get(Invoice, trip.invoice_id) if trip.invoice_id else None


def _steps(trip: Trip, inv: Invoice | None, audience: str) -> list[dict]:
    pod = trip.pod_status in (PodStatus.verified, PodStatus.billed)
    rows = [
        ("booked", True, trip.created_at), ("assigned", trip.driver_id is not None, None), ("loaded", trip.loaded_at is not None, trip.loaded_at),
        ("started", trip.started_at is not None, trip.started_at), ("delivered", trip.delivery_confirmed_at is not None or trip.state == TripState.delivered, trip.delivered_at),
    ]
    if audience == "client":
        rows += [("verified", pod, trip.verified_at), ("invoiced", bool(inv and inv.sent_at), inv.sent_at if inv else None), ("paid", bool(inv and inv.paid_at), inv.paid_at if inv else None)]
    return [{"key": k, "done": d, "at": at} for k, d, at in rows]


@public.get("/{token}")
async def page(token: str, request: Request, session: Session) -> dict:
    trip, aud = await _resolve(token, request, session)
    client = await session.get(Client, trip.client_id)
    vehicle = await session.get(Vehicle, trip.vehicle_id)
    inv = await _invoice(session, trip)
    events = (await session.scalars(select(TripEvent).where(TripEvent.trip_id == trip.id, TripEvent.public.is_(True)).order_by(TripEvent.at, TripEvent.id))).all()
    timeline = []
    for e in events:
        if aud == "receiver" and e.kind in MONEY:
            continue
        row = {"kind": e.kind, "at": e.at, "reason": (e.meta or {}).get("reason"), "minutes": (e.meta or {}).get("minutes"), "eta": (e.meta or {}).get("eta")}
        if aud == "client" and e.kind in NOTES_FOR_CLIENT:
            row["note"] = e.note
        timeline.append(row)

    live = None
    if trip.state == TripState.in_transit:  # no location is shown once the load has arrived, or before it left
        last = await session.scalar(select(LocationPing).where(LocationPing.trip_id == trip.id).order_by(LocationPing.recorded_at.desc()).limit(1))
        arrives = await arrival_estimate(session, trip)
        if last or arrives:
            live = {"lat": round(last.lat, 3) if last else None, "lng": round(last.lng, 3) if last else None, "seen_at": last.recorded_at if last else None, "eta": arrives}

    out: dict = {
        "audience": aud, "company": get_settings().company_name, "language": client.language if client else "en", "trip_code": trip.trip_code, "lr_no": trip.lr_no,
        "origin": trip.origin, "destination": trip.destination, "vehicle": vehicle.reg_no if vehicle else "", "material": trip.material, "weight_tonnes": float(trip.weight_tonnes) if trip.weight_tonnes is not None else None,
        "packages": trip.packages, "planned_start": trip.planned_start, "planned_end": trip.planned_end, "state": trip.state.value, "cancelled": trip.state == TripState.cancelled,
        "delivered_at": trip.delivery_confirmed_at or trip.delivered_at if trip.state == TripState.delivered else None, "delivery_issue": trip.delivery_issue,
        "steps": _steps(trip, inv, aud), "timeline": timeline, "live": live,
    }
    if aud == "receiver" and trip.delivery_code and trip.delivery_confirmed_at is None and trip.state in (TripState.planned, TripState.in_transit):
        out["delivery_code"] = trip.delivery_code  # shown only until the driver has entered it
    if aud == "client":
        out |= {"client_name": client.name if client else "", "freight_amount": float(trip.freight_amount), "consignee_name": trip.consignee_name, "eway_bill_no": trip.eway_bill_no,
                "pod_available": trip.pod_status in (PodStatus.verified, PodStatus.billed),
                "invoice": {"invoice_no": inv.invoice_no, "total": float(inv.total), "sent_at": inv.sent_at, "paid_at": inv.paid_at} if inv and inv.sent_at else None}
    session.add(AuditLog(actor_id=None, action="shipment.view", entity="trip", entity_id=trip.trip_code, meta={"audience": aud}))
    await session.commit()
    return out


@public.get("/{token}/pod")
async def pod_image(token: str, request: Request, session: Session, storage: Annotated[Storage, Depends(get_storage)]) -> Response:
    trip, aud = await _resolve(token, request, session)
    if aud != "client":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    sub = await session.scalar(select(PodSubmission).where(PodSubmission.trip_id == trip.id, PodSubmission.decision == PodStatus.verified).order_by(PodSubmission.created_at.desc()).limit(1))
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    try:
        data = await storage.get(sub.storage_key)
    except FileNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found") from None
    mime = "image/webp" if sub.storage_key.endswith("webp") else "image/png" if sub.storage_key.endswith("png") else "image/jpeg"
    return Response(data, media_type=mime, headers={"Cache-Control": "private, no-store"})


# ---------------------------------------------------------------- the office: get the addresses, send them, retire them


def _whatsapp(phone: str | None, text: str) -> str | None:
    return f"https://wa.me/91{phone[-10:]}?text={quote(text)}" if phone else None


async def _links(session: AsyncSession, trip: Trip) -> dict:
    client = await session.get(Client, trip.client_id)
    lang = client.language if client and client.language in ("en", "hi", "mr") else "en"
    out = {}
    for aud in ("client", "receiver"):
        url = shipment_url(trip, aud)
        phone = client.contact_phone if (aud == "client" and client) else trip.consignee_phone
        name = (client.contact_name or client.name) if (aud == "client" and client) else trip.consignee_name
        text = f"{UPDATES['link'][lang]} {url}"
        out[aud] = {"url": url, "to": name, "has_phone": bool(phone), "has_email": aud == "receiver" and bool(trip.consignee_email), "whatsapp": _whatsapp(phone, text)}
    out["views"] = {a: (await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "shipment.view", AuditLog.entity_id == trip.trip_code, AuditLog.meta["audience"].astext == a)) or 0)
                    for a in ("client", "receiver")}
    return out


@office.get("/{trip_id}/shipment-links")
async def links(trip_id: uuid.UUID, _: Office, session: Session) -> dict:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    return await _links(session, trip)


@office.post("/{trip_id}/shipment-links/send")
async def send_link(trip_id: uuid.UUID, audience: Literal["client", "receiver"], user: Office, session: Session) -> dict:
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    await tell_parties(session, trip, "link", only=audience)
    session.add(AuditLog(actor_id=user.id, action="shipment.link_sent", entity="trip", entity_id=trip.trip_code, meta={"audience": audience}))
    await session.commit()
    last = await session.scalar(select(Message.status).where(Message.trip_id == trip.id, Message.template == "shipment_update").order_by(Message.created_at.desc()).limit(1))
    return {**(await _links(session, trip)), "sent_status": last}


@office.post("/{trip_id}/shipment-links/retire")
async def retire_links(trip_id: uuid.UUID, user: Office, session: Session) -> dict:
    """Every address ever shared for this trip stops working (a number was given to the wrong person); new ones are made."""
    trip = await session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    trip.link_epoch += 1
    session.add(AuditLog(actor_id=user.id, action="shipment.links_retired", entity="trip", entity_id=trip.trip_code))
    await session.commit()
    return await _links(session, trip)

