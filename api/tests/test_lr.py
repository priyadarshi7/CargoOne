import asyncio
import re
import uuid
from datetime import UTC, datetime

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.lr import lr_format, next_lr_no
from app.models import Branch, Trip
from tests.test_onboarding import jpeg
from tests.test_pin_reset import office
from tests.test_planning import body, fresh_vehicle_and_driver, refs, t0
from tests.test_setup import digits

LR = re.compile(r"^LR/[A-Z0-9]{2,8}/\d{2}-\d{2}/\d{6}$")


def code() -> str:
    return "T" + uuid.uuid4().hex[:6].upper()


async def new_branch(client: AsyncClient, ops: dict) -> dict:
    res = await client.post("/setup/branches", headers=ops, json={"name": f"Branch {digits()}", "code": code()})
    assert res.status_code == 201, res.text
    return res.json()


def test_format() -> None:
    assert lr_format("MH20", "26-27", 123) == "LR/MH20/26-27/000123"


async def test_numbers_count_per_branch_and_restart_each_april() -> None:
    c = code()
    async with SessionLocal() as s:
        branch = Branch(name=f"B {c}", code=c)
        s.add(branch)
        await s.flush()
        first = await next_lr_no(s, branch, datetime(2027, 3, 31, 12, tzinfo=UTC))
        second = await next_lr_no(s, branch, datetime(2027, 3, 31, 13, tzinfo=UTC))
        april = await next_lr_no(s, branch, datetime(2027, 4, 1, 12, tzinfo=UTC))
        await s.commit()
    assert first == f"LR/{c}/26-27/000001" and second == f"LR/{c}/26-27/000002"
    assert april == f"LR/{c}/27-28/000001"  # the new financial year starts again at 1


async def test_two_people_creating_trips_at_once_never_share_a_number() -> None:
    c = code()
    async with SessionLocal() as s:
        branch = Branch(name=f"B {c}", code=c)
        s.add(branch)
        await s.commit()
        bid = branch.id

    async def one() -> str:
        async with SessionLocal() as s:
            b = await s.get(Branch, bid)
            n = await next_lr_no(s, b)
            await s.commit()
            return n

    numbers = await asyncio.gather(*[one() for _ in range(25)])
    assert len(set(numbers)) == 25 and all(LR.match(n) for n in numbers)


async def test_a_planned_trip_gets_its_lr_automatically_and_it_cannot_be_typed(client: AsyncClient) -> None:
    ops = await office(client)
    branch = await new_branch(client, ops)
    r = await refs(client, ops)
    v, d = await fresh_vehicle_and_driver()
    payload = body(r, v, d, t0(), branch_id=branch["id"], material="Cement bags", weight_tonnes="20", packages=400, consignee_name="Demo Consignee", consignee_phone="9876543210")
    payload["lr_no"] = "LR-MY-OWN"  # a typed number is ignored
    res = await client.post("/planning/trips", headers=ops, json=payload)
    assert res.status_code == 201, res.text
    lr = res.json()["lr_no"]
    assert lr.startswith(f"LR/{branch['code']}/") and LR.match(lr) and lr.endswith("/000001")
    v2, d2 = await fresh_vehicle_and_driver()
    second = (await client.post("/planning/trips", headers=ops, json=body(r, v2, d2, t0(), branch_id=branch["id"]))).json()["lr_no"]
    assert second.endswith("/000002")
    async with SessionLocal() as s:
        t = await s.scalar(select(Trip).where(Trip.lr_no == lr))
        assert (t.material, str(t.weight_tonnes), t.packages, t.consignee_phone) == ("Cement bags", "20.00", 400, "9876543210")


async def test_a_refused_trip_does_not_use_up_a_number(client: AsyncClient) -> None:
    ops = await office(client)
    branch = await new_branch(client, ops)
    r = await refs(client, ops)
    v, d = await fresh_vehicle_and_driver()
    clash_start = t0()
    ok = await client.post("/planning/trips", headers=ops, json=body(r, v, d, clash_start, branch_id=branch["id"]))
    assert ok.json()["lr_no"].endswith("/000001")
    refused = await client.post("/planning/trips", headers=ops, json=body(r, v, d, clash_start, branch_id=branch["id"]))
    assert refused.status_code == 409
    v2, d2 = await fresh_vehicle_and_driver()
    assert (await client.post("/planning/trips", headers=ops, json=body(r, v2, d2, t0(), branch_id=branch["id"]))).json()["lr_no"].endswith("/000002")  # no gap


async def test_overloading_a_truck_is_refused(client: AsyncClient) -> None:
    ops = await office(client)
    r = await refs(client, ops)
    v, d = await fresh_vehicle_and_driver()
    await client.patch(f"/setup/vehicles/{v}", headers=ops, json={"capacity_tonnes": "10"})
    over = await client.post("/planning/trips", headers=ops, json=body(r, v, d, t0(), weight_tonnes="12"))
    assert over.status_code == 422 and "can carry" in over.json()["detail"]
    assert (await client.post("/planning/trips", headers=ops, json=body(r, v, d, t0(), weight_tonnes="10"))).status_code == 201


async def test_the_lr_pdf_is_printable_and_only_the_trips_own_driver_may_get_it(client: AsyncClient, driver: dict) -> None:
    from tests.test_tracking import driver_with_trip

    ops = await office(client)
    h, trip_id = await driver_with_trip(client)
    res = await client.get(f"/trips/{trip_id}/lr.pdf", headers=ops)
    assert res.status_code == 200 and res.content[:5] == b"%PDF-" and res.headers["content-type"] == "application/pdf"
    assert ".pdf" in res.headers["content-disposition"]
    assert (await client.get(f"/trips/{trip_id}/lr.pdf", headers=h)).status_code == 200  # their own trip
    assert (await client.get(f"/trips/{trip_id}/lr.pdf", headers=driver)).status_code == 404  # someone else's
    assert (await client.get(f"/trips/{trip_id}/lr.pdf")).status_code == 401
    assert (await client.get(f"/trips/{uuid.uuid4()}/lr.pdf", headers=ops)).status_code == 404
    md = await office(client, "md@cargoone.dev")
    assert (await client.get(f"/trips/{trip_id}/lr.pdf", headers=md)).status_code == 403


async def test_a_signed_scan_of_the_lr_can_be_attached_to_the_trip(client: AsyncClient) -> None:
    from tests.test_tracking import driver_with_trip

    ops = await office(client)
    billing = await office(client, "billing@cargoone.dev")
    _, trip_id = await driver_with_trip(client)
    up = await client.post("/documents", headers=ops, data={"owner_type": "trip", "owner_id": trip_id, "kind": "lr_scan"}, files={"file": ("lr.jpg", jpeg(), "image/jpeg")})
    assert up.status_code == 201, up.text
    listed = (await client.get("/documents", headers=billing, params={"owner_type": "trip", "owner_id": trip_id})).json()
    assert [x["kind"] for x in listed] == ["lr_scan"]
    assert (await client.get(f"/documents/{up.json()['id']}/file", headers=billing)).status_code == 200
    assert (await client.post("/documents", headers=billing, data={"owner_type": "trip", "owner_id": trip_id, "kind": "lr_scan"}, files={"file": ("a.jpg", jpeg(), "image/jpeg")})).status_code == 403


async def test_branch_codes(client: AsyncClient) -> None:
    ops = await office(client)
    b = await new_branch(client, ops)
    dup = await client.post("/setup/branches", headers=ops, json={"name": "Another", "code": b["code"].lower()})
    assert dup.status_code == 409  # codes are unique (stored upper-case)
    assert (await client.post("/setup/branches", headers=ops, json={"name": "Bad", "code": "no way!"})).status_code == 422
    renamed = await client.patch(f"/setup/branches/{b['id']}", headers=ops, json={"code": "zz" + digits(5)})
    assert renamed.json()["code"].startswith("ZZ")
    billing = await office(client, "billing@cargoone.dev")
    assert (await client.get("/setup/branches", headers=billing)).status_code == 200
    assert (await client.post("/setup/branches", headers=billing, json={"name": "X1", "code": "X1"})).status_code == 403
