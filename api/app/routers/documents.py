"""Photos and PDFs of the papers behind a truck or a driver: RC, insurance, fitness, permit, PUC, driving licence.

One current file per paper kind: uploading again replaces the old one. Files are private (a driving licence is personal
data under DPDP 2023): they are only served through these role-checked endpoints, never by a public URL.
Truck papers are visible to ops and billing; a driver's papers only to ops (and admin). Only ops/admin may add or remove."""
import io
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Response, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AuditLog, Document, Role, Trip, User, Vehicle
from app.security import require_roles
from app.storage import Storage, get_storage

router = APIRouter(prefix="/documents", tags=["documents"])
Session = Annotated[AsyncSession, Depends(get_session)]
Manager = Annotated[User, Depends(require_roles(Role.ops))]
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]

KINDS = {"vehicle": ("rc", "insurance", "fitness", "permit", "puc"), "driver": ("licence", "licence_back"), "trip": ("lr_scan",)}
OwnerType = Literal["vehicle", "driver", "trip"]
MAX_BYTES = 3 * 1024 * 1024
MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}


def sniff(data: bytes) -> str | None:
    """The real type from the first bytes. The upload's own content type and file name are never trusted."""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:5] == b"%PDF-":
        return "application/pdf"
    return None


def _out(d: Document) -> dict:
    return {"id": str(d.id), "owner_type": d.owner_type, "owner_id": str(d.owner_id), "kind": d.kind, "mime": d.mime, "size_bytes": d.size_bytes,
            "uploaded_at": d.created_at.isoformat() if d.created_at else None}


async def _owner_exists(session: AsyncSession, owner_type: str, owner_id: uuid.UUID) -> bool:
    if owner_type == "vehicle":
        return await session.get(Vehicle, owner_id) is not None
    if owner_type == "trip":
        return await session.get(Trip, owner_id) is not None
    u = await session.get(User, owner_id)
    return u is not None and u.role == Role.driver


def _may_see(user: User, owner_type: str) -> bool:
    return owner_type != "driver" or user.role in (Role.ops, Role.admin)


@router.get("")
async def list_documents(owner_type: OwnerType, owner_id: uuid.UUID, user: Office, session: Session) -> list[dict]:
    if not _may_see(user, owner_type):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not allowed")
    rows = (await session.scalars(select(Document).where(Document.owner_type == owner_type, Document.owner_id == owner_id).order_by(Document.kind))).all()
    return [_out(d) for d in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile, owner_type: Annotated[OwnerType, Form()], owner_id: Annotated[uuid.UUID, Form()], kind: Annotated[str, Form()],
    actor: Manager, session: Session, storage: Annotated[Storage, Depends(get_storage)],
) -> dict:
    if kind not in KINDS[owner_type]:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown paper. Choose one of: {', '.join(KINDS[owner_type])}")
    if not await _owner_exists(session, owner_type, owner_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    data = await file.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "File is too big. Keep it under 3 MB (a phone photo is usually fine).")
    mime = sniff(data)
    if mime is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a JPEG, PNG or WebP photo, or a PDF")
    if mime != "application/pdf":
        try:
            Image.open(io.BytesIO(data)).verify()
        except (UnidentifiedImageError, OSError):
            raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "That image could not be read") from None
    old = await session.scalar(select(Document).where(Document.owner_type == owner_type, Document.owner_id == owner_id, Document.kind == kind))
    key = f"docs/{owner_type}/{owner_id}/{kind}-{uuid.uuid4().hex[:8]}{MIME[mime]}"
    await storage.put(key, data)
    if old is not None:
        await storage.delete(old.storage_key)  # an outdated licence photo is personal data we no longer need
        await session.delete(old)
        await session.flush()
    doc = Document(owner_type=owner_type, owner_id=owner_id, kind=kind, storage_key=key, mime=mime, size_bytes=len(data), uploaded_by=actor.id)
    session.add(doc)
    session.add(AuditLog(actor_id=actor.id, action="document.upload", entity=owner_type, entity_id=str(owner_id), meta={"kind": kind}))
    await session.commit()
    return _out(doc)


async def _doc(session: AsyncSession, doc_id: uuid.UUID, user: User) -> Document:
    d = await session.get(Document, doc_id)
    if d is None or not _may_see(user, d.owner_type):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    return d


@router.get("/{doc_id}/file")
async def get_file(doc_id: uuid.UUID, user: Office, session: Session, storage: Annotated[Storage, Depends(get_storage)]) -> Response:
    d = await _doc(session, doc_id, user)
    return Response(await storage.get(d.storage_key), media_type=d.mime, headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: uuid.UUID, actor: Manager, session: Session, storage: Annotated[Storage, Depends(get_storage)]) -> Response:
    d = await _doc(session, doc_id, actor)
    await storage.delete(d.storage_key)
    session.add(AuditLog(actor_id=actor.id, action="document.delete", entity=d.owner_type, entity_id=str(d.owner_id), meta={"kind": d.kind}))
    await session.delete(d)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
