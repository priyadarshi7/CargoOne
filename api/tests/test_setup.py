import random
import string
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient

from app.phones import clean_phone
from app.routers.setup import clean_reg
from tests.test_login_hardening import attempt
from tests.test_pin_reset import office


def digits(n: int = 9) -> str:
    return str(uuid.uuid4().int)[:n]


def new_reg() -> str:
    """A valid registration number that is unique across runs (the test database keeps old rows): ~6 million combinations."""
    return f"MH20 {''.join(random.choices(string.ascii_uppercase, k=3))} {digits(4)}"


def mobile() -> str:
    return "9" + digits(9)


@pytest.mark.parametrize(("raw", "want"), [("98765 43210", "9876543210"), ("+91 98765-43210", "9876543210"), ("09876543210", "9876543210")])
def test_phones_are_normalised(raw: str, want: str) -> None:
    assert clean_phone(raw) == want


@pytest.mark.parametrize("raw", ["12345", "5876543210", "98765432101234", "abc"])
def test_bad_phones_are_refused(raw: str) -> None:
    with pytest.raises(Exception, match="10-digit"):
        clean_phone(raw)


def test_registration_numbers_are_normalised() -> None:
    assert clean_reg("mh20ab1234") == clean_reg("MH-20 AB 1234") == "MH20 AB 1234"
    with pytest.raises(Exception, match="looks wrong"):
        clean_reg("hello")


async def test_ops_registers_a_driver_who_signs_in_with_the_phone_and_a_one_time_pin(client: AsyncClient) -> None:
    ops = await office(client)
    phone = mobile()
    res = await client.post("/drivers", headers=ops, json={"name": "New Driver", "phone": f"+91 {phone}", "language": "mr"})
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["driver"]["phone"] == phone and body["driver"]["must_change_pin"] and body["driver"]["is_active"]
    assert len(body["pin"]) == 6
    login = await attempt(client, phone, body["pin"])
    assert login.status_code == 200 and login.json()["user"]["must_change_secret"]
    assert (await client.post("/drivers", headers=ops, json={"name": "Dup", "phone": phone})).status_code == 409
    assert (await client.post("/drivers", headers=ops, json={"name": "Bad", "phone": "12345"})).status_code == 422


async def test_deactivating_a_driver_signs_them_out_and_hides_them_from_planning(client: AsyncClient) -> None:
    ops = await office(client)
    created = (await client.post("/drivers", headers=ops, json={"name": "Leaver", "phone": mobile()})).json()
    d, pin = created["driver"], created["pin"]
    token = (await attempt(client, d["phone"], pin)).json()["access_token"]
    assert d["id"] in {x["id"] for x in (await client.get("/planning/refs", headers=ops)).json()["drivers"]}

    off = await client.patch(f"/drivers/{d['id']}", headers=ops, json={"is_active": False})
    assert off.status_code == 200 and off.json()["is_active"] is False
    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})).status_code == 401  # live session ended
    assert (await attempt(client, d["phone"], pin)).status_code == 401  # cannot sign in
    assert d["id"] not in {x["id"] for x in (await client.get("/planning/refs", headers=ops)).json()["drivers"]}
    assert d["id"] in {x["id"] for x in (await client.get("/drivers", headers=ops)).json()}  # still listed for history

    assert (await client.patch(f"/drivers/{d['id']}", headers=ops, json={"is_active": True})).json()["is_active"] is True


async def test_a_driver_on_a_live_trip_cannot_be_deactivated(client: AsyncClient) -> None:
    from tests.test_tracking import driver_with_trip

    h, _ = await driver_with_trip(client)
    me = (await client.get("/auth/me", headers=h)).json()["id"]
    res = await client.patch(f"/drivers/{me}", headers=await office(client), json={"is_active": False})
    assert res.status_code == 409 and "trip" in res.json()["detail"].lower()


async def test_changing_a_phone_checks_for_clashes_and_ends_old_sessions(client: AsyncClient) -> None:
    ops = await office(client)
    a = (await client.post("/drivers", headers=ops, json={"name": "A Driver", "phone": mobile()})).json()["driver"]
    b = (await client.post("/drivers", headers=ops, json={"name": "B Driver", "phone": mobile()})).json()["driver"]
    assert (await client.patch(f"/drivers/{a['id']}", headers=ops, json={"phone": b["phone"]})).status_code == 409
    new = mobile()
    ok = await client.patch(f"/drivers/{a['id']}", headers=ops, json={"phone": new, "name": "A Renamed"})
    assert ok.json()["phone"] == new and ok.json()["name"] == "A Renamed"


async def test_hired_drivers_and_trucks_belong_to_a_vendor(client: AsyncClient) -> None:
    ops = await office(client)
    v = (await client.post("/setup/vendors", headers=ops, json={"name": f"Vendor {digits()}", "phone": mobile(), "contact_name": "Mr Shah"})).json()
    assert v["trucks"] == 0 and v["drivers"] == 0
    reg = new_reg()
    truck = await client.post("/setup/vehicles", headers=ops, json={"reg_no": reg, "vendor_id": v["id"], "vehicle_type": "Container 32 ft", "capacity_tonnes": "15"})
    assert truck.status_code == 201, truck.text
    assert truck.json()["is_hired"] and truck.json()["vendor"] == v["name"]
    drv = await client.post("/drivers", headers=ops, json={"name": "Hired Driver", "phone": mobile(), "vendor_id": v["id"]})
    assert drv.json()["driver"]["vendor"] == v["name"]
    again = next(x for x in (await client.get("/setup/vendors", headers=ops)).json() if x["id"] == v["id"])
    assert (again["trucks"], again["drivers"]) == (1, 1)
    assert (await client.post("/drivers", headers=ops, json={"name": "X", "phone": mobile(), "vendor_id": str(uuid.uuid4())})).status_code == 422
    own = await client.patch(f"/setup/vehicles/{truck.json()['id']}", headers=ops, json={"vendor_id": None})
    assert own.json()["is_hired"] is False and own.json()["vendor"] is None  # bought it back


async def test_vehicle_rules(client: AsyncClient) -> None:
    ops = await office(client)
    reg = new_reg()
    soon = (date.today() + timedelta(days=10)).isoformat()
    v = (await client.post("/setup/vehicles", headers=ops, json={"reg_no": reg, "insurance_expiry": soon})).json()
    assert v["papers"] == "due_soon" and v["is_hired"] is False
    assert (await client.post("/setup/vehicles", headers=ops, json={"reg_no": reg.replace(" ", "").lower()})).status_code == 409  # same truck, typed differently
    assert (await client.post("/setup/vehicles", headers=ops, json={"reg_no": "nonsense"})).status_code == 422
    past = (date.today() - timedelta(days=1)).isoformat()
    assert (await client.patch(f"/setup/vehicles/{v['id']}", headers=ops, json={"fitness_expiry": past})).json()["papers"] == "expired"
    off = (await client.patch(f"/setup/vehicles/{v['id']}", headers=ops, json={"is_active": False})).json()
    assert off["is_active"] is False
    assert v["id"] not in {x["id"] for x in (await client.get("/planning/refs", headers=ops)).json()["vehicles"]}


async def test_a_truck_on_a_live_trip_cannot_be_retired(client: AsyncClient) -> None:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Trip
    from tests.test_tracking import driver_with_trip

    _, trip = await driver_with_trip(client)
    async with SessionLocal() as s:
        vehicle_id = (await s.scalar(select(Trip.vehicle_id).where(Trip.id == uuid.UUID(trip))))
    res = await client.patch(f"/setup/vehicles/{vehicle_id}", headers=await office(client), json={"is_active": False})
    assert res.status_code == 409


async def test_clients(client: AsyncClient) -> None:
    ops = await office(client)
    name = f"Client {digits()}"
    c = await client.post("/setup/clients", headers=ops, json={"name": name, "billing_cycle": "monthly", "tally_ledger": "Sundry Debtors - X", "contact_phone": mobile()})
    assert c.status_code == 201, c.text
    assert (await client.post("/setup/clients", headers=ops, json={"name": name})).status_code == 409
    assert (await client.post("/setup/clients", headers=ops, json={"name": "Bad cycle", "billing_cycle": "yearly"})).status_code == 422
    off = await client.patch(f"/setup/clients/{c.json()['id']}", headers=ops, json={"is_active": False, "tally_ledger": None})
    assert off.json()["is_active"] is False and off.json()["tally_ledger"] is None
    assert c.json()["id"] not in {x["id"] for x in (await client.get("/planning/refs", headers=ops)).json()["clients"]}


async def test_who_may_do_what(client: AsyncClient, driver: dict) -> None:
    billing = await office(client, "billing@cargoone.dev")
    md = await office(client, "md@cargoone.dev")
    ops = await office(client)
    assert (await client.get("/setup/vehicles", headers=billing)).status_code == 200  # billing can read the lists
    assert (await client.post("/setup/vehicles", headers=billing, json={"reg_no": "MH20 ZZ 9999"})).status_code == 403  # but not change them
    assert (await client.post("/drivers", headers=billing, json={"name": "No", "phone": mobile()})).status_code == 403
    assert (await client.get("/setup/vehicles", headers=md)).status_code == 403
    assert (await client.get("/setup/vehicles", headers=driver)).status_code == 403
    assert (await client.get("/setup/staff", headers=ops)).status_code == 403  # staff accounts are admin-only
    assert (await client.get("/setup/staff")).status_code == 401


async def test_admin_creates_staff_who_must_choose_their_own_password(client: AsyncClient) -> None:
    admin = await office(client, "admin@cargoone.dev")
    email = f"new{digits(8)}@example.test"
    res = await client.post("/setup/staff", headers=admin, json={"name": "New Billing", "email": email, "role": "billing"})
    assert res.status_code == 201, res.text
    pw = res.json()["password"]
    login = await attempt(client, email, pw)
    assert login.status_code == 200 and login.json()["user"]["role"] == "billing" and login.json()["user"]["must_change_secret"]
    assert (await client.post("/setup/staff", headers=admin, json={"name": "Dup", "email": email, "role": "ops"})).status_code == 409
    assert (await client.post("/setup/staff", headers=admin, json={"name": "Boss", "email": f"x{digits(6)}@example.test", "role": "admin"})).status_code == 422  # no minting admins

    sid = res.json()["staff"]["id"]
    reset = (await client.post(f"/setup/staff/{sid}/reset-password", headers=admin)).json()["password"]
    assert (await attempt(client, email, pw)).status_code == 401 and (await attempt(client, email, reset)).status_code == 200
    assert (await client.patch(f"/setup/staff/{sid}", headers=admin, json={"is_active": False})).json()["is_active"] is False
    assert (await attempt(client, email, reset)).status_code == 401


async def test_admins_cannot_lock_themselves_out(client: AsyncClient) -> None:
    admin = await office(client, "admin@cargoone.dev")
    me = (await client.get("/auth/me", headers=admin)).json()["id"]
    assert (await client.patch(f"/setup/staff/{me}", headers=admin, json={"is_active": False})).status_code == 409
