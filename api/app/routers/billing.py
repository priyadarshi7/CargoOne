"""Billing queue, draft invoices and exports (Tally XML, CSV, PDF with PODs).
Creating an invoice only makes a DRAFT inside CargoOne. Nothing is ever sent to a client automatically."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.pdf import PdfTrip, build_invoice_pdf
from app.billing.periods import IST, financial_year, period_of
from app.billing.tally import build_csv, build_tally_xml
from app.config import get_settings
from app.db import get_session
from app.models import AuditLog, Client, Invoice, PodStatus, PodSubmission, Role, Trip, User, Vehicle
from app.security import require_roles
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


def _out(inv: Invoice, client: str, n: int) -> InvoiceOut:
    return InvoiceOut(id=str(inv.id), invoice_no=inv.invoice_no, client=client, period_label=inv.period_label,
                      total=float(inv.total), trip_count=n, created_at=inv.created_at, exported_at=inv.exported_at)


@router.get("/invoices", response_model=list[InvoiceOut])
async def list_invoices(_: Biller, session: Session) -> list[InvoiceOut]:
    counts = select(Trip.invoice_id, func.count().label("n")).group_by(Trip.invoice_id).subquery()
    rows = (await session.execute(
        select(Invoice, Client.name, func.coalesce(counts.c.n, 0))
        .join(Client, Client.id == Invoice.client_id).outerjoin(counts, counts.c.invoice_id == Invoice.id)
        .order_by(Invoice.created_at.desc()).limit(200)
    )).all()
    return [_out(i, c, n) for i, c, n in rows]


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


@router.get("/invoices/{invoice_id}/csv")
async def export_csv(invoice_id: uuid.UUID, user: Biller, session: Session) -> Response:
    inv, _client, trips = await _load(session, invoice_id)
    rows = [{"invoice_no": inv.invoice_no, "trip_code": t.trip_code, "lr_no": t.lr_no, "eway_bill_no": t.eway_bill_no,
             "vehicle": v.reg_no, "origin": t.origin, "destination": t.destination,
             "delivered_on": t.delivered_at.astimezone(IST).date().isoformat() if t.delivered_at else "",
             "freight": f"{t.freight_amount:.2f}"} for t, v in trips]
    await _mark_exported(session, user, inv, "csv")
    return _download(build_csv(rows), "text/csv", f"{inv.invoice_no}.csv")


@router.get("/invoices/{invoice_id}/pdf")
async def export_pdf(invoice_id: uuid.UUID, user: Biller, session: Session,
                     storage: Annotated[Storage, Depends(get_storage)]) -> Response:
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
    pdf = build_invoice_pdf(company=get_settings().company_name, invoice_no=inv.invoice_no, created_at=inv.created_at,
                            client=client.name, period_label=inv.period_label, trips=pdf_trips)
    session.add(AuditLog(actor_id=user.id, action="invoice.export.pdf", entity="invoice", entity_id=str(inv.id)))
    await session.commit()
    return _download(pdf, "application/pdf", f"{inv.invoice_no}.pdf")
