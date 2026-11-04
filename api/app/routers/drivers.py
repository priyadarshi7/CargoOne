"""Office tools for driver accounts: list them and reset a forgotten PIN.

A reset gives the office a one-time temporary PIN to read out over the phone. The driver's old sessions stop working,
the account is unlocked, and at next sign-in the driver must choose their own PIN (the temporary one is known to the
office, so it can never stay). The PIN is returned once and never stored in clear or written to logs/audit."""
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_policy import check_secret
from app.db import get_session
from app.models import AuditLog, Branch, Role, User
from app.security import hash_secret, require_roles

router = APIRouter(prefix="/drivers", tags=["drivers"])
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Session = Annotated[AsyncSession, Depends(get_session)]


class DriverOut(BaseModel):
    id: str
    name: str
    phone: str | None
    branch: str | None
    locked: bool
    must_change_pin: bool


class ResetOut(BaseModel):
    pin: str


def temporary_pin() -> str:
    while True:
        pin = f"{secrets.randbelow(10**6):06d}"
        if check_secret(pin, is_pin=True) is None:
            return pin


@router.get("", response_model=list[DriverOut])
async def list_drivers(_: Office, session: Session) -> list[DriverOut]:
    rows = (await session.execute(
        select(User, Branch.name).outerjoin(Branch, Branch.id == User.branch_id).where(User.role == Role.driver).order_by(User.name)
    )).all()
    now = datetime.now(UTC)
    return [DriverOut(id=str(u.id), name=u.name, phone=u.phone, branch=b, locked=bool(u.locked_until and u.locked_until > now),
                      must_change_pin=u.must_change_secret) for u, b in rows]


@router.post("/{driver_id}/reset-pin", response_model=ResetOut)
async def reset_pin(driver_id: uuid.UUID, actor: Office, session: Session) -> ResetOut:
    driver = await session.get(User, driver_id)
    if driver is None or driver.role != Role.driver:  # office users change their own password; nobody resets another office user here
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found")
    pin = temporary_pin()
    driver.password_hash = hash_secret(pin)
    driver.must_change_secret = True
    driver.token_version += 1  # signs the driver out everywhere
    driver.failed_logins, driver.locked_until = 0, None
    session.add(AuditLog(actor_id=actor.id, action="pin.reset", entity="user", entity_id=str(driver.id)))
    await session.commit()
    return ResetOut(pin=pin)
