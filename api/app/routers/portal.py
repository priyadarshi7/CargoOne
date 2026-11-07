"""A client's own login: their shipments and requests, and a way to ask for the next truck. Nothing else, and nothing about any other client.

The login is made by the ops head for a named person at the client (an email and a temporary password that must be replaced at first
sign-in). Every call here is scoped to the client the login belongs to, taken from the account and never from the request."""
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import online
from app.billing.claims import client_invoice_view
from app.billing.periods import IST
from app.db import get_session
from app.models import AuditLog, Client, Invoice, PodStatus, Role, TransportRequest, Trip, TripState, User
from app.notify.service import safely, send_to_phone
from app.phones import clean_phone
from app.places import Coords
from app.ratelimit import RateLimiter
from app.routers.requests import _link, status_token
from app.security import require_roles
from app.shipment import shipment_token
from app.storage import Storage, get_storage

router = APIRouter(prefix="/portal", tags=["client portal"])
Session = Annotated[AsyncSession, Depends(get_session)]
Member = Annotated[User, Depends(require_roles(Role.client))]
request_limiter = RateLimiter(max_hits=20, window_s=3600)  # per login


async def _client(session: AsyncSession, user: User) -> Client:
    client = await session.get(Client, user.client_id) if user.client_id else None
    if client is None or not client.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This login is not linked to an active client")
    return client


def _stage(t: Trip, inv: Invoice | None) -> str:
    if t.state == TripState.cancelled:
        return "cancelled"
    if inv and inv.paid_at:
        return "paid"
    if inv and inv.sent_at:
        return "invoiced"
    if t.pod_status in (PodStatus.verified, PodStatus.billed):
        return "verified"
    if t.state == TripState.delivered:
        return "delivered"
    if t.state == TripState.in_transit:
        return "started"
    return "loaded" if t.loaded_at else "booked"


@router.get("/me")
async def me(user: Member, session: Session) -> dict:
    client = await _client(session, user)
    return {"name": user.name, "company": client.name, "language": user.language, "has_phone": bool(client.contact_phone or user.phone)}


@router.get("/shipments")
async def shipments(user: Member, session: Session) -> list[dict]:
    client = await _client(session, user)
    rows = (await session.execute(select(Trip, Invoice).outerjoin(Invoice, Invoice.id == Trip.invoice_id).where(Trip.client_id == client.id).order_by(Trip.created_at.desc()).limit(200))).all()
    return [{"trip_code": t.trip_code, "origin": t.origin, "destination": t.destination, "stage": _stage(t, inv), "planned_start": t.planned_start, "delivered_at": t.delivered_at,
             "freight_amount": float(t.freight_amount), "token": shipment_token(t, "client")} for t, inv in rows]


async def _my_invoice(session: AsyncSession, user: User, invoice_id: uuid.UUID) -> Invoice:
    client = await _client(session, user)
    inv = await session.get(Invoice, invoice_id)
    if inv is None or inv.client_id != client.id or inv.sent_at is None:  # another client's, or not sent yet: the same answer
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    return inv


@router.get("/invoices")
async def invoices(user: Member, session: Session) -> list[dict]:
    """The invoices billing has sent to this client, newest first, with what is still due and where their own payment notes stand."""
    client = await _client(session, user)
    rows = (await session.scalars(select(Invoice).where(Invoice.client_id == client.id, Invoice.sent_at.is_not(None)).order_by(Invoice.sent_at.desc()).limit(100))).all()
    return [await client_invoice_view(session, i) for i in rows]


@router.get("/invoices/{invoice_id}/pdf")
async def invoice_pdf(invoice_id: uuid.UUID, user: Member, session: Session, storage: Annotated[Storage, Depends(get_storage)]) -> Response:
    from app.routers.billing import invoice_pdf_bytes

    inv = await _my_invoice(session, user, invoice_id)
    _, pdf = await invoice_pdf_bytes(session, storage, inv.id)
    session.add(AuditLog(actor_id=user.id, action="invoice.view", entity="invoice", entity_id=str(inv.id), meta={"via": "portal"}))
    await session.commit()
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{inv.invoice_no.replace("/", "-")}.pdf"', "Cache-Control": "private, no-store"})


@router.post("/invoices/{invoice_id}/pay")
async def pay_online(invoice_id: uuid.UUID, user: Member, session: Session) -> dict:
    """Opens a Razorpay order for what is left on the invoice."""
    return await online.start(session, await _my_invoice(session, user, invoice_id), user.id)


@router.post("/invoices/{invoice_id}/pay/confirm")
async def pay_online_confirm(invoice_id: uuid.UUID, body: online.Returned, user: Member, session: Session) -> dict:
    """The Razorpay pop-up came back: the payment is checked and applied once."""
    inv = await _my_invoice(session, user, invoice_id)
    await online.finish(session, inv, body)
    return await client_invoice_view(session, inv)


@router.get("/requests")
async def requests(user: Member, session: Session) -> list[dict]:
    client = await _client(session, user)
    rows = (await session.scalars(select(TransportRequest).where(TransportRequest.client_id == client.id).order_by(TransportRequest.created_at.desc()).limit(100))).all()
    return [{"reference": r.reference, "status": r.status, "origin": r.origin, "destination": r.destination, "material": r.material, "pickup_date": r.pickup_date.isoformat(),
             "quote_amount": float(r.quote_amount) if r.quote_amount is not None and r.status in ("accepted", "booked") else None,
             "needs_reply": r.status == "accepted" and r.quote_amount is not None and r.quote_accepted_at is None, "token": status_token(r.reference)} for r in rows]


class NewRequest(Coords):
    origin: str = Field(min_length=2, max_length=120)
    destination: str = Field(min_length=2, max_length=120)
    material: str = Field(min_length=2, max_length=160)
    weight_tonnes: Decimal | None = Field(default=None, gt=0, le=100, decimal_places=2)
    truck_type: str | None = Field(default=None, max_length=60)
    pickup_date: date
    notes: str | None = Field(default=None, max_length=500)
    phone: str | None = None  # only needed when neither the client nor the login has a number saved

    @field_validator("pickup_date")
    @classmethod
    def _soon(cls, v: date) -> date:
        today = datetime.now(IST).date()
        if v < today or v > today + timedelta(days=180):
            raise ValueError("Pickup date must be from today up to 6 months ahead")
        return v


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def new_request(body: NewRequest, user: Member, session: Session) -> dict:
    """A repeat client asks for the next truck: no company details to retype, and the request is already theirs."""
    client = await _client(session, user)
    phone = client.contact_phone or user.phone or body.phone
    if not phone:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Add a phone number the office can reach you on.")
    if request_limiter.blocked(str(user.id)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests in a short time. Please try again later.")
    request_limiter.record(str(user.id))
    ref = f"REQ-{await session.scalar(select(func.nextval('request_ref_seq')))}"
    req = TransportRequest(
        reference=ref, company_name=client.name, contact_name=user.name, phone=clean_phone(phone), gstin=client.gstin, language=user.language, origin=body.origin.strip(),
        destination=body.destination.strip(), material=body.material.strip(), weight_tonnes=body.weight_tonnes, truck_type=(body.truck_type or "").strip() or None,
        pickup_date=body.pickup_date, notes=(body.notes or "").strip() or None, consent_at=datetime.now(UTC), client_id=client.id,
        origin_lat=body.origin_lat, origin_lng=body.origin_lng, destination_lat=body.destination_lat, destination_lng=body.destination_lng)
    session.add(req)
    session.add(AuditLog(actor_id=user.id, action="request.submit", entity="request", entity_id=ref, meta={"portal": True}))
    await session.commit()
    await safely(session, send_to_phone(session, req.phone, req.language, "request_received", {"name": user.name, "reference": ref, "link": _link(ref)},
                                        secret=status_token(ref).split(".")[1]))
    await session.commit()
    return {"reference": ref, "token": status_token(ref)}


__all__ = ["router", "uuid"]
