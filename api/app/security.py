"""Password hashing, JWT issue/verify and role-based access dependencies.

Authorisation is enforced here in the API (there is no database row-level security),
so every protected endpoint must depend on `require_roles(...)`.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import Role, User

_hasher = PasswordHasher()
_bearer = HTTPBearer(auto_error=False)
TOKEN_TTL = timedelta(hours=12)


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
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    unauthorised = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    if creds is None:
        raise unauthorised
    try:
        claims = jwt.decode(creds.credentials, get_settings().jwt_secret, algorithms=["HS256"])
        user = await session.get(User, uuid.UUID(claims["sub"]))
    except (jwt.PyJWTError, ValueError, KeyError):
        raise unauthorised from None
    if user is None:
        raise unauthorised
    if claims.get("ver", 0) != user.token_version:
        raise unauthorised  # signed in before the password/PIN was changed
    return user


def require_roles(*roles: Role):
    """Dependency factory: 403 unless the caller has one of `roles` (admin always allowed)."""
    allowed = {*roles, Role.admin}

    async def guard(user: Annotated[User, Depends(current_user)]) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return guard
