"""A hired driver's private link does everything a driver's own sign-in does, for one trip, and nothing else."""
import io
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import AuditLog, Trip, TripState, User
from app.notify import sms as sms_mod
from app.notify.sms import MockSms, SmsError, TwilioSms, get_sms, send_sms
from tests.test_planning import fresh_vehicle_and_driver
from tests.test_pod_upload import make_trip
from tests.test_upload_links import biller, new_link, token_of


def photo() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 90, 60)).save(buf, "JPEG")
    return buf.getvalue()


def as_link(link: dict) -> dict:
    return {"Authorization": f"Link {token_of(link)}"}


def new_phone() -> str:
    return f"9{uuid.uuid4().int % 10**9:09d}"


async def hired_trip(client: AsyncClient, *, phone: str | None = None) -> tuple[str, dict, dict]:
    trip_id, _ = await make_trip(assigned=False)
    vehicle, _ = await fresh_vehicle_and_driver()  # its own truck, so no other test's trip keeps it busy
    async with SessionLocal() as s:  # a trip nobody has started yet
        trip = await s.get(Trip, uuid.UUID(trip_id))
        trip.state, trip.vehicle_id = TripState.planned, uuid.UUID(vehicle)
        await s.commit()
    link = await new_link(client, trip_id, phone=phone or new_phone(), driver_name="Ramesh Yadav", lang="mr")
    return trip_id, link, as_link(link)


async def test_the_link_makes_a_driver_record_and_signs_in_as_them(client: AsyncClient) -> None:
    trip_id, _, h = await hired_trip(client)
    me = (await client.get("/auth/me", headers=h)).json()
    assert me["role"] == "driver" and me["name"] == "Ramesh Yadav"
    async with SessionLocal() as s:
        person = await s.get(User, uuid.UUID(me["id"]))
        assert person.employment_type == "hired" and person.password_hash is None and person.language == "mr"
        assert (await s.get(Trip, uuid.UUID(trip_id))).driver_id == person.id
    mine = (await client.get("/trips/mine", headers=h)).json()
    assert [t["id"] for t in mine] == [trip_id]


async def test_the_whole_driver_journey_runs_on_the_link(client: AsyncClient) -> None:
    trip_id, _, h = await hired_trip(client)
    async with SessionLocal() as s:  # booked trips get this from the planning screen
        (await s.get(Trip, uuid.UUID(trip_id))).delivery_code = "4821"
        await s.commit()
    assert (await client.post(f"/trips/{trip_id}/ack", headers=h)).status_code == 200
    assert (await client.post(f"/trips/{trip_id}/start", headers=h)).status_code == 409  # loading first, like an own driver
    loaded = await client.post(f"/trips/{trip_id}/loaded", headers=h, files={"file": ("l.jpg", photo(), "image/jpeg")})
    assert loaded.status_code == 200, loaded.text
    assert (await client.post(f"/trips/{trip_id}/start", headers=h)).status_code == 200
    assert (await client.post("/tracking/consent", headers=h)).status_code == 204
    ping = {"pings": [{"lat": 19.9, "lng": 75.3, "recorded_at": datetime.now(UTC).isoformat()}]}
    assert (await client.post(f"/trips/{trip_id}/pings", headers=h, json=ping)).json()["stored"] == 1
    assert (await client.post(f"/trips/{trip_id}/events", headers=h, json={"kind": "delay", "reason": "traffic", "minutes": 30})).status_code == 201
    assert (await client.post(f"/trips/{trip_id}/arrived", headers=h)).status_code == 200
    async with SessionLocal() as s:
        code = (await s.get(Trip, uuid.UUID(trip_id))).delivery_code
    assert code
    wrong = "0000" if code != "0000" else "1111"
    assert (await client.post(f"/trips/{trip_id}/deliver", headers=h, json={"code": wrong})).status_code == 422
    assert (await client.post(f"/trips/{trip_id}/deliver", headers=h, json={"code": code})).status_code == 200
    office = (await client.get(f"/trips/{trip_id}/timeline", headers=await biller(client))).json()
    assert office["loaded_at"] and office["started_at"] and office["delivery_confirmed_at"]


async def test_expenses_the_inbox_and_alerts_work_on_the_link(client: AsyncClient) -> None:
    trip_id, _, h = await hired_trip(client)
    exp = await client.post("/expenses", headers=h, data={"client_expense_id": uuid.uuid4().hex, "trip_id": trip_id, "category": "toll", "amount": "310", "incurred_at": datetime.now(UTC).isoformat()})
    assert exp.status_code == 200, exp.text
    assert (await client.get("/expenses/mine", headers=h)).status_code == 200
    assert (await client.get("/notifications/mine?limit=5", headers=h)).status_code == 200
    sub = {"endpoint": f"https://push.example/{uuid.uuid4().hex}", "keys": {"p256dh": "k" * 20, "auth": "a" * 8}}
    assert (await client.post("/push/subscribe", headers=h, json=sub)).status_code == 204
    assert (await client.get("/trips/office-contact", headers=h)).status_code == 200


async def test_a_link_is_confined_to_its_own_trip(client: AsyncClient) -> None:
    trip_a, _, h = await hired_trip(client)
    me = (await client.get("/auth/me", headers=h)).json()["id"]
    trip_b, _ = await make_trip(assigned=False)
    async with SessionLocal() as s:  # the same person is on another trip too
        (await s.get(Trip, uuid.UUID(trip_b))).driver_id = uuid.UUID(me)
        await s.commit()
    assert [t["id"] for t in (await client.get("/trips/mine", headers=h)).json()] == [trip_a]
    assert (await client.post(f"/trips/{trip_b}/ack", headers=h)).status_code == 404
    assert (await client.post(f"/trips/{trip_b}/start", headers=h)).status_code == 404
    exp = {"client_expense_id": uuid.uuid4().hex, "trip_id": trip_b, "category": "toll", "amount": "50", "incurred_at": datetime.now(UTC).isoformat()}
    assert (await client.post("/expenses", headers=h, data=exp)).status_code == 404


async def test_a_link_opens_no_office_door_and_cannot_set_a_pin(client: AsyncClient) -> None:
    _, _, h = await hired_trip(client)
    for path in ("/trips", "/setup/drivers", "/tracking/live"):
        assert (await client.get(path, headers=h)).status_code in (403, 404), path
    assert (await client.post("/auth/change-secret", headers=h, json={"current": "x", "new": "123456"})).status_code == 401


async def test_revoked_expired_and_wrong_links_are_refused(client: AsyncClient) -> None:
    trip_id, _, h = await hired_trip(client)
    assert (await client.get("/auth/me", headers={"Authorization": "Link " + "x" * 43})).status_code == 401
    assert (await client.get("/auth/me", headers={"Authorization": "Link short"})).status_code == 401
    assert (await client.delete(f"/trips/{trip_id}/upload-link", headers=await biller(client))).status_code == 204
    assert (await client.get("/auth/me", headers=h)).status_code == 401
    fresh = as_link(await new_link(client, trip_id))
    assert (await client.get("/auth/me", headers=fresh)).status_code == 200
    assert (await client.get("/auth/me", headers=h)).status_code == 401  # a new link replaced the old one


async def test_the_same_mobile_number_is_the_same_driver_on_the_next_trip(client: AsyncClient) -> None:
    phone = new_phone()
    _, _, first = await hired_trip(client, phone=phone)
    _, _, second = await hired_trip(client, phone=phone)
    assert (await client.get("/auth/me", headers=first)).json()["id"] == (await client.get("/auth/me", headers=second)).json()["id"]


async def test_a_mobile_number_of_office_staff_is_refused(client: AsyncClient) -> None:
    trip_id, _ = await make_trip(assigned=False)
    async with SessionLocal() as s:
        staff = await s.scalar(select(User).where(User.email == "ops@cargoone.dev"))
        old, staff.phone = staff.phone, "9111111111"
        await s.commit()
    try:
        res = await client.post(f"/trips/{trip_id}/upload-link", headers=await biller(client), json={"phone": "9111111111"})
        assert res.status_code == 409
    finally:
        async with SessionLocal() as s:
            (await s.scalar(select(User).where(User.email == "ops@cargoone.dev"))).phone = old
            await s.commit()


# --- text messages: tests must never reach Twilio ---

def test_tests_use_the_simulated_sender() -> None:
    assert isinstance(get_sms(), MockSms)


def test_twilio_sends_the_right_request_and_reports_why_it_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def fake_post(url: str, **kw):
        seen.update(url=url, **kw)
        return httpx.Response(201, json={"sid": "SM1"}, request=httpx.Request("POST", url))

    monkeypatch.setattr(sms_mod.httpx, "post", fake_post)
    TwilioSms("AC123", "tok", "+15005550006", "").send("9876543210", "hello")
    assert seen["url"].endswith("/Accounts/AC123/Messages.json") and seen["data"] == {"To": "+919876543210", "Body": "hello", "From": "+15005550006"}
    assert seen["auth"] == ("AC123", "tok")

    monkeypatch.setattr(sms_mod.httpx, "post", lambda url, **kw: httpx.Response(400, json={"message": "Number is not verified"}, request=httpx.Request("POST", url)))
    with pytest.raises(SmsError, match="not verified"):
        TwilioSms("AC123", "tok", "", "MG1").send("9876543210", "hello")


async def test_the_send_ceiling_stops_real_texts(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    fake = TwilioSms("AC", "t", "+1", "")
    monkeypatch.setattr(TwilioSms, "send", lambda self, phone, text: sent.append(phone))
    async with SessionLocal() as s:
        before = await s.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == "sms.sent")) or 0
        monkeypatch.setattr(get_settings(), "sms_max_total", before + 1)
        assert await send_sms(s, fake, "9876543210", "one") is None
        await s.flush()
        refused = await send_sms(s, fake, "9876543210", "two")
        await s.rollback()
    assert refused and "limit" in refused and len(sent) == 1


async def test_a_failed_text_still_gives_the_office_a_working_link(client: AsyncClient) -> None:
    class Broken(TwilioSms):
        def send(self, phone: str, text: str) -> None:
            raise SmsError("Number is not verified")

    app.dependency_overrides[get_sms] = lambda: Broken("AC", "t", "+1", "")
    try:
        trip_id, _ = await make_trip(assigned=False)
        link = await new_link(client, trip_id, phone=new_phone())
    finally:
        app.dependency_overrides.pop(get_sms, None)
    assert link["sms_sent"] is False and "not verified" in link["sms_error"]
    assert (await client.get("/auth/me", headers=as_link(link))).status_code == 200


async def test_the_link_lasts_until_after_the_planned_end(client: AsyncClient) -> None:
    trip_id, _ = await make_trip(assigned=False)
    async with SessionLocal() as s:
        (await s.get(Trip, uuid.UUID(trip_id))).planned_end = datetime.now(UTC) + timedelta(days=6)
        await s.commit()
    link = await new_link(client, trip_id)
    assert datetime.fromisoformat(link["expires_at"]) > datetime.now(UTC) + timedelta(days=7)
