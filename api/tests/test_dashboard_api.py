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


async def test_md_digest_is_a_real_pdf_and_restricted(client: AsyncClient, driver: dict) -> None:
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    res = await client.get("/dashboard/digest.pdf", headers=md)
    assert res.status_code == 200 and res.content.startswith(b"%PDF") and "attachment" in res.headers["content-disposition"]
    assert (await client.get("/dashboard/digest.pdf?days=3", headers=md)).status_code == 422
    biller = await login(client, "billing@cargoone.dev", "cargoone-dev")
    for h in (driver, biller):
        assert (await client.get("/dashboard/digest.pdf", headers=h)).status_code == 403
    assert (await client.get("/dashboard/digest.pdf")).status_code == 401


async def test_counts_waiting_on_a_person_agree_everywhere_and_ignore_the_window(client: AsyncClient, driver: dict) -> None:
    """The Today tab, the review queue and the dashboard must say the same number, even for a POD that has waited longer than the window."""
    import uuid
    from datetime import UTC, datetime, timedelta

    from app.db import SessionLocal
    from app.devtools.synthetic_pod import SCENARIOS, render
    from app.models import Trip
    from tests.test_pod_upload import make_trip, post

    tid, lr = await make_trip()
    assert (await post(client, driver, tid, render(SCENARIOS["shortage"], lr))).json()["decision"] == "needs_review"
    async with SessionLocal() as s:
        t = await s.get(Trip, uuid.UUID(tid))
        t.delivered_at = datetime.now(UTC) - timedelta(days=60)  # older than the 30-day view
        await s.commit()
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    queue = len((await client.get("/review", headers=billing)).json())
    today = (await client.get("/home", headers=billing)).json()["awaiting_review"]
    missing = (await client.get("/home", headers=billing)).json()["pod_missing"]
    ready = (await client.get("/home", headers=billing)).json()["ready_to_bill"]
    for days in (30, 90):
        board = (await client.get(f"/dashboard?days={days}", headers=md)).json()
        assert board["pipeline"]["awaiting_review"] == queue == today
        assert board["missing"]["total"] == missing  # delivered over a day ago, no usable POD: one rule everywhere
        assert board["pipeline"]["ready_to_bill"] == ready
