"""'Needs attention': the short list of things that are waiting on a person, in one place for ops, billing and the MD.

Each item has a count, the age of the oldest, and where to go to fix it. Reading is open to the office; the "remind drivers"
action sends one SMS per driver per trip per day (through the SMS adapter: a mock today) and records each send in the audit log."""
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AuditLog, Expense, ExpenseStatus, PodStatus, Role, Trip, TripState, User, Vehicle
from app.notify.sms import MockSms, Sms, get_sms, mask_phone, reminder_text
from app.security import require_roles

router = APIRouter(prefix="/attention", tags=["attention"])
Viewer = Annotated[User, Depends(require_roles(Role.ops, Role.billing, Role.md))]
Sender = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Session = Annotated[AsyncSession, Depends(get_session)]

MISSING = (PodStatus.pending, PodStatus.retake_requested)
REVIEW_AFTER_HOURS = 4  # a read waiting for a human longer than this is overdue
UNBILLED_AFTER_DAYS = 3  # verified, but no invoice yet
EXPENSE_AFTER_DAYS = 2
PAPERS_WITHIN_DAYS = 30
REMIND_EVERY = timedelta(hours=24)


def _age_days(then: datetime | None, now: datetime) -> int | None:
    return None if then is None else max(0, (now - then).days)


def _missing_clause(now: datetime):
    return (Trip.pod_status.in_(MISSING), Trip.state != TripState.cancelled, Trip.delivered_at.is_not(None), Trip.delivered_at <= now - timedelta(days=1))


@router.get("")
async def attention(_: Viewer, session: Session) -> dict:
    now = datetime.now(UTC)
    today = date.today()

    miss_n, miss_oldest = (await session.execute(select(func.count(), func.min(Trip.delivered_at)).where(*_missing_clause(now)))).one()
    review_n, review_oldest = (await session.execute(
        select(func.count(), func.min(Trip.pod_uploaded_at)).where(Trip.pod_status == PodStatus.needs_review, Trip.pod_uploaded_at <= now - timedelta(hours=REVIEW_AFTER_HOURS))
    )).one()
    bill_n, bill_oldest = (await session.execute(
        select(func.count(), func.min(Trip.verified_at)).where(Trip.pod_status == PodStatus.verified, Trip.invoice_id.is_(None), Trip.verified_at <= now - timedelta(days=UNBILLED_AFTER_DAYS))
    )).one()
    exp_n, exp_oldest = (await session.execute(
        select(func.count(), func.min(Expense.created_at)).where(Expense.status == ExpenseStatus.pending, Expense.created_at <= now - timedelta(days=EXPENSE_AFTER_DAYS))
    )).one()

    soon = today + timedelta(days=PAPERS_WITHIN_DAYS)
    papers = []
    for v in (await session.scalars(select(Vehicle).where(Vehicle.is_active))).all():
        due = [(label, d) for label, d in (("insurance", v.insurance_expiry), ("fitness", v.fitness_expiry), ("permit", v.permit_expiry), ("PUC", v.puc_expiry)) if d and d <= soon]
        if due:
            label, d = min(due, key=lambda x: x[1])
            papers.append({"reg_no": v.reg_no, "document": label, "date": d.isoformat(), "expired": d < today, "days": (d - today).days})
    papers.sort(key=lambda p: p["days"])
    licences = sorted(
        ({"name": u.name, "date": u.licence_expiry.isoformat(), "expired": u.licence_expiry < today, "days": (u.licence_expiry - today).days}
         for u in (await session.scalars(select(User).where(User.role == Role.driver, User.is_active, User.licence_expiry.is_not(None), User.licence_expiry <= soon))).all()),
        key=lambda p: p["days"])

    items = [
        {"key": "missing_pod", "count": miss_n, "oldest_days": _age_days(miss_oldest, now), "to": "/office", "severity": "high"},
        {"key": "review_waiting", "count": review_n, "oldest_days": _age_days(review_oldest, now), "to": "/office/review", "severity": "high"},
        {"key": "unbilled", "count": bill_n, "oldest_days": _age_days(bill_oldest, now), "to": "/office/billing", "severity": "medium"},
        {"key": "expenses_pending", "count": exp_n, "oldest_days": _age_days(exp_oldest, now), "to": "/office/expenses", "severity": "low"},
        {"key": "papers", "count": len(papers), "oldest_days": None, "to": "/office/setup?tab=trucks", "severity": "medium", "detail": papers[:5]},
        {"key": "licences", "count": len(licences), "oldest_days": None, "to": "/office/setup?tab=drivers", "severity": "medium", "detail": licences[:5]},
    ]
    return {"items": [i for i in items if i["count"]], "total": sum(i["count"] for i in items), "as_of": now.isoformat()}


@router.post("/remind-drivers")
async def remind_drivers(actor: Sender, session: Session, sms: Annotated[Sms, Depends(get_sms)]) -> dict:
    """Text each driver who still owes a POD for a delivered trip. At most once per trip per 24 h, so pressing it twice is harmless."""
    now = datetime.now(UTC)
    rows = (await session.execute(
        select(Trip, User).join(User, User.id == Trip.driver_id).where(*_missing_clause(now), User.is_active).order_by(Trip.delivered_at).limit(500)
    )).all()
    recent = set((await session.scalars(
        select(AuditLog.entity_id).where(AuditLog.action == "reminder.sent", AuditLog.at >= now - REMIND_EVERY)
    )).all())
    sent = skipped = no_phone = 0
    for trip, driver in rows:
        if str(trip.id) in recent:
            skipped += 1
        elif not driver.phone:
            no_phone += 1
        else:
            sms.send(driver.phone, reminder_text(driver.language, trip.destination))
            session.add(AuditLog(actor_id=actor.id, action="reminder.sent", entity="trip", entity_id=str(trip.id), meta={"to": mask_phone(driver.phone)}))
            sent += 1
    await session.commit()
    no_driver = (await session.scalar(select(func.count()).select_from(Trip).where(*_missing_clause(now), Trip.driver_id.is_(None)))) or 0
    return {"sent": sent, "skipped_recent": skipped, "no_phone": no_phone, "no_driver": no_driver, "simulated": isinstance(sms, MockSms)}
