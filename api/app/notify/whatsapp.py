"""WhatsApp sending behind an interface. Two senders:

* `MockWhatsApp` records the message and says "simulated": nothing leaves the machine. Used until the Meta credentials are set.
* `MetaWhatsApp` sends through the WhatsApp Business Cloud API. A business may only START a conversation with an approved
  *template*, so every message here is a template with fixed text and numbered blanks. The text of each template (to be
  registered once in Meta Business Manager, in English, Hindi and Marathi) is in docs/07-whatsapp-setup.md and must match
  `TEXT` below, with {name} {link}... replaced by {{1}} {{2}}... in the order of `PARAMS`.

Phone numbers are personal data: logs and the message table only ever hold the masked form."""
import logging
import re
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import quote

import httpx

from app.config import Settings, get_settings

log = logging.getLogger("cargoone.whatsapp")

PARAMS: dict[str, tuple[str, ...]] = {
    "welcome": ("name", "link"),
    "trip_assigned": ("name", "trip_code", "lr", "route", "vehicle", "start", "link"),
    "trip_update": ("name", "trip_code", "change", "link"),
    "request_received": ("name", "reference", "link"),
    "request_update": ("name", "reference", "update", "link"),
}

TEXT: dict[str, dict[str, str]] = {
    "welcome": {
        "en": "Hello {name}, welcome to CargoOne. Set your PIN and install the driver app here: {link}",
        "hi": "नमस्ते {name}, CargoOne में आपका स्वागत है। अपना PIN बनाने और ड्राइवर ऐप इंस्टॉल करने के लिए यहाँ खोलें: {link}",
        "mr": "नमस्कार {name}, CargoOne मध्ये तुमचे स्वागत आहे. तुमचा PIN तयार करण्यासाठी आणि ड्रायव्हर अ‍ॅप इन्स्टॉल करण्यासाठी येथे उघडा: {link}",
    },
    "trip_assigned": {
        "en": "Hello {name}, a new trip is assigned to you. Trip {trip_code}, LR {lr}. Route: {route}. Truck: {vehicle}. Start: {start}. Open the app to see the details and start the trip: {link}",
        "hi": "नमस्ते {name}, आपको नई ट्रिप दी गई है। ट्रिप {trip_code}, LR {lr}। रूट: {route}। ट्रक: {vehicle}। शुरू: {start}। विवरण देखने और ट्रिप शुरू करने के लिए ऐप खोलें: {link}",
        "mr": "नमस्कार {name}, तुम्हाला नवीन ट्रिप दिली आहे. ट्रिप {trip_code}, LR {lr}. मार्ग: {route}. ट्रक: {vehicle}. सुरू: {start}. तपशील पाहण्यासाठी आणि ट्रिप सुरू करण्यासाठी अ‍ॅप उघडा: {link}",
    },
    "trip_update": {
        "en": "Hello {name}, trip {trip_code} {change}. Details: {link}",
        "hi": "नमस्ते {name}, ट्रिप {trip_code} {change}। विवरण: {link}",
        "mr": "नमस्कार {name}, ट्रिप {trip_code} {change}. तपशील: {link}",
    },
    "request_received": {
        "en": "Hello {name}, we have received your transport request {reference}. You can follow it here: {link}",
        "hi": "नमस्ते {name}, आपका ट्रांसपोर्ट अनुरोध {reference} हमें मिल गया है। यहाँ देख सकते हैं: {link}",
        "mr": "नमस्कार {name}, तुमची वाहतूक विनंती {reference} आम्हाला मिळाली आहे. येथे पाहू शकता: {link}",
    },
    "request_update": {
        "en": "Hello {name}, update on your transport request {reference}: {update}. Details: {link}",
        "hi": "नमस्ते {name}, आपके ट्रांसपोर्ट अनुरोध {reference} की जानकारी: {update}। विवरण: {link}",
        "mr": "नमस्कार {name}, तुमच्या वाहतूक विनंती {reference} बद्दल माहिती: {update}. तपशील: {link}",
    },
}


def render(template: str, lang: str, values: dict[str, str]) -> str:
    return TEXT[template].get(lang, TEXT[template]["en"]).format(**values)


def meta_clean(text: str) -> str:
    """Meta rejects newlines, tabs and runs of 4+ spaces inside a template parameter."""
    return re.sub(r"\s+", " ", text).strip()[:900]


def click_to_chat(phone: str, text: str) -> str:
    """A link that opens WhatsApp with the message ready to send from the office person's own phone: the manual fallback."""
    return f"https://wa.me/91{phone}?text={quote(text)}"


@dataclass
class SendResult:
    status: Literal["sent", "simulated", "failed"]
    provider_id: str | None = None
    error: str | None = None


class WhatsApp(Protocol):
    name: str

    async def send(self, phone: str, template: str, lang: str, values: dict[str, str]) -> SendResult: ...


class MockWhatsApp:
    name = "mock"

    def __init__(self) -> None:
        self.outbox: list[tuple[str, str, str]] = []  # (phone, template, full text), for tests and local inspection

    async def send(self, phone: str, template: str, lang: str, values: dict[str, str]) -> SendResult:
        self.outbox.append((phone, template, render(template, lang, values)))
        return SendResult("simulated")


class MetaWhatsApp:
    name = "meta"

    def __init__(self, s: Settings) -> None:
        self._s = s

    async def send(self, phone: str, template: str, lang: str, values: dict[str, str]) -> SendResult:
        s = self._s
        body = {
            "messaging_product": "whatsapp", "to": f"91{phone}", "type": "template",
            "template": {
                "name": f"{s.whatsapp_template_prefix}_{template}", "language": {"code": lang if lang in ("en", "hi", "mr") else "en"},
                "components": [{"type": "body", "parameters": [{"type": "text", "text": meta_clean(values[k])} for k in PARAMS[template]]}],
            },
        }
        url = f"https://graph.facebook.com/{s.whatsapp_api_version}/{s.whatsapp_phone_number_id}/messages"
        try:
            async with httpx.AsyncClient(timeout=8.0) as http:
                res = await http.post(url, json=body, headers={"Authorization": f"Bearer {s.whatsapp_token}"})
        except httpx.HTTPError as e:
            return SendResult("failed", error=f"network: {type(e).__name__}")
        if res.status_code // 100 == 2:
            msgs = res.json().get("messages") or [{}]
            return SendResult("sent", provider_id=msgs[0].get("id"))
        try:
            err = res.json().get("error", {})
            detail = f"{err.get('code', '')} {str(err.get('message', ''))[:120]}".strip()  # codes and generic text only, never the number
        except ValueError:
            detail = ""
        return SendResult("failed", error=f"http {res.status_code} {detail}".strip()[:200])


_mock = MockWhatsApp()


def get_whatsapp() -> WhatsApp:
    s = get_settings()
    if s.whatsapp_provider == "meta":
        if s.whatsapp_token and s.whatsapp_phone_number_id:
            return MetaWhatsApp(s)
        log.warning("WHATSAPP_PROVIDER=meta but token or phone number id is missing: messages are only recorded, not sent")
    return _mock


def is_live() -> bool:
    return get_whatsapp().name == "meta"
