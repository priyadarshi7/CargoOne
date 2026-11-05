"""Role home numbers: office roles only, and the MD never sees the freight total."""
from httpx import AsyncClient

from tests.test_pin_reset import office


async def test_home_counts_for_each_office_role(client: AsyncClient) -> None:
    for who in ("ops@cargoone.dev", "billing@cargoone.dev"):
        res = await client.get("/home", headers=await office(client, who))
        assert res.status_code == 200
        body = res.json()
        assert {"planned", "in_transit", "pod_missing", "awaiting_review", "requests_new", "ready_to_bill", "ready_amount"} <= body.keys()
        assert body["ready_amount"] is not None


async def test_md_gets_counts_without_the_freight_total(client: AsyncClient) -> None:
    res = await client.get("/home", headers=await office(client, "md@cargoone.dev"))
    assert res.status_code == 200
    assert res.json()["ready_amount"] is None


async def test_home_needs_an_office_login(client: AsyncClient) -> None:
    assert (await client.get("/home")).status_code == 401
