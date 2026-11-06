"""Receiving a POD photo: validate, store privately, AI-check, apply the routing rules, persist, audit.
Shared by every entry point (logged-in driver/office, and the tokenised SMS link) so the rules cannot drift."""
import io
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.registry import AllProvidersFailed, run_extraction
from app.config import get_settings
from app.events import record
from app.models import AuditLog, PodStatus, PodSubmission, Trip, TripState
from app.pod.decision import Decision, Voice, decide
from app.storage import Storage

ALLOWED = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}
MAX_PIXELS = 25_000_000  # decompression-bomb guard
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


def result_of(sub: PodSubmission, trip: Trip, *, duplicate: bool = False) -> UploadResult:
    voice = Voice((sub.ai_result or {}).get("_voice", "review"))
    return UploadResult(
        submission_id=str(sub.id), decision=Decision(sub.decision.value), reasons=list(sub.decision_reasons),
        voice=voice, attempt=sub.attempt, retakes_left=max(0, get_settings().max_retakes - trip.retake_count),
        duplicate=duplicate,
    )


def validate_image(data: bytes) -> tuple[str, str]:
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


async def ingest_pod(
    session: AsyncSession, storage: Storage, *, trip: Trip, file: UploadFile, client_upload_id: str,
    captured_at: datetime, lat: float | None, lng: float | None, actor_id: uuid.UUID | None, source: str,
) -> UploadResult:
    s = get_settings()

    # Idempotency: an offline retry of an already-processed upload returns the stored verdict.
    prior = await session.scalar(select(PodSubmission).where(PodSubmission.client_upload_id == client_upload_id))
    if prior is not None:
        if prior.trip_id != trip.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Upload id already used")
        return result_of(prior, trip, duplicate=True)

    if trip.pod_status not in OPEN_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"POD already {trip.pod_status.value}")

    if trip.delivery_code and trip.delivery_confirmed_at is None and source != "office":
        raise HTTPException(status.HTTP_409_CONFLICT, "Enter the receiver's 4-digit code first: it proves who received the goods")
    data = await file.read(s.max_image_bytes + 1)
    if len(data) > s.max_image_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Image must be under 300 KB")
    mime, ext = validate_image(data)
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
        captured_at=captured_at, lat=lat, lng=lng, source=source,
        client_upload_id=client_upload_id, ai_provider=ai_provider, ai_result=ai_result,
        ai_confidence=confidence, decision=PodStatus(decision.value), decision_reasons=reasons,
    )
    session.add(sub)
    trip.pod_status = PodStatus(decision.value)
    trip.pod_uploaded_at = datetime.now(UTC)
    if trip.state in (TripState.planned, TripState.in_transit):
        trip.state = TripState.delivered  # a POD photo means the goods arrived
    if trip.first_pod_at is None:
        trip.first_pod_at = trip.pod_uploaded_at
    if decision == Decision.retake_requested:
        trip.retake_count += 1
    if decision == Decision.verified:
        trip.verified_at = datetime.now(UTC)
    session.add(AuditLog(actor_id=actor_id, action="pod.upload", entity="trip", entity_id=str(trip.id),
                         meta={"attempt": attempt, "decision": decision.value, "source": source}))
    if trip.delivery_confirmed_at is None:
        trip.delivery_confirmed_at = trip.pod_uploaded_at  # office upload, or a trip made before delivery codes existed: the photo itself is the proof
        record(session, trip, "delivered", actor=actor_id, public=True, meta={"by": "pod_photo"})
    await session.commit()
    if decision == Decision.verified:
        from app.notify.service import safely
        from app.notify.shipment import tell_parties

        await safely(session, tell_parties(session, trip, "verified"))
    return result_of(sub, trip)


__all__ = ["AllProvidersFailed", "UploadResult", "ingest_pod", "result_of", "validate_image"]
