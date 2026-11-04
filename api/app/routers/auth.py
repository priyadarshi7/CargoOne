import math
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_policy import check_secret
from app.config import get_settings
from app.db import get_session
from app.models import AuditLog, Role, User
from app.notify.sms import mask_phone
from app.ratelimit import RateLimiter
from app.security import create_token, current_user, hash_secret, verify_secret

router = APIRouter(prefix="/auth", tags=["auth"])

# Failed attempts only. Per source address, and per typed identifier (so unknown accounts behave exactly like known
# ones and the lock cannot be used to find out who has an account). Real accounts are also locked in the database,
# which survives restarts and works across several API processes.
ip_failures = RateLimiter(max_hits=30, window_s=900)
ident_failures = RateLimiter(max_hits=5, window_s=900)
_DUMMY_HASH = hash_secret("not-a-real-secret")  # verified against when the account does not exist: same response time


class LoginIn(BaseModel):
    identifier: str = Field(min_length=3, max_length=160, description="email (office) or phone (driver)")
    secret: str = Field(min_length=4, max_length=128, description="password (office) or PIN (driver)")


class UserOut(BaseModel):
    id: str
    name: str
    role: str
    language: str


class TokenOut(BaseModel):
    access_token: str
    user: UserOut


def _out(u: User) -> UserOut:
    return UserOut(id=str(u.id), name=u.name, role=u.role.value, language=u.language)


def _mask_ident(ident: str) -> str:
    """Audit entries never hold a full phone number or email."""
    return mask_phone(ident) if ident.isdigit() or ident.startswith("+") else (ident[:1] + "***" + ident[ident.find("@"):] if "@" in ident else ident[:1] + "***")


def _too_many(minutes: int) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many failed attempts. Try again in {max(1, minutes)} minutes.",
                         headers={"Retry-After": str(max(1, minutes) * 60)})


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, request: Request, session: Annotated[AsyncSession, Depends(get_session)]) -> TokenOut:
    s = get_settings()
    now = datetime.now(UTC)
    raw = body.identifier.strip()
    ident = raw.lower()
    ip = request.client.host if request.client else "unknown"
    if ip_failures.blocked(ip) or ident_failures.blocked(ident):
        raise _too_many(s.login_lock_minutes)
    user = await session.scalar(select(User).where(or_(User.email == ident, User.phone == raw)))
    if user and user.locked_until and user.locked_until > now:
        raise _too_many(math.ceil((user.locked_until - now).total_seconds() / 60))

    ok = verify_secret(body.secret, user.password_hash if user else _DUMMY_HASH) and user is not None
    if not ok:
        ip_failures.record(ip)
        ident_failures.record(ident)
        if user:
            user.failed_logins += 1
            if user.failed_logins >= s.login_max_failures:
                user.locked_until = now + timedelta(minutes=s.login_lock_minutes)
                user.failed_logins = 0
        session.add(AuditLog(actor_id=user.id if user else None, action="login.failed", entity="user",
                             entity_id=_mask_ident(ident), meta={"locked": bool(user and user.locked_until and user.locked_until > now)}))
        await session.commit()  # persist the count before answering
        # Same answer for unknown user and wrong secret: do not reveal which accounts exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    user.failed_logins, user.locked_until = 0, None
    session.add(AuditLog(actor_id=user.id, action="login.success", entity="user", entity_id=str(user.id)))
    await session.commit()
    return TokenOut(access_token=create_token(user), user=_out(user))


class ChangeSecret(BaseModel):
    current: str = Field(min_length=1, max_length=128)
    new: str = Field(min_length=1, max_length=128)


@router.post("/change-secret", response_model=TokenOut)
async def change_secret(body: ChangeSecret, user: Annotated[User, Depends(current_user)],
                        session: Annotated[AsyncSession, Depends(get_session)]) -> TokenOut:
    """Change your own password (office) or PIN (drivers). Every other signed-in session of yours is signed out."""
    if not verify_secret(body.current, user.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your current password or PIN is not correct")
    if body.new == body.current:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The new one must be different from the current one")
    problem = check_secret(body.new, is_pin=user.role == Role.driver, email=user.email)
    if problem:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, problem)
    user.password_hash = hash_secret(body.new)
    user.token_version += 1
    session.add(AuditLog(actor_id=user.id, action="secret.change", entity="user", entity_id=str(user.id)))
    await session.commit()
    return TokenOut(access_token=create_token(user), user=_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(current_user)]) -> UserOut:
    return _out(user)
