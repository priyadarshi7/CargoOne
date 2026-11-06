"""Place suggestions for the origin / destination fields: type a few letters, get real places with map coordinates.

Photon (komoot) answers from OpenStreetMap data: free, no key. Our server asks on the browser's behalf, so the browser never
talks to a third party, the answers are cached, and the provider can be swapped in one place. Results are limited to India.
The text typed is sent to the provider, nothing else (no names, phone numbers or account details)."""
import time

import httpx
from pydantic import BaseModel, Field, model_validator

PHOTON_URL = "https://photon.komoot.io/api/"
INDIA_BBOX = "68.0,6.0,98.0,36.0"  # west, south, east, north
BIAS = (19.8762, 75.3433)  # Chhatrapati Sambhajinagar: results near the depot rank first
TTL_S = 24 * 3600
MAX_CACHE = 2000

_cache: dict[str, tuple[float, list["Place"]]] = {}


class Place(BaseModel):
    label: str  # what is written into the field, e.g. "Waluj MIDC, Chhatrapati Sambhajinagar, Maharashtra" (at most 120 characters)
    name: str
    detail: str  # the rest of the address, shown in smaller type
    lat: float
    lng: float


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


async def search(q: str, transport: httpx.AsyncBaseTransport | None = None) -> list[Place]:
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
