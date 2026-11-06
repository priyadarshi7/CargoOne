"""Place suggestions (see app/places.py). Public on purpose: the company request form needs it before anyone has an account;
a per-address rate limit keeps it from being used as a free geocoder."""
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, status

from app import places
from app.ratelimit import RateLimiter

router = APIRouter(prefix="/places", tags=["places"])
limiter = RateLimiter(max_hits=60, window_s=60)  # per address: typing with a pause between keystrokes is a few calls a minute


@router.get("/search", response_model=list[places.Place])
async def search(request: Request, q: Annotated[str, Query(min_length=3, max_length=80)]) -> list[places.Place]:
    ip = request.client.host if request.client else "unknown"
    if limiter.blocked(ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many searches. Wait a moment.")
    limiter.record(ip)
    try:
        return await places.search(q)
    except places.PlacesUnavailable:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Place search is not available right now. Type the place instead.") from None
