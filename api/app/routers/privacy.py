"""Data-principal requests (DPDP Act 2023): a person asks what is held about them, or asks for it to be erased. Admin and MD only
(the privacy officer); every request is audited with the phone number masked."""
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import privacy
from app.db import get_session
from app.models import AuditLog, Role, User
from app.phones import clean_phone
from app.security import require_roles

router = APIRouter(prefix="/privacy", tags=["privacy"])
Officer = Annotated[User, Depends(require_roles(Role.admin, Role.md))]
Session = Annotated[AsyncSession, Depends(get_session)]


class Person(BaseModel):
    phone: str


@router.post("/access")
async def access(body: Person, user: Officer, session: Session) -> dict:
    phone = clean_phone(body.phone)
    session.add(AuditLog(actor_id=user.id, action="privacy.access", entity="person", meta={"phone": "******" + phone[-4:]}))
    found = await privacy.held_about(session, phone)
    await session.commit()
    return found


@router.post("/erase")
async def erase(body: Person, user: Officer, session: Session) -> dict:
    """Takes the person's name, phone and email off every trip and request. Photos and invoices stay until the retention date (tax records)."""
    return await privacy.erase_about(session, clean_phone(body.phone), user.id)
