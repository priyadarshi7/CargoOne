"""Data-principal rights (DPDP Act 2023). A person asks what is held about them, to correct it, to erase it, to stop a consent, or complains.

Public side (no login): anyone can leave a request with their mobile number (rate-limited, like the transport request form); they get a reference.
Office side (admin and MD, the privacy officer): the register of requests, who is held under a number, erasing it, and closing the request with what was done.
The officer confirms who is asking (calls the number back) before showing or erasing anything: the form proves nothing about the sender."""
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import case, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app import privacy
from app.config import get_settings
from app.db import get_session
from app.models import AuditLog, PrivacyRequest, Role, User
from app.phones import clean_phone
from app.ratelimit import RateLimiter
from app.security import require_roles

router = APIRouter(prefix="/privacy", tags=["privacy"])
public = APIRouter(prefix="/public/privacy", tags=["privacy"])
Officer = Annotated[User, Depends(require_roles(Role.admin, Role.md))]
Session = Annotated[AsyncSession, Depends(get_session)]
Kind = Literal["access", "correction", "erasure", "consent", "complaint"]
ip_limiter = RateLimiter(max_hits=5, window_s=3600)
phone_limiter = RateLimiter(max_hits=3, window_s=86400)


class Person(BaseModel):
    phone: str


class NewRequest(BaseModel):
    kind: Kind
    phone: str
    name: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=500)
    website: str = ""  # hidden field: only bots fill it


class Close(BaseModel):
    outcome: Literal["done", "refused"]
    note: str = Field(min_length=3, max_length=300)


def _row(r: PrivacyRequest) -> dict:
    return {"id": str(r.id), "reference": r.reference, "kind": r.kind, "name": r.name, "phone": r.phone, "message": r.message, "source": r.source,
            "status": r.status, "outcome": r.outcome, "due_at": r.due_at, "closed_at": r.closed_at, "created_at": r.created_at,
            "overdue": r.status == "open" and r.due_at < datetime.now(UTC)}


async def _create(session: AsyncSession, body: NewRequest, source: str) -> PrivacyRequest:
    phone = clean_phone(body.phone)
    for _ in range(5):
        req = PrivacyRequest(reference=f"PRV-{secrets.randbelow(900_000) + 100_000}", kind=body.kind, name=(body.name or "").strip() or None, phone=phone,
                             message=(body.message or "").strip() or None, source=source,
                             due_at=datetime.now(UTC) + timedelta(days=get_settings().privacy_reply_days))
        session.add(req)
        try:
            await session.flush()
            return req
        except IntegrityError:  # the reference was taken: draw another
            await session.rollback()
    raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Please try again")


@public.post("", status_code=status.HTTP_201_CREATED)
async def ask(body: NewRequest, request: Request, session: Session) -> dict:
    if body.website.strip():  # a bot: pretend it worked, store nothing
        return {"reference": "PRV-0", "reply_days": get_settings().privacy_reply_days}
    phone = clean_phone(body.phone)
    ip = request.client.host if request.client else "unknown"
    if ip_limiter.blocked(ip) or phone_limiter.blocked(phone):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests from here. Please try again later or write to us.")
    ip_limiter.record(ip)
    phone_limiter.record(phone)
    req = await _create(session, body, "public")
    session.add(AuditLog(actor_id=None, action="privacy.request", entity="privacy_request", entity_id=req.reference, meta={"kind": req.kind}))
    await session.commit()
    return {"reference": req.reference, "reply_days": get_settings().privacy_reply_days}


@public.get("/contact")
async def contact() -> dict:
    s = get_settings()
    return {"company": s.company_name, "officer": s.grievance_officer, "email": s.grievance_email, "reply_days": s.privacy_reply_days,
            "years": s.retention_years, "tracking_days": s.tracking_retention_days, "request_days": s.request_retention_days}


@router.get("/requests")
async def requests(_: Officer, session: Session) -> list[dict]:
    """Open ones first, the one due soonest on top; closed ones after."""
    rows = (await session.scalars(select(PrivacyRequest).order_by(case((PrivacyRequest.status == "open", 0), else_=1), PrivacyRequest.due_at))).all()
    return [_row(r) for r in rows]


@router.post("/requests", status_code=status.HTTP_201_CREATED)
async def log_request(body: NewRequest, user: Officer, session: Session) -> dict:
    """A person asked by phone, in writing or in person: the officer puts it in the register."""
    req = await _create(session, body, "office")
    session.add(AuditLog(actor_id=user.id, action="privacy.request", entity="privacy_request", entity_id=req.reference, meta={"kind": req.kind}))
    await session.commit()
    return _row(req)


@router.post("/requests/{request_id}/close")
async def close(request_id: uuid.UUID, body: Close, user: Officer, session: Session) -> dict:
    req = await session.get(PrivacyRequest, request_id)
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Request not found")
    if req.status != "open":
        raise HTTPException(status.HTTP_409_CONFLICT, "This request is already closed")
    req.status, req.outcome, req.closed_at, req.closed_by = body.outcome, body.note.strip(), datetime.now(UTC), user.id
    privacy.mask_closed(req)
    session.add(AuditLog(actor_id=user.id, action="privacy.close", entity="privacy_request", entity_id=req.reference, meta={"outcome": body.outcome}))
    await session.commit()
    return _row(req)


@router.post("/access")
async def access(body: Person, user: Officer, session: Session) -> dict:
    phone = clean_phone(body.phone)
    session.add(AuditLog(actor_id=user.id, action="privacy.access", entity="person", meta={"phone": "******" + phone[-4:]}))
    found = await privacy.held_about(session, phone)
    await session.commit()
    return found


@router.post("/erase")
async def erase(body: Person, user: Officer, session: Session) -> dict:
    """Takes the person's name, phone and email off every trip and request, and closes a driver's account. Photos and invoices stay until the retention date (tax records)."""
    return await privacy.erase_about(session, clean_phone(body.phone), user.id)
