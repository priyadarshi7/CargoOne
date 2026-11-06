"""Pure rules for live tracking: distance, and whether a truck is moving, stopped or silent."""
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

STOP_RADIUS_M = 150  # GPS jitter while parked is well inside this


@dataclass(frozen=True)
class Fix:
    lat: float
    lng: float
    at: datetime


def haversine_m(a: Fix, b: Fix) -> float:
    r = 6_371_000
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def movement(fixes: list[Fix], now: datetime, *, stale_after: timedelta, stopped_after: timedelta) -> tuple[str, int]:
    """(state, minutes) where state is 'no_signal' | 'stopped' | 'moving' | 'unknown'.

    minutes = how long the truck has been silent (no_signal) or stationary (stopped), else 0.
    `fixes` may be in any order. Stationary means every fix since the truck last left a 150 m circle around its
    latest position - so a truck that stopped 3 hours ago is 'stopped' for 180 minutes, not just for the pings we hold."""
    if not fixes:
        return "unknown", 0
    fixes = sorted(fixes, key=lambda f: f.at)
    last = fixes[-1]
    if now - last.at > stale_after:
        return "no_signal", int((now - last.at).total_seconds() // 60)
    since = last.at
    for f in reversed(fixes):
        if haversine_m(f, last) > STOP_RADIUS_M:
            break
        since = f.at
    stopped_for = last.at - since
    # We only know the truck was there since the first fix inside the circle; if that is the oldest fix we hold the
    # true stop may be longer, which only makes the alert later, never wrong.
    if stopped_for >= stopped_after:
        return "stopped", int(stopped_for.total_seconds() // 60)
    return "moving", 0


def eta(last: Fix, dest_lat: float, dest_lng: float, *, speed_kmh: float, road_factor: float) -> datetime:
    """When the truck should arrive: the straight line to the drop point, stretched for real roads, at an average speed. An estimate, shown as one."""
    metres = haversine_m(last, Fix(dest_lat, dest_lng, last.at)) * road_factor
    return last.at + timedelta(seconds=metres / 1000 / max(speed_kmh, 5) * 3600)
