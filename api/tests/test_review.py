import uuid

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import AuditLog, PodStatus, Trip
from tests.conftest import login
from tests.test_pod_upload import make_trip, post


async def shortage_trip(client: AsyncClient, driver: dict) -> tuple[str, str, str]:
    trip_id, lr = await make_trip()
    body = (await post(client, driver, trip_id, render(SCENARIOS["shortage"], lr))).json()
    assert body["decision"] == "needs_review"
    return trip_id, lr, body["submission_id"]


async def billing(client: AsyncClient) -> dict:
    return await login(client, "billing@cargoone.dev", "cargoone-dev")


async def status_of(trip_id: str) -> PodStatus:
    async with SessionLocal() as s:
        return (await s.get(Trip, uuid.UUID(trip_id))).pod_status


async def test_queue_lists_review_items_without_pii(client: AsyncClient, driver: dict) -> None:
    trip_id, _, sub_id = await shortage_trip(client, driver)
    res = await client.get("/review", headers=await billing(client))
    assert res.status_code == 200
    item = next(i for i in res.json() if i["trip_id"] == trip_id)
    assert item["submission_id"] == sub_id and "shortage_or_damage" in item["reasons"]
    assert item["ai"]["remarks"] == "Short by 6 cartons"
    assert "_voice" not in item["ai"] and "Demo Consignee" not in res.text


async def test_only_billing_and_ops_can_review(client: AsyncClient, driver: dict) -> None:
    trip_id, _, _ = await shortage_trip(client, driver)
    assert (await client.get("/review", headers=driver)).status_code == 403
    assert (await client.get("/review")).status_code == 401
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    assert (await client.post(f"/review/{trip_id}/decision", headers=md, json={"action": "approve"})).status_code == 403


async def test_approve_with_corrections_verifies_and_audits(client: AsyncClient, driver: dict) -> None:
    trip_id, _, _ = await shortage_trip(client, driver)
    h = await billing(client)
    res = await client.post(f"/review/{trip_id}/decision", headers=h, json={
        "action": "approve", "corrected": {"remarks": "6 cartons short, accepted", "quantity_received": "48 cartons"},
        "note": "client confirmed on call"})
    assert res.status_code == 200, res.text
    assert res.json()["corrected"]["quantity_received"] == "48 cartons"
    assert res.json()["ai"]["remarks"] == "Short by 6 cartons"  # AI output preserved next to the correction
    assert await status_of(trip_id) == PodStatus.verified
    async with SessionLocal() as s:
        n = await s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "review.approve", AuditLog.entity_id == trip_id))
    assert n == 1
    again = await client.post(f"/review/{trip_id}/decision", headers=h, json={"action": "approve"})
    assert again.status_code == 409  # cannot decide twice


async def test_cannot_approve_when_lr_does_not_match_trip(client: AsyncClient, driver: dict) -> None:
    trip_id, _, _ = await shortage_trip(client, driver)
    res = await client.post(f"/review/{trip_id}/decision", headers=await billing(client),
                            json={"action": "approve", "corrected": {"lr_no": "LR-WRONG"}})
    assert res.status_code == 422 and await status_of(trip_id) == PodStatus.needs_review


async def test_retake_then_cap_forces_approve_or_reject(client: AsyncClient, driver: dict) -> None:
    h = await billing(client)
    trip_id, lr, _ = await shortage_trip(client, driver)
    assert (await client.post(f"/review/{trip_id}/decision", headers=h, json={"action": "request_retake"})).status_code == 200
    assert await status_of(trip_id) == PodStatus.retake_requested
    # driver retakes, again lands in review; second human retake allowed, third is not
    for expected in (200, 409):
        await post(client, driver, trip_id, render(SCENARIOS["shortage"], lr))
        res = await client.post(f"/review/{trip_id}/decision", headers=h, json={"action": "request_retake"})
        assert res.status_code == expected, res.text
        if expected == 200:
            assert res.json()["retakes_left"] == 0
    rejected = await client.post(f"/review/{trip_id}/decision", headers=h, json={"action": "reject"})
    assert rejected.status_code == 200 and await status_of(trip_id) == PodStatus.rejected


async def test_unknown_trip_404(client: AsyncClient) -> None:
    res = await client.get(f"/review/{uuid.uuid4()}", headers=await billing(client))
    assert res.status_code == 404
