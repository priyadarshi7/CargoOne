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


# ---------------------------------------------------------------- Google (Places API (New) + Geocoding), with a fake Google


KEY = "test-server-key-1234567890"


@pytest.fixture
def google(monkeypatch):
    """Google is switched on (a server key and a browser key are set) and every call it would make is recorded."""
    from types import SimpleNamespace

    monkeypatch.setattr(places, "get_settings", lambda: SimpleNamespace(places_provider="auto", google_maps_server_key=KEY, google_maps_browser_key="browser-key-abc"))
    calls: list[httpx.Request] = []
    replies: dict[str, httpx.Response | dict] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        for part, reply in replies.items():
            if part in str(request.url):
                return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)
        return httpx.Response(404, json={})

    return SimpleNamespace(calls=calls, replies=replies, transport=httpx.MockTransport(handler))


AUTOCOMPLETE = {"suggestions": [
    {"placePrediction": {"placeId": "ChIJabcdefghij1", "text": {"text": "Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra, India"},
                         "structuredFormat": {"mainText": {"text": "Waluj MIDC"}, "secondaryText": {"text": "Chhatrapati Sambhajinagar, Maharashtra"}}}},
    {"queryPrediction": {"text": {"text": "waluj midc companies"}}},  # a search phrase, not a place: dropped
    {"placePrediction": {"placeId": "ChIJabcdefghij2", "text": {"text": "Waluj Gaon, Maharashtra, India"}}},  # no structured part: split from the text
]}


async def test_google_suggestions_are_places_without_positions_until_one_is_picked(google) -> None:
    google.replies["places:autocomplete"] = AUTOCOMPLETE
    got = await places.search("waluj", "sess-1234567890", google.transport)
    assert [p.name for p in got] == ["Waluj MIDC", "Waluj Gaon"] and got[0].id == "ChIJabcdefghij1"
    assert got[0].label == "Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra" and got[0].lat is None and got[0].lng is None
    assert got[1].detail == "Maharashtra, India"
    sent = google.calls[0]
    assert sent.headers["x-goog-api-key"] == KEY  # in a header, never in the address
    assert KEY not in str(sent.url)
    import json

    body = json.loads(sent.content)
    assert body["includedRegionCodes"] == ["in"] and body["sessionToken"] == "sess-1234567890" and body["input"] == "waluj"


async def test_google_answers_are_not_kept(google) -> None:
    google.replies["places:autocomplete"] = AUTOCOMPLETE
    await places.search("waluj", None, google.transport)
    await places.search("waluj", None, google.transport)
    assert len(google.calls) == 2  # Google's terms do not allow caching its results


async def test_picking_a_google_suggestion_fetches_its_position_in_the_same_session(google) -> None:
    google.replies["/v1/places/ChIJabcdefghij1"] = {"id": "ChIJabcdefghij1", "displayName": {"text": "Waluj MIDC"},
                                                    "formattedAddress": "Waluj, Chhatrapati Sambhajinagar, Maharashtra 431136, India", "location": {"latitude": 19.8601234, "longitude": 75.2145678}}
    p = await places.details("ChIJabcdefghij1", "sess-1234567890", google.transport)
    assert (p.lat, p.lng) == (19.860123, 75.214568) and p.label.startswith("Waluj MIDC, Waluj,") and len(p.label) <= 120
    sent = google.calls[0]
    assert sent.headers["x-goog-fieldmask"] == "id,displayName,formattedAddress,location"  # only what is used, so only that is billed
    assert sent.url.params["sessionToken"] == "sess-1234567890"


async def test_the_pin_address_comes_from_geocoding_and_keeps_the_pins_own_position(google) -> None:
    google.replies["geocode/json"] = {"status": "OK", "results": [{"place_id": "ChIJxyz12345678", "formatted_address": "MIDC Waluj, Chhatrapati Sambhajinagar, Maharashtra 431136, India"}]}
    p = await places.reverse(19.86, 75.21, google.transport)
    assert p.label.startswith("MIDC Waluj") and (p.lat, p.lng) == (19.86, 75.21)  # the pin stays where the person put it
    assert google.calls[0].url.params["latlng"] == "19.86,75.21"
    google.replies["geocode/json"] = {"status": "ZERO_RESULTS", "results": []}
    assert (await places.reverse(19.86, 75.21, google.transport)).label == "19.86000, 75.21000"  # open fields: the coordinates are better than nothing


async def test_a_google_failure_never_leaks_the_key_and_the_form_keeps_working(google) -> None:
    google.replies["places:autocomplete"] = httpx.Response(403, json={"error": {"message": f"API key {KEY} is not allowed"}})
    with pytest.raises(places.PlacesUnavailable) as e:
        await places.search("waluj", None, google.transport)
    assert KEY not in str(e.value) and "403" in str(e.value)
    google.replies["geocode/json"] = {"status": "REQUEST_DENIED", "error_message": f"key {KEY} invalid", "results": []}
    with pytest.raises(places.PlacesUnavailable) as e2:
        await places.reverse(19.86, 75.21, google.transport)
    assert KEY not in str(e2.value)


def test_which_provider_is_used_and_what_the_browser_may_know(monkeypatch) -> None:
    from types import SimpleNamespace

    def use(**kw):
        monkeypatch.setattr(places, "get_settings", lambda: SimpleNamespace(**{"places_provider": "auto", "google_maps_server_key": "", "google_maps_browser_key": "", **kw}))

    use()
    assert places.provider() == "photon" and places.browser_config() == {"provider": "photon", "maps_key": None}  # no key: the free search
    use(google_maps_server_key="s", google_maps_browser_key="b")
    assert places.browser_config() == {"provider": "google", "maps_key": "b"}  # the SERVER key is never offered
    use(google_maps_server_key="s")
    assert places.browser_config() == {"provider": "google", "maps_key": None}  # suggestions work, no map without the browser key
    use(places_provider="photon", google_maps_server_key="s", google_maps_browser_key="b")
    assert places.browser_config() == {"provider": "photon", "maps_key": None}  # switched off on purpose


async def test_the_endpoints_check_what_they_are_given_and_say_when_not_set_up(client: AsyncClient) -> None:
    assert (await client.get("/places/config")).json() == {"provider": "photon", "maps_key": None}
    assert (await client.get("/places/details", params={"id": "short"})).status_code == 422  # not a place id
    assert (await client.get("/places/details", params={"id": "../../etc/passwd"})).status_code == 422
    assert (await client.get("/places/details", params={"id": "ChIJabcdefghij1"})).status_code == 503  # Google is not configured here
    assert (await client.get("/places/search", params={"q": "waluj", "session": "x"})).status_code == 422  # session tokens are 8-64 safe characters
    assert (await client.get("/places/reverse", params={"lat": 51.5, "lng": -0.1})).status_code == 422  # outside India
