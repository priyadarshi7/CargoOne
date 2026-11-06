import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Client, Role, Trip, TripEvent, User, Vehicle
from app.planning import overlaps, window
from app.security import hash_secret
from tests.conftest import login
from tests.test_pod_upload import post

H = timedelta(hours=1)


def t0() -> datetime:
    return datetime.now(UTC).replace(microsecond=0) + timedelta(days=30)  # far from any other test's data


async def ops(client: AsyncClient) -> dict:
    return await login(client, "ops@cargoone.dev", "cargoone-dev")


async def refs(client: AsyncClient, h: dict) -> dict:
    return (await client.get("/planning/refs", headers=h)).json()


async def fresh_vehicle_and_driver() -> tuple[str, str]:
    tag = uuid.uuid4().hex[:6].upper()
    async with SessionLocal() as s:
        v = Vehicle(reg_no=f"MH20 PL {tag.upper()}", is_hired=False)
        d = User(name=f"Plan Driver {tag}", phone=f"7{str(uuid.uuid4().int)[:9]}", role=Role.driver, password_hash=hash_secret("4821"), language="en")
        s.add_all([v, d])
        await s.commit()
        return str(v.id), str(d.id)


def body(r: dict, vehicle_id: str, driver_id: str | None, start: datetime | None, hours: int = 10, **extra) -> dict:
    start = start or datetime.now(UTC).replace(microsecond=0) + H  # a trip always has a start now
    return {"client_id": r["clients"][0]["id"], "vehicle_id": vehicle_id, "driver_id": driver_id, "destination": "Nagpur",
            "freight_amount": "25000", "lr_no": f"LR-{uuid.uuid4().hex[:6]}", "eway_bill_no": f"{uuid.uuid4().int % 10**12:012d}",
            "planned_start": start.isoformat(), "planned_end": (start + hours * H).isoformat(), "eway_valid_until": (start + (hours + 72) * H).isoformat(), **extra}


def test_window_and_overlap_rules() -> None:
    a = datetime(2026, 1, 1, 8, tzinfo=UTC)
    assert window(None, None) is None
    assert window(a, None) == (a, a + timedelta(days=1))  # default length one day
    assert window(a, a - H) == (a, a + timedelta(days=1))  # nonsense end ignored
    w1, w2 = window(a, a + 2 * H), window(a + 2 * H, a + 4 * H)
    assert not overlaps(w1, w2) and overlaps(w1, window(a + H, a + 3 * H)) and not overlaps(w1, None)


async def test_create_plans_a_trip_with_a_generated_code(client: AsyncClient) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    res = await client.post("/planning/trips", headers=h, json=body(r, v, d, t0()))
    assert res.status_code == 201, res.text
    code = res.json()["trip_code"]
    assert code.startswith("TRP-7")
    async with SessionLocal() as s:
        trip = await s.scalar(select(Trip).where(Trip.trip_code == code))
        assert trip.state.value == "planned" and trip.pod_status.value == "pending" and trip.origin
    codes = {(await client.post("/planning/trips", headers=h, json=body(r, v, None, t0() + (i + 3) * timedelta(days=2)))).json()["trip_code"] for i in range(3)}
    assert len(codes) == 3  # sequence, never repeats


async def test_vehicle_and_driver_double_booking_is_refused_unless_forced(client: AsyncClient) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    start = t0()
    assert (await client.post("/planning/trips", headers=h, json=body(r, v, d, start))).status_code == 201

    v2, d2 = await fresh_vehicle_and_driver()
    same_truck = await client.post("/planning/trips", headers=h, json=body(r, v, d2, start + 2 * H))
    assert same_truck.status_code == 409 and same_truck.json()["detail"]["clashes"][0]["kind"] == "vehicle"
    same_driver = await client.post("/planning/trips", headers=h, json=body(r, v2, d, start + 2 * H))
    assert same_driver.status_code == 409 and same_driver.json()["detail"]["clashes"][0]["kind"] == "driver"
    both = await client.post("/planning/trips", headers=h, json=body(r, v, d, start + H))
    assert {c["kind"] for c in both.json()["detail"]["clashes"]} == {"vehicle", "driver"}

    assert (await client.post("/planning/trips", headers=h, json=body(r, v, d, start + 10 * H))).status_code == 201  # back-to-back is fine
    forced = await client.post("/planning/trips", headers=h, json=body(r, v, d, start + H, force=True))
    assert forced.status_code == 201  # deliberate overlap


async def test_replan_checks_clashes_but_not_against_itself(client: AsyncClient) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    start = t0()
    a = (await client.post("/planning/trips", headers=h, json=body(r, v, d, start))).json()["id"]
    b = (await client.post("/planning/trips", headers=h, json=body(r, v, d, start + 24 * H))).json()["id"]
    assert (await client.patch(f"/planning/trips/{a}", headers=h, json={"planned_start": (start + H).isoformat(), "reason": "Customer asked for later"})).status_code == 200  # own slot
    clash = await client.patch(f"/planning/trips/{b}", headers=h, json={"planned_start": (start + 2 * H).isoformat(), "planned_end": (start + 5 * H).isoformat(), "reason": "Test"})
    assert clash.status_code == 409
    v2, _ = await fresh_vehicle_and_driver()
    assert (await client.patch(f"/planning/trips/{b}", headers=h, json={"vehicle_id": v2, "driver_id": None, "reason": "Test"})).status_code == 200
    assert (await client.patch(f"/planning/trips/{b}", headers=h, json={"planned_end": (start - H).isoformat(), "reason": "Test"})).status_code == 422


async def test_trip_lifecycle_start_cancel_and_delivered_by_pod(client: AsyncClient, driver: dict) -> None:
    h = await ops(client)
    r = await refs(client, h)
    me = (await client.get("/auth/me", headers=driver)).json()["id"]
    v, _ = await fresh_vehicle_and_driver()
    async with SessionLocal() as s:  # this shared test driver may be "on the road" from another test; a driver can only be on one trip
        for t in (await s.scalars(select(Trip).where(Trip.driver_id == uuid.UUID(me), Trip.state == "in_transit"))).all():
            t.state = "delivered"
        await s.commit()
    trip = (await client.post("/planning/trips", headers=h, json=body(r, v, me, None))).json()
    mine = (await client.get("/trips/mine", headers=driver)).json()
    assert next(t for t in mine if t["id"] == trip["id"])["state"] == "planned"

    assert (await client.post(f"/trips/{trip['id']}/start", headers=driver)).status_code == 409  # not loaded yet
    from tests.test_journey import LOADED
    assert (await client.post(f"/trips/{trip['id']}/loaded", headers=driver, files=LOADED)).status_code == 200
    started = await client.post(f"/trips/{trip['id']}/start", headers=driver)
    assert started.status_code == 200 and started.json()["state"] == "in_transit" and started.json()["started_at"]
    again = await client.post(f"/trips/{trip['id']}/start", headers=driver)
    assert again.json()["started_at"] == started.json()["started_at"]  # idempotent
    assert (await client.patch(f"/planning/trips/{trip['id']}", headers=h, json={"driver_id": None, "reason": "Test"})).status_code == 409  # on the road

    other = (await client.post("/planning/trips", headers=h, json=body(r, v, None, t0() + timedelta(days=3)))).json()
    assert (await client.post(f"/trips/{other['id']}/start", headers=driver)).status_code == 404  # not their trip
    assert (await client.post(f"/planning/trips/{other['id']}/cancel", headers=h, json={"reason": "Client cancelled the load"})).status_code == 200
    assert other["id"] not in {t["id"] for t in (await client.get("/trips", headers=h)).json()}  # cancelled trips drop out of lists
    assert (await client.post(f"/trips/{other['id']}/start", headers=h)).status_code == 409


async def test_a_pod_photo_marks_the_trip_delivered_and_blocks_cancel(client: AsyncClient, driver: dict) -> None:
    from app.devtools.synthetic_pod import SCENARIOS, render
    from tests.test_pod_upload import make_trip

    trip_id, lr = await make_trip()
    assert (await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))).status_code == 200
    async with SessionLocal() as s:
        assert (await s.get(Trip, uuid.UUID(trip_id))).state.value == "delivered"
    assert (await client.post(f"/planning/trips/{trip_id}/cancel", headers=await ops(client), json={"reason": "Test"})).status_code == 409


async def test_validation_roles_and_board(client: AsyncClient, driver: dict) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    good = body(r, v, d, None)
    for bad in ({"eway_bill_no": "123"}, {"freight_amount": "0"}, {"vehicle_id": str(uuid.uuid4())}, {"client_id": str(uuid.uuid4())}, {"driver_id": r["clients"][0]["id"]}):
        assert (await client.post("/planning/trips", headers=h, json={**good, **bad})).status_code in (422,), bad
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    assert (await client.post("/planning/trips", headers=billing, json=good)).status_code == 403  # billing may look, not plan
    assert (await client.get("/planning/board", headers=billing)).status_code == 200
    for hh in (driver, md):
        assert (await client.get("/planning/board", headers=hh)).status_code == 403
    assert (await client.get("/planning/board")).status_code == 401
    created = (await client.post("/planning/trips", headers=h, json=good)).json()
    board = (await client.get("/planning/board", headers=h)).json()
    assert created["id"] in {t["id"] for t in board["trips"]} and v in {x["id"] for x in board["vehicles"]}
    async with SessionLocal() as s:
        assert await s.scalar(select(Client.id).where(Client.id == uuid.UUID(r["clients"][0]["id"])))


async def test_a_trip_cannot_be_booked_into_the_past_or_for_months(client: AsyncClient) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    now = datetime.now(UTC).replace(microsecond=0)
    for start, why in ((now - 2 * H, "passed"), (now - timedelta(days=3), "passed"), (now + timedelta(days=400), "year")):
        res = await client.post("/planning/trips", headers=h, json=body(r, v, d, start))
        assert res.status_code == 422 and why in res.text, (start, res.text)
    long_trip = await client.post("/planning/trips", headers=h, json=body(r, v, d, now + 2 * H, hours=24 * 70))
    assert long_trip.status_code == 422 and "60 days" in long_trip.text
    assert (await client.post("/planning/trips", headers=h, json=body(r, v, d, now + 5 * 60 * timedelta(seconds=1)))).status_code == 201  # "from now" is fine


async def test_replanning_checks_a_changed_time_but_not_an_untouched_one(client: AsyncClient) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    start = datetime.now(UTC).replace(microsecond=0) + 3 * H
    trip = (await client.post("/planning/trips", headers=h, json=body(r, v, d, start))).json()["id"]
    assert (await client.patch(f"/planning/trips/{trip}", headers=h, json={"planned_start": (start - timedelta(days=2)).isoformat(), "reason": "Test"})).status_code == 422
    async with SessionLocal() as s:  # the time passes without the trip starting: a new driver can still be given
        t = await s.get(Trip, uuid.UUID(trip))
        t.planned_start, t.planned_end = start - timedelta(days=1), start - timedelta(hours=14)
        await s.commit()
    assert (await client.patch(f"/planning/trips/{trip}", headers=h, json={"driver_id": None, "reason": "Driver is unwell"})).status_code == 200


async def test_a_trip_needs_a_start_and_an_e_way_bill_that_covers_it(client: AsyncClient) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    start = datetime.now(UTC).replace(microsecond=0) + 5 * H
    good = body(r, v, d, start)
    for field in ("planned_start", "eway_valid_until"):
        missing = {k: x for k, x in good.items() if k != field}
        assert (await client.post("/planning/trips", headers=h, json=missing)).status_code == 422, field
    for bad, why in (({"eway_valid_until": (start - H).isoformat()}, "expire"), ({"eway_valid_until": (datetime.now(UTC) - H).isoformat()}, "expired"),
                     ({"eway_valid_until": (start + 2 * H).isoformat()}, "expires before the trip is due to end")):
        res = await client.post("/planning/trips", headers=h, json={**good, **bad})
        assert res.status_code == 422 and why in res.text, (bad, res.text)
    assert (await client.post("/planning/trips", headers=h, json=good)).status_code == 201


async def test_one_e_way_bill_covers_one_trip_until_that_trip_is_cancelled(client: AsyncClient) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    v2, d2 = await fresh_vehicle_and_driver()
    ewb = f"{uuid.uuid4().int % 10**12:012d}"
    first = (await client.post("/planning/trips", headers=h, json=body(r, v, d, t0(), eway_bill_no=ewb))).json()
    again = await client.post("/planning/trips", headers=h, json=body(r, v2, d2, t0(), eway_bill_no=ewb))
    assert again.status_code == 409 and first["trip_code"] in again.text
    assert (await client.post(f"/planning/trips/{first['id']}/cancel", headers=h, json={"reason": "Wrong consignment"})).status_code == 200
    assert (await client.post("/planning/trips", headers=h, json=body(r, v2, d2, t0(), eway_bill_no=ewb))).status_code == 201  # a cancelled trip frees it


async def test_cancelling_or_changing_a_plan_needs_a_reason_that_is_kept(client: AsyncClient) -> None:
    h = await ops(client)
    r = await refs(client, h)
    v, d = await fresh_vehicle_and_driver()
    v2, _ = await fresh_vehicle_and_driver()
    trip = (await client.post("/planning/trips", headers=h, json=body(r, v, d, t0()))).json()
    assert (await client.patch(f"/planning/trips/{trip['id']}", headers=h, json={"vehicle_id": v2})).status_code == 422  # no reason
    assert (await client.patch(f"/planning/trips/{trip['id']}", headers=h, json={"vehicle_id": v2, "reason": "  "})).status_code == 422
    assert (await client.patch(f"/planning/trips/{trip['id']}", headers=h, json={"vehicle_id": v2, "reason": "First truck broke down"})).status_code == 200
    assert (await client.patch(f"/planning/trips/{trip['id']}", headers=h, json={})).status_code == 200  # nothing changed: nothing to explain
    assert (await client.post(f"/planning/trips/{trip['id']}/cancel", headers=h, json={})).status_code == 422
    assert (await client.post(f"/planning/trips/{trip['id']}/cancel", headers=h, json={"reason": "Client postponed"})).status_code == 200
    async with SessionLocal() as s:
        t = await s.get(Trip, uuid.UUID(trip["id"]))
        assert t.cancel_reason == "Client postponed"
        events = {(e.kind, e.note) for e in (await s.scalars(select(TripEvent).where(TripEvent.trip_id == t.id))).all()}
    assert ("replanned", "First truck broke down") in events and ("cancelled", "Client postponed") in events and ("booked", None) in events


async def test_a_driver_starts_only_near_the_planned_time_and_never_two_trips_at_once(client: AsyncClient, driver: dict) -> None:
    h = await ops(client)
    r = await refs(client, h)
    me = (await client.get("/auth/me", headers=driver)).json()["id"]
    async with SessionLocal() as s:
        for t in (await s.scalars(select(Trip).where(Trip.driver_id == uuid.UUID(me), Trip.state == "in_transit"))).all():
            t.state = "delivered"
        await s.commit()
    v, _ = await fresh_vehicle_and_driver()
    v2, _ = await fresh_vehicle_and_driver()
    far = (await client.post("/planning/trips", headers=h, json=body(r, v, me, datetime.now(UTC) + timedelta(days=2)))).json()
    early = await client.post(f"/trips/{far['id']}/start", headers=driver)
    assert early.status_code == 409 and "up to 3 hours before" in early.text
    assert (await client.post(f"/trips/{far['id']}/start", headers=h)).status_code == 200  # the office may start it for them
    soon = (await client.post("/planning/trips", headers=h, json=body(r, v2, me, datetime.now(UTC) + 2 * H, force=True))).json()
    from tests.test_journey import LOADED
    await client.post(f"/trips/{soon['id']}/loaded", headers=driver, files=LOADED)
    busy = await client.post(f"/trips/{soon['id']}/start", headers=driver)
    assert busy.status_code == 409 and far["trip_code"] in busy.text
