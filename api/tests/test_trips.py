from httpx import AsyncClient

from tests.conftest import login


async def test_office_sees_all_seed_trips_without_consignee_pii(client: AsyncClient) -> None:
    h = await login(client, "billing@cargoone.dev", "cargoone-dev")
    res = await client.get("/trips", headers=h)
    assert res.status_code == 200
    codes = {t["trip_code"] for t in res.json()}
    assert {"TRP-66120", "TRP-66134", "TRP-66141"} <= codes
    assert "Demo Consignee" not in res.text and "9000000099" not in res.text  # DPDP: PII not listed
    assert all(len(t["eway_bill_no"]) == 12 for t in res.json())


async def test_md_can_read_but_driver_cannot_list_all(client: AsyncClient) -> None:
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    assert (await client.get("/trips", headers=md)).status_code == 200
    driver = await login(client, "9000000001", "1234")
    assert (await client.get("/trips", headers=driver)).status_code == 403


async def test_driver_sees_only_own_trips(client: AsyncClient) -> None:
    h = await login(client, "9000000001", "1234")
    res = await client.get("/trips/mine", headers=h)
    assert res.status_code == 200
    codes = {t["trip_code"] for t in res.json()}
    assert "TRP-66141" not in codes  # hired-driver trip is not assigned to this driver
    assert {"TRP-66120", "TRP-66134"} <= codes


async def test_office_cannot_use_driver_endpoint_and_anon_blocked(client: AsyncClient) -> None:
    ops = await login(client, "ops@cargoone.dev", "cargoone-dev")
    assert (await client.get("/trips/mine", headers=ops)).status_code == 403
    assert (await client.get("/trips")).status_code == 401
