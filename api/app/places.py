"""Place suggestions and the map picker's address lookup for the origin / destination fields.

Two providers behind one interface, chosen by settings:
  - Google (Places API (New) + Geocoding API) when GOOGLE_MAPS_SERVER_KEY is set: the best address data in India. Autocomplete
    gives place names; the coordinates come from a Place Details call made with the same session token (that pairing is what Google
    bills as one session). Google results are never cached here (Google's terms forbid it).
  - Photon (komoot) on OpenStreetMap data: free, no key, the fallback. Its answers are cached for a day.
Our server asks on the browser's behalf, so the browser never talks to a provider for search, and the server key never reaches a
browser. Results are limited to India. Only the typed text (or a picked pin's position) is sent: no names, phone numbers or account details.
Errors never include the request address, because Geocoding takes its key in the address."""
import time

import httpx
from pydantic import BaseModel, Field, model_validator

from app.config import get_settings

PHOTON_URL = "https://photon.komoot.io/api/"
GOOGLE_AUTOCOMPLETE = "https://places.googleapis.com/v1/places:autocomplete"
GOOGLE_DETAILS = "https://places.googleapis.com/v1/places/{id}"
GOOGLE_GEOCODE = "https://maps.googleapis.com/maps/api/geocode/json"
INDIA_BBOX = "68.0,6.0,98.0,36.0"  # west, south, east, north
BIAS = (19.8762, 75.3433)  # Chhatrapati Sambhajinagar: results near the depot rank first
TTL_S = 24 * 3600
MAX_CACHE = 2000

_cache: dict[str, tuple[float, list["Place"]]] = {}


class Place(BaseModel):
    label: str  # what is written into the field, e.g. "Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra" (at most 120 characters)
    name: str
    detail: str  # the rest of the address, shown in smaller type
    lat: float | None = None  # Google suggestions have no position until the person picks one (details()); Photon ones always do
    lng: float | None = None
    id: str | None = None  # Google's place id, needed to fetch the position


class Coords(BaseModel):
    """Optional exact positions that come with a form's origin and destination when the person picked a suggestion.
    India only (the same box the search uses); a latitude always comes with its longitude."""

    origin_lat: float | None = Field(default=None, ge=6, le=36)
    origin_lng: float | None = Field(default=None, ge=68, le=98)
    destination_lat: float | None = Field(default=None, ge=6, le=36)
    destination_lng: float | None = Field(default=None, ge=68, le=98)

    @model_validator(mode="after")
    def _pairs(self) -> "Coords":
        if (self.origin_lat is None) != (self.origin_lng is None) or (self.destination_lat is None) != (self.destination_lng is None):
            raise ValueError("A map position needs both latitude and longitude")
        return self


class PlacesUnavailable(Exception):
    """The provider did not answer. The form keeps working: the person can type the place."""


async def _fetch(q: str, transport: httpx.AsyncBaseTransport | None = None) -> dict:
    params = {"q": q, "limit": "8", "lang": "en", "bbox": INDIA_BBOX, "lat": str(BIAS[0]), "lon": str(BIAS[1])}
    try:
        async with httpx.AsyncClient(timeout=6.0, transport=transport, headers={"User-Agent": "CargoOne/1.0"}) as http:
            res = await http.get(PHOTON_URL, params=params)
        res.raise_for_status()
        return res.json()
    except (httpx.HTTPError, ValueError) as e:
        raise PlacesUnavailable(type(e).__name__) from e


def _shape(feature: dict) -> Place | None:
    props, geom = feature.get("properties") or {}, feature.get("geometry") or {}
    coords = geom.get("coordinates")
    if props.get("countrycode") != "IN" or not (isinstance(coords, list) and len(coords) == 2):
        return None
    lng, lat = float(coords[0]), float(coords[1])
    first = props.get("name") or " ".join(x for x in (props.get("housenumber"), props.get("street")) if x)
    parts: list[str] = []
    for part in (first, props.get("street") if props.get("name") else None, props.get("district") or props.get("locality"), props.get("city") or props.get("county"), props.get("state")):
        if part and part not in parts:
            parts.append(str(part))
    if not parts:
        return None
    label = ", ".join(parts)[:120].rstrip(", ")
    return Place(label=label, name=parts[0], detail=", ".join(parts[1:]), lat=round(lat, 6), lng=round(lng, 6))


def provider() -> str:
    cfg = get_settings()
    return "google" if cfg.places_provider != "photon" and cfg.google_maps_server_key else "photon"


def browser_config() -> dict:
    """What the browser may know: which provider, and (for the map) the browser key, which Google expects to be public and restricted by site."""
    cfg = get_settings()
    on = provider() == "google" and bool(cfg.google_maps_browser_key)
    return {"provider": provider(), "maps_key": cfg.google_maps_browser_key if on else None}


async def _google(method: str, url: str, *, headers: dict | None = None, json: dict | None = None, params: dict | None = None,
                  transport: httpx.AsyncBaseTransport | None = None) -> dict:
    key = get_settings().google_maps_server_key
    try:
        async with httpx.AsyncClient(timeout=6.0, transport=transport) as http:
            res = await http.request(method, url, headers={"X-Goog-Api-Key": key, **(headers or {})}, json=json, params=params)
        if res.status_code >= 400:
            raise PlacesUnavailable(f"google http {res.status_code}")  # the code only: bodies and addresses may echo the key
        return res.json()
    except PlacesUnavailable:
        raise
    except (httpx.HTTPError, ValueError) as e:
        raise PlacesUnavailable(type(e).__name__) from e


def _split(label: str) -> tuple[str, str]:
    head, _, rest = label.partition(", ")
    return head, rest


async def _google_search(q: str, session: str | None, transport: httpx.AsyncBaseTransport | None) -> list[Place]:
    body: dict = {"input": q, "includedRegionCodes": ["in"], "languageCode": "en",
                  "locationBias": {"circle": {"center": {"latitude": BIAS[0], "longitude": BIAS[1]}, "radius": 50000.0}}}
    if session:
        body["sessionToken"] = session
    data = await _google("POST", GOOGLE_AUTOCOMPLETE, json=body, transport=transport)
    out: list[Place] = []
    for sug in data.get("suggestions") or []:
        pred = sug.get("placePrediction")
        if not pred or not pred.get("placeId"):
            continue  # query suggestions ("pizza near me") are not places
        fmt = pred.get("structuredFormat") or {}
        full = ((pred.get("text") or {}).get("text") or "").strip()
        main = ((fmt.get("mainText") or {}).get("text") or "").strip() or _split(full)[0]
        detail = ((fmt.get("secondaryText") or {}).get("text") or "").strip() or _split(full)[1]
        if main:
            label = (f"{main}, {detail}" if detail else main)[:120].rstrip(", ")
            out.append(Place(id=pred["placeId"], label=label, name=main, detail=detail))
    return out


async def details(place_id: str, session: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> Place:
    """The position of a picked Google suggestion. Pass the session token the search used, so Google counts search + pick as one session."""
    if provider() != "google":
        raise PlacesUnavailable("not configured")
    data = await _google("GET", GOOGLE_DETAILS.format(id=place_id), headers={"X-Goog-FieldMask": "id,displayName,formattedAddress,location"},
                         params={"sessionToken": session} if session else None, transport=transport)
    loc = data.get("location") or {}
    if "latitude" not in loc or "longitude" not in loc:
        raise PlacesUnavailable("no position")
    name = ((data.get("displayName") or {}).get("text") or "").strip()
    address = (data.get("formattedAddress") or "").strip()
    label = (f"{name}, {address}" if name and name not in address else address or name)[:120].rstrip(", ")
    head, rest = _split(label)
    return Place(id=place_id, label=label, name=name or head, detail=rest, lat=round(float(loc["latitude"]), 6), lng=round(float(loc["longitude"]), 6))


async def reverse(lat: float, lng: float, transport: httpx.AsyncBaseTransport | None = None) -> Place:
    """The address of a point on the map (the pin under the picker). Returns the position it was asked about, so the pin stays where it was put."""
    here = f"{lat:.5f}, {lng:.5f}"
    if provider() == "google":
        data = await _google("GET", GOOGLE_GEOCODE, params={"latlng": f"{lat},{lng}", "language": "en", "key": get_settings().google_maps_server_key}, transport=transport)
        if data.get("status") not in ("OK", "ZERO_RESULTS"):
            raise PlacesUnavailable(f"geocode {data.get('status')}")  # REQUEST_DENIED etc.: the key or the API is not set up
        first = (data.get("results") or [{}])[0]
        label = (first.get("formatted_address") or "").strip()[:120].rstrip(", ")
        head, rest = _split(label)
        return Place(id=first.get("place_id"), label=label or here, name=head or here, detail=rest, lat=round(lat, 6), lng=round(lng, 6))
    try:
        async with httpx.AsyncClient(timeout=6.0, transport=transport, headers={"User-Agent": "CargoOne/1.0"}) as http:
            res = await http.get(PHOTON_URL.replace("/api/", "/reverse"), params={"lat": str(lat), "lon": str(lng), "lang": "en"})
        res.raise_for_status()
        found = next((p for p in map(_shape, res.json().get("features") or []) if p), None)
    except (httpx.HTTPError, ValueError) as e:
        raise PlacesUnavailable(type(e).__name__) from e
    label = found.label if found else here
    head, rest = _split(label)
    return Place(label=label, name=head, detail=rest, lat=round(lat, 6), lng=round(lng, 6))


async def search(q: str, session: str | None = None, transport: httpx.AsyncBaseTransport | None = None) -> list[Place]:
    if provider() == "google":
        return await _google_search(q.strip(), session, transport)  # never cached: Google's terms
    key = " ".join(q.lower().split())
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    data = await _fetch(q.strip(), transport)
    seen: set[tuple[float, float]] = set()
    places: list[Place] = []
    for f in data.get("features") or []:
        p = _shape(f)
        if p and (p.lat, p.lng) not in seen:
            seen.add((p.lat, p.lng))
            places.append(p)
    if len(_cache) >= MAX_CACHE:
        _cache.clear()
    _cache[key] = (time.monotonic() + TTL_S, places)
    return places
