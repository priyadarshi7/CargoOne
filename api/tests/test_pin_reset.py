import uuid

from httpx import AsyncClient
from sqlalchemy import Text, cast, func, select

from app.auth_policy import check_secret
from app.db import SessionLocal
from app.models import AuditLog, Role, User
from app.routers.auth import ident_failures, ip_failures
from app.routers.drivers import temporary_pin
from app.security import hash_secret
from tests.test_login_hardening import attempt, make_user


async def office(client: AsyncClient, who: str = "ops@cargoone.dev") -> dict:
    res = await attempt(client, who, "cargoone-dev")
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def new_driver() -> User:
    tag = str(uuid.uuid4().int)[:9]
    async with SessionLocal() as s:
        u = User(name=f"Driver {tag}", phone=f"8{tag}", role=Role.driver, password_hash=hash_secret("4821"), language="hi")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def test_reset_gives_a_one_time_pin_and_forces_a_new_one(client: AsyncClient) -> None:
    d = await new_driver()
    old = (await attempt(client, d.phone, "4821")).json()["access_token"]
    res = await client.post(f"/drivers/{d.id}/reset-pin", headers=await office(client))
    assert res.status_code == 200
    temp = res.json()["pin"]
    assert len(temp) == 6 and temp.isdigit()

    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {old}"})).status_code == 401  # old session void
    assert (await attempt(client, d.phone, "4821")).status_code == 401  # old PIN void
    login = await attempt(client, d.phone, temp)
    assert login.status_code == 200 and login.json()["user"]["must_change_secret"] is True
    h = {"Authorization": f"Bearer {login.json()['access_token']}"}

    blocked = await client.get("/trips/mine", headers=h)  # nothing works until a PIN is chosen
    assert blocked.status_code == 403 and "own PIN" in blocked.json()["detail"]
    assert (await client.get("/auth/me", headers=h)).status_code == 200
    assert (await client.post("/auth/change-secret", headers=h, json={"current": temp, "new": temp})).status_code == 422  # cannot keep it
    done = await client.post("/auth/change-secret", headers=h, json={"current": temp, "new": "730194"})
    assert done.status_code == 200 and done.json()["user"]["must_change_secret"] is False
    assert (await client.get("/trips/mine", headers={"Authorization": f"Bearer {done.json()['access_token']}"})).status_code == 200


async def test_reset_unlocks_a_locked_driver(client: AsyncClient) -> None:
    d = await new_driver()
    for _ in range(5):
        await attempt(client, d.phone, "0000x")
    listed = (await client.get("/drivers", headers=await office(client))).json()
    assert next(x for x in listed if x["id"] == str(d.id))["locked"] is True
    ident_failures.reset()
    ip_failures.reset()
    temp = (await client.post(f"/drivers/{d.id}/reset-pin", headers=await office(client))).json()["pin"]
    assert (await attempt(client, d.phone, temp)).status_code == 200


async def test_only_drivers_can_be_reset_and_only_by_ops_or_billing(client: AsyncClient, driver: dict) -> None:
    d = await new_driver()
    other_office = await make_user(Role.ops)
    assert (await client.post(f"/drivers/{other_office.id}/reset-pin", headers=await office(client))).status_code == 404
    assert (await client.post(f"/drivers/{uuid.uuid4()}/reset-pin", headers=await office(client))).status_code == 404
    md = await office(client, "md@cargoone.dev")
    for h in (driver, md):
        assert (await client.post(f"/drivers/{d.id}/reset-pin", headers=h)).status_code == 403
        assert (await client.get("/drivers", headers=h)).status_code == 403
    assert (await client.post(f"/drivers/{d.id}/reset-pin")).status_code == 401
    assert (await client.post(f"/drivers/{d.id}/reset-pin", headers=await office(client, "billing@cargoone.dev"))).status_code == 200


async def test_the_pin_is_never_stored_or_audited(client: AsyncClient) -> None:
    d = await new_driver()
    temp = (await client.post(f"/drivers/{d.id}/reset-pin", headers=await office(client))).json()["pin"]
    async with SessionLocal() as s:
        stored = await s.scalar(select(User.password_hash).where(User.id == d.id))
        in_audit = await s.scalar(select(func.count()).select_from(AuditLog).where(cast(AuditLog.meta, Text).contains(temp)))
        logged = await s.scalar(select(AuditLog.action).where(AuditLog.entity_id == str(d.id), AuditLog.action == "pin.reset"))
    assert temp not in stored and in_audit == 0 and logged == "pin.reset"


def test_temporary_pins_always_pass_the_policy() -> None:
    assert all(check_secret(temporary_pin(), is_pin=True) is None for _ in range(300))
