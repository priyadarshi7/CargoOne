"""Password hashing, JWT issue/verify and role-based access dependencies.

Authorisation is enforced here in the API (there is no database row-level security),
so every protected endpoint must depend on `require_roles(...)`.
"""
import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import AccessLink, LinkKind, Role, Trip, User

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)
TOKEN_TTL = timedelta(hours=12)
PIN_FREE_PATHS = {"/auth/me", "/auth/change-secret"}  # all a person with a temporary PIN may do
LINK_REFUSED = {"/auth/change-secret"}  # a private link has no PIN to change


def link_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def link_trip_id(request: Request) -> uuid.UUID | None:
    """The one trip a request is confined to when it came in on a hired driver's private link; None for a normal sign-in."""
    return getattr(request.state, "link_trip_id", None)


def confine_to_link(request: Request, trip_id: uuid.UUID) -> None:
    """A private link may only touch its own trip, even when the same person has other trips."""
    only = link_trip_id(request)
    if only is not None and only != trip_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")


async def _link_user(request: Request, raw: str, session: AsyncSession) -> User:
    """A hired driver's private link signs them in as the trip's driver, for that trip only. The link is the secret: only its hash is stored."""
    from app.routers.links import bad_token_limiter  # the same guess throttle as the public upload endpoints

    bad = HTTPException(status.HTTP_401_UNAUTHORIZED, "This link is not valid or has expired. Ask the office for a new one.")
    link = await session.get(AccessLink, link_hash(raw)) if 20 <= len(raw) <= 128 else None
    if link is None or link.kind != LinkKind.sms_upload:
        ip = request.client.host if request.client else "unknown"
        if bad_token_limiter.blocked(ip):
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again later.")
        bad_token_limiter.record(ip)
        raise bad
    if link.revoked or link.expires_at <= datetime.now(UTC) or request.url.path in LINK_REFUSED:
        raise bad
    trip = await session.get(Trip, link.trip_id)
    user = await session.get(User, trip.driver_id) if trip is not None and trip.driver_id else None
    if user is None or not user.is_active or user.role != Role.driver:
        raise bad
    only = link.trip_id
    if (asked := request.path_params.get("trip_id")) is not None and str(asked) != str(only):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    request.state.link_trip_id = only
    return user


def hash_secret(secret: str) -> str:
    return _hasher.hash(secret)


def verify_secret(secret: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return _hasher.verify(hashed, secret)
    except VerifyMismatchError:
        return False


def create_token(user: User) -> str:
    now = datetime.now(UTC)
    payload = {"sub": str(user.id), "role": user.role.value, "ver": user.token_version, "iat": now, "exp": now + TOKEN_TTL}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


async def current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    unauthorised = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    header = request.headers.get("authorization", "")
    if header[:5].lower() == "link ":
        return await _link_user(request, header[5:].strip(), session)
    if creds is None:
        raise unauthorised
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
        user = await session.get(User, uuid.UUID(claims["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorised from None
    if user is None or not user.is_active:
        raise unauthorised  # unknown, or deactivated since the token was issued
    if claims.get("ver", 0) != user.token_version:
        raise unauthorised  # signed in before the password/PIN was changed
    if user.must_change_secret and request.url.path not in PIN_FREE_PATHS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Choose your own PIN first", headers={"X-Must-Change-Secret": "1"})
    return user


def require_roles(*roles: Role):
    """Dependency factory: 403 unless the caller has one of `roles` (admin always allowed)."""
    allowed = {*roles, Role.admin}

    async def guard(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return guard
