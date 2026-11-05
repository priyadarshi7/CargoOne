"""Office tools for driver accounts: list them and reset a forgotten PIN.

A reset gives the office a one-time temporary PIN to read out over the phone. The driver's old sessions stop working,
the account is unlocked, and at next sign-in the driver must choose their own PIN (the temporary one is known to the
office, so it can never stay). The PIN is returned once and never stored in clear or written to logs/audit."""
import re
import secrets
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_policy import check_secret
from app.db import get_session
from app.models import AuditLog, Branch, Role, Trip, TripState, User, Vehicle, Vendor
from app.phones import clean_phone
from app.routers.setup import paper_state
from app.security import hash_secret, require_roles

router = APIRouter(prefix="/drivers", tags=["drivers"])
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Manager = Annotated[User, Depends(require_roles(Role.ops))]  # adding/removing people is the ops head's job (admin always allowed)
Session = Annotated[AsyncSession, Depends(get_session)]


class DriverOut(BaseModel):
    id: str
    name: str
    phone: str | None
    language: str
    branch: str | None
    vendor_id: str | None
    vendor: str | None
    is_active: bool
    locked: bool
    must_change_pin: bool
    employment_type: str | None
    licence_no: str | None
    licence_expiry: date | None
    licence: str | None  # ok | due_soon | expired
    assigned_vehicle_id: str | None
    assigned_vehicle: str | None


Employment = Literal["company", "contract", "hired"]


def clean_licence(text: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    if not 9 <= len(key) <= 20:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Driving licence number looks wrong. Example: MH20 20190012345")
    return key


class DriverIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str
    language: Literal["en", "hi", "mr"] = "hi"
    employment_type: Employment = "company"
    vendor_id: uuid.UUID | None = None  # required for a hired driver
    licence_no: str
    licence_expiry: date
    assigned_vehicle_id: uuid.UUID | None = None


class DriverPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    phone: str | None = None
    language: Literal["en", "hi", "mr"] | None = None
    employment_type: Employment | None = None
    vendor_id: uuid.UUID | None = None
    clear_vendor: bool = False
    licence_no: str | None = None
    licence_expiry: date | None = None
    assigned_vehicle_id: uuid.UUID | None = None
    clear_vehicle: bool = False
    is_active: bool | None = None


class CreatedOut(BaseModel):
    driver: DriverOut
    pin: str


class ResetOut(BaseModel):
    pin: str


def temporary_pin() -> str:
    while True:
        pin = f"{secrets.randbelow(10**6):06d}"
        if check_secret(pin, is_pin=True) is None:
            return pin


def _out(u: User, vendor: str | None, branch: str | None = None, vehicle: str | None = None) -> DriverOut:
    now = datetime.now(UTC)
    return DriverOut(id=str(u.id), name=u.name, phone=u.phone, language=u.language, branch=branch, vendor_id=str(u.vendor_id) if u.vendor_id else None,
                     vendor=vendor, is_active=u.is_active, locked=bool(u.locked_until and u.locked_until > now), must_change_pin=u.must_change_secret,
                     employment_type=u.employment_type, licence_no=u.licence_no, licence_expiry=u.licence_expiry, licence=paper_state(u.licence_expiry),
                     assigned_vehicle_id=str(u.assigned_vehicle_id) if u.assigned_vehicle_id else None, assigned_vehicle=vehicle)


async def _row(session: AsyncSession, u: User) -> DriverOut:
    vendor = await session.scalar(select(Vendor.name).where(Vendor.id == u.vendor_id)) if u.vendor_id else None
    vehicle = await session.scalar(select(Vehicle.reg_no).where(Vehicle.id == u.assigned_vehicle_id)) if u.assigned_vehicle_id else None
    return _out(u, vendor, vehicle=vehicle)


@router.get("", response_model=list[DriverOut])
async def list_drivers(_: Office, session: Session) -> list[DriverOut]:
    rows = (await session.execute(
        select(User, Branch.name, Vendor.name, Vehicle.reg_no).outerjoin(Branch, Branch.id == User.branch_id).outerjoin(Vendor, Vendor.id == User.vendor_id)
        .outerjoin(Vehicle, Vehicle.id == User.assigned_vehicle_id).where(User.role == Role.driver).order_by(User.is_active.desc(), User.name)
    )).all()
    return [_out(u, v, b, r) for u, b, v, r in rows]


async def _vendor_ok(session: AsyncSession, vendor_id: uuid.UUID | None) -> None:
    if vendor_id is not None and await session.get(Vendor, vendor_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown vendor")


async def _vehicle_ok(session: AsyncSession, vehicle_id: uuid.UUID | None) -> None:
    if vehicle_id is None:
        return
    v = await session.get(Vehicle, vehicle_id)
    if v is None or not v.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown or inactive truck")


def _employment_ok(employment: str, vendor_id: uuid.UUID | None) -> None:
    if employment == "hired" and vendor_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "A hired driver needs the vendor they come from")
    if employment != "hired" and vendor_id is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a hired driver belongs to a vendor")


async def _phone_free(session: AsyncSession, phone: str, *, except_id: uuid.UUID | None = None) -> None:
    other = await session.scalar(select(User.id).where(User.phone == phone))
    if other is not None and other != except_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "That phone number already belongs to another user")


@router.post("", response_model=CreatedOut, status_code=status.HTTP_201_CREATED)
async def create_driver(body: DriverIn, actor: Manager, session: Session) -> CreatedOut:
    """Register a driver by mobile number. They sign in with that number and a one-time PIN the office reads out, then choose their own."""
    phone = clean_phone(body.phone)
    await _phone_free(session, phone)
    await _vendor_ok(session, body.vendor_id)
    _employment_ok(body.employment_type, body.vendor_id)
    await _vehicle_ok(session, body.assigned_vehicle_id)
    if body.licence_expiry < date.today():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This driving licence has already expired")
    pin = temporary_pin()
    driver = User(name=body.name.strip(), phone=phone, role=Role.driver, language=body.language, vendor_id=body.vendor_id,
                  employment_type=body.employment_type, licence_no=clean_licence(body.licence_no), licence_expiry=body.licence_expiry,
                  assigned_vehicle_id=body.assigned_vehicle_id, password_hash=hash_secret(pin), must_change_secret=True)
    session.add(driver)
    await session.flush()
    session.add(AuditLog(actor_id=actor.id, action="driver.create", entity="user", entity_id=str(driver.id), meta={"hired": body.vendor_id is not None}))
    await session.commit()
    return CreatedOut(driver=await _row(session, driver), pin=pin)


@router.patch("/{driver_id}", response_model=DriverOut)
async def update_driver(driver_id: uuid.UUID, body: DriverPatch, actor: Manager, session: Session) -> DriverOut:
    driver = await session.get(User, driver_id)
    if driver is None or driver.role != Role.driver:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Driver not found")
    changed: list[str] = []
    if body.name is not None:
        driver.name = body.name.strip()
        changed.append("name")
    if body.phone is not None:
        phone = clean_phone(body.phone)
        if phone != driver.phone:
            await _phone_free(session, phone, except_id=driver.id)
            driver.phone = phone
            driver.token_version += 1  # the identity they sign in with changed: old sessions end
            changed.append("phone")
    if body.language is not None:
        driver.language = body.language
        changed.append("language")
    if body.clear_vendor:
        driver.vendor_id = None
        changed.append("vendor")
    elif body.vendor_id is not None:
        await _vendor_ok(session, body.vendor_id)
        driver.vendor_id = body.vendor_id
        changed.append("vendor")
    if body.employment_type is not None:
        driver.employment_type = body.employment_type
        changed.append("employment")
    if driver.employment_type:
        _employment_ok(driver.employment_type, driver.vendor_id)
    if body.licence_no is not None:
        driver.licence_no = clean_licence(body.licence_no)
        changed.append("licence")
    if body.licence_expiry is not None:
        driver.licence_expiry = body.licence_expiry
        changed.append("licence_expiry")
    if body.clear_vehicle:
        driver.assigned_vehicle_id = None
        changed.append("vehicle")
    elif body.assigned_vehicle_id is not None:
        await _vehicle_ok(session, body.assigned_vehicle_id)
        driver.assigned_vehicle_id = body.assigned_vehicle_id
        changed.append("vehicle")
    if body.is_active is not None and body.is_active != driver.is_active:
        if not body.is_active:
            busy = await session.scalar(select(Trip.trip_code).where(Trip.driver_id == driver.id, Trip.state.in_([TripState.planned, TripState.in_transit])).limit(1))
            if busy:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Still on trip {busy}. Reassign or finish it first.")
            driver.token_version += 1  # signs them out now
        driver.is_active = body.is_active
        changed.append("activated" if body.is_active else "deactivated")
    session.add(AuditLog(actor_id=actor.id, action="driver.update", entity="user", entity_id=str(driver.id), meta={"changed": changed}))
    await session.commit()
    return await _row(session, driver)


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
