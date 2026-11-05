"""The page a new driver opens from their WhatsApp message: choose a PIN once, and land signed in on the driver home screen.

The link is a one-time bearer secret (256-bit, only its SHA-256 is stored, 72 h, replaced when a new one is issued). It works only
while the account still has its temporary, office-known PIN, so once the driver has chosen their own PIN the link is dead. This
turns "the office reads a PIN over the phone" into "the driver sets a PIN nobody else ever sees"; the office-read PIN remains as
the fallback when WhatsApp does not arrive."""
import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_policy import check_secret
from app.db import get_session
from app.models import AuditLog, OnboardingLink, User
from app.ratelimit import RateLimiter
from app.routers.auth import TokenOut, _out
from app.security import create_token, hash_secret

router = APIRouter(prefix="/onboard", tags=["onboarding"])
Session = Annotated[AsyncSession, Depends(get_session)]
bad_token_limiter = RateLimiter(max_hits=30, window_s=60)  # per address: guessing links


class Info(BaseModel):
    name: str
    language: str
    expires_at: datetime


class SetPin(BaseModel):
    pin: str = Field(min_length=4, max_length=8)


async def _resolve(token: str, request: Request, session: AsyncSession) -> tuple[OnboardingLink, User]:
    link = await session.get(OnboardingLink, hashlib.sha256(token.encode()).hexdigest()) if 20 <= len(token) <= 128 else None
    if link is None:
        ip = request.client.host if request.client else "unknown"
        if bad_token_limiter.blocked(ip):  # only unknown tokens count: a real driver behind a shared mobile address stays able to use their own link
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
        bad_token_limiter.record(ip)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    user = await session.get(User, link.user_id)
    if link.used_at is not None or link.expires_at <= datetime.now(UTC) or user is None or not user.is_active or not user.must_change_secret:
        raise HTTPException(status.HTTP_410_GONE, "This link has already been used or has expired. Ask the office to send a new one.")
    return link, user


@router.get("/{token}", response_model=Info)
async def info(token: str, request: Request, session: Session) -> Info:
    link, user = await _resolve(token, request, session)
    return Info(name=user.name, language=user.language, expires_at=link.expires_at)  # no phone, no company data


@router.post("/{token}", response_model=TokenOut)
async def set_pin(token: str, body: SetPin, request: Request, session: Session) -> TokenOut:
    link, user = await _resolve(token, request, session)
    problem = check_secret(body.pin, is_pin=True)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    user.password_hash = hash_secret(body.pin)
    user.must_change_secret = False
    user.token_version += 1
    user.failed_logins, user.locked_until = 0, None
    link.used_at = datetime.now(UTC)
    session.add(AuditLog(actor_id=user.id, action="driver.onboarded", entity="user", entity_id=str(user.id)))
    await session.commit()
    return TokenOut(access_token=create_token(user), user=_out(user))
