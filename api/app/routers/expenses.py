"""Driver expenses (fuel, toll, repairs...), advances and settlement, trip profit and fuel-economy flags.

The driver enters an amount (and litres + odometer for fuel) and may attach a receipt photo. The office approves or
rejects each one; only approved expenses reduce a trip's margin. Fuel entries are checked against the truck's own
history the moment they arrive, so a suspicious fill reaches the reviewer already flagged."""
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.expenses import Fill, legs, usual_kmpl
from app.expenses import leg as make_leg
from app.models import (
    Advance,
    AuditLog,
    Client,
    Expense,
    ExpenseCategory,
    ExpenseStatus,
    Role,
    Trip,
    TripState,
    User,
    Vehicle,
)
from app.notify.service import expense_decided, safely
from app.pod.ingest import validate_image
from app.security import confine_to_link, current_user, link_trip_id, require_roles
from app.storage import Storage, get_storage

log = logging.getLogger("cargoone.expenses")
router = APIRouter(tags=["expenses"])
Session = Annotated[AsyncSession, Depends(get_session)]
Driver = Annotated[User, Depends(require_roles(Role.driver))]
Office = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Reader = Annotated[User, Depends(require_roles(Role.ops, Role.billing, Role.md))]
OFFICE = {Role.ops, Role.billing, Role.md, Role.admin}


class ExpenseOut(BaseModel):
    id: str
    category: str
    amount: float
    litres: float | None
    odometer_km: int | None
    note: str | None
    status: str
    flags: list[str]
    trip_code: str | None
    vehicle: str
    driver: str
    incurred_at: datetime
    has_receipt: bool
    review_note: str | None


def _out(e: Expense, trip_code: str | None, vehicle: str, driver: str) -> ExpenseOut:
    return ExpenseOut(id=str(e.id), category=e.category.value, amount=float(e.amount), litres=float(e.litres) if e.litres is not None else None,
                      odometer_km=e.odometer_km, note=e.note, status=e.status.value, flags=list(e.flags or []), trip_code=trip_code,
                      vehicle=vehicle, driver=driver, incurred_at=e.incurred_at, has_receipt=bool(e.receipt_key), review_note=e.review_note)


_Q = (select(Expense, Trip.trip_code, Vehicle.reg_no, User.name)
      .outerjoin(Trip, Trip.id == Expense.trip_id).join(Vehicle, Vehicle.id == Expense.vehicle_id).join(User, User.id == Expense.driver_id))


async def _fills(session: AsyncSession, vehicle_id: uuid.UUID) -> list[Fill]:
    rows = (await session.execute(
        select(Expense.incurred_at, Expense.odometer_km, Expense.litres)
        .where(Expense.vehicle_id == vehicle_id, Expense.category == ExpenseCategory.fuel, Expense.status != ExpenseStatus.rejected,
               Expense.odometer_km.is_not(None), Expense.litres.is_not(None))
    )).all()
    return [Fill(at, odo, float(lt)) for at, odo, lt in rows]


@router.post("/expenses", response_model=ExpenseOut)
async def add_expense(
    request: Request, user: Driver, session: Session, storage: Annotated[Storage, Depends(get_storage)],
    client_expense_id: Annotated[str, Form(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")],
    trip_id: Annotated[uuid.UUID, Form()],
    category: Annotated[ExpenseCategory, Form()],
    amount: Annotated[Decimal, Form(gt=0, le=500_000, decimal_places=2)],
    incurred_at: Annotated[datetime, Form()],
    litres: Annotated[Decimal | None, Form(gt=0, le=1000, decimal_places=2)] = None,
    odometer_km: Annotated[int | None, Form(ge=0, le=9_999_999)] = None,
    note: Annotated[str | None, Form(max_length=200)] = None,
    photo: UploadFile | None = None,
) -> ExpenseOut:
    confine_to_link(request, trip_id)
    existing = await session.scalar(select(Expense).where(Expense.client_expense_id == client_expense_id))
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.driver_id != user.id or trip.state == TripState.cancelled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Trip not found")
    vehicle = await session.get(Vehicle, trip.vehicle_id)
    if existing is not None and existing.driver_id != user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "That entry id is already used")
    if existing is not None:  # a retry of the same entry: return it, do not duplicate
        return _out(existing, trip.trip_code, vehicle.reg_no, user.name)
    if incurred_at > datetime.now(UTC) + timedelta(minutes=5):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The date is in the future")
    if category == ExpenseCategory.fuel and (litres is None or odometer_km is None):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Fuel needs the litres and the odometer reading")
    if category != ExpenseCategory.fuel:
        litres = odometer_km = None

    receipt_key = None
    exp_id = uuid.uuid4()
    if photo is not None and photo.filename != "":
        data = await photo.read(get_settings().max_image_bytes + 1)
        if len(data) > get_settings().max_image_bytes:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The photo is too large (300 KB at most)")
        _, ext = validate_image(data)
        receipt_key = f"expenses/{exp_id}.{ext}"
        await storage.put(receipt_key, data)

    flags: list[str] = []
    if category == ExpenseCategory.fuel:
        history = sorted(await _fills(session, trip.vehicle_id), key=lambda f: f.at)
        before = [f for f in history if f.at <= incurred_at]
        if before:
            flags = list(make_leg(before[-1], Fill(incurred_at, odometer_km, float(litres)), usual_kmpl(history)).flags)

    exp = Expense(id=exp_id, client_expense_id=client_expense_id, trip_id=trip.id, vehicle_id=trip.vehicle_id, driver_id=user.id, category=category,
                  amount=amount, litres=litres, odometer_km=odometer_km, note=(note or "").strip() or None, receipt_key=receipt_key,
                  flags=flags, incurred_at=incurred_at)
    session.add(exp)
    session.add(AuditLog(actor_id=user.id, action="expense.create", entity="expense", entity_id=str(exp_id), meta={"category": category.value, "flags": flags}))
    await session.commit()
    return _out(exp, trip.trip_code, vehicle.reg_no, user.name)


@router.get("/expenses/mine", response_model=list[ExpenseOut])
async def my_expenses(user: Driver, session: Session) -> list[ExpenseOut]:
    rows = (await session.execute(_Q.where(Expense.driver_id == user.id).order_by(Expense.created_at.desc()).limit(30))).all()
    return [_out(*r) for r in rows]


@router.get("/expenses", response_model=list[ExpenseOut])
async def list_expenses(
    _: Reader, session: Session,
    status_: Annotated[ExpenseStatus | None, Query(alias="status")] = ExpenseStatus.pending,
    trip_id: uuid.UUID | None = None,
) -> list[ExpenseOut]:
    q = _Q.order_by(Expense.created_at.desc()).limit(300)
    if status_:
        q = q.where(Expense.status == status_)
    if trip_id:
        q = q.where(Expense.trip_id == trip_id)
    return [_out(*r) for r in (await session.execute(q)).all()]


class Decision(BaseModel):
    action: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=200)


@router.post("/expenses/{expense_id}/decision", response_model=ExpenseOut)
async def decide(expense_id: uuid.UUID, body: Decision, user: Office, session: Session) -> ExpenseOut:
    exp = await session.get(Expense, expense_id)
    if exp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    if exp.status != ExpenseStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already {exp.status.value}")
    if body.action == "reject" and len((body.note or "").strip()) < 3:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Say why it is rejected, so the driver knows")
    exp.status = ExpenseStatus.approved if body.action == "approve" else ExpenseStatus.rejected
    exp.reviewed_by, exp.reviewed_at, exp.review_note = user.id, datetime.now(UTC), (body.note or "").strip() or None
    session.add(AuditLog(actor_id=user.id, action=f"expense.{body.action}", entity="expense", entity_id=str(exp.id)))
    await session.commit()
    await safely(session, expense_decided(session, exp.driver_id, exp.status == ExpenseStatus.approved,
                                          f"{exp.category.value} ₹{exp.amount:,.0f}", exp.review_note))
    row = (await session.execute(_Q.where(Expense.id == exp.id))).one()
    return _out(*row)


@router.get("/expenses/{expense_id}/receipt")
async def receipt(expense_id: uuid.UUID, user: Annotated[User, Depends(current_user)], session: Session, storage: Annotated[Storage, Depends(get_storage)]) -> Response:
    exp = await session.get(Expense, expense_id)
    allowed = exp is not None and (user.role in OFFICE or exp.driver_id == user.id)
    if not allowed or not exp.receipt_key:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    try:
        data = await storage.get(exp.receipt_key)
    except FileNotFoundError:
        log.error("expense receipt missing from storage: %s", exp.id)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image file is missing") from None
    media = {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[exp.receipt_key.rsplit(".", 1)[-1]]
    return Response(data, media_type=media, headers={"Cache-Control": "private, no-store"})


# ------------------------------------------------------------------ advances and settlement


class NewAdvance(BaseModel):
    driver_id: uuid.UUID
    amount: Decimal = Field(gt=0, le=500_000, decimal_places=2)
    note: str | None = Field(default=None, max_length=200)


@router.post("/finance/advances", status_code=status.HTTP_201_CREATED)
async def give_advance(body: NewAdvance, user: Office, session: Session) -> dict:
    driver = await session.get(User, body.driver_id)
    if driver is None or driver.role != Role.driver:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown driver")
    adv = Advance(driver_id=driver.id, amount=body.amount, note=(body.note or "").strip() or None, given_by=user.id)
    session.add(adv)
    session.add(AuditLog(actor_id=user.id, action="advance.create", entity="user", entity_id=str(driver.id), meta={"amount": float(body.amount)}))
    await session.commit()
    return {"id": str(adv.id)}


@router.get("/finance/mine")
async def my_money(request: Request, user: Driver, session: Session) -> dict:
    """What a driver can see of their own money: advances taken, expenses approved and waiting, and the balance (positive = cash still with
    the driver). A hired driver's private link is confined to one trip, so it shows none of this."""
    if link_trip_id(request) is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not available on a private link")
    advanced = await session.scalar(select(func.coalesce(func.sum(Advance.amount), 0)).where(Advance.driver_id == user.id))
    by_status = dict((await session.execute(select(Expense.status, func.sum(Expense.amount)).where(Expense.driver_id == user.id).group_by(Expense.status))).all())
    approved, waiting = by_status.get(ExpenseStatus.approved, Decimal(0)), by_status.get(ExpenseStatus.pending, Decimal(0))
    recent = (await session.scalars(select(Advance).where(Advance.driver_id == user.id).order_by(Advance.given_at.desc()).limit(5))).all()
    return {"advances": float(advanced), "approved": float(approved), "waiting": float(waiting), "balance": float(advanced - approved),
            "recent_advances": [{"amount": float(a.amount), "note": a.note, "given_at": a.given_at.isoformat()} for a in recent]}


@router.get("/finance/settlement")
async def settlement(_: Reader, session: Session) -> dict:
    """Per driver: cash advanced minus approved expenses. Positive = the driver still holds company cash."""
    adv = dict((await session.execute(select(Advance.driver_id, func.sum(Advance.amount)).group_by(Advance.driver_id))).all())
    spent: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: {"approved": Decimal(0), "pending": Decimal(0)})
    for d, st, total in (await session.execute(select(Expense.driver_id, Expense.status, func.sum(Expense.amount)).group_by(Expense.driver_id, Expense.status))).all():
        if st in (ExpenseStatus.approved, ExpenseStatus.pending):
            spent[d][st.value] = total
    ids = set(adv) | set(spent)
    names = dict((await session.execute(select(User.id, User.name).where(User.id.in_(ids)))).all()) if ids else {}
    rows = [{"driver_id": str(i), "driver": names.get(i, "?"), "advances": float(adv.get(i, 0)), "approved": float(spent[i]["approved"]) if i in spent else 0.0,
             "pending": float(spent[i]["pending"]) if i in spent else 0.0, "balance": float(adv.get(i, 0) - (spent[i]["approved"] if i in spent else 0))} for i in ids]
    recent = (await session.execute(
        select(Advance, User.name).join(User, User.id == Advance.driver_id).order_by(Advance.given_at.desc()).limit(20))).all()
    return {"drivers": sorted(rows, key=lambda r: r["driver"]),
            "recent_advances": [{"driver": n, "amount": float(a.amount), "note": a.note, "given_at": a.given_at.isoformat()} for a, n in recent]}


# ------------------------------------------------------------------ profit per trip and fuel economy


@router.get("/finance/pnl")
async def pnl(_: Reader, session: Session, days: Annotated[int, Query(ge=7, le=365)] = 90) -> dict:
    since = datetime.now(UTC) - timedelta(days=days)
    trips = (await session.execute(
        select(Trip, Client.name, Vehicle.reg_no).join(Client, Client.id == Trip.client_id).join(Vehicle, Vehicle.id == Trip.vehicle_id)
        .where(Trip.state != TripState.cancelled,
               or_(Trip.delivered_at >= since, Trip.first_pod_at >= since, (Trip.delivered_at.is_(None)) & (Trip.created_at >= since)))
        .order_by(Trip.created_at.desc()).limit(500)
    )).all()
    by_trip: dict[uuid.UUID, dict[str, Decimal]] = defaultdict(lambda: {"approved": Decimal(0), "pending": Decimal(0)})
    by_cat: dict[str, Decimal] = defaultdict(Decimal)
    for tid, st, cat, total in (await session.execute(
        select(Expense.trip_id, Expense.status, Expense.category, func.sum(Expense.amount)).where(Expense.trip_id.is_not(None)).group_by(Expense.trip_id, Expense.status, Expense.category)
    )).all():
        if st == ExpenseStatus.approved:
            by_trip[tid]["approved"] += total
            by_cat[cat.value] += total
        elif st == ExpenseStatus.pending:
            by_trip[tid]["pending"] += total
    rows = []
    for t, client, reg in trips:
        cost, pend = by_trip[t.id]["approved"], by_trip[t.id]["pending"]
        margin = t.freight_amount - cost
        rows.append({"trip_id": str(t.id), "trip_code": t.trip_code, "client": client, "vehicle": reg, "destination": t.destination, "state": t.state.value,
                     "freight": float(t.freight_amount), "expenses": float(cost), "pending": float(pend), "margin": float(margin),
                     "margin_pct": round(float(margin / t.freight_amount * 100), 1) if t.freight_amount else None})
    no_costs = sum(1 for r in rows if r["expenses"] == 0 and r["pending"] == 0)
    freight = sum(r["freight"] for r in rows)
    spent = sum(r["expenses"] for r in rows)

    vehicles = []
    for vid, reg in (await session.execute(select(Vehicle.id, Vehicle.reg_no).order_by(Vehicle.reg_no))).all():
        fills = await _fills(session, vid)
        if len(fills) < 2:
            continue
        ls = legs(fills)
        good = [lg.kmpl for lg in ls if lg.kmpl is not None and not lg.flags]
        flagged = [lg for lg in ls if lg.flags]
        vehicles.append({"vehicle": reg, "fills": len(fills), "km": sum(lg.km for lg in ls if lg.km > 0), "litres": round(sum(lg.litres for lg in ls), 1),
                         "avg_kmpl": round(sum(good) / len(good), 2) if good else None, "usual_kmpl": usual_kmpl(fills),
                         "flagged": len(flagged), "flags": sorted({f for lg in flagged for f in lg.flags})})
    return {"window_days": days, "trips_without_costs": no_costs, "totals": {"freight": freight, "expenses": spent, "margin": freight - spent,
                                            "margin_pct": round((freight - spent) / freight * 100, 1) if freight else None},
            "by_category": {k: float(v) for k, v in sorted(by_cat.items(), key=lambda kv: -kv[1])}, "trips": rows, "vehicles": vehicles}
