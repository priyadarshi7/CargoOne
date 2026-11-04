from httpx import AsyncClient

from tests.conftest import login


async def test_ops_and_md_can_read_dashboard(client: AsyncClient) -> None:
    for who in ("ops@cargoone.dev", "md@cargoone.dev"):
        res = await client.get("/dashboard", headers=await login(client, who, "cargoone-dev"))
        assert res.status_code == 200, res.text
        body = res.json()
        assert {"kpis", "targets", "working_capital", "missing", "pipeline", "branches", "trend", "oldest_missing"} <= body.keys()
        assert body["targets"]["within_24h_pct"] == 80 and body["targets"]["baseline_pod_to_invoice_days"] == 18


async def test_billing_and_drivers_cannot_read_dashboard(client: AsyncClient, driver: dict) -> None:
    assert (await client.get("/dashboard", headers=driver)).status_code == 403
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    assert (await client.get("/dashboard", headers=billing)).status_code == 403
    assert (await client.get("/dashboard")).status_code == 401


async def test_window_is_validated_and_output_has_no_personal_data(client: AsyncClient) -> None:
    h = await login(client, "md@cargoone.dev", "cargoone-dev")
    assert (await client.get("/dashboard?days=3", headers=h)).status_code == 422
    res = await client.get("/dashboard?days=30", headers=h)
    assert res.status_code == 200 and "Demo Consignee" not in res.text and "9000000099" not in res.text
