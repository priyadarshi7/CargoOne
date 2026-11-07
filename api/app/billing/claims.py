"""The client says "I have paid" and billing checks the bank. A claim never changes the invoice by itself: only a person at billing confirming it
records the payment (and then the invoice may become paid). Used by the client's login and by the client's private shipment page."""
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import razorpay
from app.models import Invoice, Payment


async def paid_total(session: AsyncSession, invoice_id: uuid.UUID) -> Decimal:
    return await session.scalar(select(func.coalesce(func.sum(Payment.amount), 0)).where(Payment.invoice_id == invoice_id)) or Decimal(0)


async def client_invoice_view(session: AsyncSession, inv: Invoice) -> dict:
    """What a client sees about one of their invoices: what is due and what was received."""
    paid = await paid_total(session, inv.id)
    pays = (await session.scalars(select(Payment).where(Payment.invoice_id == inv.id).order_by(Payment.paid_on, Payment.created_at))).all()
    return {"id": str(inv.id), "invoice_no": inv.invoice_no, "period_label": inv.period_label, "total": float(inv.total), "sent_at": inv.sent_at, "paid_at": inv.paid_at,
            "paid_amount": float(paid), "balance": float(inv.total - paid), "can_pay_online": razorpay.configured() and inv.paid_at is None and inv.total > paid,
            "payments": [{"amount": float(p.amount), "paid_on": p.paid_on.isoformat(), "reference": p.reference} for p in pays]}
