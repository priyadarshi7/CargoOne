"""Ways out of the places a trip or an invoice used to get stuck."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import AuditLog, PodStatus, Trip, TripState
from tests.conftest import login
from tests.test_invoice_lifecycle import biller, invoiced, kinds
from tests.test_pod_upload import make_trip, post
from tests.test_review import shortage_trip, status_of


async def test_a_rejected_pod_can_be_reopened_and_decided_again(client: AsyncClient, driver: dict) -> None:
    trip_id, _, _ = await shortage_trip(client, driver)
    h = await biller(client)
    assert (await client.post(f"/review/{trip_id}/decision", headers=h, json={"action": "reject"})).status_code == 200
    assert await status_of(trip_id) == PodStatus.rejected
    ops = await login(client, "ops@cargoone.dev", "cargoone-dev")
    assert (await client.post(f"/review/{trip_id}/reopen", headers=h, json={"reason": "mis-click"})).status_code == 403  # billing decides, ops or admin reopen
    assert (await client.post(f"/review/{trip_id}/reopen", headers=ops, json={"reason": "x"})).status_code == 422  # a reason is needed
    res = await client.post(f"/review/{trip_id}/reopen", headers=ops, json={"reason": "Rejected by mistake"})
    assert res.status_code == 200 and res.json()["pod_status"] == "needs_review"
    assert "pod_reopened" in await kinds(trip_id)
    assert (await client.post(f"/review/{trip_id}/reopen", headers=ops, json={"reason": "again"})).status_code == 409  # only a rejected one
    assert (await client.post(f"/review/{trip_id}/decision", headers=h, json={"action": "approve"})).status_code == 200
    assert await status_of(trip_id) == PodStatus.verified
    async with SessionLocal() as s:
        assert await s.scalar(select(AuditLog).where(AuditLog.action == "review.reopen", AuditLog.entity_id == trip_id)) is not None


async def test_an_invoice_made_by_mistake_can_be_cancelled_before_it_leaves(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    assert (await client.post(f"/billing/invoices/{inv['id']}/cancel", headers=h, json={"reason": "wrong"})).status_code == 403  # ops or admin
    ops = await login(client, "ops@cargoone.dev", "cargoone-dev")
    assert (await client.post(f"/billing/invoices/{inv['id']}/cancel", headers=ops, json={"reason": ""})).status_code == 422
    assert (await client.post(f"/billing/invoices/{inv['id']}/cancel", headers=ops, json={"reason": "Wrong trips picked"})).status_code == 204
    assert await status_of(tid) == PodStatus.verified
    queue = (await client.get("/billing/queue", headers=h)).json()
    assert tid in [t["id"] for g in queue for t in g["trips"]]  # back in the queue, ready for a right invoice
    assert inv["id"] not in [i["id"] for i in (await client.get("/billing/invoices", headers=h)).json()]
    assert "invoice_cancelled" in await kinds(tid)
    again = await client.post("/billing/invoices", headers=h, json={"trip_ids": [tid]})
    assert again.status_code == 201 and again.json()["invoice_no"] != inv["invoice_no"]  # the number is not reused


async def test_a_sent_invoice_cannot_be_cancelled(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    assert (await client.post(f"/billing/invoices/{inv['id']}/sent", headers=h)).status_code == 200
    admin = await login(client, "admin@cargoone.dev", "cargoone-dev")
    res = await client.post(f"/billing/invoices/{inv['id']}/cancel", headers=admin, json={"reason": "too late"})
    assert res.status_code == 409
    assert await status_of(tid) == PodStatus.billed


async def test_a_cancelled_trip_takes_no_photo(client: AsyncClient, driver: dict) -> None:
    tid, lr = await make_trip()
    async with SessionLocal() as s:
        t = await s.get(Trip, uuid.UUID(tid))
        t.state = TripState.cancelled
        await s.commit()
    res = await post(client, driver, tid, render(SCENARIOS["clean"], lr))
    assert res.status_code == 409 and "cancelled" in res.text
    assert await status_of(tid) == PodStatus.pending
