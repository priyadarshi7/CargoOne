"""A person's own notifications (the driver's inbox), and the office's log of WhatsApp messages."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Message, Notification, Role, User
from app.notify.whatsapp import get_whatsapp
from app.security import current_user, require_roles

router = APIRouter(tags=["notifications"])
Session = Annotated[AsyncSession, Depends(get_session)]
Me = Annotated[User, Depends(current_user)]
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]


@router.get("/notifications/mine")
async def mine(user: Me, session: Session, limit: int = 20) -> dict:
    rows = (await session.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(min(max(limit, 1), 50)))).all()
    unread = await session.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))) or 0
    return {"unread": unread, "items": [{"id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body, "link": n.link, "trip_id": str(n.trip_id) if n.trip_id else None,
                                         "read": n.read_at is not None, "created_at": n.created_at.isoformat()} for n in rows]}


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def read_all(user: Me, session: Session) -> Response:
    await session.execute(update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None)).values(read_at=func.now()))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/messages")
async def message_log(_: Office, session: Session, limit: int = 100) -> dict:
    """What was sent (or tried) to drivers. `live` is false while WhatsApp is the recording-only mock."""
    rows = (await session.execute(select(Message, User.name).outerjoin(User, User.id == Message.user_id).order_by(Message.created_at.desc()).limit(min(max(limit, 1), 300)))).all()
    return {"live": get_whatsapp().name == "meta", "provider": get_whatsapp().name, "items": [
        {"id": str(m.id), "at": m.created_at.isoformat(), "driver": name, "to": m.to_masked, "template": m.template, "status": m.status, "error": m.error, "text": m.body,
         "trip_id": str(m.trip_id) if m.trip_id else None} for m, name in rows]}


_ = uuid  # (kept for route parameter types added later)
