"""Development only: wipe the test data so the product can be tried again from day zero.

It exists only when APP_ENV is dev or test (in staging/production the endpoints answer 404, as if they were not there), needs the
ops head or admin, and a typed confirmation. It keeps the office logins and the branches (there is no screen to recreate branches) and
removes everything else: drivers, trucks, clients, vendors, trips, PODs, papers, requests, messages and their files."""
import shutil
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import AuditLog, Role, User
from app.security import require_roles

router = APIRouter(prefix="/devtools", tags=["devtools"])
Session = Annotated[AsyncSession, Depends(get_session)]
Actor = Annotated[User, Depends(require_roles(Role.ops))]

COUNTED = {"drivers": "users where role = 'driver'", "trucks": "vehicles", "vendors": "vendors", "clients": "clients", "trips": "trips", "pods": "pod_submissions",
           "papers": "documents", "requests": "transport_requests", "messages": "messages"}
WIPE = ("access_links, advances, audit_log, expenses, invoices, location_pings, pod_submissions, trips, vehicles, clients, vendors, documents, notifications, "
        "messages, onboarding_links, transport_requests, lr_counters")


def _dev_only() -> None:
    if not get_settings().is_dev:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")


class Confirm(BaseModel):
    confirm: str


@router.get("/test-data")
async def info(_: Actor, session: Session) -> dict:
    _dev_only()
    counts = {name: await session.scalar(text(f"select count(*) from {sql}")) for name, sql in COUNTED.items()}
    return {"enabled": True, "counts": counts}


@router.post("/reset-test-data")
async def reset(body: Confirm, actor: Actor, session: Session) -> dict:
    _dev_only()
    if body.confirm.strip() != "DELETE":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Type DELETE to confirm")
    # users reference trucks and vendors, so wiping those cascades to users: set the office accounts aside and put them back
    await session.execute(text("create temp table keep_users on commit drop as select * from users where role <> 'driver'"))
    await session.execute(text(f"truncate {WIPE} restart identity cascade"))
    await session.execute(text("insert into users select * from keep_users"))
    await session.execute(text("alter sequence request_ref_seq restart"))
    await session.execute(text("alter sequence trip_code_seq restart"))
    session.add(AuditLog(actor_id=actor.id, action="devtools.reset", entity="system", entity_id=None))
    await session.commit()
    root = Path(get_settings().storage_dir).resolve()
    if root.is_dir():
        for child in root.iterdir():
            shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink(missing_ok=True)
    return {"ok": True}
