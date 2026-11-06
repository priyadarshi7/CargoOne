"""Tell the client and the receiver where their shipment is: a WhatsApp note at each step, in the client's language, each carrying the
private shipment link for that person. Never blocks the action that caused it (callers wrap it in `safely`)."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, Trip, Vehicle
from app.notify.service import send_to_phone, when_text
from app.shipment import shipment_url

L = ("en", "hi", "mr")
UPDATES: dict[str, dict[str, str]] = {
    "assigned": {"en": "a truck is assigned ({vehicle}), pickup {when}", "hi": "ट्रक तय हो गया है ({vehicle}), पिकअप {when}", "mr": "ट्रक ठरला आहे ({vehicle}), पिकअप {when}"},
    "replanned": {"en": "the plan has changed: truck {vehicle}, pickup {when}", "hi": "योजना बदली है: ट्रक {vehicle}, पिकअप {when}", "mr": "योजना बदलली आहे: ट्रक {vehicle}, पिकअप {when}"},
    "started": {"en": "the truck has left and your goods are on the way", "hi": "ट्रक निकल चुका है और आपका माल रास्ते में है", "mr": "ट्रक निघाला आहे आणि तुमचा माल रस्त्यात आहे"},
    "delay": {"en": "the truck is running late ({reason}, about {minutes} minutes)", "hi": "ट्रक देर से चल रहा है ({reason}, लगभग {minutes} मिनट)", "mr": "ट्रक उशिरा चालला आहे ({reason}, सुमारे {minutes} मिनिटे)"},
    "breakdown": {"en": "the truck has stopped because of a problem ({reason}). We are arranging help", "hi": "ट्रक में समस्या के कारण रुका है ({reason})। हम मदद भेज रहे हैं", "mr": "ट्रक अडचणीमुळे थांबला आहे ({reason}). आम्ही मदत पाठवत आहोत"},
    "resolved": {"en": "the truck is moving again", "hi": "ट्रक फिर चल पड़ा है", "mr": "ट्रक पुन्हा निघाला आहे"},
    "late": {"en": "arrival is now expected around {eta}", "hi": "अब पहुँचने का अनुमान {eta} के आसपास है", "mr": "आता पोहोचण्याचा अंदाज {eta} च्या सुमारास आहे"},
    "delivered": {"en": "your goods have been delivered", "hi": "आपका माल पहुँच गया है", "mr": "तुमचा माल पोहोचला आहे"},
    "verified": {"en": "the proof of delivery has been checked and is ready to view", "hi": "डिलीवरी का सबूत जाँच लिया गया है और देखने के लिए तैयार है", "mr": "डिलिव्हरीचा पुरावा तपासला आहे आणि पाहण्यासाठी तयार आहे"},
    "invoiced": {"en": "invoice {invoice} for Rs {amount} has been issued for this shipment", "hi": "इस खेप के लिए बिल {invoice} (Rs {amount}) जारी हो गया है", "mr": "या खेपेसाठी बिल {invoice} (Rs {amount}) जारी झाले आहे"},
    "paid": {"en": "payment received for invoice {invoice}. Thank you", "hi": "बिल {invoice} का भुगतान मिल गया। धन्यवाद", "mr": "बिल {invoice} चे पैसे मिळाले. धन्यवाद"},
    "link": {"en": "you can follow your shipment on this page", "hi": "आप अपनी खेप इस पेज पर देख सकते हैं", "mr": "तुम्ही तुमची खेप या पेजवर पाहू शकता"},
    "cancelled": {"en": "this trip has been cancelled", "hi": "यह ट्रिप रद्द कर दी गई है", "mr": "ही ट्रिप रद्द करण्यात आली आहे"},
}
REASONS: dict[str, dict[str, str]] = {
    "traffic": {"en": "heavy traffic", "hi": "भारी ट्रैफ़िक", "mr": "जास्त वाहतूक"},
    "weather": {"en": "bad weather", "hi": "खराब मौसम", "mr": "खराब हवामान"},
    "police": {"en": "checking on the road", "hi": "रास्ते में जाँच", "mr": "रस्त्यात तपासणी"},
    "waiting": {"en": "waiting at a gate or for unloading", "hi": "गेट पर या उतराई के लिए इंतज़ार", "mr": "गेटवर किंवा उतरवण्यासाठी प्रतीक्षा"},
    "rest": {"en": "the driver's rest stop", "hi": "ड्राइवर का आराम", "mr": "ड्रायव्हरची विश्रांती"},
    "tyre": {"en": "a tyre problem", "hi": "टायर की समस्या", "mr": "टायरची अडचण"},
    "engine": {"en": "an engine problem", "hi": "इंजन की समस्या", "mr": "इंजिनची अडचण"},
    "accident": {"en": "an accident", "hi": "दुर्घटना", "mr": "अपघात"},
    "other": {"en": "another reason", "hi": "कोई और कारण", "mr": "इतर कारण"},
}
# Who hears about each step. The receiver never hears about money.
AUDIENCE = {"assigned": ("client",), "replanned": ("client",), "started": ("client", "receiver"), "delay": ("client", "receiver"), "breakdown": ("client", "receiver"),
            "resolved": ("client", "receiver"), "late": ("client", "receiver"), "delivered": ("client",), "verified": ("client",), "invoiced": ("client",),
            "paid": ("client",), "cancelled": ("client", "receiver"), "link": ("client", "receiver")}


def reason_text(code: str | None, lang: str) -> str:
    return REASONS.get(code or "other", REASONS["other"]).get(lang, REASONS["other"]["en"])


async def tell_parties(session: AsyncSession, trip: Trip, kind: str, only: str | None = None, **fmt: object) -> None:
    client = await session.get(Client, trip.client_id)
    if client is None:
        return
    lang = client.language if client.language in L else "en"
    vehicle = await session.get(Vehicle, trip.vehicle_id)
    values = {"vehicle": vehicle.reg_no if vehicle else "-", "when": when_text(trip.planned_start), **{k: str(v) for k, v in fmt.items()}}
    if "reason" in values:
        values["reason"] = reason_text(values["reason"], lang)
    text = UPDATES[kind][lang].format(**values)
    sent: set[str] = set()
    for aud in AUDIENCE[kind]:
        if only and aud != only:
            continue
        phone = client.contact_phone if aud == "client" else trip.consignee_phone
        name = (client.contact_name or client.name) if aud == "client" else (trip.consignee_name or "")
        if not phone or phone in sent:
            continue
        sent.add(phone)
        link = shipment_url(trip, aud)
        await send_to_phone(session, phone, lang, "shipment_update", {"name": name or "Sir/Madam", "trip_code": trip.trip_code, "update": text, "link": link},
                            trip=trip, secret=link.rsplit("/", 1)[1])
    await session.commit()
