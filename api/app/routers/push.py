"""Web Push for the app: the phone asks for the public key, subscribes, and can send itself a test alert."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import PushSubscription, User
from app.notify.push import live, push_user
from app.security import current_user

router = APIRouter(prefix="/push", tags=["push"])
Session = Annotated[AsyncSession, Depends(get_session)]
Me = Annotated[User, Depends(current_user)]
MAX_PER_PERSON = 5  # a person with more phones than this keeps only the newest ones


class Keys(BaseModel):
    p256dh: str = Field(min_length=10, max_length=200)
    auth: str = Field(min_length=4, max_length=100)


class Subscribe(BaseModel):
    endpoint: str = Field(pattern=r"^https://", max_length=600)
    keys: Keys


class Unsubscribe(BaseModel):
    endpoint: str = Field(max_length=600)


@router.get("/key")
async def key(_: Me) -> dict:
    """The public key the phone needs to subscribe. `live` is false while no keys are configured (alerts are only recorded)."""
    return {"key": get_settings().vapid_public_key or None, "live": live()}


@router.post("/subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def subscribe(body: Subscribe, user: Me, session: Session, request: Request) -> Response:
    """Save this phone. The same phone signing in as someone else moves to the new person (a shared device never alerts the old driver)."""
    existing = await session.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    agent = (request.headers.get("user-agent") or "")[:200]
    if existing:
        existing.user_id, existing.p256dh, existing.auth, existing.user_agent = user.id, body.keys.p256dh, body.keys.auth, agent
    else:
        session.add(PushSubscription(user_id=user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth, user_agent=agent))
    await session.flush()
    mine = (await session.scalars(select(PushSubscription.id).where(PushSubscription.user_id == user.id).order_by(PushSubscription.created_at.desc()))).all()
    if len(mine) > MAX_PER_PERSON:
        await session.execute(delete(PushSubscription).where(PushSubscription.id.in_(mine[MAX_PER_PERSON:])))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/unsubscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe(body: Unsubscribe, user: Me, session: Session) -> Response:
    await session.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint, PushSubscription.user_id == user.id))
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/status")
async def my_status(user: Me, session: Session) -> dict:
    n = await session.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id)) or 0
    return {"phones": n, "live": live()}


@router.post("/test")
async def test_alert(user: Me, session: Session) -> dict:
    """Send an alert to this person's own phones, to check that alerts really arrive."""
    lang = user.language if user.language in ("en", "hi", "mr") else "en"
    title = {"en": "CargoOne test alert", "hi": "CargoOne टेस्ट अलर्ट", "mr": "CargoOne टेस्ट अलर्ट"}[lang]
    body = {"en": "If you can read this, alerts work on this phone.", "hi": "अगर आप यह पढ़ पा रहे हैं, तो इस फ़ोन पर अलर्ट चालू हैं।",
            "mr": "तुम्हाला हे वाचता येत असेल, तर या फोनवर अलर्ट चालू आहेत."}[lang]
    sent = await push_user(session, user.id, title, body, "/driver/messages", wait=True)
    return {"sent": sent, "live": live()}
