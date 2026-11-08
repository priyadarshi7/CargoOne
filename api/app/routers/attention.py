"""'Needs attention': the short list of things that are waiting on a person, in one place for ops, billing and the MD.

Each item has a count, the age of the oldest, and where to go to fix it. Reading is open to the office; the "remind drivers"
action sends one SMS per driver per trip per day (through the SMS adapter: a mock today) and records each send in the audit log."""
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db import get_session
from app.models import (
    AuditLog,
    Expense,
    ExpenseStatus,
    Invoice,
    Message,
    OnlinePayment,
    PodStatus,
    Role,
    TransportRequest,
    Trip,
    TripEvent,
    TripState,
    User,
    Vehicle,
)
from app.notify.sms import MockSms, Sms, get_sms, mask_phone, reminder_text, send_sms
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
QUOTE_FOLLOW_UP_DAYS = 2  # a quote nobody has answered for this long needs a call
PAYMENT_DUE_DAYS = 30  # sent to the client and still not paid
INVOICE_UNSENT_DAYS = 1  # made but nobody has marked it sent
NOT_STARTED_AFTER_MIN = 60
UNASSIGNED_WITHIN_HOURS = 48
UNACKNOWLEDGED_WITHIN_HOURS = 12
MESSAGES_FAILED_DAYS = 3


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

    req_n, req_oldest = (await session.execute(select(func.count(), func.min(TransportRequest.created_at)).where(TransportRequest.status == "new"))).one()

    # requests: a client's "no" nobody has read, a "yes" nobody has booked, a quote nobody has answered
    no_n, no_oldest = (await session.execute(select(func.count(), func.min(TransportRequest.decided_at)).where(
        TransportRequest.status == "declined", TransportRequest.declined_by == "client", TransportRequest.decline_seen_at.is_(None)))).one()
    book_n, book_oldest = (await session.execute(select(func.count(), func.min(func.coalesce(TransportRequest.quote_accepted_at, TransportRequest.decided_at))).where(
        TransportRequest.status == "accepted", or_(TransportRequest.quote_amount.is_(None), TransportRequest.quote_accepted_at.is_not(None))))).one()
    wait_n, wait_oldest = (await session.execute(select(func.count(), func.min(TransportRequest.quote_sent_at)).where(
        TransportRequest.status == "accepted", TransportRequest.quote_amount.is_not(None), TransportRequest.quote_accepted_at.is_(None),
        TransportRequest.quote_sent_at <= now - timedelta(days=QUOTE_FOLLOW_UP_DAYS)))).one()

    # trips that are not going to plan: nobody assigned, driver silent, late start, broken down, running late, short or damaged at the door
    live_planned = (Trip.state == TripState.planned,)
    unassigned_n, _ = (await session.execute(select(func.count(), func.min(Trip.planned_start)).where(
        *live_planned, Trip.driver_id.is_(None), Trip.planned_start <= now + timedelta(hours=UNASSIGNED_WITHIN_HOURS)))).one()
    silent_n, _ = (await session.execute(select(func.count(), func.min(Trip.planned_start)).where(
        *live_planned, Trip.driver_id.is_not(None), Trip.acknowledged_at.is_(None), Trip.planned_start <= now + timedelta(hours=UNACKNOWLEDGED_WITHIN_HOURS)))).one()
    nostart_n, nostart_oldest = (await session.execute(select(func.count(), func.min(Trip.planned_start)).where(
        *live_planned, Trip.driver_id.is_not(None), Trip.planned_start <= now - timedelta(minutes=NOT_STARTED_AFTER_MIN)))).one()
    resolved = aliased(TripEvent)
    broken = (select(TripEvent.id).where(TripEvent.trip_id == Trip.id, TripEvent.kind == "breakdown",
                                         ~exists().where(resolved.trip_id == Trip.id, resolved.kind == "resolved", resolved.at > TripEvent.at)))
    broke_n, broke_oldest = (await session.execute(select(func.count(), func.min(Trip.started_at)).where(Trip.state == TripState.in_transit, exists(broken)))).one()
    late_n, _ = (await session.execute(select(func.count(), func.min(Trip.late_alert_at)).where(
        Trip.state == TripState.in_transit, Trip.late_alert_at >= now - timedelta(hours=4)))).one()
    short_n, short_oldest = (await session.execute(select(func.count(), func.min(Trip.delivered_at)).where(
        Trip.delivery_issue.is_(True), Trip.invoice_id.is_(None), Trip.state != TripState.cancelled))).one()

    # money: an invoice nobody sent, and one sent long ago and still unpaid
    unsent_n, unsent_oldest = (await session.execute(select(func.count(), func.min(Invoice.created_at)).where(
        Invoice.sent_at.is_(None), Invoice.created_at <= now - timedelta(days=INVOICE_UNSENT_DAYS)))).one()
    overdue_n, overdue_oldest = (await session.execute(select(func.count(), func.min(Invoice.sent_at)).where(
        Invoice.sent_at.is_not(None), Invoice.paid_at.is_(None), Invoice.sent_at <= now - timedelta(days=PAYMENT_DUE_DAYS)))).one()

    review_pay_n, review_pay_oldest = (await session.execute(select(func.count(), func.min(OnlinePayment.paid_at)).where(OnlinePayment.status == "review"))).one()  # money taken online that no longer fits its invoice

    # a note to a client or driver that did not go out
    failed_n, _ = (await session.execute(select(func.count(), func.min(Message.created_at)).where(
        Message.status == "failed", Message.created_at >= now - timedelta(days=MESSAGES_FAILED_DAYS)))).one()

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
        {"key": "requests_new", "count": req_n, "oldest_days": _age_days(req_oldest, now), "to": "/office/requests", "severity": "high"},
        {"key": "quote_declined", "count": no_n, "oldest_days": _age_days(no_oldest, now), "to": "/office/requests", "severity": "high"},
        {"key": "ready_to_book", "count": book_n, "oldest_days": _age_days(book_oldest, now), "to": "/office/requests", "severity": "high"},
        {"key": "quote_waiting", "count": wait_n, "oldest_days": _age_days(wait_oldest, now), "to": "/office/requests", "severity": "medium"},
        {"key": "breakdown_open", "count": broke_n, "oldest_days": _age_days(broke_oldest, now), "to": "/office/trips", "severity": "high"},
        {"key": "late_running", "count": late_n, "oldest_days": None, "to": "/office/trips", "severity": "high"},
        {"key": "not_started", "count": nostart_n, "oldest_days": _age_days(nostart_oldest, now), "to": "/office/trips", "severity": "high"},
        {"key": "unassigned", "count": unassigned_n, "oldest_days": None, "to": "/office/planning", "severity": "high"},
        {"key": "not_acknowledged", "count": silent_n, "oldest_days": None, "to": "/office/trips", "severity": "medium"},
        {"key": "delivery_issue", "count": short_n, "oldest_days": _age_days(short_oldest, now), "to": "/office/trips", "severity": "medium"},
        {"key": "invoice_unsent", "count": unsent_n, "oldest_days": _age_days(unsent_oldest, now), "to": "/office/billing", "severity": "medium"},
        {"key": "online_review", "count": review_pay_n, "oldest_days": _age_days(review_pay_oldest, now), "to": "/office/billing", "severity": "high"},
        {"key": "payment_overdue", "count": overdue_n, "oldest_days": _age_days(overdue_oldest, now), "to": "/office/billing", "severity": "high"},
        {"key": "messages_failed", "count": failed_n, "oldest_days": None, "to": "/office/setup?tab=messages", "severity": "medium"},
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
    sent = skipped = no_phone = failed = 0
    for trip, driver in rows:
        if str(trip.id) in recent:
            skipped += 1
        elif not driver.phone:
            no_phone += 1
        else:
            if await send_sms(session, sms, driver.phone, reminder_text(driver.language, trip.destination), actor=actor.id):
                failed += 1  # not marked as reminded, so pressing the button again tries once more
                continue
            session.add(AuditLog(actor_id=actor.id, action="reminder.sent", entity="trip", entity_id=str(trip.id), meta={"to": mask_phone(driver.phone)}))
            sent += 1
    await session.commit()
    no_driver = (await session.scalar(select(func.count()).select_from(Trip).where(*_missing_clause(now), Trip.driver_id.is_(None)))) or 0
    return {"sent": sent, "failed": failed, "skipped_recent": skipped, "no_phone": no_phone, "no_driver": no_driver, "simulated": isinstance(sms, MockSms)}
