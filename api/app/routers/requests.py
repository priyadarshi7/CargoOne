"""Transport requests: a company that is not yet a client (or is) asks for a truck through a public page, and the office answers.

Public side (no login): submit a request, and follow it by a private link. Office side: ops reviews, onboards the company as a
client in one step (or links it to an existing client), quotes, declines, and books the trip from it (planning does the last step).

The public form is the one place the internet can write to our database, so it is guarded: a hidden field only bots fill in, per-address
and per-phone limits, strict field sizes, an explicit agreement to be contacted, and nothing about other requests or clients is ever
returned. Add a CAPTCHA (for example Cloudflare Turnstile) before advertising the address widely."""
import base64
import hashlib
import hmac
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST
from app.config import get_settings
from app.db import get_session
from app.models import AuditLog, Client, Role, TransportRequest, Trip, User
from app.notify.service import safely, send_email, send_to_phone
from app.phones import clean_phone
from app.places import Coords
from app.ratelimit import RateLimiter
from app.security import require_roles

public = APIRouter(prefix="/public/requests", tags=["public requests"])
office = APIRouter(prefix="/requests", tags=["requests"])
Session = Annotated[AsyncSession, Depends(get_session)]
Viewer = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Manager = Annotated[User, Depends(require_roles(Role.ops))]

submit_limiter = RateLimiter(max_hits=5, window_s=3600)  # per address
phone_limiter = RateLimiter(max_hits=3, window_s=86400)  # per phone number
bad_token_limiter = RateLimiter(max_hits=30, window_s=60)  # per address: guessing status links
GSTIN = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def gstin_ok(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    v = re.sub(r"\s", "", value).upper()
    if not GSTIN.fullmatch(v):
        raise ValueError("GSTIN looks wrong. It has 15 characters, for example 27ABCDE1234F1Z5")
    return v


def status_token(reference: str) -> str:
    """The private status link of a request: the reference plus a signature only the server can make (HMAC of the reference with the server secret).
    Nothing is stored, so every later message can carry the same working link; changing the server secret retires all of them."""
    sig = hmac.new(get_settings().jwt_secret.encode(), reference.encode(), hashlib.sha256).digest()
    return f"{reference}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')[:32]}"


class RequestIn(Coords):
    company_name: str = Field(min_length=2, max_length=160)
    contact_name: str = Field(min_length=2, max_length=120)
    phone: str
    email: str | None = Field(default=None, max_length=160, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    gstin: str | None = None
    language: Literal["en", "hi", "mr"] = "en"
    origin: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    material: str = Field(min_length=2, max_length=160)
    weight_tonnes: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    truck_type: str | None = Field(default=None, max_length=60)
    pickup_date: date
    notes: str | None = Field(default=None, max_length=500)
    consent: bool
    website: str = Field(default="", max_length=200)  # honeypot: a person never sees or fills this

    @field_validator("gstin")
    @classmethod
    def _gstin(cls, v: str | None) -> str | None:
        return gstin_ok(v)

    @field_validator("pickup_date")
    @classmethod
    def _soon(cls, v: date) -> date:
        today = datetime.now(IST).date()
        if v < today or v > today + timedelta(days=180):
            raise ValueError("Pickup date must be from today up to 6 months ahead")
        return v


def _link(reference: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/request/{status_token(reference)}"


@public.post("", status_code=status.HTTP_201_CREATED)
async def submit(body: RequestIn, request: Request, session: Session) -> dict:
    if not body.consent:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Please agree to be contacted about this request")
    if body.website.strip():  # a bot: pretend it worked, store nothing
        return {"reference": "REQ-0", "status_url": "", "message_status": "skipped"}
    phone = clean_phone(body.phone)
    ip = request.client.host if request.client else "unknown"
    if submit_limiter.blocked(ip) or phone_limiter.blocked(phone):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests from here. Please try again later or call us.")
    submit_limiter.record(ip)
    phone_limiter.record(phone)

    ref = f"REQ-{await session.scalar(select(func.nextval('request_ref_seq')))}"
    req = TransportRequest(
        reference=ref, company_name=body.company_name.strip(), contact_name=body.contact_name.strip(), phone=phone, email=body.email,
        gstin=body.gstin, language=body.language, origin=body.origin.strip(), destination=body.destination.strip(), material=body.material.strip(),
        weight_tonnes=body.weight_tonnes, truck_type=(body.truck_type or "").strip() or None, pickup_date=body.pickup_date, notes=(body.notes or "").strip() or None,
        consent_at=datetime.now(UTC),
        origin_lat=body.origin_lat, origin_lng=body.origin_lng, destination_lat=body.destination_lat, destination_lng=body.destination_lng,
    )
    session.add(req)
    session.add(AuditLog(actor_id=None, action="request.submit", entity="request", entity_id=ref))
    await session.commit()
    result = {"reference": ref, "status_url": _link(ref), "message_status": "skipped"}
    sent: dict = {}

    async def notify() -> None:
        msg = await send_to_phone(session, phone, body.language, "request_received", {"name": body.contact_name.strip(), "reference": ref, "link": _link(ref)},
                                  secret=status_token(ref).split(".")[1])
        sent["status"] = msg.status
        if body.email:  # a second channel for companies that gave an address
            await send_email(session, body.email, body.language, "request_received", {"name": body.contact_name.strip(), "reference": ref, "link": _link(ref)},
                             secret=status_token(ref).split(".")[1])
        await session.commit()

    await safely(session, notify())
    result["message_status"] = sent.get("status", "skipped")
    return result


async def _by_token(token: str, request: Request, session: AsyncSession) -> TransportRequest:
    ref, _, sig = token.partition(".")
    req = await session.scalar(select(TransportRequest).where(TransportRequest.reference == ref)) if 4 <= len(ref) <= 16 and len(sig) >= 20 else None
    if req is None or not hmac.compare_digest(status_token(req.reference), token):
        req = None
    if req is None:
        ip = request.client.host if request.client else "unknown"
        if bad_token_limiter.blocked(ip):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
        bad_token_limiter.record(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return req


@public.get("/{token}")
async def follow(token: str, request: Request, session: Session) -> dict:
    """What the requester may see about their own request: no contact details, no other requests, no internal notes beyond the reply."""
    r = await _by_token(token, request, session)
    trip = await session.get(Trip, r.trip_id) if r.trip_id else None
    return {
        "reference": r.reference, "status": r.status, "company_name": r.company_name, "origin": r.origin, "destination": r.destination, "material": r.material,
        "weight_tonnes": float(r.weight_tonnes) if r.weight_tonnes is not None else None, "pickup_date": r.pickup_date.isoformat(), "created_at": r.created_at.isoformat(),
        "reply": r.ops_note, "quote_amount": float(r.quote_amount) if r.quote_amount is not None and r.status in ("accepted", "booked") else None,
        "trip_code": trip.trip_code if trip else None, "planned_start": trip.planned_start.isoformat() if trip and trip.planned_start else None, "language": r.language,
        "can_respond": r.status == "accepted" and r.quote_amount is not None and r.quote_accepted_at is None,  # the quote waits for their yes or no
        "quote_accepted": r.quote_accepted_at is not None,
    }


class QuoteReply(BaseModel):
    decision: Literal["accept", "decline"]
    reason: str | None = Field(default=None, max_length=200)


@public.post("/{token}/quote")
async def reply_to_quote(token: str, body: QuoteReply, request: Request, session: Session) -> dict:
    """The requester says yes or no to the quote on their own status page. A yes lets the office book the trip; a no closes the request."""
    r = await _by_token(token, request, session)
    if r.status != "accepted" or r.quote_amount is None or r.quote_accepted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no quote waiting for an answer")
    if body.decision == "accept":
        r.quote_accepted_at, r.quote_accepted_via = datetime.now(UTC), "online"
        session.add(AuditLog(actor_id=None, action="request.quote_accepted", entity="request", entity_id=r.reference, meta={"via": "online"}))
    else:
        r.status, r.decided_at = "declined", datetime.now(UTC)
        r.ops_note = f"The quote was turned down by the requester{': ' + body.reason.strip() if body.reason and body.reason.strip() else ''}"
        session.add(AuditLog(actor_id=None, action="request.quote_declined", entity="request", entity_id=r.reference))
    await session.commit()
    return {"status": r.status, "quote_accepted": r.quote_accepted_at is not None}


# ---------------------------------------------------------------- the office

def _out(r: TransportRequest, client: str | None = None, trip_code: str | None = None) -> dict:
    return {
        "id": str(r.id), "reference": r.reference, "status": r.status, "created_at": r.created_at.isoformat(), "company_name": r.company_name,
        "contact_name": r.contact_name, "phone": r.phone, "email": r.email, "gstin": r.gstin, "language": r.language, "origin": r.origin, "destination": r.destination,
        "origin_lat": r.origin_lat, "origin_lng": r.origin_lng, "destination_lat": r.destination_lat, "destination_lng": r.destination_lng,
        "material": r.material, "weight_tonnes": float(r.weight_tonnes) if r.weight_tonnes is not None else None, "truck_type": r.truck_type,
        "pickup_date": r.pickup_date.isoformat(), "notes": r.notes, "client_id": str(r.client_id) if r.client_id else None, "client": client,
        "trip_id": str(r.trip_id) if r.trip_id else None, "trip_code": trip_code, "quote_amount": float(r.quote_amount) if r.quote_amount is not None else None,
        "reply": r.ops_note, "quote_accepted_at": r.quote_accepted_at.isoformat() if r.quote_accepted_at else None, "quote_accepted_via": r.quote_accepted_via,
    }


@office.get("")
async def list_requests(_: Viewer, session: Session, state: Literal["open", "all"] = "open") -> list[dict]:
    q = (select(TransportRequest, Client.name, Trip.trip_code).outerjoin(Client, Client.id == TransportRequest.client_id).outerjoin(Trip, Trip.id == TransportRequest.trip_id)
         .order_by(case((TransportRequest.status == "new", 0), (TransportRequest.status == "accepted", 1), else_=2), TransportRequest.created_at.desc()).limit(300))
    if state == "open":
        q = q.where(TransportRequest.status.in_(["new", "accepted"]))
    return [_out(r, c, t) for r, c, t in (await session.execute(q)).all()]


async def _get(session: AsyncSession, request_id: uuid.UUID) -> TransportRequest:
    r = await session.get(TransportRequest, request_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    return r


UPDATES = {
    "accepted": {"en": "accepted. We will confirm the truck and pickup shortly", "hi": "स्वीकार हो गया है। हम जल्द ही ट्रक और पिकअप की पुष्टि करेंगे",
                 "mr": "मान्य झाली आहे. आम्ही लवकरच ट्रक आणि पिकअपची खात्री देऊ"},
    "booked": {"en": "booked as trip {trip}, pickup {when}", "hi": "ट्रिप {trip} के रूप में बुक हो गया, पिकअप {when}", "mr": "ट्रिप {trip} म्हणून बुक झाले, पिकअप {when}"},
    "declined": {"en": "could not be taken up this time", "hi": "इस बार स्वीकार नहीं किया जा सका", "mr": "यावेळी स्वीकारता आली नाही"},
}


async def tell_requester(session: AsyncSession, r: TransportRequest, kind: str, **fmt: str) -> None:
    """A WhatsApp note to the requester, with their status link."""
    text = UPDATES[kind].get(r.language, UPDATES[kind]["en"]).format(**fmt)
    await send_to_phone(session, r.phone, r.language, "request_update", {"name": r.contact_name, "reference": r.reference, "update": text, "link": _link(r.reference)},
                        secret=status_token(r.reference).split(".")[1])
    if r.email:
        await send_email(session, r.email, r.language, "request_update", {"name": r.contact_name, "reference": r.reference, "update": text, "link": _link(r.reference)},
                         secret=status_token(r.reference).split(".")[1])
    await session.commit()


class Accept(BaseModel):
    client_id: uuid.UUID | None = None  # an existing client; blank = onboard the requesting company as a new one
    billing_cycle: Literal["weekly", "fortnightly", "monthly", "per_trip"] = "weekly"
    quote_amount: Decimal | None = Field(default=None, gt=0, le=10_000_000, decimal_places=2)
    note: str | None = Field(default=None, max_length=300)


class Decline(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@office.post("/{request_id}/accept")
async def accept(request_id: uuid.UUID, body: Accept, actor: Manager, session: Session) -> dict:
    r = await _get(session, request_id)
    if r.status != "new":
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request is already {r.status}")
    if body.client_id or r.client_id:
        client = await session.get(Client, body.client_id or r.client_id)
        if client is None or not client.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown or inactive client")
    else:
        client = Client(name=r.company_name, contact_name=r.contact_name, contact_phone=r.phone, gstin=r.gstin, billing_cycle=body.billing_cycle)
        session.add(client)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(status.HTTP_409_CONFLICT, "A client with this company name already exists. Pick it from the list instead of creating a new one.") from None
    r.status, r.client_id, r.quote_amount, r.ops_note = "accepted", client.id, body.quote_amount, (body.note or "").strip() or None
    r.decided_by, r.decided_at = actor.id, datetime.now(UTC)
    session.add(AuditLog(actor_id=actor.id, action="request.accept", entity="request", entity_id=r.reference, meta={"new_client": body.client_id is None}))
    await session.commit()
    result = _out(r, client.name)
    await safely(session, tell_requester(session, r, "accepted"))
    return result


class PhoneYes(BaseModel):
    note: str | None = Field(default=None, max_length=200)


@office.post("/{request_id}/quote-confirmed")
async def quote_confirmed(request_id: uuid.UUID, body: PhoneYes, actor: Manager, session: Session) -> dict:
    """The requester said yes on the phone: record it (and who took the call) so the trip can be booked."""
    r = await _get(session, request_id)
    if r.status != "accepted" or r.quote_amount is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "There is no quote waiting for an answer")
    if r.quote_accepted_at is None:
        r.quote_accepted_at, r.quote_accepted_via = datetime.now(UTC), "phone"
        session.add(AuditLog(actor_id=actor.id, action="request.quote_accepted", entity="request", entity_id=r.reference, meta={"via": "phone", "note": body.note}))
        await session.commit()
    return _out(r)


@office.post("/{request_id}/decline")
async def decline(request_id: uuid.UUID, body: Decline, actor: Manager, session: Session) -> dict:
    r = await _get(session, request_id)
    if r.status not in ("new", "accepted"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"This request is already {r.status}")
    r.status, r.ops_note, r.decided_by, r.decided_at = "declined", body.reason.strip(), actor.id, datetime.now(UTC)
    session.add(AuditLog(actor_id=actor.id, action="request.decline", entity="request", entity_id=r.reference))
    await session.commit()
    result = _out(r)
    await safely(session, tell_requester(session, r, "declined"))
    return result


async def book(session: AsyncSession, request_id: uuid.UUID, trip: Trip) -> tuple[TransportRequest, dict] | None:
    """Called by planning when a trip is created from an accepted request. Returns the request and what to tell the requester."""
    r = await session.get(TransportRequest, request_id)
    if r is None or r.status != "accepted" or r.client_id != trip.client_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "That request is not accepted for this client")
    if r.quote_amount is not None and r.quote_accepted_at is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The client has not accepted the quote yet. Ask them to accept it on their request page, or record their yes from a phone call.")
    r.status, r.trip_id = "booked", trip.id
    session.add(AuditLog(actor_id=None, action="request.book", entity="request", entity_id=r.reference, meta={"trip": trip.trip_code}))
    when = f"{trip.planned_start.astimezone(IST):%d %b, %H:%M}" if trip.planned_start else r.pickup_date.strftime("%d %b")
    return r, {"trip": trip.trip_code, "when": when}
