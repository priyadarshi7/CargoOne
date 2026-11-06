import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import Trip, TripEvent
from tests.conftest import login
from tests.test_pod_upload import make_trip, post
from tests.test_shipments import tokens


async def biller(client: AsyncClient) -> dict:
    return await login(client, "billing@cargoone.dev", "cargoone-dev")


async def invoiced(client: AsyncClient, driver: dict, freight: int = 1000) -> tuple[dict, str, dict]:
    """A delivered, verified trip on a fresh invoice. Returns (biller headers, trip id, invoice)."""
    tid, lr = await make_trip(freight=freight)
    assert (await post(client, driver, tid, render(SCENARIOS["clean"], lr))).status_code == 200
    h = await biller(client)
    res = await client.post("/billing/invoices", headers=h, json={"trip_ids": [tid]})
    assert res.status_code == 201, res.text
    return h, tid, res.json()


async def kinds(trip_id: str) -> list[str]:
    async with SessionLocal() as s:
        return [e.kind for e in (await s.scalars(select(TripEvent).where(TripEvent.trip_id == uuid.UUID(trip_id)).order_by(TripEvent.id))).all()]


def today() -> str:
    return datetime.now(UTC).date().isoformat()


async def test_an_invoice_is_sent_by_a_person_and_only_then_can_it_be_paid(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    assert inv["sent_at"] is None and inv["paid_at"] is None and inv["balance"] == 1000.0
    pay = {"amount": "1000", "paid_on": today(), "reference": "UTR123"}
    early = await client.post(f"/billing/invoices/{inv['id']}/payments", headers=h, json=pay)
    assert early.status_code == 409 and "sent" in early.text
    ops = await login(client, "ops@cargoone.dev", "cargoone-dev")
    t = await tokens(client, ops, tid)
    assert (await client.get(f"/public/shipments/{t['client']}")).json()["invoice"] is None  # a draft is the office's business

    sent = await client.post(f"/billing/invoices/{inv['id']}/sent", headers=h)
    assert sent.status_code == 200 and sent.json()["sent_at"]
    again = await client.post(f"/billing/invoices/{inv['id']}/sent", headers=h)
    assert again.json()["sent_at"] == sent.json()["sent_at"]  # marking twice changes nothing
    page = (await client.get(f"/public/shipments/{t['client']}")).json()
    assert page["invoice"]["invoice_no"] == inv["invoice_no"] and page["invoice"]["paid_at"] is None
    assert page["steps"][6] == {"key": "invoiced", "done": True, "at": page["invoice"]["sent_at"]}
    assert (await client.get(f"/public/shipments/{t['receiver']}")).json().get("invoice") is None  # the receiver never sees money
    assert (await kinds(tid)).count("invoiced") == 1


async def test_payments_add_up_and_the_last_one_closes_the_trip(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    await client.post(f"/billing/invoices/{inv['id']}/sent", headers=h)
    url = f"/billing/invoices/{inv['id']}/payments"
    assert (await client.post(url, headers=h, json={"amount": "1500", "paid_on": today()})).status_code == 422  # more than the balance
    assert (await client.post(url, headers=h, json={"amount": "100", "paid_on": (datetime.now(UTC) + timedelta(days=2)).date().isoformat()})).status_code == 422
    assert (await client.post(url, headers=h, json={"amount": "100", "paid_on": "2020-01-01"})).status_code == 422  # before the invoice existed
    assert (await client.post(url, headers=h, json={"amount": "0", "paid_on": today()})).status_code == 422

    part = await client.post(url, headers=h, json={"amount": "400", "paid_on": today(), "reference": "UTR1"})
    assert part.status_code == 201 and part.json()["balance"] == 600.0 and part.json()["paid_at"] is None
    async with SessionLocal() as s:
        assert (await s.get(Trip, uuid.UUID(tid))).closed_at is None  # part-paid: still open
    done = await client.post(url, headers=h, json={"amount": "600", "paid_on": today(), "reference": "UTR2"})
    assert done.json()["balance"] == 0 and done.json()["paid_at"]
    async with SessionLocal() as s:
        assert (await s.get(Trip, uuid.UUID(tid))).closed_at is not None
    assert "paid" in await kinds(tid) and "closed" in await kinds(tid)
    assert (await client.post(url, headers=h, json={"amount": "1", "paid_on": today()})).status_code == 409  # already paid in full
    ops = await login(client, "ops@cargoone.dev", "cargoone-dev")
    t = await tokens(client, ops, tid)
    inv_page = (await client.get(f"/public/shipments/{t['client']}")).json()["invoice"]
    assert inv_page["paid_at"]
    listed = next(i for i in (await client.get("/billing/invoices", headers=h)).json() if i["id"] == inv["id"])
    assert listed["paid_amount"] == 1000.0 and listed["balance"] == 0
    assert (await client.get(url, headers=h)).json()[0]["reference"] == "UTR1"


async def test_a_closed_trip_cannot_be_cancelled_or_changed(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    await client.post(f"/billing/invoices/{inv['id']}/sent", headers=h)
    await client.post(f"/billing/invoices/{inv['id']}/payments", headers=h, json={"amount": "1000", "paid_on": today()})
    ops = await login(client, "ops@cargoone.dev", "cargoone-dev")
    cancel = await client.post(f"/planning/trips/{tid}/cancel", headers=ops, json={"reason": "Test"})
    assert cancel.status_code == 409 and "closed" in cancel.text
    assert (await client.patch(f"/planning/trips/{tid}", headers=ops, json={"driver_id": None, "reason": "Test"})).status_code == 409


async def test_only_an_admin_can_undo_a_payment_and_it_reopens_the_trip(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    await client.post(f"/billing/invoices/{inv['id']}/sent", headers=h)
    await client.post(f"/billing/invoices/{inv['id']}/payments", headers=h, json={"amount": "1000", "paid_on": today(), "reference": "WRONG"})
    pid = (await client.get(f"/billing/invoices/{inv['id']}/payments", headers=h)).json()[0]["id"]
    url = f"/billing/invoices/{inv['id']}/payments/{pid}/void"
    assert (await client.post(url, headers=h, json={"reason": "Entered against the wrong invoice"})).status_code == 403  # billing cannot
    admin = await login(client, "admin@cargoone.dev", "cargoone-dev")
    assert (await client.post(url, headers=admin, json={"reason": "x"})).status_code == 422  # a reason is needed
    res = await client.post(url, headers=admin, json={"reason": "Entered against the wrong invoice"})
    assert res.status_code == 200 and res.json()["paid_at"] is None and res.json()["balance"] == 1000.0
    async with SessionLocal() as s:
        assert (await s.get(Trip, uuid.UUID(tid))).closed_at is None
    assert "reopened" in await kinds(tid)
    assert (await client.post(f"/billing/invoices/{inv['id']}/payments", headers=h, json={"amount": "1000", "paid_on": today()})).status_code == 201  # and it can be paid again
