"""Place suggestions and the exact map positions that come with the origin and destination fields."""
import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app import places
from app.db import SessionLocal
from app.models import TransportRequest, Trip
from app.places import _fetch as real_fetch  # captured before the tests replace it
from app.routers import places as places_router
from tests.test_notifications import onboard, plan_for, register
from tests.test_pin_reset import office
from tests.test_requests import payload, submit

PHOTON = {"features": [
    {"geometry": {"coordinates": [75.2145, 19.8601]}, "properties": {"name": "Waluj MIDC", "district": "Waluj", "city": "Chhatrapati Sambhajinagar", "state": "Maharashtra", "countrycode": "IN"}},
    {"geometry": {"coordinates": [75.2145, 19.8601]}, "properties": {"name": "Waluj MIDC duplicate point", "city": "Chhatrapati Sambhajinagar", "state": "Maharashtra", "countrycode": "IN"}},
    {"geometry": {"coordinates": [-0.13, 51.5]}, "properties": {"name": "Waluj Street", "city": "London", "countrycode": "GB"}},
    {"geometry": {"coordinates": [75.35, 19.9]}, "properties": {"street": "Jalna Road", "housenumber": "12", "city": "Chhatrapati Sambhajinagar", "state": "Maharashtra", "countrycode": "IN"}},
    {"geometry": {"coordinates": "broken"}, "properties": {"name": "Broken", "countrycode": "IN"}},
]}


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    places._cache.clear()
    places_router.limiter.reset()
    calls: list[str] = []

    async def fake(q, transport=None):
        calls.append(q)
        return PHOTON

    monkeypatch.setattr(places, "_fetch", fake)
    return calls


async def test_suggestions_are_indian_places_with_positions_and_a_label_that_fits_the_field(client: AsyncClient) -> None:
    res = await client.get("/places/search", params={"q": "waluj"})  # public: the company form has no login
    assert res.status_code == 200
    got = res.json()
    assert [p["name"] for p in got] == ["Waluj MIDC", "12 Jalna Road"]  # London dropped, duplicate point dropped, broken row dropped
    first = got[0]
    assert first["label"] == "Waluj MIDC, Waluj, Chhatrapati Sambhajinagar, Maharashtra" and len(first["label"]) <= 120
    assert (first["lat"], first["lng"]) == (19.8601, 75.2145)  # latitude first, even though the provider sends longitude first


async def test_the_search_is_guarded_and_cached(client: AsyncClient, fresh, monkeypatch) -> None:
    assert (await client.get("/places/search", params={"q": "ab"})).status_code == 422  # too short to be worth a lookup
    await client.get("/places/search", params={"q": "Waluj"})
    await client.get("/places/search", params={"q": "  waluj "})
    assert fresh == ["Waluj"]  # the second ask was answered from memory
    monkeypatch.setattr(places_router.limiter, "max_hits", 3)  # the real limit is 60 a minute
    codes = [(await client.get("/places/search", params={"q": f"waluj{i}"})).status_code for i in range(4)]
    assert codes[-1] == 429


async def test_when_the_provider_is_down_the_form_is_told_to_let_people_type(client: AsyncClient, monkeypatch) -> None:
    async def down(q, transport=None):
        raise places.PlacesUnavailable("ConnectError")

    monkeypatch.setattr(places, "_fetch", down)
    res = await client.get("/places/search", params={"q": "waluj"})
    assert res.status_code == 503 and "Type the place" in res.json()["detail"]


async def test_the_provider_request_asks_for_india_near_the_depot() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.url.params)
        seen["agent"] = request.headers["user-agent"]
        return httpx.Response(200, json={"features": []})

    await real_fetch("waluj", httpx.MockTransport(handler))
    assert seen["bbox"] == places.INDIA_BBOX and seen["q"] == "waluj" and seen["agent"] == "CargoOne/1.0"  # no personal contact in the agent
    assert (float(seen["lat"]), float(seen["lon"])) == places.BIAS


async def test_a_request_keeps_the_exact_places_picked(client: AsyncClient) -> None:
    sent = await submit(client, origin_lat=19.8601, origin_lng=75.2145, destination_lat=18.5204, destination_lng=73.8567)
    async with SessionLocal() as s:
        r = (await s.scalars(select(TransportRequest).where(TransportRequest.reference == sent["reference"]))).one()
    assert (r.origin_lat, r.origin_lng, r.destination_lat, r.destination_lng) == (19.8601, 75.2145, 18.5204, 73.8567)
    ops = await office(client)
    listed = next(x for x in (await client.get("/requests?state=open", headers=ops)).json() if x["reference"] == sent["reference"])
    assert listed["destination_lat"] == 18.5204  # the office sees it and planning carries it into the trip


async def test_a_request_without_picked_places_still_works_and_bad_positions_are_refused(client: AsyncClient) -> None:
    await submit(client)  # typed freely: no positions
    for bad in ({"origin_lat": 19.8}, {"destination_lng": 73.8}, {"origin_lat": 51.5, "origin_lng": -0.1}, {"destination_lat": 999, "destination_lng": 73.8}):
        assert (await client.post("/public/requests", json=payload(**bad))).status_code == 422, bad


async def test_a_planned_trip_keeps_the_drop_point_and_the_driver_gets_it_for_navigation(client: AsyncClient) -> None:
    ops = await office(client)
    made = await register(client, ops)
    driver = await onboard(client, made["invite"]["url"])
    await plan_for(client, ops, made["driver"]["id"], destination_lat=18.5204, destination_lng=73.8567, origin_lat=19.8601, origin_lng=75.2145)
    mine = (await client.get("/trips/mine", headers=driver)).json()
    assert (mine[0]["destination_lat"], mine[0]["destination_lng"]) == (18.5204, 73.8567)
    async with SessionLocal() as s:
        t = (await s.scalars(select(Trip).where(Trip.driver_id == made["driver"]["id"]))).one()
    assert (t.origin_lat, t.origin_lng) == (19.8601, 75.2145)
