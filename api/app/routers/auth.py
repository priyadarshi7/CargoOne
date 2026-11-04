from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import User
from app.security import create_token, current_user, verify_secret

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: Annotated[AsyncSession, Depends(get_session)]) -> TokenOut:
    ident = body.identifier.strip().lower()
    user = await session.scalar(
        select(User).where(or_(User.email == ident, User.phone == body.identifier.strip()))
    )
    # Same error for unknown user and wrong secret: do not reveal which accounts exist.
    if user is None or not verify_secret(body.secret, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    return TokenOut(access_token=create_token(user), user=_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: Annotated[User, Depends(current_user)]) -> UserOut:
    return _out(user)
