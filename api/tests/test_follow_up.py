"""Gaps in the hand-offs: a client's no, a yes nobody booked, a cancelled trip's request, and the trouble on the road that the office must see."""
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import update

from app.db import SessionLocal
from app.models import Client, Invoice, Message, Trip, TripEvent, TripState
from tests.test_attention import item
from tests.test_pin_reset import office
from tests.test_planning import body as plan_body
from tests.test_planning import fresh_vehicle_and_driver, refs, t0
from tests.test_requests import submit, token_of
from tests.test_setup import digits


async def count(client: AsyncClient, key: str) -> int:
    return (await item(client, key) or {"count": 0})["count"]


async def quoted(client: AsyncClient, ops: dict, amount: str = "40000") -> tuple[dict, str]:
    sent = await submit(client)
    req = next(r for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == sent["reference"])
    assert (await client.post(f"/requests/{req['id']}/accept", headers=ops, json={"quote_amount": amount})).status_code == 200
    return req, token_of(sent)


async def test_a_clients_no_to_the_quote_reaches_the_office_with_the_reason(client: AsyncClient) -> None:
    ops = await office(client)
    before = await count(client, "quote_declined")
    req, token = await quoted(client, ops)
    assert (await client.post(f"/public/requests/{token}/quote", json={"decision": "decline", "reason": "Too expensive"})).status_code == 200
    # it is counted, listed among the open ones with who said no and why, and it keeps being counted until someone has looked
    assert await count(client, "quote_declined") == before + 1
    row = next(r for r in (await client.get("/requests", headers=ops)).json() if r["id"] == req["id"])
    assert row["status"] == "declined" and row["declined_by"] == "client" and row["decline_reason"] == "Too expensive" and row["decline_seen"] is False
    assert (await client.get("/home", headers=ops)).json()["requests_attention"] >= 1
    assert (await client.post(f"/requests/{req['id']}/seen", headers=ops)).json()["decline_seen"] is True
    assert await count(client, "quote_declined") == before
    assert all(r["id"] != req["id"] for r in (await client.get("/requests", headers=ops)).json())  # closed and read: off the open list
    assert any(r["id"] == req["id"] for r in (await client.get("/requests?state=declined", headers=ops)).json())  # but still findable


async def test_the_office_can_send_a_new_price_after_a_no_and_the_client_can_answer_again(client: AsyncClient) -> None:
    ops = await office(client)
    req, token = await quoted(client, ops, "50000")
    await client.post(f"/public/requests/{token}/quote", json={"decision": "decline", "reason": "Cheaper elsewhere"})
    res = await client.post(f"/requests/{req['id']}/requote", headers=ops, json={"quote_amount": "44000", "note": "Best price for a regular client"})
    assert res.status_code == 200 and res.json()["status"] == "accepted" and res.json()["quote_amount"] == 44000 and res.json()["declined_by"] is None
    mine = (await client.get(f"/public/requests/{token}")).json()
    assert mine["can_respond"] is True and mine["quote_amount"] == 44000 and mine["reply"] == "Best price for a regular client"
    assert (await client.post(f"/public/requests/{token}/quote", json={"decision": "accept"})).status_code == 200
    # a price that was already agreed cannot be changed from under the client
    assert (await client.post(f"/requests/{req['id']}/requote", headers=ops, json={"quote_amount": "10000"})).status_code == 409
    # and an office decline is not something to re-quote
    other, _ = await quoted(client, ops)
    await client.post(f"/requests/{other['id']}/decline", headers=ops, json={"reason": "No truck free"})
    assert (await client.post(f"/requests/{other['id']}/requote", headers=ops, json={"quote_amount": "10000"})).status_code == 409


async def test_a_yes_nobody_has_booked_and_a_quote_nobody_answered_are_flagged(client: AsyncClient) -> None:
    ops = await office(client)
    ready, waiting = await count(client, "ready_to_book"), await count(client, "quote_waiting")
    req, token = await quoted(client, ops)
    assert await count(client, "ready_to_book") == ready  # not before the client agrees
    async with SessionLocal() as s:  # the quote went out three days ago and nobody has answered
        from app.models import TransportRequest
        await s.execute(update(TransportRequest).where(TransportRequest.id == uuid.UUID(req["id"])).values(quote_sent_at=datetime.now(UTC) - timedelta(days=3)))
        await s.commit()
    assert await count(client, "quote_waiting") == waiting + 1
    await client.post(f"/public/requests/{token}/quote", json={"decision": "accept"})
    assert await count(client, "quote_waiting") == waiting and await count(client, "ready_to_book") == ready + 1


async def test_cancelling_a_trip_opens_its_request_again_for_booking(client: AsyncClient) -> None:
    ops = await office(client)
    req, token = await quoted(client, ops)
    await client.post(f"/public/requests/{token}/quote", json={"decision": "accept"})
    accepted = next(r for r in (await client.get("/requests", headers=ops)).json() if r["id"] == req["id"])
    r = await refs(client, ops)
    v, d = await fresh_vehicle_and_driver()
    trip = await client.post("/planning/trips", headers=ops, json=plan_body(r, v, d, t0(), request_id=req["id"], client_id=accepted["client_id"]))
    assert trip.status_code == 201, trip.text
    booked = (await client.get(f"/public/requests/{token}")).json()
    assert booked["status"] == "booked" and booked["trip_code"]
    cancel = await client.post(f"/planning/trips/{trip.json()['id']}/cancel", headers=ops, json={"reason": "Client postponed the load"})
    assert cancel.status_code == 200, cancel.text
    again = (await client.get(f"/public/requests/{token}")).json()
    assert again["status"] == "accepted" and again["trip_code"] is None and again["quote_accepted"] is True  # the agreed quote stands
    row = next(x for x in (await client.get("/requests", headers=ops)).json() if x["id"] == req["id"])
    assert row["status"] == "accepted" and row["trip_code"] is None  # in the office's list as something to book again


async def make_trip(client: AsyncClient, ops: dict, **values) -> str:
    r = await refs(client, ops)
    v, d = await fresh_vehicle_and_driver()
    res = await client.post("/planning/trips", headers=ops, json=plan_body(r, v, d, datetime.now(UTC) + timedelta(days=9)))
    assert res.status_code == 201, res.text
    trip_id = res.json()["id"]
    if values:
        async with SessionLocal() as s:
            await s.execute(update(Trip).where(Trip.id == uuid.UUID(trip_id)).values(**values))
            await s.commit()
    return trip_id


async def test_trips_that_are_not_going_to_plan_are_flagged(client: AsyncClient) -> None:
    ops = await office(client)
    now = datetime.now(UTC)
    base = {k: await count(client, k) for k in ("not_started", "unassigned", "not_acknowledged", "breakdown_open", "late_running", "delivery_issue")}
    await make_trip(client, ops, planned_start=now - timedelta(hours=3), planned_end=now + timedelta(hours=9))  # should have left
    await make_trip(client, ops, driver_id=None, planned_start=now + timedelta(hours=10))  # nobody to drive it
    await make_trip(client, ops, planned_start=now + timedelta(hours=5), planned_end=now + timedelta(hours=20))  # driver has not opened the job
    assert await count(client, "not_started") == base["not_started"] + 1
    assert await count(client, "unassigned") == base["unassigned"] + 1
    assert await count(client, "not_acknowledged") >= base["not_acknowledged"] + 1

    road = await make_trip(client, ops, state=TripState.in_transit, started_at=now - timedelta(hours=2), planned_start=now - timedelta(hours=2), late_alert_at=now - timedelta(hours=1))
    async with SessionLocal() as s:
        s.add(TripEvent(trip_id=uuid.UUID(road), kind="breakdown", note="engine"))
        await s.commit()
    assert await count(client, "breakdown_open") == base["breakdown_open"] + 1 and await count(client, "late_running") == base["late_running"] + 1
    async with SessionLocal() as s:  # the driver says it is moving again
        s.add(TripEvent(trip_id=uuid.UUID(road), kind="resolved"))
        await s.commit()
    assert await count(client, "breakdown_open") == base["breakdown_open"]

    short = await make_trip(client, ops, state=TripState.delivered, delivery_issue=True)
    assert await count(client, "delivery_issue") == base["delivery_issue"] + 1
    async with SessionLocal() as s:
        await s.execute(update(Trip).where(Trip.id == uuid.UUID(short)).values(delivery_issue=False))
        await s.commit()
    assert await count(client, "delivery_issue") == base["delivery_issue"]


async def test_unsent_and_unpaid_invoices_and_failed_messages_are_flagged(client: AsyncClient) -> None:
    ops = await office(client)
    r = await refs(client, ops)
    base = {k: await count(client, k) for k in ("invoice_unsent", "payment_overdue", "messages_failed")}
    now = datetime.now(UTC)
    async with SessionLocal() as s:
        cid = uuid.UUID(r["clients"][0]["id"])
        assert await s.get(Client, cid)
        s.add(Invoice(invoice_no=f"GAP-{digits(8)}", client_id=cid, total=1000, created_at=now - timedelta(days=2)))  # made, nobody marked it sent
        s.add(Invoice(invoice_no=f"GAP-{digits(8)}", client_id=cid, total=1000, created_at=now - timedelta(days=40), sent_at=now - timedelta(days=35)))  # sent, never paid
        s.add(Message(channel="whatsapp", template="shipment_update", provider="meta", status="failed", error="template not approved", body="x"))
        await s.commit()
    assert await count(client, "invoice_unsent") == base["invoice_unsent"] + 1
    assert await count(client, "payment_overdue") == base["payment_overdue"] + 1
    assert await count(client, "messages_failed") == base["messages_failed"] + 1
