"""Where the photo was taken, as proof. A delivery photo should come from near the place the load was going to.

Only the people at the door can give this: an office upload is made at a desk, so it is not checked. A photo with no location, or taken far
from the destination, is not refused (a driver may have no signal or a switched-off GPS); it goes to a person with the reason written."""
from dataclasses import dataclass
from datetime import UTC, datetime

from app.tracking import Fix, haversine_m


@dataclass(frozen=True)
class PlaceCheck:
    reason: str | None  # None: nothing to flag
    distance_km: float | None = None


def check_place(*, source: str, lat: float | None, lng: float | None, dest_lat: float | None, dest_lng: float | None, max_km: float) -> PlaceCheck:
    if source == "office":
        return PlaceCheck(None)
    if lat is None or lng is None:
        return PlaceCheck("gps_missing")
    if dest_lat is None or dest_lng is None:
        return PlaceCheck(None)  # the trip has no map point for its destination: nothing to compare with
    now = datetime.now(UTC)
    km = haversine_m(Fix(lat, lng, now), Fix(dest_lat, dest_lng, now)) / 1000
    return PlaceCheck("far_from_destination" if km > max_km else None, round(km, 1))
