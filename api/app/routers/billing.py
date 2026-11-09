"""Billing queue, draft invoices and exports (Tally XML, CSV, PDF with PODs).
Creating an invoice only makes a DRAFT inside CargoOne. Nothing is ever sent to a client automatically."""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import tally_api
from app.billing.pdf import PdfTrip, build_invoice_pdf
from app.billing.periods import IST, financial_year, period_of
from app.billing.tally import build_csv, build_tally_xml
from app.config import get_settings
from app.db import get_session
from app.events import record
from app.models import (
    AuditLog,
    Client,
    Invoice,
    Payment,
    PodStatus,
    PodSubmission,
    Role,
    Trip,
    User,
    Vehicle,
)
from app.notify.service import safely, send_email
from app.notify.shipment import tell_parties
from app.security import require_roles
from app.shipment import shipment_url
from app.storage import Storage, get_storage

router = APIRouter(prefix="/billing", tags=["billing"])
Biller = Annotated[User, Depends(require_roles(Role.billing, Role.ops))]
Session = Annotated[AsyncSession, Depends(get_session)]


class QueueTrip(BaseModel):
    id: str
    trip_code: str
    lr_no: str
    eway_bill_no: str
    destination: str
    freight_amount: float
    delivered_at: datetime | None
    verified_at: datetime | None


class QueueGroup(BaseModel):
    client_id: str
    client: str
    billing_cycle: str
    period_key: str
    period_label: str
    total: float
    oldest_verified_at: datetime | None
    trips: list[QueueTrip]


class InvoiceOut(BaseModel):
    id: str
    invoice_no: str
    client: str
    period_label: str | None
    total: float
    trip_count: int
    created_at: datetime
    exported_at: datetime | None
    sent_at: datetime | None
    paid_at: datetime | None
    paid_amount: float
    balance: float
    client_has_email: bool = False  # there is an address to send the invoice to
    tally_pushed_at: datetime | None = None
    tally_voucher_no: str | None = None


class CreateInvoice(BaseModel):
    trip_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)


@router.get("/queue", response_model=list[QueueGroup])
async def queue(_: Biller, session: Session) -> list[QueueGroup]:
    """Verified, not-yet-invoiced trips grouped by client and billing-cycle period. Oldest waiting first."""
    rows = (await session.execute(
        select(Trip, Client).join(Client, Client.id == Trip.client_id)
        .where(Trip.pod_status == PodStatus.verified, Trip.invoice_id.is_(None))
        .order_by(Trip.verified_at)
    )).all()
    groups: dict[tuple[str, str], QueueGroup] = {}
    for trip, client in rows:
        key, label, _start = period_of(client.billing_cycle, trip.delivered_at or trip.verified_at or trip.created_at)
        g = groups.setdefault((str(client.id), key), QueueGroup(
            client_id=str(client.id), client=client.name, billing_cycle=client.billing_cycle, period_key=key,
            period_label=label, total=0.0, oldest_verified_at=trip.verified_at, trips=[]))
        g.trips.append(QueueTrip(
            id=str(trip.id), trip_code=trip.trip_code, lr_no=trip.lr_no, eway_bill_no=trip.eway_bill_no,
            destination=trip.destination, freight_amount=float(trip.freight_amount),
            delivered_at=trip.delivered_at, verified_at=trip.verified_at))
        g.total += float(trip.freight_amount)
    return sorted(groups.values(), key=lambda g: g.oldest_verified_at or datetime.max.replace(tzinfo=UTC))


@router.post("/invoices", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def create_invoice(body: CreateInvoice, user: Biller, session: Session) -> InvoiceOut:
    ids = list(dict.fromkeys(body.trip_ids))
    trips = (await session.scalars(select(Trip).where(Trip.id.in_(ids)).with_for_update())).all()
    if len(trips) != len(ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Some trips were not found")
    if len({t.client_id for t in trips}) != 1:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "An invoice covers one client only")
    bad = [t.trip_code for t in trips if t.pod_status != PodStatus.verified or t.invoice_id is not None]
    if bad:  # also what a second biller sees if someone already invoiced these
        raise HTTPException(status.HTTP_409_CONFLICT, f"Not billable (not verified or already invoiced): {', '.join(bad)}")

    client = await session.get(Client, trips[0].client_id)
    now = datetime.now(UTC)
    seq = await session.scalar(text("select nextval('invoice_no_seq')"))
    labels = {period_of(client.billing_cycle, t.delivered_at or t.verified_at or t.created_at)[1] for t in trips}
    total = sum((t.freight_amount for t in trips), Decimal(0))
    inv = Invoice(
        invoice_no=f"{get_settings().invoice_prefix}/{financial_year(now)}/{seq:05d}", client_id=client.id,
        total=total, period_label=labels.pop() if len(labels) == 1 else "Multiple periods")
    session.add(inv)
    await session.flush()
    for t in trips:
        t.invoice_id, t.invoiced_at, t.pod_status = inv.id, now, PodStatus.billed
    session.add(AuditLog(actor_id=user.id, action="invoice.create", entity="invoice", entity_id=str(inv.id),
                         meta={"invoice_no": inv.invoice_no, "trips": len(trips), "total": str(total)}))
    await session.commit()
    await session.refresh(inv)
    return _out(inv, client.name, len(trips))


def _out(inv: Invoice, client: str, n: int, paid: Decimal = Decimal(0), has_email: bool = False) -> InvoiceOut:
    return InvoiceOut(tally_pushed_at=inv.tally_pushed_at, tally_voucher_no=inv.tally_voucher_no, client_has_email=has_email, id=str(inv.id), invoice_no=inv.invoice_no, client=client, period_label=inv.period_label,
                      total=float(inv.total), trip_count=n, created_at=inv.created_at, exported_at=inv.exported_at,
                      sent_at=inv.sent_at, paid_at=inv.paid_at, paid_amount=float(paid), balance=float(inv.total - paid))


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(_: Biller, session: Session) -> list[InvoiceOut]:
    counts = select(Trip.invoice_id, func.count().label("n")).group_by(Trip.invoice_id).subquery()
    paid = select(Payment.invoice_id, func.sum(Payment.amount).label("paid")).group_by(Payment.invoice_id).subquery()
    rows = (await session.execute(
        select(Invoice, Client, func.coalesce(counts.c.n, 0), func.coalesce(paid.c.paid, 0))
        .join(Client, Client.id == Invoice.client_id).outerjoin(counts, counts.c.invoice_id == Invoice.id).outerjoin(paid, paid.c.invoice_id == Invoice.id)
        .order_by(Invoice.created_at.desc()).limit(200)
    )).all()
    has_login = set((await session.scalars(select(User.client_id).where(User.role == Role.client, User.is_active.is_(True), User.email.is_not(None)))).all())
    return [_out(i, c.name, n, p, bool(c.email) or c.id in has_login) for i, c, n, p in rows]


async def _load(session: AsyncSession, invoice_id: uuid.UUID):
    inv = await session.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    client = await session.get(Client, inv.client_id)
    trips = (await session.execute(
        select(Trip, Vehicle).join(Vehicle, Vehicle.id == Trip.vehicle_id)
        .where(Trip.invoice_id == inv.id).order_by(Trip.trip_code))).all()
    return inv, client, trips


async def _mark_exported(session: AsyncSession, user: User, inv: Invoice, kind: str) -> None:
    inv.exported_at = datetime.now(UTC)
    session.add(AuditLog(actor_id=user.id, action=f"invoice.export.{kind}", entity="invoice", entity_id=str(inv.id)))
    await session.commit()


def _download(content: str | bytes, media: str, filename: str) -> Response:
    safe = filename.replace("/", "-")
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{safe}"',
                                                        "Cache-Control": "private, no-store"})


@router.get("/invoices/{invoice_id}/tally")
async def export_tally(invoice_id: uuid.UUID, user: Biller, session: Session) -> Response:
    inv, client, trips = await _load(session, invoice_id)
    s = get_settings()
    xml = build_tally_xml(
        invoice_no=inv.invoice_no, created_at=inv.created_at, party_ledger=client.tally_ledger or client.name,
        sales_ledger=s.tally_sales_ledger, total=inv.total, lr_numbers=[t.lr_no for t, _ in trips], company=s.tally_company)
    await _mark_exported(session, user, inv, "tally")
    return _download(xml, "application/xml", f"{inv.invoice_no}-tally.xml")


@router.get("/tally/status")
async def tally_status(_: Biller) -> dict:
    return await tally_api.status()


class PushIn(BaseModel):
    create_missing: bool = False  # the person agreed to create the party / sales ledger in Tally
    voucher_date: date | None = None  # booked on this date instead of the invoice's own (Tally's period and, in Educational mode, allowed days are strict)


@router.post("/invoices/{invoice_id}/tally/push")
async def push_to_tally(invoice_id: uuid.UUID, user: Biller, session: Session, body: PushIn | None = None) -> dict:
    """A person pushes the invoice into Tally as one Sales voucher. Sent once: if Tally already has a voucher with this invoice number nothing is created again."""
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    _, client, trips = await _load(session, invoice_id)
    s = get_settings()
    try:
        done = await tally_api.push_invoice(invoice_no=inv.invoice_no, created_at=inv.created_at, party=client.tally_ledger or client.name, sales=s.tally_sales_ledger,
                                            total=inv.total, lr_numbers=[t.lr_no for t, _ in trips], create_missing=bool(body and body.create_missing), voucher_date=body.voucher_date if body else None)
    except tally_api.LedgersMissing as e:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "ledgers_missing", "missing": e.missing, "message": str(e)}) from None
    except tally_api.DateRejected as e:
        raise HTTPException(status.HTTP_409_CONFLICT, {"code": "voucher_date", "message": str(e), "period_start": e.period[0].isoformat(), "period_end": e.period[1].isoformat()}) from None
    except tally_api.TallyError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(e)) from None
    inv.tally_pushed_at = inv.tally_pushed_at or datetime.now(UTC)
    inv.tally_voucher_no = done["voucher_no"] or inv.tally_voucher_no
    session.add(AuditLog(actor_id=user.id, action="invoice.tally_push", entity="invoice", entity_id=str(inv.id),
                         meta={"company": done["company"], "voucher": done["voucher_no"], "voucher_date": body.voucher_date.isoformat() if body and body.voucher_date else None, "already": done["already"], "created_ledgers": done["created"]}))
    await session.commit()
    return {"voucher_no": done["voucher_no"], "already": done["already"], "created_ledgers": done["created"], "company": done["company"]}


@router.get("/invoices/{invoice_id}/csv")
async def export_csv(invoice_id: uuid.UUID, user: Biller, session: Session) -> Response:
    inv, _client, trips = await _load(session, invoice_id)
    rows = [{"invoice_no": inv.invoice_no, "trip_code": t.trip_code, "lr_no": t.lr_no, "eway_bill_no": t.eway_bill_no,
             "vehicle": v.reg_no, "origin": t.origin, "destination": t.destination,
             "delivered_on": t.delivered_at.astimezone(IST).date().isoformat() if t.delivered_at else "",
             "freight": f"{t.freight_amount:.2f}"} for t, v in trips]
    await _mark_exported(session, user, inv, "csv")
    return _download(build_csv(rows), "text/csv", f"{inv.invoice_no}.csv")


async def invoice_pdf_bytes(session: AsyncSession, storage: Storage, invoice_id: uuid.UUID) -> tuple[Invoice, bytes]:
    """The invoice PDF with each trip's POD photo attached: for billing, and for the client once it has been sent."""
    inv, client, trips = await _load(session, invoice_id)
    pdf_trips: list[PdfTrip] = []
    for t, v in trips:
        sub = await session.scalar(select(PodSubmission).where(PodSubmission.trip_id == t.id)
                                   .order_by(PodSubmission.attempt.desc()).limit(1))
        image = None
        if sub is not None:
            try:
                image = await storage.get(sub.storage_key)
            except FileNotFoundError:
                image = None  # the invoice still renders, with a visible "image unavailable" note
        pdf_trips.append(PdfTrip(
            trip_code=t.trip_code, lr_no=t.lr_no, eway_bill_no=t.eway_bill_no, route=f"{t.origin} to {t.destination}",
            vehicle=v.reg_no, delivered_on=t.delivered_at.astimezone(IST).strftime("%d %b %Y") if t.delivered_at else "-",
            freight=t.freight_amount, image=image))
    return inv, build_invoice_pdf(company=get_settings().company_name, invoice_no=inv.invoice_no, created_at=inv.created_at,
                                  client=client.name, period_label=inv.period_label, trips=pdf_trips)


@router.get("/invoices/{invoice_id}/pdf")
async def export_pdf(invoice_id: uuid.UUID, user: Biller, session: Session,
                     storage: Annotated[Storage, Depends(get_storage)]) -> Response:
    inv, pdf = await invoice_pdf_bytes(session, storage, invoice_id)
    session.add(AuditLog(actor_id=user.id, action="invoice.export.pdf", entity="invoice", entity_id=str(inv.id)))
    await session.commit()
    return _download(pdf, "application/pdf", f"{inv.invoice_no}.pdf")


# ---------------------------------------------------------------- sent, paid, closed


class PaymentIn(BaseModel):
    amount: Decimal = Field(gt=0, le=100_000_000, decimal_places=2)
    paid_on: date
    reference: str | None = Field(default=None, max_length=80)  # UTR or cheque number


class VoidIn(BaseModel):
    reason: str = Field(min_length=3, max_length=200)


async def _paid_total(session: AsyncSession, invoice_id: uuid.UUID) -> Decimal:
    return await session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.invoice_id == invoice_id)) or Decimal(0)


async def _invoice_trips(session: AsyncSession, invoice_id: uuid.UUID) -> list[Trip]:
    return list((await session.scalars(select(Trip).where(Trip.invoice_id == invoice_id).order_by(Trip.trip_code))).all())


@router.post("/invoices/{invoice_id}/sent", response_model=InvoiceOut)
async def mark_sent(invoice_id: uuid.UUID, user: Biller, session: Session) -> InvoiceOut:
    """A person confirms the invoice has gone to the client (the system never sends it by itself). The client's shipment page then shows it."""
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    client = await session.get(Client, inv.client_id)
    trips = await _invoice_trips(session, inv.id)
    if inv.sent_at is None:
        inv.sent_at, inv.sent_by = datetime.now(UTC), user.id
        for t in trips:
            record(session, t, "invoiced", actor=user.id, public=True, meta={"invoice": inv.invoice_no})
        session.add(AuditLog(actor_id=user.id, action="invoice.sent", entity="invoice", entity_id=str(inv.id), meta={"invoice_no": inv.invoice_no}))
        await session.commit()
        if trips:  # one note per invoice, however many trips it covers
            await safely(session, tell_parties(session, trips[0], "invoiced", invoice=inv.invoice_no, amount=f"{inv.total:,.0f}"))
    return _out(inv, client.name, len(trips), await _paid_total(session, inv.id))


@router.get("/invoices/{invoice_id}/payments")
async def list_payments(invoice_id: uuid.UUID, _: Biller, session: Session) -> list[dict]:
    rows = (await session.scalars(select(Payment).where(Payment.invoice_id == invoice_id).order_by(Payment.paid_on, Payment.created_at))).all()
    return [{"id": str(p.id), "amount": float(p.amount), "paid_on": p.paid_on.isoformat(), "reference": p.reference} for p in rows]


async def record_payment(session: AsyncSession, user: User | None, inv: Invoice, amount: Decimal, paid_on: date, reference: str | None) -> tuple[Payment, bool, Decimal]:
    """Money received. The checks, the payment, and (when the payments reach the total) the paid invoice and the closed trips: the one place this happens,
    whether billing types it in or confirms what the client said. Returns the payment, whether the invoice is now paid in full, and the amount paid so far."""
    if inv.sent_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Mark the invoice as sent before recording a payment")
    if inv.paid_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice is already paid in full")
    if paid_on > datetime.now(IST).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The payment date cannot be in the future")
    if paid_on < inv.created_at.astimezone(IST).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The payment date is before the invoice was made")
    paid = await _paid_total(session, inv.id)
    if paid + amount > inv.total:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"That is more than the balance of Rs {inv.total - paid:,.2f}")
    pay = Payment(invoice_id=inv.id, amount=amount, paid_on=paid_on, reference=(reference or "").strip() or None, recorded_by=user.id if user else None)
    session.add(pay)
    paid += amount
    trips = await _invoice_trips(session, inv.id)
    now = datetime.now(UTC)
    full = paid >= inv.total
    if full:
        inv.paid_at = now
        for t in trips:
            t.closed_at = now
            record(session, t, "paid", actor=user.id if user else None, public=True, meta={"invoice": inv.invoice_no})
            record(session, t, "closed", actor=user.id if user else None)
    session.add(AuditLog(actor_id=user.id if user else None, action="invoice.payment", entity="invoice", entity_id=str(inv.id),
                         meta={"amount": str(amount), "paid_on": paid_on.isoformat(), "reference": reference, "closed": full}))
    return pay, full, paid


async def tell_payment(session: AsyncSession, inv: Invoice, full: bool, amount: Decimal, paid: Decimal) -> None:
    trips = await _invoice_trips(session, inv.id)
    if not trips:
        return
    if full:
        await safely(session, tell_parties(session, trips[0], "paid", invoice=inv.invoice_no))
    else:
        await safely(session, tell_parties(session, trips[0], "payment_part", invoice=inv.invoice_no, amount=f"{amount:,.0f}", balance=f"{inv.total - paid:,.0f}"))


@router.post("/invoices/{invoice_id}/payments", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def add_payment(invoice_id: uuid.UUID, body: PaymentIn, user: Biller, session: Session) -> InvoiceOut:
    """Money received. When the payments add up to the total the invoice is paid and its trips are closed."""
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    _, full, paid = await record_payment(session, user, inv, body.amount, body.paid_on, body.reference)
    await session.commit()
    if full:
        await tell_payment(session, inv, True, body.amount, paid)
    client = await session.get(Client, inv.client_id)
    return _out(inv, client.name, len(await _invoice_trips(session, inv.id)), paid)


# ---------------------------------------------------------------- the invoice goes to the client; the client says it was paid


async def _client_emails(session: AsyncSession, client: Client) -> list[str]:
    """The billing address if there is one; otherwise the sign-in emails of the client's own people."""
    if client.email:
        return [client.email]
    return list((await session.scalars(select(User.email).where(User.role == Role.client, User.client_id == client.id, User.is_active.is_(True), User.email.is_not(None)).order_by(User.created_at))).all())


@router.post("/invoices/{invoice_id}/send", response_model=InvoiceOut)
async def send_invoice(invoice_id: uuid.UUID, user: Biller, session: Session) -> InvoiceOut:
    """A person sends the invoice to the client: an email with the private link where the invoice can be viewed and downloaded, and a WhatsApp note.
    Nothing is ever sent without this click. The invoice then counts as sent."""
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    client = await session.get(Client, inv.client_id)
    to = await _client_emails(session, client)
    if not to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "This client has no email address yet: add one under Setup, Clients")
    trips = await _invoice_trips(session, inv.id)
    if not trips:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice has no trips")
    lang = client.language if client.language in ("en", "hi", "mr") else "en"
    link = shipment_url(trips[0], "client")
    for addr in to:
        msg = await send_email(session, addr, lang, "invoice_sent", {"name": client.contact_name or client.name, "invoice": inv.invoice_no, "amount": f"{inv.total:,.0f}", "link": link},
                               secret=link.rsplit("/", 1)[1])
        msg.trip_id = trips[0].id
    first = inv.sent_at is None
    if first:
        inv.sent_at, inv.sent_by = datetime.now(UTC), user.id
        for t in trips:
            record(session, t, "invoiced", actor=user.id, public=True, meta={"invoice": inv.invoice_no})
    session.add(AuditLog(actor_id=user.id, action="invoice.sent", entity="invoice", entity_id=str(inv.id), meta={"invoice_no": inv.invoice_no, "emailed": len(to), "again": not first}))
    await session.commit()
    if first:
        await safely(session, tell_parties(session, trips[0], "invoiced", invoice=inv.invoice_no, amount=f"{inv.total:,.0f}"))
    return _out(inv, client.name, len(trips), await _paid_total(session, inv.id), has_email=True)


class CancelIn(BaseModel):
    reason: str = Field(min_length=3, max_length=300)


@router.post("/invoices/{invoice_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invoice(invoice_id: uuid.UUID, body: CancelIn, user: Annotated[User, Depends(require_roles(Role.admin, Role.ops))], session: Session) -> None:
    """Undo an invoice made by mistake, while nothing outside CargoOne knows about it: not sent, not in Tally, not paid.
    Its trips go back to the billing queue. The number is not reused (the gap is in the audit log, with the reason)."""
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invoice not found")
    if inv.sent_at is not None or inv.paid_at is not None or inv.tally_pushed_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice was already sent, paid or put in Tally, so it cannot be cancelled here")
    if await _paid_total(session, inv.id) > 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice has payments recorded")
    trips = await _invoice_trips(session, inv.id)
    for t in trips:
        t.invoice_id, t.invoiced_at, t.pod_status = None, None, PodStatus.verified
        record(session, t, "invoice_cancelled", actor=user.id, note=body.reason, meta={"invoice": inv.invoice_no})
    session.add(AuditLog(actor_id=user.id, action="invoice.cancel", entity="invoice", entity_id=str(inv.id),
                         meta={"invoice_no": inv.invoice_no, "trips": len(trips), "total": str(inv.total), "reason": body.reason.strip()}))
    await session.flush()
    await session.delete(inv)
    await session.commit()


@router.post("/invoices/{invoice_id}/payments/{payment_id}/void", response_model=InvoiceOut)
async def void_payment(invoice_id: uuid.UUID, payment_id: uuid.UUID, body: VoidIn, user: Annotated[User, Depends(require_roles(Role.admin))], session: Session) -> InvoiceOut:
    """Only an admin can undo a recorded payment, and must say why. A paid invoice goes back to unpaid and its trips are reopened."""
    inv = await session.get(Invoice, invoice_id, with_for_update=True)
    pay = await session.get(Payment, payment_id)
    if inv is None or pay is None or pay.invoice_id != inv.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    meta = {"amount": str(pay.amount), "paid_on": pay.paid_on.isoformat(), "reference": pay.reference, "reason": body.reason.strip()}
    await session.delete(pay)
    await session.flush()
    trips = await _invoice_trips(session, inv.id)
    if inv.paid_at is not None:
        inv.paid_at = None
        for t in trips:
            t.closed_at = None
            record(session, t, "reopened", actor=user.id, note=body.reason, meta={"invoice": inv.invoice_no})
    session.add(AuditLog(actor_id=user.id, action="invoice.payment_voided", entity="invoice", entity_id=str(inv.id), meta=meta))
    await session.commit()
    client = await session.get(Client, inv.client_id)
    return _out(inv, client.name, len(trips), await _paid_total(session, inv.id))
