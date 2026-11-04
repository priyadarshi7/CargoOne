from typing import Annotated

from fastapi import Depends
from httpx import AsyncClient

from app.main import app
from app.models import Role, User
from app.security import require_roles
from tests.conftest import login


@app.get("/_test/billing-only")
async def _billing_only(user: Annotated[User, Depends(require_roles(Role.billing))]) -> dict[str, str]:
    return {"role": user.role.value}


async def test_office_login_and_me(client: AsyncClient) -> None:
    headers = await login(client, "billing@cargoone.dev", "cargoone-dev")
    me = await client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["role"] == "billing"


async def test_driver_logs_in_with_phone_and_pin(client: AsyncClient) -> None:
    headers = await login(client, "9000000001", "1234")
    me = await client.get("/auth/me", headers=headers)
    assert me.json()["role"] == "driver"
    assert me.json()["language"] == "mr"


async def test_wrong_secret_and_unknown_user_look_identical(client: AsyncClient) -> None:
    bad = await client.post("/auth/login", json={"identifier": "billing@cargoone.dev", "secret": "nope1"})
    unknown = await client.post("/auth/login", json={"identifier": "ghost@cargoone.dev", "secret": "nope1"})
    assert bad.status_code == unknown.status_code == 401
    assert bad.json() == unknown.json()


async def test_requires_token(client: AsyncClient) -> None:
    assert (await client.get("/auth/me")).status_code == 401
    bad = await client.get("/auth/me", headers={"Authorization": "Bearer garbage"})
    assert bad.status_code == 401


async def test_role_guard(client: AsyncClient) -> None:
    driver = await login(client, "9000000001", "1234")
    assert (await client.get("/_test/billing-only", headers=driver)).status_code == 403
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    assert (await client.get("/_test/billing-only", headers=billing)).status_code == 200
    admin = await login(client, "admin@cargoone.dev", "cargoone-dev")  # admin always allowed
    assert (await client.get("/_test/billing-only", headers=admin)).status_code == 200
