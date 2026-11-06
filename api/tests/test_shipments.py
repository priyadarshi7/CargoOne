import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Client, Message, Trip
from tests.test_journey import code_of, my_trip, on_the_road


async def tokens(client: AsyncClient, h: dict, trip_id: str) -> dict[str, str]:
    res = (await client.get(f"/trips/{trip_id}/shipment-links", headers=h)).json()
    return {"client": res["client"]["url"].split("/s/")[1], "receiver": res["receiver"]["url"].split("/s/")[1]}


async def test_the_client_and_the_receiver_see_different_things_on_the_same_shipment(client: AsyncClient, driver: dict) -> None:
    h, tid = await on_the_road(client, driver)
    t = await tokens(client, h, tid)
    c = (await client.get(f"/public/shipments/{t['client']}")).json()
    r = (await client.get(f"/public/shipments/{t['receiver']}")).json()
    assert c["audience"] == "client" and r["audience"] == "receiver"
    assert c["freight_amount"] == 25000.0 and "freight_amount" not in r  # no price for the receiver
    assert "delivery_code" not in c and r["delivery_code"] == await code_of(tid)  # the code is for the receiver only
    assert [s["key"] for s in c["steps"]] == ["booked", "assigned", "loaded", "started", "delivered", "verified", "invoiced", "paid"]
    assert [s["key"] for s in r["steps"]] == ["booked", "assigned", "loaded", "started", "delivered"]
    assert [e["kind"] for e in c["timeline"]] == ["booked", "assigned", "loaded", "started"]
    # nothing that identifies the driver or the office's people
    me = (await client.get("/auth/me", headers=driver)).json()
    for page in (c, r):
        assert me["name"] not in str(page) and "phone" not in str(page).lower()


async def test_the_code_disappears_once_the_driver_has_entered_it(client: AsyncClient, driver: dict) -> None:
    h, tid = await on_the_road(client, driver)
    t = await tokens(client, h, tid)
    code = await code_of(tid)
    assert (await client.get(f"/public/shipments/{t['receiver']}")).json()["delivery_code"] == code
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": code})).status_code == 200
    r = (await client.get(f"/public/shipments/{t['receiver']}")).json()
    assert "delivery_code" not in r and r["state"] == "delivered" and r["steps"][4]["done"] is True
    assert r["live"] is None  # no location once the load has arrived


async def test_an_address_that_was_altered_swapped_or_retired_shows_nothing(client: AsyncClient, driver: dict) -> None:
    h, tid = await on_the_road(client, driver)
    t = await tokens(client, h, tid)
    code, aud, sig = t["client"].split(".")
    for bad in (f"{code}.{aud[0]}9.{sig}", f"{code}.r{aud[1:]}.{sig}", f"{code}.{aud}.{'A' * len(sig)}", "TRP-1.c0.abc", "nonsense", f"{code}.x0.{sig}"):
        assert (await client.get(f"/public/shipments/{bad}")).status_code == 404, bad
    assert (await client.get(f"/public/shipments/{t['client']}")).status_code == 200
    fresh = (await client.post(f"/trips/{tid}/shipment-links/retire", headers=h)).json()
    assert (await client.get(f"/public/shipments/{t['client']}")).status_code == 404  # the old address is dead
    assert (await client.get(f"/public/shipments/{t['receiver']}")).status_code == 404
    assert (await client.get(f"/public/shipments/{fresh['client']['url'].split('/s/')[1]}")).status_code == 200


async def test_the_position_is_rounded_and_only_shown_while_the_truck_is_on_the_road(client: AsyncClient, driver: dict) -> None:
    await client.post("/tracking/consent", headers=driver)
    h, tid = await on_the_road(client, driver)
    t = await tokens(client, h, tid)
    assert (await client.get(f"/public/shipments/{t['client']}")).json()["live"] is None  # no fix yet
    ping = {"pings": [{"lat": 19.876234, "lng": 75.343378, "recorded_at": datetime.now(UTC).isoformat()}]}
    assert (await client.post(f"/trips/{tid}/pings", headers=driver, json=ping)).status_code == 200
    live = (await client.get(f"/public/shipments/{t['client']}")).json()["live"]
    assert live["lat"] == 19.876 and live["lng"] == 75.343  # about 100 m, not the exact spot


async def test_the_receiver_never_hears_about_money_and_the_client_sees_the_invoice_only_once_sent(client: AsyncClient, driver: dict) -> None:
    h, tid = await on_the_road(client, driver)
    t = await tokens(client, h, tid)
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": await code_of(tid)})).status_code == 200
    async with SessionLocal() as s:
        trip = await s.get(Trip, uuid.UUID(tid))
        from app.events import record
        record(s, trip, "verified", public=True)
        record(s, trip, "invoiced", public=True)
        await s.commit()
    r = (await client.get(f"/public/shipments/{t['receiver']}")).json()
    c = (await client.get(f"/public/shipments/{t['client']}")).json()
    assert {"verified", "invoiced"}.isdisjoint(e["kind"] for e in r["timeline"])
    assert {"verified", "invoiced"} <= {e["kind"] for e in c["timeline"]}
    assert c["invoice"] is None  # drafted or not sent: nothing to show


async def test_the_office_can_send_the_address_and_every_message_is_logged(client: AsyncClient, driver: dict) -> None:
    h, tid = await on_the_road(client, driver)
    async with SessionLocal() as s:
        trip = await s.get(Trip, uuid.UUID(tid))
        cl = await s.get(Client, trip.client_id)
        cl.contact_phone, cl.language = "9000000123", "hi"
        trip.consignee_phone, trip.consignee_name = "9000000456", "Sai Traders"
        await s.commit()
    links = (await client.get(f"/trips/{tid}/shipment-links", headers=h)).json()
    assert links["client"]["has_phone"] and links["receiver"]["whatsapp"].startswith("https://wa.me/919000000456?text=")
    sent = await client.post(f"/trips/{tid}/shipment-links/send?audience=receiver", headers=h)
    assert sent.status_code == 200
    async with SessionLocal() as s:
        msgs = (await s.scalars(select(Message).where(Message.trip_id == uuid.UUID(tid), Message.template == "shipment_update"))).all()
    msgs = [m for m in msgs if m.to_masked.endswith("456")]  # the client's own number may have heard about earlier steps
    assert len(msgs) == 1 and "/s/" in msgs[0].body and "•••" in msgs[0].body  # the private part is never kept in the log


async def test_only_the_client_can_open_the_proof_of_delivery(client: AsyncClient, driver: dict) -> None:
    h, tid = await on_the_road(client, driver)
    t = await tokens(client, h, tid)
    assert (await client.get(f"/public/shipments/{t['receiver']}/pod")).status_code == 404
    assert (await client.get(f"/public/shipments/{t['client']}/pod")).status_code == 404  # nothing verified yet


async def test_a_cancelled_trip_says_so_on_both_pages(client: AsyncClient, driver: dict) -> None:
    h, trip = await my_trip(client, driver)
    t = await tokens(client, h, trip["id"])
    assert (await client.post(f"/planning/trips/{trip['id']}/cancel", headers=h, json={"reason": "Client postponed"})).status_code == 200
    c = (await client.get(f"/public/shipments/{t['client']}")).json()
    r = (await client.get(f"/public/shipments/{t['receiver']}")).json()
    assert c["cancelled"] and r["cancelled"]
    assert any(e["kind"] == "cancelled" and e.get("note") == "Client postponed" for e in c["timeline"])
    assert all("note" not in e for e in r["timeline"])  # the reason is the client's business
