import smtplib
from typing import ClassVar

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import Settings
from app.db import SessionLocal
from app.models import Message
from app.notify import email as em
from app.notify.email import SmtpEmail, compose, get_email, mask_email
from tests.test_pin_reset import office
from tests.test_requests import payload, submit, token_of


def cfg(**kw) -> Settings:
    return Settings(_env_file=None, email_provider="smtp", smtp_host="smtp.example.test", smtp_user="ops@example.test", smtp_password="app-password-123", **kw)


def test_the_subject_and_body_follow_the_language() -> None:
    values = {"name": "Anil", "reference": "REQ-1001", "link": "https://x/request/REQ-1001.abc"}
    for lang in ("en", "hi", "mr"):
        subject, body = compose("request_received", lang, values)
        assert "REQ-1001" in subject and "REQ-1001" in body and "https://x/request/REQ-1001.abc" in body
    assert compose("request_received", "xx", values)[0].startswith("CargoOne: we received")  # unknown language falls back to English
    assert mask_email("anil@acme.example") == "a***@acme.example"


async def test_a_request_with_an_email_gets_an_email_and_every_update_too(client: AsyncClient) -> None:
    ops = await office(client)
    sent = await submit(client, email="anil@acme.example")
    async with SessionLocal() as s:
        mails = (await s.scalars(select(Message).where(Message.channel == "email", Message.template == "request_received").order_by(Message.created_at.desc()))).all()
        m = mails[0]
        assert (m.status, m.provider, m.to_masked) == ("simulated", "mock", "a***@acme.example")  # honest: recorded, not sent
        assert sent["reference"] in m.body and token_of(sent).split(".")[1] not in m.body  # the link's secret part is not kept
    rid = next(r["id"] for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == sent["reference"])
    await client.post(f"/requests/{rid}/accept", headers=ops, json={"note": "ok"})
    async with SessionLocal() as s:
        upd = await s.scalar(select(Message).where(Message.channel == "email", Message.template == "request_update").order_by(Message.created_at.desc()))
        assert upd.to_masked == "a***@acme.example" and "accepted" in upd.body


async def test_no_address_means_no_email(client: AsyncClient) -> None:
    async with SessionLocal() as s:
        before = len((await s.scalars(select(Message.id).where(Message.channel == "email"))).all())
    res = await client.post("/public/requests", json=payload(email=None))
    assert res.status_code == 201
    async with SessionLocal() as s:
        assert len((await s.scalars(select(Message.id).where(Message.channel == "email"))).all()) == before


class FakeSmtp:
    log: ClassVar[list] = []
    fail: Exception | None = None

    def __init__(self, host, port, timeout=None, context=None):
        FakeSmtp.log.append(("connect", host, port, type(self).__name__))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        FakeSmtp.log.append(("starttls",))

    def login(self, user, password):
        FakeSmtp.log.append(("login", user, password))
        if FakeSmtp.fail:
            raise FakeSmtp.fail

    def send_message(self, msg):
        FakeSmtp.log.append(("send", msg["To"], msg["From"], msg["Subject"], msg.get_content()))


class FakeSsl(FakeSmtp):
    pass


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch):
    FakeSmtp.log, FakeSmtp.fail = [], None
    monkeypatch.setattr(em.smtplib, "SMTP", FakeSmtp)
    monkeypatch.setattr(em.smtplib, "SMTP_SSL", FakeSsl)
    return FakeSmtp


async def test_the_smtp_sender_connects_secures_logs_in_and_sends_utf8(smtp) -> None:
    res = await SmtpEmail(cfg()).send("anil@acme.example", "CargoOne: आपका अनुरोध", "नमस्ते Anil")
    assert res.status == "sent"
    kinds = [e[0] for e in smtp.log]
    assert kinds == ["connect", "starttls", "login", "send"]  # in this order: never log in before the connection is encrypted
    assert smtp.log[0][1:3] == ("smtp.example.test", 587)
    sent = smtp.log[-1]
    assert sent[1] == "anil@acme.example" and sent[2] == "ops@example.test" and "आपका" in sent[3] and "नमस्ते" in sent[4]


async def test_ssl_mode_and_a_custom_from_address(smtp) -> None:
    res = await SmtpEmail(cfg(smtp_security="ssl", smtp_port=465, email_from="CargoOne <desk@example.test>")).send("a@b.example", "s", "b")
    assert res.status == "sent" and smtp.log[0][3] == "FakeSsl" and "starttls" not in [e[0] for e in smtp.log]
    assert smtp.log[-1][2] == "CargoOne <desk@example.test>"


@pytest.mark.parametrize(("error", "fragment"), [
    (smtplib.SMTPAuthenticationError(535, b"bad credentials"), "app password"),
    (smtplib.SMTPRecipientsRefused({"a@b.example": (550, b"no such user")}), "refused"),
    (smtplib.SMTPSenderRefused(553, b"not allowed", "x@y.example"), "From address"),
    (TimeoutError("timed out"), "could not connect"),
])
async def test_failures_say_what_to_fix_and_never_echo_the_password(smtp, error, fragment) -> None:
    smtp.fail = error
    res = await SmtpEmail(cfg()).send("a@b.example", "s", "b")
    assert res.status == "failed" and fragment in res.error and "app-password-123" not in res.error


def test_smtp_without_a_host_falls_back_to_the_recording_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(em, "get_settings", lambda: Settings(_env_file=None, email_provider="smtp", smtp_host=""))
    assert get_email().name == "mock"
    monkeypatch.setattr(em, "get_settings", lambda: cfg())
    assert get_email().name == "smtp"


async def test_the_test_email_button_is_for_ops_and_is_logged(client: AsyncClient) -> None:
    ops = await office(client)
    res = await client.post("/messages/test-email", headers=ops, json={"to": "owner@example.test"})
    assert res.status_code == 200 and res.json() == {"status": "simulated", "error": None, "provider": "mock"}
    log = (await client.get("/messages", headers=ops)).json()
    assert log["email_live"] is False and any(i["channel"] == "email" and i["template"] == "test" and i["to"] == "o***@example.test" for i in log["items"])
    assert (await client.post("/messages/test-email", headers=ops, json={"to": "not an address"})).status_code == 422
    assert (await client.post("/messages/test-email", headers=await office(client, "billing@cargoone.dev"), json={"to": "a@b.example"})).status_code == 403
