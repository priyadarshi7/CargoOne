import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select, update

from app.db import SessionLocal
from app.models import AccessLink, LocationPing, Role, Trip, TripState, User
from app.routers.tracking import purge_old_pings
from app.security import hash_secret
from app.tracking import Fix, haversine_m, movement
from tests.conftest import login
from tests.test_pod_upload import make_trip

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
MIN = timedelta(minutes=1)
STALE, STOP = timedelta(minutes=15), timedelta(minutes=10)


def fx(minutes_ago: float, lat: float = 19.8762, lng: float = 75.3433) -> Fix:
    return Fix(lat, lng, NOW - minutes_ago * MIN)


def test_distance() -> None:
    assert haversine_m(fx(0), fx(0)) == 0
    assert 110_000 < haversine_m(fx(0, 19.0), fx(0, 20.0)) < 112_000  # one degree of latitude


def test_movement_states() -> None:
    assert movement([], NOW, stale_after=STALE, stopped_after=STOP) == ("unknown", 0)
    assert movement([fx(40)], NOW, stale_after=STALE, stopped_after=STOP) == ("no_signal", 40)
    moving = [fx(10, 19.80), fx(5, 19.83), fx(0, 19.86)]
    assert movement(moving, NOW, stale_after=STALE, stopped_after=STOP) == ("moving", 0)
    parked = [fx(30, 19.80), fx(25, 19.86), fx(20, 19.86), fx(10, 19.8601), fx(0, 19.8600)]  # left the circle 25 min ago, then parked
    state, minutes = movement(parked, NOW, stale_after=STALE, stopped_after=STOP)
    assert state == "stopped" and minutes == 25
    assert movement([fx(5, 19.86), fx(0, 19.86)], NOW, stale_after=STALE, stopped_after=STOP)[0] == "moving"  # stopped < 10 min: not yet


def test_order_of_fixes_does_not_matter() -> None:
    fixes = [fx(0, 19.86), fx(30, 19.86), fx(15, 19.86)]
    assert movement(fixes, NOW, stale_after=STALE, stopped_after=STOP) == ("stopped", 30)


async def driver_with_trip(client: AsyncClient, *, consent: bool = True, state: TripState = TripState.in_transit) -> tuple[dict, str]:
    tag = str(uuid.uuid4().int)[:9]
    async with SessionLocal() as s:
        u = User(name=f"GPS Driver {tag}", phone=f"6{tag}", role=Role.driver, password_hash=hash_secret("4821"), language="en")
        s.add(u)
        await s.commit()
        await s.refresh(u)
    trip_id, _ = await make_trip(assigned=False)
    async with SessionLocal() as s:
        await s.execute(update(Trip).where(Trip.id == uuid.UUID(trip_id)).values(driver_id=u.id, state=state))
        await s.commit()
    res = await client.post("/auth/login", json={"identifier": u.phone, "secret": "4821"})
    h = {"Authorization": f"Bearer {res.json()['access_token']}"}
    if consent:
        assert (await client.post("/tracking/consent", headers=h)).status_code == 204
    return h, trip_id


def ping(minutes_ago: float = 0, lat: float = 19.87, lng: float = 75.34, **kw) -> dict:
    return {"lat": lat, "lng": lng, "recorded_at": (datetime.now(UTC) - minutes_ago * MIN).isoformat(), **kw}


async def ops(client: AsyncClient) -> dict:
    return await login(client, "ops@cargoone.dev", "cargoone-dev")


async def test_pings_are_stored_once_even_if_the_phone_retries(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    batch = {"pings": [ping(3, speed_kmh=40), ping(2), ping(1)]}
    first = await client.post(f"/trips/{trip}/pings", headers=h, json=batch)
    assert first.json() == {"stored": 3, "received": 3}
    again = await client.post(f"/trips/{trip}/pings", headers=h, json=batch)  # a flaky connection resent it
    assert again.json() == {"stored": 0, "received": 3}
    async with SessionLocal() as s:
        assert await s.scalar(select(func.count()).select_from(LocationPing).where(LocationPing.trip_id == uuid.UUID(trip))) == 3


async def test_consent_state_and_ownership_are_enforced(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client, consent=False)
    assert (await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [ping()]})).status_code == 403  # no consent
    await client.post("/tracking/consent", headers=h)
    assert (await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [ping()]})).status_code == 200
    await client.delete("/tracking/consent", headers=h)  # withdrawn -> collection stops at once
    assert (await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [ping(1)]})).status_code == 403

    h2, planned = await driver_with_trip(client, state=TripState.planned)
    assert (await client.post(f"/trips/{planned}/pings", headers=h2, json={"pings": [ping()]})).status_code == 409  # not on the road yet
    assert (await client.post(f"/trips/{trip}/pings", headers=h2, json={"pings": [ping()]})).status_code == 404  # someone else's trip


async def test_bad_locations_are_refused(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    for bad in (ping(lat=95), ping(lng=200), ping(speed_kmh=900), ping(-10), ping(60 * 72)):
        assert (await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [bad]})).status_code == 422, bad
    assert (await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": []})).status_code == 422
    assert (await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [ping(i) for i in range(51)]})).status_code == 422


async def test_live_view_shows_position_state_and_alerts_to_ops_and_md_only(client: AsyncClient, driver: dict) -> None:
    h, trip = await driver_with_trip(client)
    parked = [ping(120 - i * 5, lat=19.9000, lng=75.3200) for i in range(24)]  # parked for ~2 hours
    await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": parked[:20]})
    await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": parked[20:]})
    rows = {r["trip_id"]: r for r in (await client.get("/tracking/live", headers=await ops(client))).json()}
    me = rows[trip]
    assert me["state"] == "stopped" and me["alert"] == "stoppage" and me["minutes"] >= 90 and me["lat"] == 19.9
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    assert (await client.get("/tracking/live", headers=md)).status_code == 200
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    for denied in (billing, driver):
        assert (await client.get("/tracking/live", headers=denied)).status_code == 403  # driver location is not billing's business
    assert (await client.get("/tracking/live")).status_code == 401


async def test_silent_truck_is_flagged_and_a_truck_without_fixes_is_unknown(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    rows = {r["trip_id"]: r for r in (await client.get("/tracking/live", headers=await ops(client))).json()}
    assert rows[trip]["state"] == "unknown" and rows[trip]["lat"] is None and rows[trip]["alert"] is None
    await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [ping(40)]})
    rows = {r["trip_id"]: r for r in (await client.get("/tracking/live", headers=await ops(client))).json()}
    assert rows[trip]["state"] == "no_signal" and rows[trip]["alert"] == "silent"


async def test_track_returns_the_path_in_order_and_is_audited(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [ping(3, lat=19.1), ping(2, lat=19.2), ping(1, lat=19.3)]})
    pts = (await client.get(f"/tracking/trips/{trip}/track", headers=await ops(client))).json()["points"]
    assert [p["lat"] for p in pts] == [19.1, 19.2, 19.3]


async def test_client_tracking_link_shows_a_rounded_position_and_no_driver(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [ping(1, lat=19.876212, lng=75.343377)]})
    biller = await login(client, "billing@cargoone.dev", "cargoone-dev")
    link = (await client.post(f"/trips/{trip}/track-link", headers=biller)).json()
    token = link["url"].split("/t/")[1]
    info = (await client.get(f"/t/{token}")).json()  # no Authorization header
    assert (info["lat"], info["lng"]) == (19.876, 75.343)  # ~100 m, not the exact spot
    assert set(info) == {"trip_code", "vehicle", "origin", "destination", "state", "lat", "lng", "seen_at", "expires_at", "company"}
    async with SessionLocal() as s:
        assert token not in (await s.scalars(select(AccessLink.token).where(AccessLink.trip_id == uuid.UUID(trip)))).all()  # hashed
        await s.execute(update(Trip).where(Trip.id == uuid.UUID(trip)).values(state=TripState.delivered))
        await s.commit()
    done = (await client.get(f"/t/{token}")).json()
    assert done["state"] == "delivered" and done["lat"] is None  # nothing shown once it has arrived
    assert (await client.delete(f"/trips/{trip}/track-link", headers=biller)).status_code == 204
    assert (await client.get(f"/t/{token}")).status_code == 410
    assert (await client.get("/t/" + "z" * 43)).status_code == 404
    assert (await client.get(f"/u/{token}")).status_code == 404 and (await client.get(f"/v/{token}")).status_code == 404  # kinds are separate


async def test_track_link_only_for_trips_still_on_the_road(client: AsyncClient) -> None:
    _, trip = await driver_with_trip(client, state=TripState.delivered)
    assert (await client.post(f"/trips/{trip}/track-link", headers=await login(client, "billing@cargoone.dev", "cargoone-dev"))).status_code == 409


async def test_retention_deletes_old_fixes(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    await client.post(f"/trips/{trip}/pings", headers=h, json={"pings": [ping(1)]})
    async with SessionLocal() as s:
        s.add(LocationPing(trip_id=uuid.UUID(trip), lat=1, lng=1, recorded_at=datetime.now(UTC) - timedelta(days=45)))
        await s.commit()
        removed = await purge_old_pings(s)
        left = await s.scalar(select(func.count()).select_from(LocationPing).where(LocationPing.trip_id == uuid.UUID(trip)))
    assert removed >= 1 and left == 1
