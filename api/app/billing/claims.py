"""The client says "I have paid" and billing checks the bank. A claim never changes the invoice by itself: only a person at billing confirming it
records the payment (and then the invoice may become paid). Used by the client's login and by the client's private shipment page."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST
from app.models import Invoice, Payment, PaymentClaim

MAX_PENDING = 3  # a client waiting on billing does not need a fourth


class ClaimIn(BaseModel):
    amount: Decimal = Field(gt=0, le=100_000_000, decimal_places=2)
    paid_on: date
    reference: str = Field(min_length=3, max_length=80)  # UTR or cheque number
    note: str | None = Field(default=None, max_length=200)


async def paid_total(session: AsyncSession, invoice_id: uuid.UUID) -> Decimal:
    return await session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.invoice_id == invoice_id)) or Decimal(0)


async def create_claim(session: AsyncSession, inv: Invoice, body: ClaimIn, *, via: Literal["portal", "link"], user_id: uuid.UUID | None) -> PaymentClaim:
    if inv.sent_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice has not been sent yet")
    if inv.paid_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice is already paid in full")
    if body.paid_on > datetime.now(IST).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The payment date cannot be in the future")
    if body.paid_on < inv.created_at.astimezone(IST).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The payment date is before the invoice was made")
    balance = inv.total - await paid_total(session, inv.id)
    if body.amount > balance:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"That is more than the balance of Rs {balance:,.2f}")
    waiting = await session.scalar(select(func.count()).select_from(PaymentClaim).where(PaymentClaim.invoice_id == inv.id, PaymentClaim.status == "pending")) or 0
    if waiting >= MAX_PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Billing is still checking your earlier payments for this invoice")
    claim = PaymentClaim(invoice_id=inv.id, amount=body.amount, paid_on=body.paid_on, reference=body.reference.strip(), note=(body.note or "").strip() or None, via=via, claimed_by=user_id)
    session.add(claim)
    return claim


def claim_out(c: PaymentClaim) -> dict:
    return {"id": str(c.id), "amount": float(c.amount), "paid_on": c.paid_on.isoformat(), "reference": c.reference, "status": c.status,
            "reject_reason": c.reject_reason, "created_at": c.created_at}


async def client_invoice_view(session: AsyncSession, inv: Invoice) -> dict:
    """What a client sees about one of their invoices: what is due, what was received, and where their own payment claims stand."""
    paid = await paid_total(session, inv.id)
    claims = (await session.scalars(select(PaymentClaim).where(PaymentClaim.invoice_id == inv.id).order_by(PaymentClaim.created_at.desc()).limit(5))).all()
    pays = (await session.scalars(select(Payment).where(Payment.invoice_id == inv.id).order_by(Payment.paid_on, Payment.created_at))).all()
    return {"id": str(inv.id), "invoice_no": inv.invoice_no, "period_label": inv.period_label, "total": float(inv.total), "sent_at": inv.sent_at, "paid_at": inv.paid_at,
            "paid_amount": float(paid), "balance": float(inv.total - paid), "claims": [claim_out(c) for c in claims],
            "payments": [{"amount": float(p.amount), "paid_on": p.paid_on.isoformat(), "reference": p.reference} for p in pays]}
