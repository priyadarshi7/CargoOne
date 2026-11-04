"""Human review of PODs the AI would not auto-verify (shortage/damage, low confidence, retake cap, AI outage).
The image stays the source of truth: reviewers may correct extracted fields, but corrections are stored
beside the AI output, never over it. Nothing here sends an invoice."""
import re
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.config import get_settings
from app.db import get_session
from app.models import AuditLog, Client, PodStatus, PodSubmission, Role, Trip, User
from app.security import require_roles

router = APIRouter(prefix="/review", tags=["review"])
Reviewer = Annotated[User, Depends(require_roles(Role.billing, Role.ops))]
Session = Annotated[AsyncSession, Depends(get_session)]


class ReviewItem(BaseModel):
    """No consignee name/phone here: the reviewer judges the image, not personal data."""

    trip_id: str
    trip_code: str
    client: str
    lr_no: str
    destination: str
    freight_amount: float
    submission_id: str
    attempt: int
    reasons: list[str]
    confidence: float | None
    ai: dict
    corrected: dict | None
    captured_at: datetime
    lat: float | None
    lng: float | None
    retakes_left: int


class CorrectedFields(BaseModel):
    lr_no: str | None = Field(default=None, max_length=40)
    delivery_date: date | None = None
    quantity_received: str | None = Field(default=None, max_length=60)
    remarks: str | None = Field(default=None, max_length=300)
    shortage_or_damage: bool | None = None


class ReviewDecision(BaseModel):
    action: Literal["approve", "request_retake", "reject"]
    corrected: CorrectedFields | None = None
    note: str | None = Field(default=None, max_length=500)


def _norm(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _item(trip: Trip, client: str, sub: PodSubmission) -> ReviewItem:
    return ReviewItem(
        trip_id=str(trip.id), trip_code=trip.trip_code, client=client, lr_no=trip.lr_no,
        destination=trip.destination, freight_amount=float(trip.freight_amount),
        submission_id=str(sub.id), attempt=sub.attempt, reasons=list(sub.decision_reasons),
        confidence=sub.ai_confidence, ai={k: v for k, v in (sub.ai_result or {}).items() if not k.startswith("_")},
        corrected=sub.corrected_fields, captured_at=sub.captured_at, lat=sub.lat, lng=sub.lng,
        retakes_left=max(0, get_settings().max_retakes - trip.retake_count),
    )


def _latest_per_trip():
    """Each trip with its most recent submission (the one a reviewer must judge)."""
    other = aliased(PodSubmission)  # alias: otherwise the subquery auto-correlates to the joined table
    latest_attempt = (
        select(other.attempt).where(other.trip_id == Trip.id).order_by(other.attempt.desc()).limit(1).scalar_subquery()
    )
    return (
        select(Trip, Client.name, PodSubmission)
        .join(Client, Client.id == Trip.client_id)
        .join(PodSubmission, (PodSubmission.trip_id == Trip.id) & (PodSubmission.attempt == latest_attempt))
    )


@router.get("", response_model=list[ReviewItem])
async def queue(_: Reviewer, session: Session) -> list[ReviewItem]:
    """Oldest first, so the longest-waiting POD (and its working-capital cost) is handled first."""
    q = _latest_per_trip().where(Trip.pod_status == PodStatus.needs_review).order_by(PodSubmission.created_at)
    return [_item(t, c, s) for t, c, s in (await session.execute(q)).all()]


@router.get("/{trip_id}", response_model=ReviewItem)
async def detail(trip_id: uuid.UUID, _: Reviewer, session: Session) -> ReviewItem:
    row = (await session.execute(_latest_per_trip().where(Trip.id == trip_id))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No POD for this trip")
    return _item(*row)


@router.post("/{trip_id}/decision", response_model=ReviewItem)
async def decide_review(trip_id: uuid.UUID, body: ReviewDecision, user: Reviewer, session: Session) -> ReviewItem:
    row = (await session.execute(_latest_per_trip().where(Trip.id == trip_id).with_for_update(of=Trip))).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No POD for this trip")
    trip, client, sub = row
    if trip.pod_status != PodStatus.needs_review:  # also blocks double-submits and races between reviewers
        raise HTTPException(status.HTTP_409_CONFLICT, f"POD is {trip.pod_status.value}, not awaiting review")

    now = datetime.now(UTC)
    corrected = body.corrected.model_dump(mode="json", exclude_none=True) if body.corrected else {}
    if body.note:
        corrected["_note"] = body.note

    if body.action == "approve":
        final = {**(sub.ai_result or {}), **corrected}
        if _norm(final.get("lr_no")) != _norm(trip.lr_no):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "LR number does not match this trip")
        if not final.get("delivery_date"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Delivery date is required to approve")
        trip.pod_status = PodStatus.verified
        trip.verified_at = now
        if trip.delivered_at is None:
            trip.delivered_at = datetime.fromisoformat(str(final["delivery_date"])).replace(tzinfo=UTC)
        sub.decision = PodStatus.verified
    elif body.action == "request_retake":
        if trip.retake_count >= get_settings().max_retakes:
            raise HTTPException(status.HTTP_409_CONFLICT, "Retake limit reached: approve or reject instead")
        trip.pod_status = PodStatus.retake_requested
        trip.retake_count += 1
        sub.decision = PodStatus.retake_requested
    else:
        trip.pod_status = PodStatus.rejected
        sub.decision = PodStatus.rejected

    sub.corrected_fields = corrected or None
    sub.reviewed_by, sub.reviewed_at = user.id, now
    session.add(AuditLog(actor_id=user.id, action=f"review.{body.action}", entity="trip", entity_id=str(trip.id),
                         meta={"submission": str(sub.id), "corrected": sorted(k for k in corrected if k != "_note")}))
    await session.commit()
    return _item(trip, client, sub)
