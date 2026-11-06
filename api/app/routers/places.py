"""Place search, place position, pin address, and what the browser may know (see app/places.py). Public on purpose: the company request
form needs it before anyone has an account; a per-address rate limit keeps it from being used as a free geocoder."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app import places
from app.ratelimit import RateLimiter

router = APIRouter(prefix="/places", tags=["places"])
limiter = RateLimiter(max_hits=120, window_s=60)  # per address: typing, picking and moving a map pin are a few calls each

Session = Annotated[str | None, Query(pattern=r"^[A-Za-z0-9_-]{8,64}$", description="one per search-then-pick, so the provider bills it as one session")]
Lat = Annotated[float, Query(ge=6, le=36)]  # India's box, the same one the saved coordinates must be in
Lng = Annotated[float, Query(ge=68, le=98)]


def _guard(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if limiter.blocked(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many searches. Wait a moment.")
    limiter.record(ip)


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Place search is not available right now. Type the place instead.")


@router.get("/config")
async def config() -> dict:
    """Which provider is in use and, for the map, the browser key (Google expects that key to be public; restrict it by site in Google Cloud)."""
    return places.browser_config()


@router.get("/search", response_model=list[places.Place])
async def search(request: Request, q: Annotated[str, Query(min_length=3, max_length=80)], session: Session = None) -> list[places.Place]:
    _guard(request)
    try:
        return await places.search(q, session)
    except places.PlacesUnavailable:
        raise _unavailable() from None


@router.get("/details", response_model=places.Place)
async def details(request: Request, id: Annotated[str, Query(pattern=r"^[A-Za-z0-9_-]{10,300}$")], session: Session = None) -> places.Place:
    """The position of a picked Google suggestion (Photon suggestions already carry theirs)."""
    _guard(request)
    try:
        return await places.details(id, session)
    except places.PlacesUnavailable:
        raise _unavailable() from None


@router.get("/reverse", response_model=places.Place)
async def reverse(request: Request, lat: Lat, lng: Lng) -> places.Place:
    """The address under the map pin."""
    _guard(request)
    try:
        return await places.reverse(lat, lng)
    except places.PlacesUnavailable:
        raise _unavailable() from None
