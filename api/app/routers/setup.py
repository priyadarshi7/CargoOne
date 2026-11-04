"""Setup of the things trips are made of: vehicles, clients, hired-truck vendors, and office staff.

Reading is open to ops and billing (they pick from these lists); changing them is the ops head's job, and office staff
accounts are admin-only. Nothing here is ever deleted: a truck, client or person that is no longer used is made
inactive, so old trips, invoices and the audit trail keep pointing at real records."""
import re
import secrets
import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth_policy import check_secret
from app.db import get_session
from app.models import AuditLog, Client, Role, Trip, TripState, User, Vehicle, Vendor
from app.phones import clean_phone
from app.security import hash_secret, require_roles

router = APIRouter(prefix="/setup", tags=["setup"])
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Manager = Annotated[User, Depends(require_roles(Role.ops))]
AdminOnly = Annotated[User, Depends(require_roles())]  # no extra roles: only admin passes
Session = Annotated[AsyncSession, Depends(get_session)]

LIVE = [TripState.planned, TripState.in_transit]
REG = re.compile(r"([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})")


def clean_reg(text: str) -> str:
    """MH20AB1234, mh 20 ab 1234 and MH-20-AB-1234 are the same truck. Stored as 'MH20 AB 1234'."""
    key = re.sub(r"[^A-Za-z0-9]", "", text).upper()
    m = REG.fullmatch(key)
    if not m:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Registration number looks wrong. Example: MH20 AB 1234")
    return f"{m[1]}{m[2]} {m[3]} {m[4]}"


async def _audit(session: AsyncSession, actor: User, action: str, entity: str, entity_id: object, **meta: object) -> None:
    session.add(AuditLog(actor_id=actor.id, action=action, entity=entity, entity_id=str(entity_id), meta=meta or None))


async def _commit(session: AsyncSession, what: str, *, flush: bool = False) -> None:
    try:
        await (session.flush() if flush else session.commit())
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"That {what} already exists") from None


# ---------------------------------------------------------------- vendors

class VendorIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = None
    notes: str | None = Field(default=None, max_length=300)


class VendorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    phone: str | None = None
    notes: str | None = Field(default=None, max_length=300)
    is_active: bool | None = None


async def _vendor_out(session: AsyncSession, v: Vendor) -> dict:
    trucks = await session.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.vendor_id == v.id, Vehicle.is_active)) or 0
    drivers = await session.scalar(select(func.count()).select_from(User).where(User.vendor_id == v.id, User.is_active)) or 0
    return {"id": str(v.id), "name": v.name, "contact_name": v.contact_name, "phone": v.phone, "notes": v.notes, "is_active": v.is_active,
            "trucks": trucks, "drivers": drivers}


@router.get("/vendors")
async def list_vendors(_: Office, session: Session) -> list[dict]:
    return [await _vendor_out(session, v) for v in (await session.scalars(select(Vendor).order_by(Vendor.is_active.desc(), Vendor.name))).all()]


@router.post("/vendors", status_code=status.HTTP_201_CREATED)
async def create_vendor(body: VendorIn, actor: Manager, session: Session) -> dict:
    v = Vendor(name=body.name.strip(), contact_name=body.contact_name or None, phone=clean_phone(body.phone) if body.phone else None, notes=body.notes or None)
    session.add(v)
    await _commit(session, "vendor", flush=True)
    await _audit(session, actor, "vendor.create", "vendor", v.id)
    await _commit(session, "vendor")
    return await _vendor_out(session, v)


@router.patch("/vendors/{vendor_id}")
async def update_vendor(vendor_id: uuid.UUID, body: VendorPatch, actor: Manager, session: Session) -> dict:
    v = await session.get(Vendor, vendor_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor not found")
    sent = body.model_fields_set
    if body.name is not None:
        v.name = body.name.strip()
    if "contact_name" in sent:
        v.contact_name = body.contact_name or None
    if "phone" in sent:
        v.phone = clean_phone(body.phone) if body.phone else None
    if "notes" in sent:
        v.notes = body.notes or None
    if body.is_active is not None:
        v.is_active = body.is_active
    await _audit(session, actor, "vendor.update", "vendor", v.id, fields=sorted(sent))
    await _commit(session, "vendor")
    return await _vendor_out(session, v)


# ---------------------------------------------------------------- vehicles

class VehicleIn(BaseModel):
    reg_no: str
    vehicle_type: str | None = Field(default=None, max_length=40)
    capacity_tonnes: Decimal | None = Field(default=None, gt=0, lt=100)
    insurance_expiry: date | None = None
    fitness_expiry: date | None = None
    permit_expiry: date | None = None
    vendor_id: uuid.UUID | None = None  # set = a hired truck from that vendor


class VehiclePatch(BaseModel):
    reg_no: str | None = None
    vehicle_type: str | None = Field(default=None, max_length=40)
    capacity_tonnes: Decimal | None = Field(default=None, gt=0, lt=100)
    insurance_expiry: date | None = None
    fitness_expiry: date | None = None
    permit_expiry: date | None = None
    vendor_id: uuid.UUID | None = None
    is_active: bool | None = None


DOCS = ("insurance_expiry", "fitness_expiry", "permit_expiry")


def _vehicle_out(v: Vehicle, vendor: str | None) -> dict:
    today = date.today()
    soonest = min((getattr(v, d) for d in DOCS if getattr(v, d)), default=None)
    return {
        "id": str(v.id), "reg_no": v.reg_no, "is_hired": v.is_hired, "vendor_id": str(v.vendor_id) if v.vendor_id else None, "vendor": vendor,
        "vehicle_type": v.vehicle_type, "capacity_tonnes": float(v.capacity_tonnes) if v.capacity_tonnes is not None else None,
        **{d: getattr(v, d).isoformat() if getattr(v, d) else None for d in DOCS}, "is_active": v.is_active,
        "papers": None if soonest is None else ("expired" if soonest < today else "due_soon" if (soonest - today).days <= 30 else "ok"),
    }


async def _vendor_check(session: AsyncSession, vendor_id: uuid.UUID | None) -> None:
    if vendor_id is not None and await session.get(Vendor, vendor_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown vendor")


async def _reg_free(session: AsyncSession, reg: str, *, except_id: uuid.UUID | None = None) -> None:
    key = reg.replace(" ", "")
    other = await session.scalar(select(Vehicle.id).where(func.replace(Vehicle.reg_no, " ", "") == key))
    if other is not None and other != except_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "A truck with that registration number already exists")


@router.get("/vehicles")
async def list_vehicles(_: Office, session: Session) -> list[dict]:
    rows = (await session.execute(select(Vehicle, Vendor.name).outerjoin(Vendor, Vendor.id == Vehicle.vendor_id)
                                  .order_by(Vehicle.is_active.desc(), Vehicle.reg_no))).all()
    return [_vehicle_out(v, n) for v, n in rows]


@router.post("/vehicles", status_code=status.HTTP_201_CREATED)
async def create_vehicle(body: VehicleIn, actor: Manager, session: Session) -> dict:
    reg = clean_reg(body.reg_no)
    await _reg_free(session, reg)
    await _vendor_check(session, body.vendor_id)
    v = Vehicle(reg_no=reg, is_hired=body.vendor_id is not None, vendor_id=body.vendor_id, vehicle_type=body.vehicle_type or None,
                capacity_tonnes=body.capacity_tonnes, insurance_expiry=body.insurance_expiry, fitness_expiry=body.fitness_expiry,
                permit_expiry=body.permit_expiry)
    session.add(v)
    await _commit(session, "truck", flush=True)
    await _audit(session, actor, "vehicle.create", "vehicle", v.id, hired=v.is_hired)
    await _commit(session, "truck")
    return _vehicle_out(v, await session.scalar(select(Vendor.name).where(Vendor.id == v.vendor_id)) if v.vendor_id else None)


@router.patch("/vehicles/{vehicle_id}")
async def update_vehicle(vehicle_id: uuid.UUID, body: VehiclePatch, actor: Manager, session: Session) -> dict:
    v = await session.get(Vehicle, vehicle_id)
    if v is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Truck not found")
    sent = body.model_fields_set
    if body.reg_no is not None:
        reg = clean_reg(body.reg_no)
        await _reg_free(session, reg, except_id=v.id)
        v.reg_no = reg
    for f in ("vehicle_type", "capacity_tonnes", *DOCS):
        if f in sent:
            setattr(v, f, getattr(body, f) or None)
    if "vendor_id" in sent:  # explicit null makes it an own truck again
        await _vendor_check(session, body.vendor_id)
        v.vendor_id, v.is_hired = body.vendor_id, body.vendor_id is not None
    if body.is_active is not None and body.is_active != v.is_active:
        if not body.is_active:
            busy = await session.scalar(select(Trip.trip_code).where(Trip.vehicle_id == v.id, Trip.state.in_(LIVE)).limit(1))
            if busy:
                raise HTTPException(status.HTTP_409_CONFLICT, f"Still on trip {busy}. Reassign or finish it first.")
        v.is_active = body.is_active
    await _audit(session, actor, "vehicle.update", "vehicle", v.id, fields=sorted(sent))
    await _commit(session, "truck")
    return _vehicle_out(v, await session.scalar(select(Vendor.name).where(Vendor.id == v.vendor_id)) if v.vendor_id else None)


# ---------------------------------------------------------------- clients

class ClientIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    segment: str | None = Field(default=None, max_length=60)
    billing_cycle: Literal["weekly", "fortnightly", "monthly", "per_trip"] = "weekly"
    tally_ledger: str | None = Field(default=None, max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = None


class ClientPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    segment: str | None = Field(default=None, max_length=60)
    billing_cycle: Literal["weekly", "fortnightly", "monthly", "per_trip"] | None = None
    tally_ledger: str | None = Field(default=None, max_length=160)
    contact_name: str | None = Field(default=None, max_length=120)
    contact_phone: str | None = None
    is_active: bool | None = None


def _client_out(c: Client, trips: int) -> dict:
    return {"id": str(c.id), "name": c.name, "segment": c.segment, "billing_cycle": c.billing_cycle, "tally_ledger": c.tally_ledger,
            "contact_name": c.contact_name, "contact_phone": c.contact_phone, "is_active": c.is_active, "trips": trips}


async def _trip_count(session: AsyncSession, client_id: uuid.UUID) -> int:
    return await session.scalar(select(func.count()).select_from(Trip).where(Trip.client_id == client_id)) or 0


@router.get("/clients")
async def list_clients(_: Office, session: Session) -> list[dict]:
    counts = dict((await session.execute(select(Trip.client_id, func.count()).group_by(Trip.client_id))).all())
    return [_client_out(c, counts.get(c.id, 0)) for c in (await session.scalars(select(Client).order_by(Client.is_active.desc(), Client.name))).all()]


@router.post("/clients", status_code=status.HTTP_201_CREATED)
async def create_client(body: ClientIn, actor: Manager, session: Session) -> dict:
    c = Client(name=body.name.strip(), segment=body.segment or None, billing_cycle=body.billing_cycle, tally_ledger=body.tally_ledger or None,
               contact_name=body.contact_name or None, contact_phone=clean_phone(body.contact_phone) if body.contact_phone else None)
    session.add(c)
    await _commit(session, "client", flush=True)
    await _audit(session, actor, "client.create", "client", c.id)
    await _commit(session, "client")
    return _client_out(c, 0)


@router.patch("/clients/{client_id}")
async def update_client(client_id: uuid.UUID, body: ClientPatch, actor: Manager, session: Session) -> dict:
    c = await session.get(Client, client_id)
    if c is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Client not found")
    sent = body.model_fields_set
    if body.name is not None:
        c.name = body.name.strip()
    if body.billing_cycle is not None:
        c.billing_cycle = body.billing_cycle
    for f in ("segment", "tally_ledger", "contact_name"):
        if f in sent:
            setattr(c, f, getattr(body, f) or None)
    if "contact_phone" in sent:
        c.contact_phone = clean_phone(body.contact_phone) if body.contact_phone else None
    if body.is_active is not None:
        c.is_active = body.is_active
    await _audit(session, actor, "client.update", "client", c.id, fields=sorted(sent))
    await _commit(session, "client")
    return _client_out(c, await _trip_count(session, c.id))


# ---------------------------------------------------------------- office staff (admin only)

STAFF_ROLES = (Role.ops, Role.billing, Role.md)


class StaffIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=160)
    role: Literal["ops", "billing", "md"]
    language: Literal["en", "hi", "mr"] = "en"


class StaffPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role: Literal["ops", "billing", "md"] | None = None
    language: Literal["en", "hi", "mr"] | None = None
    is_active: bool | None = None


def _staff_out(u: User) -> dict:
    return {"id": str(u.id), "name": u.name, "email": u.email, "role": u.role.value, "language": u.language, "is_active": u.is_active,
            "must_change_password": u.must_change_secret}


def temporary_password() -> str:
    while True:
        pw = secrets.token_urlsafe(9)
        if check_secret(pw, is_pin=False) is None:
            return pw


@router.get("/staff")
async def list_staff(_: AdminOnly, session: Session) -> list[dict]:
    return [_staff_out(u) for u in (await session.scalars(select(User).where(User.role.in_([*STAFF_ROLES, Role.admin])).order_by(User.is_active.desc(), User.name))).all()]


@router.post("/staff", status_code=status.HTTP_201_CREATED)
async def create_staff(body: StaffIn, actor: AdminOnly, session: Session) -> dict:
    email = body.email.strip().lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "That email already has an account")
    pw = temporary_password()
    u = User(name=body.name.strip(), email=email, role=Role(body.role), language=body.language, password_hash=hash_secret(pw), must_change_secret=True)
    session.add(u)
    await session.flush()
    await _audit(session, actor, "staff.create", "user", u.id, role=body.role)
    await session.commit()
    return {"staff": _staff_out(u), "password": pw}  # shown once; the person must replace it at first sign-in


@router.patch("/staff/{user_id}")
async def update_staff(user_id: uuid.UUID, body: StaffPatch, actor: AdminOnly, session: Session) -> dict:
    u = await session.get(User, user_id)
    if u is None or u.role not in (*STAFF_ROLES, Role.admin):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
    if u.id == actor.id and (body.is_active is False or (body.role and body.role != u.role.value)):
        raise HTTPException(status.HTTP_409_CONFLICT, "You cannot deactivate yourself or change your own role")
    if u.role == Role.admin and (body.is_active is False or body.role):
        raise HTTPException(status.HTTP_409_CONFLICT, "Admin accounts are changed in the database, not here")
    if body.name is not None:
        u.name = body.name.strip()
    if body.language is not None:
        u.language = body.language
    if body.role is not None and body.role != u.role.value:
        u.role = Role(body.role)
        u.token_version += 1  # a new role means a new sign-in
    if body.is_active is not None and body.is_active != u.is_active:
        u.is_active = body.is_active
        u.token_version += 1
    await _audit(session, actor, "staff.update", "user", u.id, fields=sorted(body.model_fields_set))
    await session.commit()
    return _staff_out(u)


@router.post("/staff/{user_id}/reset-password")
async def reset_staff_password(user_id: uuid.UUID, actor: AdminOnly, session: Session) -> dict:
    u = await session.get(User, user_id)
    if u is None or u.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
    pw = temporary_password()
    u.password_hash, u.must_change_secret = hash_secret(pw), True
    u.token_version += 1
    u.failed_logins, u.locked_until = 0, None
    await _audit(session, actor, "staff.reset_password", "user", u.id)
    await session.commit()
    return {"password": pw}
