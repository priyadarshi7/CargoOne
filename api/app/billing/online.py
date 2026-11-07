"""Paying an invoice online. The one rule: a Razorpay payment is applied to an invoice exactly once, however many times it is reported
(the pop-up's return, the webhook, a refresh, a double click). The order row is locked while it is settled and the Razorpay payment id is unique."""
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import razorpay
from app.billing.claims import paid_total
from app.billing.periods import IST
from app.config import get_settings
from app.models import AuditLog, Client, Invoice, OnlinePayment

REUSE_FOR = timedelta(hours=1)  # a client who opens the pop-up twice gets the same order, not a pile of them


class Returned(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


def _refuse_unless_payable(inv: Invoice) -> None:
    if not razorpay.configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Online payment is not set up")
    if inv.sent_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice has not been sent yet")
    if inv.paid_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This invoice is already paid in full")


async def start(session: AsyncSession, inv: Invoice, user_id: uuid.UUID | None) -> dict:
    """What the Razorpay pop-up needs, for the balance of the invoice."""
    _refuse_unless_payable(inv)
    balance = inv.total - await paid_total(session, inv.id)
    if balance <= 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing is left to pay on this invoice")
    row = await session.scalar(select(OnlinePayment).where(OnlinePayment.invoice_id == inv.id, OnlinePayment.status == "created", OnlinePayment.amount == balance,
                                                           OnlinePayment.created_at > datetime.now(UTC) - REUSE_FOR).order_by(OnlinePayment.created_at.desc()).limit(1))
    if row is None:
        try:
            order = await razorpay.create_order(balance, inv.invoice_no, {"invoice": inv.invoice_no, "invoice_id": str(inv.id)})
        except razorpay.RazorpayError as e:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Online payment is not available right now ({e})") from None
        row = OnlinePayment(invoice_id=inv.id, order_id=order["id"], amount=balance, created_by=user_id)
        session.add(row)
        await session.commit()
    client = await session.get(Client, inv.client_id)
    s = get_settings()
    return {"key_id": s.razorpay_key_id, "order_id": row.order_id, "amount": razorpay.paise(row.amount), "currency": "INR",
            "name": s.company_name, "description": f"Invoice {inv.invoice_no}", "prefill_name": (client.contact_name or client.name) if client else ""}


async def settle(session: AsyncSession, order_id: str, payment_id: str, *, via: str) -> OnlinePayment:
    """Apply a Razorpay payment to its invoice, once. Safe to call any number of times for the same payment."""
    from app.routers.billing import record_payment, tell_payment

    op = await session.scalar(select(OnlinePayment).where(OnlinePayment.order_id == order_id).with_for_update())
    if op is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown payment order")
    if op.status != "created":
        return op  # already applied (or already flagged): the repeat changes nothing
    try:
        rp = await razorpay.fetch_payment(payment_id)
        if rp.get("order_id") != op.order_id or rp.get("currency") != "INR" or int(rp.get("amount", -1)) != razorpay.paise(op.amount):
            raise HTTPException(status.HTTP_409_CONFLICT, "That payment does not match this order")
        if rp.get("status") == "authorized":
            rp = await razorpay.capture(payment_id, op.amount)
    except razorpay.RazorpayError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not confirm the payment with Razorpay ({e})") from None
    if rp.get("status") != "captured":
        raise HTTPException(status.HTTP_409_CONFLICT, "The payment has not gone through")

    inv = await session.get(Invoice, op.invoice_id, with_for_update=True)
    op.provider_payment_id, op.method, op.paid_at = payment_id, rp.get("method"), datetime.now(UTC)
    full, paid = False, Decimal(0)
    try:
        async with session.begin_nested():
            pay, full, paid = await record_payment(session, None, inv, op.amount, datetime.now(IST).date(), payment_id)
            await session.flush()
        op.status, op.payment_id = "paid", pay.id
    except HTTPException as e:  # money was taken but the invoice moved on meanwhile (billing recorded it, or it is settled): a person decides, usually a refund
        op.status, op.note = "review", str(e.detail)[:200]
    session.add(AuditLog(actor_id=None, action="invoice.online_payment" if op.status == "paid" else "invoice.online_payment_review", entity="invoice", entity_id=str(inv.id),
                         meta={"order": op.order_id, "payment": payment_id, "amount": str(op.amount), "via": via, "method": op.method}))
    await session.commit()
    if op.status == "paid":
        await tell_payment(session, inv, full, op.amount, paid)
    return op


async def finish(session: AsyncSession, inv: Invoice, body: Returned) -> None:
    """The pop-up came back with a payment: check its signature, make sure the order is this invoice's, and apply it."""
    if not razorpay.checkout_signature_ok(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The payment could not be verified")
    op = await session.scalar(select(OnlinePayment).where(OnlinePayment.order_id == body.razorpay_order_id))
    if op is None or op.invoice_id != inv.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payment order not found")
    await settle(session, body.razorpay_order_id, body.razorpay_payment_id, via="checkout")
