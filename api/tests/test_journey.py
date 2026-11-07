import io
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Trip, TripEvent
from tests.test_planning import H, body, fresh_vehicle_and_driver, ops, refs
from tests.test_pod_upload import post


def photo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 90, 60)).save(buf, "JPEG")
    return buf.getvalue()


LOADED = {"file": ("l.jpg", photo(), "image/jpeg")}


async def my_trip(client: AsyncClient, driver: dict, **extra) -> tuple[dict, dict]:
    """A planned trip for the shared test driver, starting within the hour so the driver may start it. Returns (office headers, trip)."""
    h = await ops(client)
    r = await refs(client, h)
    me = (await client.get("/auth/me", headers=driver)).json()["id"]
    async with SessionLocal() as s:  # a driver can only be on one trip: free the shared test driver from other tests' trips
        for t in (await s.scalars(select(Trip).where(Trip.driver_id == uuid.UUID(me), Trip.state == "in_transit"))).all():
            t.state = "delivered"
        await s.commit()
    v, _ = await fresh_vehicle_and_driver()
    start = datetime.now(UTC).replace(microsecond=0) + H
    trip = (await client.post("/planning/trips", headers=h, json=body(r, v, me, start, force=True, **extra))).json()
    return h, trip


async def events(trip_id: str) -> list[TripEvent]:
    async with SessionLocal() as s:
        return list((await s.scalars(select(TripEvent).where(TripEvent.trip_id == uuid.UUID(trip_id)).order_by(TripEvent.id))).all())


async def code_of(trip_id: str) -> str:
    async with SessionLocal() as s:
        return (await s.get(Trip, uuid.UUID(trip_id))).delivery_code


async def on_the_road(client: AsyncClient, driver: dict, **extra) -> tuple[dict, str]:
    h, trip = await my_trip(client, driver, **extra)
    await client.post(f"/trips/{trip['id']}/loaded", headers=driver, files=LOADED)
    assert (await client.post(f"/trips/{trip['id']}/start", headers=driver)).status_code == 200
    return h, trip["id"]


async def test_driver_accepts_loads_with_a_photo_and_only_then_starts(client: AsyncClient, driver: dict) -> None:
    h, trip = await my_trip(client, driver)
    tid = trip["id"]
    assert (await client.post(f"/trips/{tid}/ack", headers=driver)).status_code == 200
    first = (await client.get(f"/trips/{tid}/timeline", headers=h)).json()
    assert first["acknowledged_at"] and first["loaded_at"] is None

    assert (await client.post(f"/trips/{tid}/start", headers=driver)).status_code == 409  # loading first
    assert (await client.post(f"/trips/{tid}/loaded", headers=driver)).status_code == 422  # a photo is needed
    assert (await client.post(f"/trips/{tid}/loaded", headers=driver, files={"file": ("l.jpg", b"not an image", "image/jpeg")})).status_code == 415
    ok = await client.post(f"/trips/{tid}/loaded", headers=driver, files=LOADED)
    assert ok.status_code == 200
    again = await client.post(f"/trips/{tid}/loaded", headers=driver, files=LOADED)
    assert again.json()["loaded_at"] == ok.json()["loaded_at"]  # a retry changes nothing
    assert (await client.get(f"/trips/{tid}/loading-photo", headers=h)).status_code == 200
    assert (await client.get(f"/trips/{tid}/loading-photo", headers=driver)).status_code == 403  # the office looks at it, not other drivers
    assert (await client.post(f"/trips/{tid}/start", headers=driver)).status_code == 200
    assert [e.kind for e in await events(tid)] == ["booked", "assigned", "acknowledged", "loaded", "started"]


async def test_the_office_can_confirm_loading_without_a_photo_if_it_says_why(client: AsyncClient, driver: dict) -> None:
    h, trip = await my_trip(client, driver)
    assert (await client.post(f"/trips/{trip['id']}/loaded", headers=h)).status_code == 422
    assert (await client.post(f"/trips/{trip['id']}/loaded", headers=h, data={"note": "Driver phoned: loaded, camera broken"})).status_code == 200
    assert (await client.post(f"/trips/{trip['id']}/start", headers=driver)).status_code == 200


async def test_delays_and_breakdowns_are_reported_only_on_the_road(client: AsyncClient, driver: dict) -> None:
    _h, trip = await my_trip(client, driver)
    tid = trip["id"]
    assert (await client.post(f"/trips/{tid}/events", headers=driver, json={"kind": "delay", "reason": "traffic", "minutes": 30})).status_code == 409  # not started
    await client.post(f"/trips/{tid}/loaded", headers=driver, files=LOADED)
    await client.post(f"/trips/{tid}/start", headers=driver)
    assert (await client.post(f"/trips/{tid}/events", headers=driver, json={"kind": "delay", "reason": "traffic"})).status_code == 422  # how long?
    assert (await client.post(f"/trips/{tid}/events", headers=driver, json={"kind": "breakdown", "reason": "traffic"})).status_code == 422  # not a truck fault
    assert (await client.post(f"/trips/{tid}/events", headers=driver, json={"kind": "delay", "reason": "traffic", "minutes": 45, "note": "NH52 jam"})).status_code == 201
    assert (await client.post(f"/trips/{tid}/events", headers=driver, json={"kind": "breakdown", "reason": "tyre"})).status_code == 201
    assert (await client.post(f"/trips/{tid}/events", headers=driver, json={"kind": "resolved"})).status_code == 201
    got = [(e.kind, (e.meta or {}).get("reason")) for e in await events(tid) if e.kind in ("delay", "breakdown", "resolved")]
    assert got == [("delay", "traffic"), ("breakdown", "tyre"), ("resolved", "other")]


async def test_delivery_needs_the_receivers_code_and_a_wrong_one_is_counted(client: AsyncClient, driver: dict) -> None:
    h, trip = await my_trip(client, driver)
    tid = trip["id"]
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": "0000"})).status_code == 409  # not started
    await client.post(f"/trips/{tid}/loaded", headers=driver, files=LOADED)
    await client.post(f"/trips/{tid}/start", headers=driver)
    code = await code_of(tid)
    wrong = "1234" if code != "1234" else "4321"
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={})).status_code == 422  # no code at all
    for _ in range(3):  # the missing code above counted as the first try
        assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": wrong})).status_code == 422
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": wrong})).status_code == 422  # fifth: locks
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": code})).status_code == 429  # even the right code waits out the lock
    assert (await client.get(f"/trips/{tid}/timeline", headers=h)).json()["code_locked_until"]  # the office can see the lock
    assert (await client.post(f"/trips/{tid}/delivery-code/unlock", headers=driver)).status_code == 403  # the driver cannot lift it
    assert (await client.post(f"/trips/{tid}/delivery-code/unlock", headers=h)).status_code == 200
    assert (await client.get(f"/trips/{tid}/timeline", headers=h)).json()["code_locked_until"] is None
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": code, "shortage_or_damage": True})).status_code == 422  # say what
    done = await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": code, "shortage_or_damage": True, "note": "2 cartons wet"})
    assert done.status_code == 200
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": code})).status_code == 200  # a retry is harmless
    t = (await client.get(f"/trips/{tid}/timeline", headers=h)).json()
    assert t["delivery_confirmed_at"] and t["delivery_issue"] and t["delivery_note"] == "2 cartons wet"
    kinds = [e.kind for e in await events(tid)]
    assert kinds.count("delivered") == 1 and "issue" in kinds
    async with SessionLocal() as s:
        assert (await s.get(Trip, uuid.UUID(tid))).state.value == "delivered"


async def test_the_pod_photo_waits_for_the_code_unless_the_office_uploads_it(client: AsyncClient, driver: dict) -> None:
    from app.devtools.synthetic_pod import SCENARIOS, render

    _h, tid = await on_the_road(client, driver)
    async with SessionLocal() as s:
        lr = (await s.get(Trip, uuid.UUID(tid))).lr_no
    blocked = await post(client, driver, tid, render(SCENARIOS["clean"], lr))
    assert blocked.status_code == 409 and "code" in blocked.text
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"code": await code_of(tid)})).status_code == 200
    assert (await post(client, driver, tid, render(SCENARIOS["clean"], lr))).status_code == 200


async def test_only_the_office_can_deliver_without_the_code_and_must_say_why(client: AsyncClient, driver: dict) -> None:
    h, tid = await on_the_road(client, driver)
    assert (await client.post(f"/trips/{tid}/deliver", headers=driver, json={"override_reason": "no code"})).status_code == 403
    assert (await client.post(f"/trips/{tid}/deliver", headers=h, json={"override_reason": "x"})).status_code == 422  # too short
    ok = await client.post(f"/trips/{tid}/deliver", headers=h, json={"override_reason": "Receiver unreachable, security guard signed"})
    assert ok.status_code == 200
    t = (await client.get(f"/trips/{tid}/timeline", headers=h)).json()
    assert t["delivery_override"] == "Receiver unreachable, security guard signed"


async def test_a_late_truck_is_flagged_once_and_so_is_an_e_way_bill_that_will_expire(client: AsyncClient, driver: dict) -> None:
    await client.post("/tracking/consent", headers=driver)
    _h, tid = await on_the_road(client, driver)
    now = datetime.now(UTC)
    async with SessionLocal() as s:  # a drop point about 400 km away, planned to end in 2 hours: at 40 km/h x 1.3 it cannot make it
        t = await s.get(Trip, uuid.UUID(tid))
        t.destination_lat, t.destination_lng = 21.1458, 79.0882  # Nagpur
        t.planned_end = now + 2 * H
        t.eway_valid_until = now + 4 * H
        await s.commit()
    ping = {"pings": [{"lat": 19.8762, "lng": 75.3433, "recorded_at": now.isoformat()}]}  # Chhatrapati Sambhajinagar
    assert (await client.post(f"/trips/{tid}/pings", headers=driver, json=ping)).status_code == 200
    kinds = [e.kind for e in await events(tid)]
    assert "late" in kinds and "eway_risk" in kinds
    ping["pings"][0]["recorded_at"] = (now + timedelta(seconds=20)).isoformat()
    await client.post(f"/trips/{tid}/pings", headers=driver, json=ping)
    assert [e.kind for e in await events(tid)].count("late") == 1  # not repeated on every position update
