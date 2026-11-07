"""Paying an invoice through Razorpay. Razorpay itself is faked (a transport that answers like its API); what is checked is our side:
a payment is applied once however many times it is reported, and nothing the browser says is believed without Razorpay's own word."""
import hashlib
import hmac
import json
import uuid
from decimal import Decimal

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.billing import razorpay
from app.config import get_settings
from app.db import SessionLocal
from app.models import OnlinePayment, Payment
from tests.test_attention import item
from tests.test_invoice_lifecycle import invoiced, today
from tests.test_invoice_to_client import client_of, give_email, login_for
from tests.test_pin_reset import office
from tests.test_shipments import tokens

KEY, SECRET, HOOK = "rzp_test_abc123", "secret_for_tests_only", "hook_secret_for_tests"


class FakeRazorpay:
    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.payments: dict[str, dict] = {}
        self.calls: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        self.calls.append(f"{req.method} {req.url.path}")
        assert req.headers["authorization"].startswith("Basic ")
        path = req.url.path.removeprefix("/v1")
        if req.method == "POST" and path == "/orders":
            body = json.loads(req.content)
            oid = f"order_{uuid.uuid4().hex[:14]}"
            self.orders[oid] = {"id": oid, **body}
            return httpx.Response(200, json=self.orders[oid])
        if req.method == "GET" and path.startswith("/payments/"):
            p = self.payments.get(path.rsplit("/", 1)[1])
            return httpx.Response(200, json=p) if p else httpx.Response(400, json={"error": "no such payment"})
        if req.method == "POST" and path.endswith("/capture"):
            p = self.payments[path.split("/")[2]]
            p["status"] = "captured"
            return httpx.Response(200, json=p)
        return httpx.Response(404)

    def pay(self, order_id: str, *, status: str = "captured", amount: int | None = None) -> str:
        pid = f"pay_{uuid.uuid4().hex[:14]}"
        self.payments[pid] = {"id": pid, "order_id": order_id, "amount": amount if amount is not None else self.orders[order_id]["amount"], "currency": "INR", "status": status, "method": "upi"}
        return pid


@pytest.fixture
def rzp(monkeypatch: pytest.MonkeyPatch) -> FakeRazorpay:
    s = get_settings()
    monkeypatch.setattr(s, "razorpay_key_id", KEY)
    monkeypatch.setattr(s, "razorpay_key_secret", SECRET)
    monkeypatch.setattr(s, "razorpay_webhook_secret", HOOK)
    fake = FakeRazorpay()
    monkeypatch.setattr(razorpay, "TRANSPORT", httpx.MockTransport(fake))
    return fake


def signed(order_id: str, payment_id: str, secret: str = SECRET) -> dict:
    return {"razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": hmac.new(secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()}


async def sent_invoice(client: AsyncClient, driver: dict) -> tuple[dict, dict, dict, dict]:
    h, tid, inv = await invoiced(client, driver)
    ops = await office(client)
    cid = await client_of(inv["id"])
    await give_email(client, ops, cid)
    assert (await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)).status_code == 200
    return h, await login_for(client, ops, cid), inv, await tokens(client, ops, tid)


async def payments_on(invoice_id: str) -> list[Payment]:
    async with SessionLocal() as s:
        return list((await s.scalars(select(Payment).where(Payment.invoice_id == uuid.UUID(invoice_id)))).all())


def event(kind: str, order_id: str, payment_id: str) -> bytes:
    return json.dumps({"event": kind, "payload": {"payment": {"entity": {"id": payment_id, "order_id": order_id}}}}).encode()


def hook_headers(body: bytes, event_id: str, secret: str = HOOK) -> dict:
    return {"X-Razorpay-Signature": hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), "X-Razorpay-Event-Id": event_id, "Content-Type": "application/json"}


async def test_the_client_pays_online_and_the_same_payment_reported_again_is_never_counted_twice(client: AsyncClient, driver: dict, rzp: FakeRazorpay) -> None:
    h, mine, inv, _ = await sent_invoice(client, driver)
    view = next(i for i in (await client.get("/portal/invoices", headers=mine)).json() if i["id"] == inv["id"])
    assert view["can_pay_online"] is True

    start = await client.post(f"/portal/invoices/{inv['id']}/pay", headers=mine)
    assert start.status_code == 200
    order = start.json()
    assert order["key_id"] == KEY and order["amount"] == 100000 and order["currency"] == "INR"  # the balance, in paise, fixed by the server
    again = await client.post(f"/portal/invoices/{inv['id']}/pay", headers=mine)
    assert again.json()["order_id"] == order["order_id"] and rzp.calls.count("POST /v1/orders") == 1  # opening the pop-up twice does not pile up orders

    pid = rzp.pay(order["order_id"])
    confirm = f"/portal/invoices/{inv['id']}/pay/confirm"
    assert (await client.post(confirm, headers=mine, json={**signed(order["order_id"], pid), "razorpay_signature": "0" * 64})).status_code == 400  # a made-up signature
    assert await payments_on(inv["id"]) == []

    done = await client.post(confirm, headers=mine, json=signed(order["order_id"], pid))
    assert done.status_code == 200 and done.json()["paid_at"] and done.json()["balance"] == 0
    for _ in range(2):  # a refresh, a double click, a retry
        assert (await client.post(confirm, headers=mine, json=signed(order["order_id"], pid))).status_code == 200
    # and Razorpay's webhook for the same payment arriving after
    body = event("payment.captured", order["order_id"], pid)
    assert (await client.post("/webhooks/razorpay", content=body, headers=hook_headers(body, f"evt_{uuid.uuid4().hex}"))).status_code == 200
    pays = await payments_on(inv["id"])
    assert len(pays) == 1 and pays[0].amount == Decimal("1000.00") and pays[0].reference == pid and pays[0].recorded_by is None
    async with SessionLocal() as s:
        assert (await s.scalar(select(func.count()).select_from(OnlinePayment).where(OnlinePayment.invoice_id == uuid.UUID(inv["id"]), OnlinePayment.status == "paid"))) == 1
    row = next(i for i in (await client.get("/billing/invoices", headers=h)).json() if i["id"] == inv["id"])
    assert row["paid_at"] and row["paid_amount"] == 1000.0  # billing sees it exactly as a payment they typed in


async def test_only_razorpays_own_word_counts_not_what_the_browser_sends(client: AsyncClient, driver: dict, rzp: FakeRazorpay) -> None:
    _, mine, inv, _ = await sent_invoice(client, driver)
    order = (await client.post(f"/portal/invoices/{inv['id']}/pay", headers=mine)).json()
    confirm = f"/portal/invoices/{inv['id']}/pay/confirm"

    cheap = rzp.pay(order["order_id"], amount=100)  # a payment for far less than the order, signed correctly
    assert (await client.post(confirm, headers=mine, json=signed(order["order_id"], cheap))).status_code == 409
    failed = rzp.pay(order["order_id"], status="failed")
    assert (await client.post(confirm, headers=mine, json=signed(order["order_id"], failed))).status_code == 409
    unknown = signed(order["order_id"], "pay_never_existed00")
    assert (await client.post(confirm, headers=mine, json=unknown)).status_code == 502  # Razorpay has no such payment
    assert await payments_on(inv["id"]) == []

    held = rzp.pay(order["order_id"], status="authorized")  # taken but not yet captured: we capture it
    ok = await client.post(confirm, headers=mine, json=signed(order["order_id"], held))
    assert ok.status_code == 200 and ok.json()["paid_at"] and "POST /v1/payments/" + held + "/capture" in rzp.calls
    assert len(await payments_on(inv["id"])) == 1


async def test_an_order_of_one_invoice_cannot_be_used_to_pay_another(client: AsyncClient, driver: dict, rzp: FakeRazorpay) -> None:
    _, mine, inv, _ = await sent_invoice(client, driver)
    _, theirs, other_inv, _ = await sent_invoice(client, driver)
    order = (await client.post(f"/portal/invoices/{inv['id']}/pay", headers=mine)).json()
    pid = rzp.pay(order["order_id"])
    # the same invoice's order cannot be presented against a different invoice
    assert (await client.post(f"/portal/invoices/{other_inv['id']}/pay/confirm", headers=theirs, json=signed(order["order_id"], pid))).status_code == 404
    assert await payments_on(inv["id"]) == []


async def test_online_payment_is_off_until_razorpay_keys_are_set(client: AsyncClient, driver: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "razorpay_key_id", "")
    monkeypatch.setattr(s, "razorpay_key_secret", "")
    _, mine, inv, _ = await sent_invoice(client, driver)
    view = next(i for i in (await client.get("/portal/invoices", headers=mine)).json() if i["id"] == inv["id"])
    assert view["can_pay_online"] is False
    assert (await client.post(f"/portal/invoices/{inv['id']}/pay", headers=mine)).status_code == 503


async def test_the_private_link_can_pay_too_but_only_the_clients_not_the_receivers(client: AsyncClient, driver: dict, rzp: FakeRazorpay) -> None:
    _, _, inv, t = await sent_invoice(client, driver)
    assert (await client.post(f"/public/shipments/{t['receiver']}/pay")).status_code == 404
    order = (await client.post(f"/public/shipments/{t['client']}/pay")).json()
    pid = rzp.pay(order["order_id"])
    done = await client.post(f"/public/shipments/{t['client']}/pay/confirm", json=signed(order["order_id"], pid))
    assert done.status_code == 200 and done.json()["paid_at"]
    assert len(await payments_on(inv["id"])) == 1


async def test_the_webhook_applies_a_payment_the_browser_never_reported_and_ignores_repeats_and_forgeries(client: AsyncClient, driver: dict, rzp: FakeRazorpay) -> None:
    _, mine, inv, _ = await sent_invoice(client, driver)
    order = (await client.post(f"/portal/invoices/{inv['id']}/pay", headers=mine)).json()  # the client closed the tab after paying
    pid = rzp.pay(order["order_id"])
    body = event("payment.captured", order["order_id"], pid)
    a, b = f"evt_{uuid.uuid4().hex}", f"evt_{uuid.uuid4().hex}"

    assert (await client.post("/webhooks/razorpay", content=body, headers=hook_headers(body, a, secret="wrong"))).status_code == 400
    assert await payments_on(inv["id"]) == []
    assert (await client.post("/webhooks/razorpay", content=body, headers=hook_headers(body, a))).status_code == 200
    dup = await client.post("/webhooks/razorpay", content=body, headers=hook_headers(body, a))
    assert dup.json().get("duplicate") is True
    assert len(await payments_on(inv["id"])) == 1
    nothing = event("payment.failed", order["order_id"], pid)
    assert (await client.post("/webhooks/razorpay", content=nothing, headers=hook_headers(nothing, b))).status_code == 200


async def test_the_webhook_is_refused_while_no_webhook_secret_is_set(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "razorpay_webhook_secret", "")
    body = event("payment.captured", "order_x", "pay_x")
    for secret in ("", "anything"):
        h = {"X-Razorpay-Signature": hmac.new(secret.encode(), body, hashlib.sha256).hexdigest(), "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex}"}
        assert (await client.post("/webhooks/razorpay", content=body, headers=h)).status_code == 400


async def test_money_taken_after_billing_already_settled_the_invoice_is_flagged_not_double_counted(client: AsyncClient, driver: dict, rzp: FakeRazorpay) -> None:
    h, mine, inv, _ = await sent_invoice(client, driver)
    order = (await client.post(f"/portal/invoices/{inv['id']}/pay", headers=mine)).json()
    # while the pop-up was open, the transfer arrived and billing typed it in
    paid = await client.post(f"/billing/invoices/{inv['id']}/payments", headers=h, json={"amount": "1000", "paid_on": today(), "reference": "NEFT-1"})
    assert paid.status_code == 201
    before = (await item(client, "online_review") or {"count": 0})["count"]
    pid = rzp.pay(order["order_id"])
    done = await client.post(f"/portal/invoices/{inv['id']}/pay/confirm", headers=mine, json=signed(order["order_id"], pid))
    assert done.status_code == 200
    assert len(await payments_on(inv["id"])) == 1  # still only billing's
    assert (await item(client, "online_review"))["count"] == before + 1  # a person decides, usually a refund in Razorpay
    await client.post(f"/portal/invoices/{inv['id']}/pay/confirm", headers=mine, json=signed(order["order_id"], pid))
    assert (await item(client, "online_review"))["count"] == before + 1  # and repeating it does not add another
