"""DPDP Act 2023: how long personal data is kept, and what happens when a person asks about theirs.

Retention: consignee name, phone and email, the POD photos and what the AI read off them are removed `retention_years` after a trip is
closed. The trip, its LR number, the invoice and the money stay (tax records), only the people in them go.
A request from a person (access / erase) is by phone number. Erasing takes the consignee details off every trip with that number and
off any transport request they made; the photos stay until the retention date because the tax records may need them (DPDP s.8(7)).

Run the retention job daily: `python -m app.privacy` (cron / task scheduler)."""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    AuditLog,
    LocationPing,
    PodSubmission,
    PrivacyRequest,
    Role,
    TransportRequest,
    Trip,
    User,
)
from app.routers.tracking import purge_old_pings
from app.storage import Storage, get_storage

BLANK = "(erased)"  # transport_requests keeps NOT NULL columns


def _years_ago(years: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=round(365.25 * years))


async def erase_trip_photos(session: AsyncSession, storage: Storage, trip: Trip) -> int:
    """Delete the files of one trip (POD photos and the loading photo) and what the AI read from them. The rows stay as the decision record."""
    subs = (await session.scalars(select(PodSubmission).where(PodSubmission.trip_id == trip.id))).all()
    keys = [s.storage_key for s in subs if s.storage_key]
    if trip.loading_photo_key:
        keys.append(trip.loading_photo_key)
    for key in keys:
        await storage.delete(key)
    for sub in subs:
        sub.storage_key, sub.ai_result, sub.corrected_fields = "", None, None
    trip.loading_photo_key = None
    return len(keys)


def erase_consignee(trip: Trip) -> None:
    trip.consignee_name = trip.consignee_phone = trip.consignee_email = None
    trip.delivery_note = None  # free text; may name the receiver


async def purge_expired(session: AsyncSession, storage: Storage | None = None) -> dict[str, int]:
    """The daily job. Returns how many of each were removed (no names or numbers)."""
    s, storage = get_settings(), storage or get_storage()
    out = {"trips": 0, "photos": 0, "requests": 0, "pings": 0}
    if s.retention_years > 0:
        old = (await session.scalars(select(Trip).where(Trip.closed_at < _years_ago(s.retention_years), Trip.personal_data_erased_at.is_(None)).limit(500))).all()
        for trip in old:
            out["photos"] += await erase_trip_photos(session, storage, trip)
            erase_consignee(trip)
            trip.personal_data_erased_at = datetime.now(UTC)
        out["trips"] = len(old)
    cutoff = datetime.now(UTC) - timedelta(days=s.request_retention_days)
    res = await session.execute(delete(TransportRequest).where(TransportRequest.status == "declined", TransportRequest.created_at < cutoff))
    out["requests"] = res.rowcount or 0
    session.add(AuditLog(action="privacy.purge", entity="system", meta=dict(out)))
    await session.commit()
    out["pings"] = await purge_old_pings(session)
    return out


async def held_about(session: AsyncSession, phone: str) -> dict:
    """Everything kept about a phone number: consignee records on trips and requests they made."""
    trips = (await session.scalars(select(Trip).where(Trip.consignee_phone == phone).order_by(Trip.created_at))).all()
    reqs = (await session.scalars(select(TransportRequest).where(TransportRequest.phone == phone).order_by(TransportRequest.created_at))).all()
    drivers = (await session.scalars(select(User).where(User.phone == phone, User.role == Role.driver))).all()
    return {
        "trips": [{"trip_code": t.trip_code, "lr_no": t.lr_no, "route": f"{t.origin} to {t.destination}", "consignee_name": t.consignee_name,
                   "consignee_email": t.consignee_email, "delivered_at": t.delivered_at, "closed_at": t.closed_at} for t in trips],
        "requests": [{"reference": r.reference, "company": r.company_name, "contact_name": r.contact_name, "email": r.email,
                      "status": r.status, "consent_at": r.consent_at, "created_at": r.created_at} for r in reqs],
        "drivers": [{"name": u.name, "email": u.email, "language": u.language, "licence_no": u.licence_no, "licence_expiry": u.licence_expiry,
                     "location_agreed_at": u.tracking_consent_at} for u in drivers],
    }


async def erase_about(session: AsyncSession, phone: str, actor: uuid.UUID) -> dict[str, int]:
    trips = (await session.scalars(select(Trip).where(Trip.consignee_phone == phone))).all()
    for t in trips:
        erase_consignee(t)
    reqs = (await session.scalars(select(TransportRequest).where(TransportRequest.phone == phone))).all()
    for r in reqs:
        r.contact_name, r.phone, r.email, r.notes = BLANK, "", None, None
    people = (await session.scalars(select(User).where(User.phone == phone, User.role == Role.driver))).all()
    for u in people:  # a driver (own or hired): the account is closed and the person's details are removed, the trips they drove stay
        u.name, u.phone, u.email, u.password_hash, u.is_active = "Former driver", None, None, None, False
        u.licence_no, u.licence_expiry, u.tracking_consent_at, u.token_version = None, None, None, u.token_version + 1
        await session.execute(delete(LocationPing).where(LocationPing.driver_id == u.id))
    session.add(AuditLog(actor_id=actor, action="privacy.erase", entity="person", meta={"phone": "******" + phone[-4:], "trips": len(trips), "requests": len(reqs), "drivers": len(people)}))
    await session.commit()
    return {"trips": len(trips), "requests": len(reqs), "drivers": len(people)}


def mask_closed(req: PrivacyRequest) -> None:
    """A closed request keeps what it was and what was done, but no longer the number or the name."""
    req.phone, req.name = "******" + req.phone[-4:], None


async def run_daily(stop: asyncio.Event) -> None:
    """The retention job, once a day while the API runs. One process at a time does it (a database lock), so two instances never overlap."""
    from sqlalchemy import text

    while not stop.is_set():
        try:
            async with SessionLocal() as session:
                if await session.scalar(text("select pg_try_advisory_lock(727001)")):
                    try:
                        await purge_expired(session)
                    finally:
                        await session.execute(text("select pg_advisory_unlock(727001)"))
        except Exception:
            logging.getLogger("cargoone.privacy").exception("retention job failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=86_400)
        except TimeoutError:
            pass


async def main() -> None:
    async with SessionLocal() as session:
        print(await purge_expired(session))


if __name__ == "__main__":
    asyncio.run(main())
