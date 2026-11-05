"""SMS sending behind an interface. Only a MOCK exists today: it never leaves the machine.
A real provider (MSG91 / Twilio / Gupshup) can implement `Sms` later - needs DLT-registered templates in India.
Phone numbers are personal data: logs and audit entries only ever see the masked form."""
import logging
from dataclasses import dataclass
from typing import Protocol

log = logging.getLogger("cargoone.sms")

TEMPLATES = {
    "hi": "CargoOne: {dest} की रसीद की फोटो यहाँ भेजें: {url}",
    "mr": "CargoOne: {dest} ची पावती फोटो येथे पाठवा: {url}",
    "en": "CargoOne: send the delivery receipt photo for {dest} here: {url}",
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


_mock = MockSms(outbox=[])


def get_sms() -> Sms:
    return _mock


def render(lang: str, dest: str, url: str) -> str:
    return TEMPLATES.get(lang, TEMPLATES["hi"]).format(dest=dest, url=url)
