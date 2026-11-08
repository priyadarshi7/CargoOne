"""SMS sending behind an interface. Two providers: a MOCK that never leaves the machine (the default, and the only one tests can use),
and Twilio, which really sends and is chosen only by SMS_PROVIDER=twilio with its keys in .env.
Sending to Indian numbers needs a DLT-registered sender and template (Twilio's trial also sends only to verified numbers), so the wording
below must match what is registered. A hard ceiling (SMS_MAX_TOTAL) counts every real text from the audit log, because the trial balance is small.
Phone numbers are personal data: logs and audit entries only ever see the masked form."""
import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings

log = logging.getLogger("cargoone.sms")

TEMPLATES = {
    "hi": "CargoOne: {dest} का आपका ट्रिप यहाँ खोलें: {url}",
    "mr": "CargoOne: {dest} ची तुमची ट्रिप येथे उघडा: {url}",
    "en": "CargoOne: open your trip to {dest} here: {url}",
}


REMINDERS = {
    "hi": "CargoOne: {dest} की डिलीवरी की रसीद की फोटो अभी बाकी है। ऐप खोलकर फोटो भेजें।",
    "mr": "CargoOne: {dest} च्या डिलिव्हरीच्या पावतीचा फोटो अजून बाकी आहे. अ‍ॅप उघडून फोटो पाठवा.",
    "en": "CargoOne: the receipt photo for your {dest} delivery is still pending. Open the app and send it.",
}


def reminder_text(lang: str, dest: str) -> str:
    return REMINDERS.get(lang, REMINDERS["hi"]).format(dest=dest)


def mask_phone(phone: str) -> str:
    return "*" * max(0, len(phone) - 4) + phone[-4:]


class Sms(Protocol):
    def send(self, phone: str, text: str) -> None: ...


@dataclass
class MockSms:
    """Records messages in memory (dev inspection / tests). Does not send anything."""

    outbox: list[tuple[str, str]]

    def send(self, phone: str, text: str) -> None:
        self.outbox.append((phone, text))
        log.info("SMS (mock) to %s, %d chars", mask_phone(phone), len(text))  # never log the text: it holds the link


class SmsError(Exception):
    """The provider refused or could not be reached. The message is safe to show the office (no secrets, no phone number)."""


class TwilioSms:
    """Sends through Twilio's REST API (no SDK needed). One blocking call, so callers run it with `send_sms`."""

    def __init__(self, sid: str, token: str, sender: str, service: str) -> None:
        self.sid, self.token, self.sender, self.service = sid, token, sender, service

    def send(self, phone: str, text: str) -> None:
        data = {"To": e164(phone), "Body": text}
        data["MessagingServiceSid" if self.service else "From"] = self.service or self.sender
        try:
            res = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json", data=data, auth=(self.sid, self.token), timeout=10)
        except httpx.HTTPError:
            raise SmsError("The SMS service could not be reached") from None
        if res.status_code >= 300:
            try:
                why = str(res.json().get("message", ""))[:160]
            except ValueError:
                why = ""
            log.warning("Twilio refused an SMS to %s: HTTP %s", mask_phone(phone), res.status_code)
            raise SmsError(why or f"The SMS service refused the message (HTTP {res.status_code})")
        log.info("SMS (twilio) to %s, %d chars", mask_phone(phone), len(text))


_mock = MockSms(outbox=[])
_twilio: TwilioSms | None = None


def get_sms() -> Sms:
    global _twilio
    s = get_settings()
    if s.sms_provider != "twilio":
        return _mock
    if not (s.twilio_account_sid and s.twilio_auth_token and (s.twilio_from or s.twilio_messaging_service_sid)):
        return _mock  # asked for Twilio but the keys are missing: stay safe, send nothing
    if _twilio is None or (_twilio.sid, _twilio.token) != (s.twilio_account_sid, s.twilio_auth_token):
        _twilio = TwilioSms(s.twilio_account_sid, s.twilio_auth_token, s.twilio_from, s.twilio_messaging_service_sid)
    return _twilio


def e164(phone: str) -> str:
    """+91 for a bare Indian mobile number; anything already carrying a country code is kept."""
    digits = re.sub(r"\D", "", phone)
    return ("+91" + digits) if len(digits) == 10 else ("+" + digits)


async def send_sms(session: AsyncSession, sms: Sms, phone: str, text: str, *, actor: object = None) -> str | None:
    """Send one text and say how it went: None on success (or when the sender is the simulated one), otherwise a short reason.
    A real send is counted in the audit log (the caller commits) and refused once SMS_MAX_TOTAL is reached.
    Never raises, so the action that wanted the text still completes."""
    from app.models import AuditLog

    if isinstance(sms, TwilioSms):
        used = await session.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "sms.sent")) or 0
        if used >= get_settings().sms_max_total:
            return f"The limit of {get_settings().sms_max_total} text messages is reached. Share the link yourself."
    try:
        await asyncio.to_thread(sms.send, phone, text)
    except SmsError as e:
        return str(e)
    except Exception:
        log.exception("SMS sender crashed")
        return "The SMS could not be sent"
    if isinstance(sms, TwilioSms):
        session.add(AuditLog(actor_id=actor, action="sms.sent", entity="sms", entity_id=mask_phone(phone)))
    return None


def render(lang: str, dest: str, url: str) -> str:
    return TEMPLATES.get(lang, TEMPLATES["hi"]).format(dest=dest, url=url)
