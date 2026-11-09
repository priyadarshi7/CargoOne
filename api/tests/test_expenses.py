import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.devtools.synthetic_pod import SCENARIOS, render
from app.expenses import Fill, leg, legs, usual_kmpl
from tests.conftest import login
from tests.test_tracking import driver_with_trip as _driver_with_trip


async def driver_with_trip(client: AsyncClient):
    """A driver with a trip on a brand-new truck, so fuel history from other tests cannot mix into this one."""
    from sqlalchemy import update

    from app.db import SessionLocal
    from app.models import Trip, Vehicle

    h, trip = await _driver_with_trip(client)
    async with SessionLocal() as s:
        v = Vehicle(reg_no=f"MH20 EX {uuid.uuid4().hex[:10].upper()}", is_hired=False)
        s.add(v)
        await s.flush()
        await s.execute(update(Trip).where(Trip.id == uuid.UUID(trip)).values(vehicle_id=v.id))
        await s.commit()
    return h, trip

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def fill(day: int, odo: int, litres: float) -> Fill:
    return Fill(T0 + timedelta(days=day), odo, litres)


def test_a_normal_leg_has_no_flags_and_the_right_figure() -> None:
    lg = leg(fill(0, 10_000, 100), fill(3, 10_400, 100))
    assert lg.kmpl == 4.0 and lg.flags == ()


@pytest.mark.parametrize(("odo", "litres", "flag"), [
    (9_900, 100, "odometer_backwards"), (10_000, 100, "odometer_backwards"),
    (10_050, 100, "implausible_mileage"),  # 0.5 km/l
    (11_500, 100, "implausible_mileage"),  # 15 km/l
    (10_400, 800, "implausible_litres"),
])
def test_bad_legs_are_flagged(odo: int, litres: float, flag: str) -> None:
    assert flag in leg(fill(0, 10_000, 100), fill(3, odo, litres)).flags


def test_low_mileage_is_judged_against_the_trucks_own_usual() -> None:
    fills = [fill(0, 10_000, 100), fill(3, 10_400, 100), fill(6, 10_800, 100), fill(9, 11_200, 100), fill(12, 11_400, 100)]
    ls = legs(fills)
    assert [lg.kmpl for lg in ls] == [4.0, 4.0, 4.0, 2.0] and ls[-1].flags == ("low_mileage",)
    assert usual_kmpl(fills[:4]) == 4.0 and usual_kmpl(fills[:2]) is None  # needs 3 good legs to call anything "usual"


def test_a_bad_fill_does_not_poison_the_usual() -> None:
    fills = [fill(0, 10_000, 100), fill(1, 10_400, 100), fill(2, 10_800, 100), fill(3, 11_200, 100), fill(4, 11_250, 100), fill(5, 11_650, 100)]
    assert [lg.flags for lg in legs(fills)][-2:] == [("implausible_mileage",), ()]  # 0.5 km/l flagged; the next normal leg is fine


async def ops(client: AsyncClient) -> dict:
    return await login(client, "ops@cargoone.dev", "cargoone-dev")


async def spend(client: AsyncClient, h: dict, trip: str, category: str = "toll", amount: str = "450", *, cid: str | None = None,
                photo: bytes | None = None, when: datetime | None = None, **extra):
    data = {"client_expense_id": cid or uuid.uuid4().hex, "trip_id": trip, "category": category, "amount": amount,
            "incurred_at": (when or datetime.now(UTC) - timedelta(minutes=5)).isoformat(), **extra}
    files = {"photo": ("receipt.png", photo, "image/png")} if photo else None
    return await client.post("/expenses", headers=h, data=data, files=files)


async def test_a_driver_logs_an_expense_with_a_receipt_and_sees_it_pending(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    receipt = render(SCENARIOS["clean"], "LR-REC")
    res = await spend(client, h, trip, "toll", "450.50", photo=receipt, note="Samruddhi toll")
    assert res.status_code == 200, res.text
    e = res.json()
    assert (e["status"], e["amount"], e["has_receipt"], e["category"]) == ("pending", 450.5, True, "toll") and e["trip_code"]
    mine = (await client.get("/expenses/mine", headers=h)).json()
    assert e["id"] in {x["id"] for x in mine}
    assert (await client.get(f"/expenses/{e['id']}/receipt", headers=h)).status_code == 200  # the driver can see their own
    img = await client.get(f"/expenses/{e['id']}/receipt", headers=await ops(client))
    assert img.status_code == 200 and img.headers["content-type"] == "image/png" and img.headers["cache-control"] == "private, no-store"


async def test_retries_never_duplicate(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    cid = f"retry-{uuid.uuid4().hex}"
    first = (await spend(client, h, trip, cid=cid)).json()
    again = (await spend(client, h, trip, cid=cid)).json()
    assert first["id"] == again["id"]
    assert len({x["id"] for x in (await client.get("/expenses/mine", headers=h)).json() if x["id"] == first["id"]}) == 1


async def test_input_rules(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    assert (await spend(client, h, trip, "fuel", "5000")).status_code == 422  # fuel needs litres + odometer
    assert (await spend(client, h, trip, "fuel", "5000", litres="50")).status_code == 422
    for bad in ({"amount": "0"}, {"amount": "-5"}, {"amount": "600000"}, {"category": "yacht"}):
        assert (await spend(client, h, trip, **{"category": "toll", "amount": "100", **bad})).status_code == 422, bad
    assert (await spend(client, h, trip, when=datetime.now(UTC) + timedelta(days=2))).status_code == 422  # future date
    assert (await spend(client, h, trip, photo=b"not an image")).status_code == 415
    assert (await spend(client, h, str(uuid.uuid4()))).status_code == 404  # unknown trip
    other, _ = await driver_with_trip(client)
    assert (await spend(client, other, trip)).status_code == 404  # someone else's trip
    toll = (await spend(client, h, trip, "toll", "100", litres="5", odometer_km="123")).json()  # irrelevant fuel fields are dropped
    assert toll["litres"] is None and toll["odometer_km"] is None


async def test_fuel_economy_is_checked_the_moment_it_arrives(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    now = datetime.now(UTC)
    plan = [(10, 20_000, "100"), (8, 20_400, "100"), (6, 20_800, "100"), (4, 21_200, "100")]  # a steady 4 km/l
    for days_ago, odo, litres in plan:
        r = await spend(client, h, trip, "fuel", "9000", litres=litres, odometer_km=str(odo), when=now - timedelta(days=days_ago))
        assert r.json()["flags"] == [], r.text
    low = (await spend(client, h, trip, "fuel", "9000", litres="100", odometer_km="21400", when=now - timedelta(days=2))).json()
    assert low["flags"] == ["low_mileage"]  # 2 km/l on a truck that does 4
    back = (await spend(client, h, trip, "fuel", "9000", litres="100", odometer_km="21000", when=now - timedelta(days=1))).json()
    assert "odometer_backwards" in back["flags"]


async def test_office_decides_and_only_approved_money_counts(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    a = (await spend(client, h, trip, "toll", "1000")).json()
    b = (await spend(client, h, trip, "repair", "4000")).json()
    c = (await spend(client, h, trip, "food", "300")).json()
    o = await ops(client)
    assert (await client.post(f"/expenses/{a['id']}/decision", headers=o, json={"action": "approve"})).json()["status"] == "approved"
    assert (await client.post(f"/expenses/{b['id']}/decision", headers=o, json={"action": "reject"})).status_code == 422  # needs a reason
    rej = (await client.post(f"/expenses/{b['id']}/decision", headers=o, json={"action": "reject", "note": "no bill attached"})).json()
    assert rej["status"] == "rejected" and rej["review_note"] == "no bill attached"
    assert (await client.post(f"/expenses/{a['id']}/decision", headers=o, json={"action": "reject", "note": "changed my mind"})).status_code == 409

    pnl = (await client.get("/finance/pnl", headers=o)).json()
    row = next(t for t in pnl["trips"] if t["trip_id"] == trip)
    assert row["expenses"] == 1000.0 and row["pending"] == 300.0  # approved counts; pending is shown apart; rejected is nothing
    assert row["margin"] == row["freight"] - 1000.0 and pnl["by_category"]["toll"] >= 1000.0
    assert c["id"] in {x["id"] for x in (await client.get("/expenses", headers=o)).json()}  # still in the review queue


async def test_roles(client: AsyncClient, driver: dict) -> None:
    h, trip = await driver_with_trip(client)
    e = (await spend(client, h, trip)).json()
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    assert (await client.get("/expenses", headers=md)).status_code == 200 and (await client.get("/finance/pnl", headers=md)).status_code == 200
    assert (await client.post(f"/expenses/{e['id']}/decision", headers=md, json={"action": "approve"})).status_code == 403  # MD reads, does not approve
    assert (await client.get("/expenses", headers=h)).status_code == 403  # a driver cannot list everyone's
    assert (await client.get("/finance/pnl", headers=h)).status_code == 403
    assert (await client.post("/expenses", data={}, headers=billing)).status_code == 403  # only drivers log expenses
    assert (await client.get("/expenses")).status_code == 401
    other, _ = await driver_with_trip(client)
    assert (await client.get(f"/expenses/{uuid.uuid4()}/receipt", headers=other)).status_code == 404


async def test_advances_and_settlement(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    me = (await client.get("/auth/me", headers=h)).json()["id"]
    o = await ops(client)
    assert (await client.post("/finance/advances", headers=o, json={"driver_id": me, "amount": "5000", "note": "diesel advance"})).status_code == 201
    e = (await spend(client, h, trip, "toll", "1800")).json()
    await spend(client, h, trip, "food", "200")
    await client.post(f"/expenses/{e['id']}/decision", headers=o, json={"action": "approve"})
    row = next(d for d in (await client.get("/finance/settlement", headers=o)).json()["drivers"] if d["driver_id"] == me)
    assert (row["advances"], row["approved"], row["pending"], row["balance"]) == (5000.0, 1800.0, 200.0, 3200.0)  # still holds Rs 3,200
    assert (await client.post("/finance/advances", headers=o, json={"driver_id": str(uuid.uuid4()), "amount": "100"})).status_code == 422
    assert (await client.post("/finance/advances", headers=o, json={"driver_id": me, "amount": "0"})).status_code == 422
    assert (await client.post("/finance/advances", headers=await login(client, "md@cargoone.dev", "cargoone-dev"), json={"driver_id": me, "amount": "10"})).status_code == 403


async def test_a_driver_sees_their_own_money_and_nobody_elses(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    other, _ = await driver_with_trip(client)
    me = (await client.get("/auth/me", headers=h)).json()["id"]
    o = await ops(client)
    assert (await client.post("/finance/advances", headers=o, json={"driver_id": me, "amount": "5000", "note": "diesel advance"})).status_code == 201
    e = (await spend(client, h, trip, "toll", "1800")).json()
    await spend(client, h, trip, "food", "200")
    await client.post(f"/expenses/{e['id']}/decision", headers=o, json={"action": "approve"})
    mine = (await client.get("/finance/mine", headers=h)).json()
    assert (mine["advances"], mine["approved"], mine["waiting"], mine["balance"]) == (5000.0, 1800.0, 200.0, 3200.0)
    assert mine["recent_advances"][0]["note"] == "diesel advance"
    theirs = (await client.get("/finance/mine", headers=other)).json()
    assert (theirs["advances"], theirs["approved"], theirs["balance"]) == (0.0, 0.0, 0.0)
    assert (await client.get("/finance/mine", headers=o)).status_code == 403  # office people use /finance/settlement
    assert (await client.get("/finance/mine")).status_code == 401


async def test_vehicle_economy_report_lists_flagged_trucks(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    now = datetime.now(UTC)
    for days_ago, odo in [(9, 50_000), (7, 50_400), (5, 50_800), (3, 51_200), (1, 51_350)]:
        await spend(client, h, trip, "fuel", "9000", litres="100", odometer_km=str(odo), when=now - timedelta(days=days_ago))
    veh = (await client.get("/finance/pnl", headers=await ops(client))).json()["vehicles"]
    mine = next(v for v in veh if v["flagged"] >= 1 and "low_mileage" in v["flags"])
    assert mine["usual_kmpl"] == 4.0 and mine["fills"] >= 5


async def test_an_entry_id_cannot_be_used_to_read_someone_elses_expense(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    other, other_trip = await driver_with_trip(client)
    cid = f"clash-{uuid.uuid4().hex}"
    assert (await spend(client, h, trip, cid=cid)).status_code == 200
    assert (await spend(client, other, other_trip, cid=cid)).status_code == 409
