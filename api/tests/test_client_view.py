import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update

from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import AccessLink, AuditLog, Trip
from tests.conftest import login
from tests.test_pod_upload import make_trip, post


async def biller(client: AsyncClient) -> dict:
    return await login(client, "billing@cargoone.dev", "cargoone-dev")


async def verified_trip(client: AsyncClient, driver: dict) -> str:
    trip_id, lr = await make_trip()
    assert (await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))).json()["decision"] == "verified"
    return trip_id


async def new_link(client: AsyncClient, trip_id: str) -> str:
    res = await client.post(f"/trips/{trip_id}/view-link", headers=await biller(client))
    assert res.status_code == 201, res.text
    return res.json()["url"].split("/v/")[1]


async def test_client_sees_the_pod_without_login_and_nothing_sensitive(client: AsyncClient, driver: dict) -> None:
    trip_id = await verified_trip(client, driver)
    token = await new_link(client, trip_id)
    info = (await client.get(f"/v/{token}")).json()  # no Authorization header
    assert set(info) == {"trip_code", "lr_no", "vehicle", "origin", "destination", "delivered_at", "verified_at", "expires_at", "company"}
    img = await client.get(f"/v/{token}/image")
    assert img.status_code == 200 and img.headers["content-type"].startswith("image/") and img.headers["cache-control"] == "private, no-store"


async def test_unverified_pods_cannot_be_shared(client: AsyncClient) -> None:
    trip_id, _ = await make_trip()  # still awaiting POD
    assert (await client.post(f"/trips/{trip_id}/view-link", headers=await biller(client))).status_code == 409
    assert (await client.post(f"/trips/{uuid.uuid4()}/view-link", headers=await biller(client))).status_code == 404


async def test_link_dies_if_the_pod_stops_being_verified(client: AsyncClient, driver: dict) -> None:
    trip_id = await verified_trip(client, driver)
    token = await new_link(client, trip_id)
    async with SessionLocal() as s:
        await s.execute(update(Trip).where(Trip.id == uuid.UUID(trip_id)).values(pod_status="needs_review"))
        await s.commit()
    assert (await client.get(f"/v/{token}")).status_code == 404


async def test_views_are_counted_and_new_link_revokes_old_one(client: AsyncClient, driver: dict) -> None:
    trip_id = await verified_trip(client, driver)
    old = await new_link(client, trip_id)
    for _ in range(2):
        await client.get(f"/v/{old}")
    rows = (await client.get(f"/trips/{trip_id}/view-links", headers=await biller(client))).json()
    assert rows[0]["views"] == 2 and rows[0]["last_viewed_at"] is not None
    new = await new_link(client, trip_id)
    assert (await client.get(f"/v/{old}")).status_code == 410 and (await client.get(f"/v/{new}")).status_code == 200
    rows = (await client.get(f"/trips/{trip_id}/view-links", headers=await biller(client))).json()
    assert [r["revoked"] for r in rows] == [False, True]


async def test_revoke_expiry_and_garbage_tokens(client: AsyncClient, driver: dict) -> None:
    trip_id = await verified_trip(client, driver)
    token = await new_link(client, trip_id)
    assert (await client.delete(f"/trips/{trip_id}/view-link", headers=await biller(client))).status_code == 204
    assert (await client.get(f"/v/{token}")).status_code == 410
    token2 = await new_link(client, trip_id)
    async with SessionLocal() as s:
        await s.execute(update(AccessLink).where(AccessLink.trip_id == uuid.UUID(trip_id)).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        await s.commit()
    assert (await client.get(f"/v/{token2}/image")).status_code == 410
    assert (await client.get("/v/not-a-real-token-at-all-0123456789")).status_code == 404


async def test_upload_and_view_links_are_not_interchangeable(client: AsyncClient, driver: dict) -> None:
    trip_id = await verified_trip(client, driver)
    view = await new_link(client, trip_id)
    assert (await client.get(f"/u/{view}")).status_code == 404  # a client link cannot open the upload page
    async with SessionLocal() as s:
        stored = (await s.scalars(select(AccessLink.token).where(AccessLink.trip_id == uuid.UUID(trip_id)))).all()
    assert view not in stored and all(len(t) == 64 for t in stored)  # only the hash is stored


async def test_roles_and_audit(client: AsyncClient, driver: dict) -> None:
    trip_id = await verified_trip(client, driver)
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    for h in (driver, md):
        assert (await client.post(f"/trips/{trip_id}/view-link", headers=h)).status_code == 403
        assert (await client.get(f"/trips/{trip_id}/view-links", headers=h)).status_code == 403
    assert (await client.post(f"/trips/{trip_id}/view-link")).status_code == 401
    token = await new_link(client, trip_id)
    await client.get(f"/v/{token}")
    async with SessionLocal() as s:
        view = (await s.scalars(select(AuditLog).where(AuditLog.action == "client_link.view").order_by(AuditLog.at.desc()).limit(1))).first()
    assert view.actor_id is None and token not in str(view.meta) and view.entity_id != token
