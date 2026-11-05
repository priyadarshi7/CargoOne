"""Tell a driver about something: an in-app notification (always) and a WhatsApp message (when they have a number).

Sending never blocks or breaks the action that caused it: a failed WhatsApp is recorded in `messages` with the reason and the
office can see it; the in-app notification is there regardless. Callers use the `safely` wrapper for the same reason."""
import hashlib
import logging
import secrets
import uuid
from collections.abc import Awaitable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST
from app.config import get_settings
from app.models import Message, Notification, OnboardingLink, Trip, User, Vehicle
from app.notify.email import compose, get_email, mask_email
from app.notify.sms import mask_phone
from app.notify.whatsapp import get_whatsapp, render

log = logging.getLogger("cargoone.notify")

TITLES = {
    "welcome": {"en": "Welcome to CargoOne", "hi": "CargoOne में स्वागत है", "mr": "CargoOne मध्ये स्वागत"},
    "trip_assigned": {"en": "New trip assigned", "hi": "नई ट्रिप मिली", "mr": "नवीन ट्रिप मिळाली"},
    "trip_update": {"en": "Trip changed", "hi": "ट्रिप में बदलाव", "mr": "ट्रिपमध्ये बदल"},
}
WELCOME_BODY = {"en": "Set your PIN and install the app from the link in your WhatsApp.", "hi": "WhatsApp के लिंक से अपना PIN बनाएँ और ऐप इंस्टॉल करें।",
                "mr": "WhatsApp मधील लिंकवरून तुमचा PIN तयार करा आणि अ‍ॅप इन्स्टॉल करा."}


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def when_text(dt: datetime | None) -> str:
    return f"{dt.astimezone(IST):%d %b, %H:%M}" if dt else "to be told"


def route_text(trip: Trip) -> str:
    return f"{trip.origin} - {trip.destination}"


async def issue_onboarding_link(session: AsyncSession, user: User) -> str:
    """A fresh one-time link; any earlier unused link of this person stops working. Returns the full URL (the only time it exists in clear)."""
    await session.execute(update(OnboardingLink).where(OnboardingLink.user_id == user.id, OnboardingLink.used_at.is_(None)).values(used_at=datetime.now(UTC)))
    raw = secrets.token_urlsafe(32)
    s = get_settings()
    session.add(OnboardingLink(token_hash=_hash(raw), user_id=user.id, expires_at=datetime.now(UTC) + timedelta(hours=s.onboarding_link_ttl_hours)))
    await session.flush()
    return f"{s.app_base_url.rstrip('/')}/onboard/{raw}"


async def send_whatsapp(session: AsyncSession, user: User, template: str, values: dict[str, str], *, trip: Trip | None = None, secret: str | None = None) -> Message:
    """Render, send, and record a message to a user. `secret` is a token inside the message that must not be kept in the log."""
    return await send_to_phone(session, user.phone, user.language, template, values, user_id=user.id, trip=trip, secret=secret)


async def send_to_phone(session: AsyncSession, phone: str | None, language: str, template: str, values: dict[str, str], *, user_id: uuid.UUID | None = None,
                        trip: Trip | None = None, secret: str | None = None) -> Message:
    """The same, for a bare number (someone who is not a user, such as a company that asked for transport)."""
    lang = language if language in ("en", "hi", "mr") else "en"
    text = render(template, lang, values)
    provider = get_whatsapp()
    msg = Message(user_id=user_id, trip_id=trip.id if trip else None, template=template, provider=provider.name, status="skipped",
                  to_masked=mask_phone(phone) if phone else None, body=(text.replace(secret, "•••") if secret else text)[:1200])
    if not phone:
        msg.error = "no phone number"
    else:
        try:
            res = await provider.send(phone, template, lang, values)
            msg.status, msg.provider_id, msg.error = res.status, res.provider_id, res.error
        except Exception as e:
            log.exception("whatsapp sender crashed")
            msg.status, msg.error = "failed", f"sender error: {type(e).__name__}"

    session.add(msg)
    await session.flush()
    return msg


async def send_email(session: AsyncSession, to: str | None, language: str, template: str, values: dict[str, str], *, secret: str | None = None) -> Message:
    """Render, send, and record an email (same log as WhatsApp, channel `email`). `secret` is cut out of the stored copy."""
    lang = language if language in ("en", "hi", "mr") else "en"
    subject, text = compose(template, lang, values)
    provider = get_email()
    msg = Message(channel="email", template=template, provider=provider.name, status="skipped", to_masked=mask_email(to) if to else None,
                  body=(f"{subject}\n\n{text}".replace(secret, "•••") if secret else f"{subject}\n\n{text}")[:1200])
    if not to:
        msg.error = "no email address"
    else:
        try:
            res = await provider.send(to, subject, text)
            msg.status, msg.provider_id, msg.error = res.status, res.provider_id, res.error
        except Exception as e:
            log.exception("email sender crashed")
            msg.status, msg.error = "failed", f"sender error: {type(e).__name__}"
    session.add(msg)
    await session.flush()
    return msg


def _notify(session: AsyncSession, user: User, kind: str, body: str, *, link: str | None, trip: Trip | None = None) -> None:
    lang = user.language if user.language in ("en", "hi", "mr") else "en"
    session.add(Notification(user_id=user.id, kind=kind, title=TITLES[kind][lang], body=body[:600], link=link, trip_id=trip.id if trip else None))


async def welcome_driver(session: AsyncSession, user: User) -> dict:
    """After registering a driver: a one-time link to choose a PIN and install the app, by WhatsApp, plus a notification waiting in the app."""
    url = await issue_onboarding_link(session, user)
    token = url.rsplit("/", 1)[1]
    msg = await send_whatsapp(session, user, "welcome", {"name": user.name, "link": url}, secret=token)
    lang = user.language if user.language in ("en", "hi", "mr") else "en"
    _notify(session, user, "welcome", WELCOME_BODY[lang], link="/driver")
    await session.commit()
    return {"url": url, "status": msg.status, "error": msg.error, "provider": msg.provider,
            "text": render("welcome", lang, {"name": user.name, "link": url}), "phone": user.phone}


async def trip_assigned(session: AsyncSession, trip: Trip, driver: User, vehicle: Vehicle | None) -> None:
    s = get_settings()
    secret = None
    if driver.must_change_secret:  # has not opened the app yet: the link doubles as their way in
        link = await issue_onboarding_link(session, driver)
        secret = link.rsplit("/", 1)[1]
    else:
        link = f"{s.app_base_url.rstrip('/')}/driver?trip={trip.id}"
    values = {"name": driver.name, "trip_code": trip.trip_code, "lr": trip.lr_no, "route": route_text(trip), "vehicle": vehicle.reg_no if vehicle else "-",
              "start": when_text(trip.planned_start), "link": link}
    await send_whatsapp(session, driver, "trip_assigned", values, trip=trip, secret=secret)
    _notify(session, driver, "trip_assigned", f"{trip.trip_code} · LR {trip.lr_no} · {route_text(trip)} · {values['vehicle']} · {values['start']}", link=f"/driver?trip={trip.id}", trip=trip)
    await session.commit()


async def trip_update(session: AsyncSession, trip: Trip, driver: User, change: str) -> None:
    s = get_settings()
    link = f"{s.app_base_url.rstrip('/')}/driver?trip={trip.id}"
    await send_whatsapp(session, driver, "trip_update", {"name": driver.name, "trip_code": trip.trip_code, "change": change, "link": link}, trip=trip)
    _notify(session, driver, "trip_update", f"{trip.trip_code} {change}", link=f"/driver?trip={trip.id}", trip=trip)
    await session.commit()


async def safely(session: AsyncSession, job: Awaitable[object]) -> None:
    """Run a notification job; if anything goes wrong, record it in the log and carry on: the caller's change is already saved."""
    try:
        await job
    except Exception:
        log.exception("notification failed")
        await session.rollback()


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    rows = await session.scalars(select(Notification.id).where(Notification.user_id == user_id, Notification.read_at.is_(None)))
    return len(rows.all())
