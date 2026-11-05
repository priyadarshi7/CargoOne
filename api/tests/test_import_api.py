import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import AuditLog, Trip, User, Vehicle
from tests.conftest import login
from tests.test_pod_upload import post

HEADER = "Trip ID,Client,Vehicle,Destination,Freight,LR No,E-way Bill No,Branch,Driver Phone,Consignee Name\n"


def uid() -> str:
    return uuid.uuid4().hex[:8].upper()


async def biller(client: AsyncClient) -> dict:
    return await login(client, "billing@cargoone.dev", "cargoone-dev")


async def send(client: AsyncClient, csv_text: str, *, dry_run: bool, create_clients: bool = False, name: str = "t.csv", h=None):
    return await client.post(f"/imports/trips?dry_run={str(dry_run).lower()}&create_clients={str(create_clients).lower()}",
                             headers=h or await biller(client), files={"file": (name, csv_text.encode(), "text/csv")})


async def trip_by_code(code: str) -> Trip | None:
    async with SessionLocal() as s:
        return await s.scalar(select(Trip).where(Trip.trip_code == code))


async def test_dry_run_then_commit_creates_trips_idempotently(client: AsyncClient) -> None:
    a, b = f"IMP-{uid()}", f"IMP-{uid()}"
    csv = HEADER + f"{a},Company B,MH20 EL 4521,Nagpur,38500,LR-{a},341000000001,Pune,9000000001,Some Consignee\n" \
                   f"{b},Company D,MH17 BY 3092 (hired),Indore,\"41,200\",LR-{b},341000000002,,,\n"
    dry = (await send(client, csv, dry_run=True)).json()
    assert (dry["dry_run"], dry["created"], dry["errors"]) == (True, 2, [])
    assert await trip_by_code(a) is None  # nothing persisted

    done = (await send(client, csv, dry_run=False)).json()
    assert done["created"] == 2 and done["updated"] == 0
    t = await trip_by_code(a)
    assert t.pod_status.value == "pending" and t.driver_id is not None  # driver matched by phone
    assert t.consignee_name == "Some Consignee" and t.origin == "Chhatrapati Sambhajinagar"  # default origin
    assert str((await trip_by_code(b)).freight_amount) == "41200.00"

    again = (await send(client, csv, dry_run=False)).json()  # same file again: safe
    assert (again["created"], again["updated"], again["unchanged"]) == (0, 0, 2)


async def test_reimport_updates_open_trips_but_never_trips_with_pod_activity(client: AsyncClient, driver: dict) -> None:
    code = f"IMP-{uid()}"
    await send(client, HEADER + f"{code},Company B,MH20 EL 4521,Nagpur,1000,LR-{code},341000000001,,,\n", dry_run=False)
    upd = (await send(client, HEADER + f"{code},Company B,MH20 EL 4521,Nagpur,1500,LR-{code},341000000001,,,\n", dry_run=False)).json()
    assert upd["updated"] == 1 and str((await trip_by_code(code)).freight_amount) == "1500.00"

    # give the trip a driver + a POD, then try to rewrite its LR number via import
    t = await trip_by_code(code)
    async with SessionLocal() as s:
        row = await s.get(Trip, t.id)
        row.driver_id = await s.scalar(select(User.id).where(User.phone == "9000000001"))
        await s.commit()
    assert (await post(client, driver, str(t.id), render(SCENARIOS["clean"], f"LR-{code}"))).status_code == 200
    skip = (await send(client, HEADER + f"{code},Company B,MH20 EL 4521,Nagpur,9999,LR-CHANGED,341000000001,,,\n", dry_run=False)).json()
    assert skip["skipped"] == 1 and "POD activity" in skip["warnings"][0]["message"]
    after = await trip_by_code(code)
    assert after.lr_no == f"LR-{code}" and str(after.freight_amount) == "1500.00"  # evidence untouched


async def test_bad_rows_are_reported_with_row_numbers_and_good_rows_still_import(client: AsyncClient) -> None:
    good = f"IMP-{uid()}"
    csv = HEADER + f"{good},Company B,MH20 EL 4521,Nagpur,100,LR-1,341000000001,,,\n" \
                   "BAD-1,Company B,not-a-truck,Nagpur,100,LR-2,12345,,,\n"
    res = (await send(client, csv, dry_run=False)).json()
    assert res["created"] == 1 and len(res["errors"]) == 1
    err = res["errors"][0]
    assert err["row"] == 3 and err["trip_code"] == "BAD-1" and "registration" in err["message"] and "12 digits" in err["message"]
    assert await trip_by_code("BAD-1") is None and await trip_by_code(good) is not None


async def test_unknown_client_needs_explicit_permission(client: AsyncClient) -> None:
    code, newc = f"IMP-{uid()}", f"Brand New Co {uid()}"
    csv = HEADER + f"{code},{newc},MH20 EL 4521,Nagpur,100,LR-1,341000000001,,,\n"
    refused = (await send(client, csv, dry_run=False)).json()
    assert refused["created"] == 0 and "Unknown client" in refused["errors"][0]["message"]
    ok = (await send(client, csv, dry_run=False, create_clients=True)).json()
    assert ok["created"] == 1 and ok["new_clients"] == [newc]


async def test_new_vehicles_and_branches_are_created_and_hired_flag_set(client: AsyncClient) -> None:
    code, branch = f"IMP-{uid()}", f"Branch {uid()}"
    reg = f"MH{20 + int(uid()[:2], 16) % 70} ZZ {int(uid()[:4], 16) % 9000 + 1000}"
    res = (await send(client, HEADER + f"{code},Company B,{reg} (hired),Nagpur,100,LR-1,341000000001,{branch},,\n", dry_run=False)).json()
    assert res["new_vehicles"] == 1 and res["new_branches"] == [branch]
    async with SessionLocal() as s:
        assert (await s.scalar(select(Vehicle.is_hired).where(Vehicle.reg_no == reg))) is True


async def test_file_level_problems_are_422_with_a_clear_message(client: AsyncClient) -> None:
    h = await biller(client)
    r = await client.post("/imports/trips", headers=h, files={"file": ("t.csv", b"Trip ID,Client\nA,B\n", "text/csv")})
    assert r.status_code == 422 and "Missing column" in r.json()["detail"]
    r = await client.post("/imports/trips", headers=h, files={"file": ("t.pdf", b"x", "application/pdf")})
    assert r.status_code == 422


async def test_template_downloads_and_imports_cleanly(client: AsyncClient) -> None:
    h = await biller(client)
    tpl = await client.get("/imports/trips/template", headers=h)
    assert tpl.status_code == 200 and tpl.text.startswith("Trip ID,Client")
    res = (await send(client, tpl.text, dry_run=True)).json()
    assert res["errors"] == [] and res["total"] == 2  # the template's own examples are valid


async def test_roles_and_audit(client: AsyncClient, driver: dict) -> None:
    for h in (driver, await login(client, "md@cargoone.dev", "cargoone-dev")):
        assert (await send(client, HEADER, dry_run=True, h=h)).status_code == 403
        assert (await client.get("/imports/trips/template", headers=h)).status_code == 403
    assert (await client.post("/imports/trips", files={"file": ("t.csv", b"x", "text/csv")})).status_code == 401
    code = f"IMP-{uid()}"
    await send(client, HEADER + f"{code},Company B,MH20 EL 4521,Nagpur,100,LR-1,341000000001,,,\n", dry_run=False)
    async with SessionLocal() as s:
        meta = (await s.scalars(select(AuditLog.meta).where(AuditLog.action == "import.trips").order_by(AuditLog.at.desc()).limit(1))).first()
    assert meta["created"] == 1 and "Some Consignee" not in str(meta)
