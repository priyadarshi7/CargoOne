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
    "shipment_update": ("name", "trip_code", "update", "link"),
}

TEXT: dict[str, dict[str, str]] = {
    # Meta approves "Utility" only for messages about something that already happened to the person, worded as a plain notice: no greeting
    # words like "welcome", no selling, and never a variable at the very start or end or two variables side by side, and none of the words PIN, code, password, verify or sign-in (Meta then insists on the Authentication category, which allows no links). Keep that in mind when editing.
    "welcome": {
        "en": "Hello {name}, your driver account on CargoOne has been created by your company. Please open this link to finish your registration: {link} The link can be used once and expires in 72 hours.",
        "hi": "नमस्ते {name}, आपकी कंपनी ने CargoOne पर आपका ड्राइवर खाता बना दिया है। अपना रजिस्ट्रेशन पूरा करने के लिए कृपया यह लिंक खोलें: {link} यह लिंक एक ही बार चलेगा और 72 घंटे में ख़त्म हो जाएगा।",
        "mr": "नमस्कार {name}, तुमच्या कंपनीने CargoOne वर तुमचे ड्रायव्हर खाते तयार केले आहे. तुमची नोंदणी पूर्ण करण्यासाठी कृपया ही लिंक उघडा: {link} ही लिंक एकदाच वापरता येईल आणि 72 तासांत संपेल.",
    },
    "trip_assigned": {
        "en": "Hello {name}, a trip has been assigned to you. Trip {trip_code}, LR number {lr}. Route: {route}. Truck: {vehicle}. Start: {start}. Open the trip here: {link} Please check the details before you leave.",
        "hi": "नमस्ते {name}, आपको एक ट्रिप दी गई है। ट्रिप {trip_code}, LR नंबर {lr}। रूट: {route}। ट्रक: {vehicle}। शुरू: {start}। ट्रिप यहाँ खोलें: {link} निकलने से पहले विवरण जाँच लें।",
        "mr": "नमस्कार {name}, तुम्हाला एक ट्रिप दिली आहे. ट्रिप {trip_code}, LR क्रमांक {lr}. मार्ग: {route}. ट्रक: {vehicle}. सुरू: {start}. ट्रिप येथे उघडा: {link} निघण्यापूर्वी तपशील तपासा.",
    },
    "trip_update": {
        "en": "Hello {name}, there is an update for your trip {trip_code}: {change}. See the details here: {link} Please check them before you leave.",
        "hi": "नमस्ते {name}, आपकी ट्रिप {trip_code} में बदलाव हुआ है: {change}। विवरण यहाँ देखें: {link} निकलने से पहले जाँच लें।",
        "mr": "नमस्कार {name}, तुमच्या ट्रिप {trip_code} मध्ये बदल झाला आहे: {change}. तपशील येथे पहा: {link} निघण्यापूर्वी तपासा.",
    },
    "shipment_update": {
        "en": "Hello {name}, there is an update on your shipment {trip_code}: {update}. Follow it here: {link} Thank you for your patience.",
        "hi": "नमस्ते {name}, आपकी खेप {trip_code} की जानकारी: {update}। यहाँ देखते रहें: {link} आपके धैर्य के लिए धन्यवाद।",
        "mr": "नमस्कार {name}, तुमच्या मालाची खेप {trip_code} बद्दल माहिती: {update}. येथे पाहत रहा: {link} तुमच्या संयमाबद्दल धन्यवाद.",
    },
    "request_received": {
        "en": "Hello {name}, we have received your transport request {reference}. You can follow its status here: {link} We will reply shortly.",
        "hi": "नमस्ते {name}, आपका ट्रांसपोर्ट अनुरोध {reference} हमें मिल गया है। इसकी स्थिति यहाँ देखें: {link} हम जल्द जवाब देंगे।",
        "mr": "नमस्कार {name}, तुमची वाहतूक विनंती {reference} आम्हाला मिळाली आहे. तिची स्थिती येथे पहा: {link} आम्ही लवकरच उत्तर देऊ.",
    },
    "request_update": {
        "en": "Hello {name}, there is an update on your transport request {reference}: {update}. See the details here: {link} Thank you for your patience.",
        "hi": "नमस्ते {name}, आपके ट्रांसपोर्ट अनुरोध {reference} की जानकारी: {update}। विवरण यहाँ देखें: {link} आपके धैर्य के लिए धन्यवाद।",
        "mr": "नमस्कार {name}, तुमच्या वाहतूक विनंती {reference} बद्दल माहिती: {update}. तपशील येथे पहा: {link} तुमच्या संयमाबद्दल धन्यवाद.",
    },
}


def template_name(s: Settings, template: str) -> str:
    """The name Meta knows the template by: an explicit setting if there is one, otherwise <prefix>_<template>."""
    return getattr(s, f"whatsapp_template_{template}", "") or f"{s.whatsapp_template_prefix}_{template}"


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
                "name": template_name(s, template), "language": {"code": lang if lang in ("en", "hi", "mr") else "en"},
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
