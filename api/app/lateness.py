"""Is a trip on the road going to arrive late, or after its e-way bill runs out? Checked whenever the truck's position is updated."""
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST
from app.config import get_settings
from app.events import record
from app.models import LocationPing, Trip, TripState
from app.notify.service import safely
from app.notify.shipment import tell_parties
from app.tracking import Fix, eta

REPEAT = timedelta(hours=3)  # one warning per trip per this long, not one per position update


async def arrival_estimate(session: AsyncSession, trip: Trip) -> datetime | None:
    """From the latest position and the exact drop point; None when either is unknown."""
    if trip.destination_lat is None or trip.destination_lng is None:
        return None
    last = await session.scalar(select(LocationPing).where(LocationPing.trip_id == trip.id).order_by(LocationPing.recorded_at.desc()).limit(1))
    if last is None:
        return None
    s = get_settings()
    return eta(Fix(last.lat, last.lng, last.recorded_at), trip.destination_lat, trip.destination_lng, speed_kmh=s.eta_speed_kmh, road_factor=s.eta_road_factor)


async def check_late(session: AsyncSession, trip: Trip) -> None:
    if trip.state != TripState.in_transit:
        return
    now = datetime.now(UTC)
    if trip.late_alert_at and now - trip.late_alert_at < REPEAT:
        return
    arrives = await arrival_estimate(session, trip)
    if arrives is None:
        return
    grace = timedelta(minutes=get_settings().late_grace_min)
    expiring = trip.eway_valid_until is not None and arrives > trip.eway_valid_until
    late = trip.planned_end is not None and arrives > trip.planned_end + grace
    if not (late or expiring):
        return
    trip.late_alert_at = now
    if expiring:  # the more serious one: the office must act before the e-way bill runs out on the road
        record(session, trip, "eway_risk", note=f"Expected {arrives.astimezone(IST):%d %b, %H:%M}; the e-way bill is valid until {trip.eway_valid_until.astimezone(IST):%d %b, %H:%M}",
               meta={"eta": arrives.isoformat()})
    if late:
        record(session, trip, "late", public=True, meta={"eta": arrives.isoformat()})
    await session.commit()
    if late:
        await safely(session, tell_parties(session, trip, "late", eta=f"{arrives.astimezone(IST):%d %b, %H:%M}"))
