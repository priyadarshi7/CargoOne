import json
import re

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Message, Trip
from app.notify import whatsapp as wa
from app.notify.whatsapp import PARAMS, TEXT, MetaWhatsApp, render
from tests.conftest import login
from tests.test_pin_reset import office
from tests.test_planning import body, fresh_vehicle_and_driver, refs, t0
from tests.test_setup import D


async def register(client: AsyncClient, ops: dict, **kw) -> dict:
    res = await client.post("/drivers", headers=ops, json=D(**kw))
    assert res.status_code == 201, res.text
    return res.json()


async def onboard(client: AsyncClient, invite_url: str, pin: str = "7391") -> dict:
    token = invite_url.rsplit("/", 1)[1]
    res = await client.post(f"/onboard/{token}", json={"pin": pin})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


async def inbox(client: AsyncClient, h: dict) -> dict:
    return (await client.get("/notifications/mine", headers=h)).json()


async def plan_for(client: AsyncClient, ops: dict, driver_id: str, **extra) -> dict:
    r = await refs(client, ops)
    v, _ = await fresh_vehicle_and_driver()
    res = await client.post("/planning/trips", headers=ops, json=body(r, v, driver_id, t0(), **extra))
    assert res.status_code == 201, res.text
    return res.json()


def test_every_template_has_text_in_all_languages_with_the_same_blanks() -> None:
    for name, params in PARAMS.items():
        for lang in ("en", "hi", "mr"):
            assert set(re.findall(r"\{(\w+)\}", TEXT[name][lang])) == set(params), (name, lang)
    assert "Asha" in render("welcome", "mr", {"name": "Asha", "link": "https://x/y"})


async def test_registering_a_driver_sends_the_app_link_and_records_it(client: AsyncClient) -> None:
    ops = await office(client)
    made = await register(client, ops, name="Welcome Driver", language="hi")
    inv = made["invite"]
    assert inv["status"] == "simulated" and inv["provider"] == "mock"  # honest: nothing really left the machine
    assert "/onboard/" in inv["url"] and inv["url"] in inv["text"] and "Welcome Driver" in inv["text"] and inv["whatsapp_link"].startswith("https://wa.me/91")
    async with SessionLocal() as s:
        m = await s.scalar(select(Message).where(Message.template == "welcome").order_by(Message.created_at.desc()))
        assert m.to_masked.endswith(made["driver"]["phone"][-4:]) and m.to_masked.startswith("*")
        assert inv["url"].rsplit("/", 1)[1] not in m.body and "•••" in m.body  # the one-time secret is not kept in the log


async def test_the_driver_sets_their_own_pin_from_the_link_and_the_link_dies(client: AsyncClient) -> None:
    ops = await office(client)
    made = await register(client, ops)
    token = made["invite"]["url"].rsplit("/", 1)[1]
    info = (await client.get(f"/onboard/{token}")).json()
    assert info["name"] == made["driver"]["name"] and "phone" not in info
    assert (await client.post(f"/onboard/{token}", json={"pin": "1111"})).status_code == 422  # too easy
    h = await onboard(client, made["invite"]["url"], "7391")
    assert (await client.get("/auth/me", headers=h)).json()["must_change_secret"] is False
    phone = made["driver"]["phone"]
    assert (await client.post("/auth/login", json={"identifier": phone, "secret": "7391"})).status_code == 200
    assert (await client.post("/auth/login", json={"identifier": phone, "secret": made["pin"]})).status_code == 401  # the office-known PIN is gone
    assert (await client.get(f"/onboard/{token}")).status_code == 410 and (await client.post(f"/onboard/{token}", json={"pin": "7391"})).status_code == 410
    assert (await client.get("/onboard/" + "x" * 40)).status_code == 404
    mine = await inbox(client, h)
    assert mine["unread"] == 1 and mine["items"][0]["kind"] == "welcome"


async def test_resending_replaces_the_link_and_stops_once_the_driver_is_in(client: AsyncClient) -> None:
    ops = await office(client)
    made = await register(client, ops)
    again = (await client.post(f"/drivers/{made['driver']['id']}/invite", headers=ops)).json()
    assert again["url"] != made["invite"]["url"]
    assert (await client.get(f"/onboard/{made['invite']['url'].rsplit('/', 1)[1]}")).status_code == 410  # the old link is replaced
    await onboard(client, again["url"])
    assert (await client.post(f"/drivers/{made['driver']['id']}/invite", headers=ops)).status_code == 409
    billing = await office(client, "billing@cargoone.dev")
    assert (await client.post(f"/drivers/{made['driver']['id']}/invite", headers=billing)).status_code == 403


async def test_assigning_a_trip_notifies_the_driver_in_the_app_and_on_whatsapp(client: AsyncClient) -> None:
    ops = await office(client)
    made = await register(client, ops, name="Assigned Driver")
    h = await onboard(client, made["invite"]["url"])
    await client.post("/notifications/read-all", headers=h)
    trip = await plan_for(client, ops, made["driver"]["id"])
    items = (await inbox(client, h))["items"]
    top = items[0]
    assert top["kind"] == "trip_assigned" and trip["lr_no"] in top["body"] and top["link"].startswith("/driver?trip=")
    async with SessionLocal() as s:
        m = await s.scalar(select(Message).where(Message.template == "trip_assigned", Message.trip_id.is_not(None)).order_by(Message.created_at.desc()))
        t = await s.get(Trip, m.trip_id)
        assert t.lr_no == trip["lr_no"] and trip["lr_no"] in m.body and "Assigned Driver" in m.body and f"/driver?trip={t.id}" in m.body


async def test_a_driver_who_has_not_opened_the_app_gets_a_working_way_in_with_the_trip(client: AsyncClient) -> None:
    ops = await office(client)
    made = await register(client, ops, name="Not Yet Driver")
    await plan_for(client, ops, made["driver"]["id"])
    async with SessionLocal() as s:
        m = await s.scalar(select(Message).where(Message.template == "trip_assigned").order_by(Message.created_at.desc()))
        assert "/onboard/•••" in m.body  # the link in the message is a fresh onboarding link, secret not kept
    assert (await client.get(f"/onboard/{made['invite']['url'].rsplit('/', 1)[1]}")).status_code == 410  # replaced by the newer one


async def test_replanning_and_cancelling_tell_the_right_drivers(client: AsyncClient) -> None:
    ops = await office(client)
    a = await register(client, ops, name="Driver A")
    b = await register(client, ops, name="Driver B")
    ha, hb = await onboard(client, a["invite"]["url"]), await onboard(client, b["invite"]["url"], "7392")
    trip = await plan_for(client, ops, a["driver"]["id"])
    await client.post("/notifications/read-all", headers=ha)
    await client.post("/notifications/read-all", headers=hb)

    moved = await client.patch(f"/planning/trips/{trip['id']}", headers=ops, json={"driver_id": b["driver"]["id"], "reason": "Swap"})
    assert moved.status_code == 200, moved.text
    assert "another driver" in (await inbox(client, ha))["items"][0]["body"]
    assert (await inbox(client, hb))["items"][0]["kind"] == "trip_assigned"

    await client.post("/notifications/read-all", headers=hb)
    v2, _ = await fresh_vehicle_and_driver()
    await client.patch(f"/planning/trips/{trip['id']}", headers=ops, json={"vehicle_id": v2, "reason": "Breakdown"})
    assert "truck is now" in (await inbox(client, hb))["items"][0]["body"]

    assert (await client.post(f"/planning/trips/{trip['id']}/cancel", headers=ops, json={"reason": "Load not ready"})).status_code == 200
    assert "cancelled" in (await inbox(client, hb))["items"][0]["body"]


async def test_a_broken_whatsapp_never_blocks_planning(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    class Down:
        name = "meta"

        async def send(self, *a, **k):
            raise RuntimeError("provider exploded")

    ops = await office(client)
    made = await register(client, ops)
    h = await onboard(client, made["invite"]["url"])
    monkeypatch.setattr("app.notify.service.get_whatsapp", lambda: Down())
    trip = await plan_for(client, ops, made["driver"]["id"])  # still 201
    assert trip["lr_no"].startswith("LR/")
    assert (await inbox(client, h))["items"][0]["kind"] == "trip_assigned"  # the in-app notice still arrives
    async with SessionLocal() as s:
        m = await s.scalar(select(Message).where(Message.template == "trip_assigned").order_by(Message.created_at.desc()))
        assert m.status == "failed" and "RuntimeError" in m.error  # and the office can see why WhatsApp did not go


async def test_drivers_with_no_phone_are_skipped_not_failed(client: AsyncClient) -> None:
    from app.models import User
    from app.notify.service import send_whatsapp

    async with SessionLocal() as s:
        u = User(name="No Phone", role="driver", language="en", password_hash="x")
        s.add(u)
        await s.flush()
        m = await send_whatsapp(s, u, "welcome", {"name": "No Phone", "link": "https://x"})
        assert (m.status, m.error) == ("skipped", "no phone number")
        await s.rollback()


async def test_the_inbox_is_private_and_the_message_log_is_for_the_office(client: AsyncClient, driver: dict) -> None:
    ops = await office(client)
    made = await register(client, ops)
    other = await onboard(client, made["invite"]["url"])
    mine, theirs = await inbox(client, driver), await inbox(client, other)
    assert not {i["id"] for i in mine["items"]} & {i["id"] for i in theirs["items"]}
    assert (await client.get("/notifications/mine")).status_code == 401
    log = (await client.get("/messages", headers=ops)).json()
    assert log["live"] is False and log["provider"] == "mock" and log["items"]
    assert all(re.fullmatch(r"\**\d{4}|.\*\*\*@.+", i["to"] or "0000") for i in log["items"])  # numbers and addresses are masked
    assert (await client.get("/messages", headers=await office(client, "billing@cargoone.dev"))).status_code == 200
    assert (await client.get("/messages", headers=await office(client, "md@cargoone.dev"))).status_code == 403
    assert (await client.get("/messages", headers=driver)).status_code == 403


async def test_the_drivers_own_list_carries_the_load_details_but_the_offices_list_does_not(client: AsyncClient) -> None:
    ops = await office(client)
    made = await register(client, ops)
    h = await onboard(client, made["invite"]["url"])
    await plan_for(client, ops, made["driver"]["id"], material="Steel coils", weight_tonnes="18", packages=12, consignee_name="Demo Consignee", consignee_phone="9876543210")
    mine = (await client.get("/trips/mine", headers=h)).json()[0]
    assert (mine["material"], mine["weight_tonnes"], mine["packages"], mine["consignee_name"], mine["consignee_phone"]) == ("Steel coils", 18.0, 12, "Demo Consignee", "9876543210")
    listed = (await client.get("/trips", headers=ops)).json()
    assert all("consignee_name" not in t and "consignee_phone" not in t for t in listed)


async def test_the_meta_sender_posts_an_approved_template_with_numbered_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(url=str(req.url), auth=req.headers["authorization"], body=json.loads(req.content))
        return httpx.Response(200, json={"messages": [{"id": "wamid.ABC"}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(wa.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    s = wa.get_settings().model_copy(update={"whatsapp_token": "tok", "whatsapp_phone_number_id": "123", "whatsapp_template_prefix": "cargoone"})
    res = await MetaWhatsApp(s).send("9876543210", "trip_assigned", "mr", {"name": "Ramesh", "trip_code": "TRP-1", "lr": "LR/MH20/26-27/000001", "route": "A - B",
                                                                       "vehicle": "MH20 AB 1234", "start": "05 Nov,\n09:00", "link": "https://app/driver"})
    assert (res.status, res.provider_id) == ("sent", "wamid.ABC")
    assert seen["url"].endswith("/123/messages") and seen["auth"] == "Bearer tok"
    t = seen["body"]["template"]
    assert seen["body"]["to"] == "919876543210" and t["name"] == "cargoone_trip_assigned" and t["language"]["code"] == "mr"
    params = [p["text"] for p in t["components"][0]["parameters"]]
    assert params == ["Ramesh", "TRP-1", "LR/MH20/26-27/000001", "A - B", "MH20 AB 1234", "05 Nov, 09:00", "https://app/driver"]  # in template order, no newlines


async def test_the_meta_sender_reports_failures_without_the_number(monkeypatch: pytest.MonkeyPatch) -> None:
    real = httpx.AsyncClient
    err = httpx.Response(401, json={"error": {"code": 190, "message": "Invalid OAuth access token"}})
    monkeypatch.setattr(wa.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(lambda r: err), **kw))
    s = wa.get_settings().model_copy(update={"whatsapp_token": "bad", "whatsapp_phone_number_id": "1"})
    res = await MetaWhatsApp(s).send("9876543210", "welcome", "en", {"name": "A", "link": "https://x"})
    assert res.status == "failed" and "401" in res.error and "190" in res.error and "9876543210" not in res.error


async def test_meta_without_credentials_falls_back_to_the_recording_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wa, "get_settings", lambda: wa.Settings(whatsapp_provider="meta", whatsapp_token="", whatsapp_phone_number_id="", _env_file=None))
    assert wa.get_whatsapp().name == "mock" and wa.is_live() is False
    _ = login  # (imported for parity with the other suites)


def test_template_names_can_be_overridden_and_welcome_has_its_own_default() -> None:
    from app.config import Settings

    s = Settings(_env_file=None)
    assert wa.template_name(s, "welcome") == "cargoone_driver_account" and wa.template_name(s, "trip_update") == "cargoone_trip_update"
    assert wa.template_name(s.model_copy(update={"whatsapp_template_welcome": "my_name"}), "welcome") == "my_name"
    assert wa.template_name(s.model_copy(update={"whatsapp_template_prefix": "acme"}), "request_update") == "acme_request_update"
    # the shipment update is approved as one name per language; the others keep one name for all three
    assert [wa.template_name(s, "shipment_update", x) for x in ("en", "hi", "mr")] == ["cargoone_shipment_update", "cargoone_shipment_update_hi", "cargoone_shipment_update_mr"]
    assert wa.template_name(s, "trip_update", "hi") == "cargoone_trip_update"
    assert wa.template_name(s.model_copy(update={"whatsapp_template_shipment_update_hi": "my_hi"}), "shipment_update", "hi") == "my_hi"
