"""Email behind an interface, like WhatsApp. Two senders:

* `MockEmail` records the message and says "simulated": nothing leaves the machine. Used until the SMTP settings are filled in.
* `SmtpEmail` sends through any mailbox that speaks SMTP (Gmail with an app password, the company's own mail host).

Only the standard library is used. Email is used for the companies that ask for transport (request received and every update),
and only when they gave an address. Addresses are personal data: the message log holds the masked form (a***@example.com)."""
import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Protocol

from app.config import Settings, get_settings
from app.notify.whatsapp import SendResult, render

log = logging.getLogger("cargoone.email")

SUBJECTS = {
    "shipment_update": {"en": "CargoOne: update on your shipment {trip_code}", "hi": "CargoOne: आपकी खेप {trip_code} की जानकारी", "mr": "CargoOne: तुमच्या खेप {trip_code} बद्दल माहिती"},
    "request_received": {"en": "CargoOne: we received your transport request {reference}", "hi": "CargoOne: आपका ट्रांसपोर्ट अनुरोध {reference} मिल गया",
                         "mr": "CargoOne: तुमची वाहतूक विनंती {reference} मिळाली"},
    "request_update": {"en": "CargoOne: update on your transport request {reference}", "hi": "CargoOne: आपके ट्रांसपोर्ट अनुरोध {reference} की जानकारी",
                       "mr": "CargoOne: तुमच्या वाहतूक विनंती {reference} बद्दल माहिती"},
}


# Email-only notices (no WhatsApp template exists for these): subject and body per language.
EMAIL_ONLY: dict[str, dict[str, dict[str, str]]] = {
    "client_welcome": {
        "subject": {"en": "CargoOne: your account for following shipments", "hi": "CargoOne: खेप देखने के लिए आपका खाता", "mr": "CargoOne: खेप पाहण्यासाठी तुमचे खाते"},
        "en": "Hello {name}, {company} has set up an account for you on CargoOne, to follow its shipments and ask for trucks.\n\n"
              "Choose your password here: {link}\n\nThe link can be used once and works for {hours} hours. After that you sign in with this email address ({email}) and your password.\n\n"
              "If you were not expecting this, you can ignore this email.",
        "hi": "नमस्ते {name}, {company} ने CargoOne पर आपके लिए एक खाता बनाया है, ताकि आप उसकी खेप देख सकें और ट्रक माँग सकें।\n\n"
              "अपना पासवर्ड यहाँ चुनें: {link}\n\nयह लिंक एक ही बार चलेगा और {hours} घंटे तक काम करेगा। इसके बाद इसी ईमेल पते ({email}) और अपने पासवर्ड से साइन इन करें।\n\n"
              "अगर आपको इसकी उम्मीद नहीं थी, तो इस ईमेल को अनदेखा कर दें।",
        "mr": "नमस्कार {name}, {company} ने CargoOne वर तुमच्यासाठी खाते तयार केले आहे, जेणेकरून तुम्ही त्यांची खेप पाहू शकता आणि ट्रक मागवू शकता.\n\n"
              "तुमचा पासवर्ड येथे निवडा: {link}\n\nही लिंक एकदाच वापरता येईल आणि {hours} तास चालेल. त्यानंतर याच ईमेल पत्त्याने ({email}) आणि तुमच्या पासवर्डने साइन इन करा.\n\n"
              "तुम्हाला याची अपेक्षा नसेल, तर हा ईमेल दुर्लक्षित करा.",
    },
}


def mask_email(addr: str) -> str:
    local, _, domain = addr.partition("@")
    return f"{local[:1]}***@{domain}"[:20]


def compose(template: str, lang: str, values: dict[str, str]) -> tuple[str, str]:
    """Subject and plain-text body for a template, in the person's language."""
    if template in EMAIL_ONLY:
        t = EMAIL_ONLY[template]
        return t["subject"].get(lang, t["subject"]["en"]).format(**values), f"{t.get(lang, t['en']).format(**values)}\n\n{get_settings().company_name}\n"
    subject = SUBJECTS[template].get(lang, SUBJECTS[template]["en"]).format(**values)
    return subject, f"{render(template, lang, values)}\n\n{get_settings().company_name}\n"


class Email(Protocol):
    name: str

    async def send(self, to: str, subject: str, body: str) -> SendResult: ...


class MockEmail:
    name = "mock"

    def __init__(self) -> None:
        self.outbox: list[tuple[str, str, str]] = []  # (to, subject, body), for tests and local inspection

    async def send(self, to: str, subject: str, body: str) -> SendResult:
        self.outbox.append((to, subject, body))
        return SendResult("simulated")


class SmtpEmail:
    name = "smtp"

    def __init__(self, s: Settings) -> None:
        self._s = s

    def _deliver(self, msg: EmailMessage) -> None:
        s = self._s
        ctx = ssl.create_default_context()
        if s.smtp_security == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=ctx)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
        with server:
            if s.smtp_security == "starttls":
                server.starttls(context=ctx)
            if s.smtp_user:
                # Google shows app passwords as "abcd efgh ijkl mnop"; the spaces are not part of the password
                server.login(s.smtp_user, "".join(s.smtp_password.split()))
            server.send_message(msg)

    async def send(self, to: str, subject: str, body: str) -> SendResult:
        s = self._s
        msg = EmailMessage()
        msg["Subject"], msg["To"] = subject, to
        msg["From"] = s.email_from or s.smtp_user
        msg.set_content(body, charset="utf-8")
        try:
            await asyncio.to_thread(self._deliver, msg)
        except smtplib.SMTPAuthenticationError as e:
            return SendResult("failed", error=f"login refused ({e.smtp_code}): check the user name and the app password")
        except smtplib.SMTPRecipientsRefused:
            return SendResult("failed", error="the address was refused by the mail server")
        except smtplib.SMTPSenderRefused as e:
            return SendResult("failed", error=f"sender address refused ({e.smtp_code}): the From address must belong to this mailbox")
        except smtplib.SMTPException as e:
            return SendResult("failed", error=f"smtp error {getattr(e, 'smtp_code', '')} {type(e).__name__}".strip())
        except (OSError, ssl.SSLError) as e:  # wrong host or port, blocked network, timeout, TLS mismatch
            return SendResult("failed", error=f"could not connect ({type(e).__name__}): check host, port and security setting")
        return SendResult("sent")


_mock = MockEmail()


def get_email() -> Email:
    s = get_settings()
    if s.email_provider == "smtp":
        if s.smtp_host and (s.email_from or s.smtp_user):
            return SmtpEmail(s)
        log.warning("EMAIL_PROVIDER=smtp but the host or the from address is missing: emails are only recorded, not sent")
    return _mock


def from_address(s: Settings) -> str:
    return parseaddr(s.email_from or s.smtp_user)[1]

