"""The trip's timeline: one row per thing that happened. `public` rows are what the shipment page shows to the client and the receiver."""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Trip, TripEvent


def record(session: AsyncSession, trip: Trip, kind: str, *, actor: uuid.UUID | None = None, note: str | None = None, public: bool = False,
           meta: dict | None = None) -> TripEvent:
    ev = TripEvent(trip_id=trip.id, kind=kind, actor_id=actor, note=(note or "").strip()[:300] or None, public=public, meta=meta)
    session.add(ev)
    return ev
