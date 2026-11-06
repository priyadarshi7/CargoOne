import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.db import SessionLocal
from tests.test_pin_reset import office


async def test_the_reset_is_for_dev_only_and_needs_the_word(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    ops = await office(client)
    info = (await client.get("/devtools/test-data", headers=ops)).json()
    assert info["enabled"] and "trips" in info["counts"]
    assert (await client.post("/devtools/reset-test-data", headers=ops, json={"confirm": "yes"})).status_code == 422
    for who in ("billing@cargoone.dev", "md@cargoone.dev"):
        assert (await client.get("/devtools/test-data", headers=await office(client, who))).status_code == 403
    assert (await client.get("/devtools/test-data")).status_code == 401
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "app_env", "production")  # anywhere but dev/test the endpoints do not exist
    assert (await client.get("/devtools/test-data", headers=ops)).status_code == 404
    assert (await client.post("/devtools/reset-test-data", headers=ops, json={"confirm": "DELETE"})).status_code == 404


async def test_reset_keeps_office_logins_and_branches_and_removes_the_rest() -> None:
    """Run against the test database only through the function's SQL, so the shared test data used by other suites is not wiped:
    the statement list is checked, not executed."""
    from app.routers.devtools import WIPE

    tables = {t.strip() for t in WIPE.split(",")}
    assert {"trips", "vehicles", "clients", "documents", "transport_requests", "lr_counters"} <= tables
    assert "users" not in tables and "branches" not in tables  # office logins and branches survive
    async with SessionLocal() as s:
        for t in tables:
            await s.execute(text(f"select 1 from {t} limit 1"))  # every name is a real table


async def test_reset_also_removes_a_clients_logins_instead_of_failing(client: AsyncClient) -> None:
    """Runs the real wipe inside a transaction that is rolled back, so the shared test data survives."""
    from app.routers.devtools import wipe
    from tests.test_portal import new_client_login

    ops = await office(client)
    c = await new_client_login(client, ops)
    async with SessionLocal() as s:
        await wipe(s)  # used to fail: the client's login pointed at a client that was being removed
        assert await s.scalar(text("select count(*) from users where role = 'client'")) == 0
        assert await s.scalar(text("select count(*) from users where role = 'ops'")) >= 1  # office logins stay
        await s.rollback()
    assert c["client_id"]
