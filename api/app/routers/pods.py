"""POD upload for logged-in users (driver app, office) and POD image retrieval. The upload rules live in
app/pod/ingest.py and are shared with the tokenised SMS-link route."""
import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AuditLog, PodSubmission, Role, Trip, User
from app.pod.ingest import UploadResult, ingest_pod
from app.security import current_user, require_roles
from app.storage import Storage, get_storage

log = logging.getLogger("cargoone.pods")
router = APIRouter(tags=["pods"])
OFFICE = {Role.ops, Role.billing, Role.admin}


@router.post("/trips/{trip_id}/pod", response_model=UploadResult)
async def upload_pod(
    trip_id: uuid.UUID,
    file: UploadFile,
    client_upload_id: Annotated[str, Form(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    captured_at: Annotated[datetime, Form()],
    user: Annotated[User, Depends(require_roles(Role.driver, Role.ops, Role.billing))],
    session: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
    lat: Annotated[float | None, Form(ge=-90, le=90)] = None,
    lng: Annotated[float | None, Form(ge=-180, le=180)] = None,
) -> UploadResult:
    trip = await session.get(Trip, trip_id)
    # Drivers only see their own trips; a 404 (not 403) avoids revealing that other trips exist.
    if trip is None or (user.role == Role.driver and trip.driver_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    return await ingest_pod(
        session, storage, trip=trip, file=file, client_upload_id=client_upload_id, captured_at=captured_at,
        lat=lat, lng=lng, actor_id=user.id, source="office" if user.role in OFFICE else "app")


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
