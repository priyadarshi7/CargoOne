import io
import logging
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.registry import AllProvidersFailed, run_extraction
from app.config import get_settings
from app.db import get_session
from app.models import AuditLog, PodStatus, PodSubmission, Role, Trip, User
from app.pod.decision import Decision, Voice, decide
from app.security import current_user, require_roles
from app.storage import Storage, get_storage

log = logging.getLogger("cargoone.pods")
router = APIRouter(tags=["pods"])

ALLOWED = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}
MAX_PIXELS = 25_000_000  # decompression-bomb guard
OFFICE = {Role.ops, Role.billing, Role.admin}
# A new photo is only accepted while the POD is still open; otherwise a human owns it.
OPEN_STATUSES = {PodStatus.pending, PodStatus.retake_requested, PodStatus.uploaded}


class UploadResult(BaseModel):
    submission_id: str
    decision: Decision
    reasons: list[str]
    voice: Voice
    attempt: int
    retakes_left: int
    duplicate: bool = False


def _result(sub: PodSubmission, trip: Trip, *, duplicate: bool = False) -> UploadResult:
    s = get_settings()
    voice = Voice((sub.ai_result or {}).get("_voice", "review"))
    return UploadResult(
        submission_id=str(sub.id), decision=Decision(sub.decision.value), reasons=list(sub.decision_reasons),
        voice=voice, attempt=sub.attempt, retakes_left=max(0, s.max_retakes - trip.retake_count),
        duplicate=duplicate,
    )


def _validate_image(data: bytes) -> tuple[str, str]:
    """Verify the bytes really are a reasonably sized JPEG/PNG/WEBP. Returns (mime, extension)."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt, (w, h) = im.format or "", im.size
            im.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Not a valid image") from None
    if fmt not in ALLOWED:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only JPEG, PNG or WEBP")
    if w * h > MAX_PIXELS:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Image dimensions too large")
    return ALLOWED[fmt]


@router.post("/trips/{trip_id}/pod", response_model=UploadResult)
async def upload_pod(
    trip_id: uuid.UUID,
    file: UploadFile,
    client_upload_id: Annotated[str, Form(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    captured_at: Annotated[datetime, Form()],
    user: Annotated[User, Depends(require_roles(Role.driver, Role.ops, Role.billing))],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
    response: Response,
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180)] = None,
) -> UploadResult:
    s = get_settings()
    trip = await session.get(Trip, trip_id)
    # Drivers only see their own trips; a 404 (not 403) avoids revealing that other trips exist.
    if trip is None or (user.role == Role.driver and trip.driver_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")

    # Idempotency: an offline retry of an already-processed upload returns the stored verdict.
    prior = await session.scalar(select(PodSubmission).where(PodSubmission.client_upload_id == client_upload_id))
    if prior is not None:
        if prior.trip_id != trip.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Upload id already used")
        return _result(prior, trip, duplicate=True)

    if trip.pod_status not in OPEN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"POD already {trip.pod_status.value}")

    data = await file.read(s.max_image_bytes + 1)
    if len(data) > s.max_image_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Image must be under 300 KB")
    mime, ext = _validate_image(data)
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)

    attempt = (await session.scalar(select(PodSubmission.attempt).where(PodSubmission.trip_id == trip.id)
                                    .order_by(PodSubmission.attempt.desc()).limit(1)) or 0) + 1
    sub_id = uuid.uuid4()
    key = f"pods/{trip.id}/{sub_id}.{ext}"
    await storage.put(key, data)

    try:
        out = await run_extraction(data, mime, trip.lr_no)
        verdict = decide(out.extraction, expected_lr_no=trip.lr_no, retake_count=trip.retake_count,
                         threshold=s.ai_confidence_threshold, max_retakes=s.max_retakes)
        ai_provider, ai_result, confidence = out.provider, out.extraction.model_dump(), out.extraction.confidence
    except AllProvidersFailed:
        # AI outage must never block the driver: park the POD for a human.
        verdict = None
        ai_provider, ai_result, confidence = None, {}, None

    decision = verdict.decision if verdict else Decision.needs_review
    reasons = verdict.reasons if verdict else ["ai_unavailable"]
    voice = verdict.voice if verdict else Voice.review
    ai_result = {**ai_result, "_voice": voice.value}  # remembered so duplicate replies match the first reply

    sub = PodSubmission(
        id=sub_id, trip_id=trip.id, attempt=attempt, storage_key=key, size_bytes=len(data),
        captured_at=captured_at, lat=lat, lng=lng, source="office" if user.role in OFFICE else "app",
        client_upload_id=client_upload_id, ai_provider=ai_provider, ai_result=ai_result,
        ai_confidence=confidence, decision=PodStatus(decision.value), decision_reasons=reasons,
    )
    session.add(sub)
    trip.pod_status = PodStatus(decision.value)
    trip.pod_uploaded_at = datetime.now(UTC)
    if trip.first_pod_at is None:
        trip.first_pod_at = trip.pod_uploaded_at
    if decision == Decision.retake_requested:
        trip.retake_count += 1
    if decision == Decision.verified:
        trip.verified_at = datetime.now(UTC)
    session.add(AuditLog(actor_id=user.id, action="pod.upload", entity="trip", entity_id=str(trip.id),
                         meta={"attempt": attempt, "decision": decision.value, "source": sub.source}))
    await session.commit()
    response.status_code = status.HTTP_200_OK
    return _result(sub, trip)


@router.get("/pods/{submission_id}/image")
async def pod_image(
    submission_id: uuid.UUID,
    user: Annotated[User, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
) -> Response:
    sub = await session.get(PodSubmission, submission_id)
    trip = await session.get(Trip, sub.trip_id) if sub else None
    allowed = user.role in OFFICE | {Role.md} or (user.role == Role.driver and trip and trip.driver_id == user.id)
    if sub is None or not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    session.add(AuditLog(actor_id=user.id, action="pod.view", entity="pod_submission", entity_id=str(sub.id)))
    await session.commit()
    ext = sub.storage_key.rsplit(".", 1)[-1]
    media = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[ext]
    try:
        data = await storage.get(sub.storage_key)
    except FileNotFoundError:
        log.error("pod image missing from storage: submission=%s", sub.id)  # ids only, never content/PII
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image file is missing") from None
    return Response(data, media_type=media, headers={"Cache-Control": "private, no-store"})
