"""Razorpay tells us about payments here, whether or not the client's browser came back. Optional: it needs a public address and a webhook secret
(made up by us in Razorpay > Webhooks, then set as RAZORPAY_WEBHOOK_SECRET). Without it the pop-up's return still applies the payment."""
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing import online, razorpay
from app.db import get_session
from app.models import OnlinePayment, WebhookEvent

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/razorpay")
async def razorpay_webhook(request: Request, session: Session, x_razorpay_signature: Annotated[str, Header()] = "", x_razorpay_event_id: Annotated[str, Header()] = "") -> dict:
    body = await request.body()
    if not razorpay.webhook_signature_ok(body, x_razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Bad signature")
    event = json.loads(body)
    kind = str(event.get("event", ""))[:40]
    eid = x_razorpay_event_id[:80]
    if eid:
        first = (await session.execute(insert(WebhookEvent).values(event_id=eid, kind=kind).on_conflict_do_nothing())).rowcount
        await session.commit()
        if not first:
            return {"ok": True, "duplicate": True}
    if kind in ("payment.captured", "order.paid"):
        pay = (event.get("payload", {}).get("payment") or {}).get("entity") or {}
        order_id, payment_id = pay.get("order_id"), pay.get("id")
        if order_id and payment_id and await session.scalar(select(OnlinePayment.id).where(OnlinePayment.order_id == order_id)):
            try:
                await online.settle(session, order_id, payment_id, via="webhook")
            except HTTPException:
                if eid:  # forget the event so Razorpay's retry gets another go
                    await session.rollback()
                    await session.execute(delete(WebhookEvent).where(WebhookEvent.event_id == eid))
                    await session.commit()
                raise
    return {"ok": True}
