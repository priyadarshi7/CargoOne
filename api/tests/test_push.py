"""Web Push: subscribing, one person per phone, alerts when a trip is assigned, forgetting dead phones."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import PushSubscription
from app.notify import push as push_mod
from tests.test_notifications import inbox, onboard, plan_for, register
from tests.test_pin_reset import office


def sub(endpoint: str | None = None) -> dict:
    return {"endpoint": endpoint or f"https://push.example/{uuid.uuid4().hex}", "keys": {"p256dh": "BPubKeyForTestsOnly12345", "auth": "authsecret1234"}}


async def new_driver(client: AsyncClient, ops: dict) -> tuple[dict, dict]:
    made = await register(client, ops)
    return made, await onboard(client, made["invite"]["url"])


async def test_key_endpoint_says_recording_without_keys(client: AsyncClient) -> None:
    h = await office(client)
    res = await client.get("/push/key", headers=h)
    assert res.status_code == 200
    assert res.json() == {"key": None, "live": False}
    assert (await client.get("/push/key")).status_code == 401


async def test_subscribe_moves_with_the_phone_and_unsubscribe_forgets_it(client: AsyncClient) -> None:
    ops = await office(client)
    _, a = await new_driver(client, ops)
    _, b = await new_driver(client, ops)
    s = sub()
    assert (await client.post("/push/subscribe", headers=a, json=s)).status_code == 204
    assert (await client.get("/push/status", headers=a)).json()["phones"] == 1
    assert (await client.post("/push/subscribe", headers=b, json=s)).status_code == 204  # same phone, new person
    assert (await client.get("/push/status", headers=a)).json()["phones"] == 0
    assert (await client.get("/push/status", headers=b)).json()["phones"] == 1
    assert (await client.post("/push/unsubscribe", headers=b, json={"endpoint": s["endpoint"]})).status_code == 204
    assert (await client.get("/push/status", headers=b)).json()["phones"] == 0


async def test_only_https_endpoints_and_a_cap_per_person(client: AsyncClient) -> None:
    ops = await office(client)
    _, d = await new_driver(client, ops)
    assert (await client.post("/push/subscribe", headers=d, json=sub("http://insecure.example/x"))).status_code == 422
    for _ in range(7):
        assert (await client.post("/push/subscribe", headers=d, json=sub())).status_code == 204
    assert (await client.get("/push/status", headers=d)).json()["phones"] == 5


async def test_assigning_a_trip_records_an_alert_for_that_driver(client: AsyncClient) -> None:
    ops = await office(client)
    made, d = await new_driver(client, ops)
    push_mod.outbox.clear()
    trip = await plan_for(client, ops, made["driver"]["id"])
    mine = [p for uid, p in push_mod.outbox if str(uid) == made["driver"]["id"]]
    assert mine, "no alert recorded"
    assert trip["trip_code"] in mine[-1]["body"]
    assert mine[-1]["url"].startswith("/driver?trip=")
    assert (await inbox(client, d))["unread"] >= 1  # the in-app message is still there


async def test_live_send_forgets_a_phone_the_push_service_says_is_gone(client: AsyncClient, monkeypatch) -> None:
    ops = await office(client)
    made, d = await new_driver(client, ops)
    good, gone = sub(), sub()
    for s in (good, gone):
        await client.post("/push/subscribe", headers=d, json=s)
    sent: list[str] = []

    def fake(target, payload):
        sent.append(target.endpoint)
        return 410 if target.endpoint == gone["endpoint"] else 201

    monkeypatch.setattr(push_mod, "live", lambda: True)
    monkeypatch.setattr("app.routers.push.live", lambda: True)
    monkeypatch.setattr(push_mod, "_send_one", fake)
    res = await client.post("/push/test", headers=d)
    assert res.json() == {"sent": 2, "live": True}
    assert set(sent) == {good["endpoint"], gone["endpoint"]}
    async with SessionLocal() as s:
        left = (await s.scalars(select(PushSubscription.endpoint).where(PushSubscription.user_id == uuid.UUID(made["driver"]["id"])))).all()
    assert left == [good["endpoint"]]


async def test_a_driver_can_mark_one_message_read_but_not_someone_elses(client: AsyncClient) -> None:
    ops = await office(client)
    made, d = await new_driver(client, ops)
    _, other = await new_driver(client, ops)
    await plan_for(client, ops, made["driver"]["id"])
    mine = (await inbox(client, d))["items"]
    assert mine and not mine[0]["read"]
    assert (await client.post(f"/notifications/{mine[0]['id']}/read", headers=other)).status_code == 204  # not theirs: changes nothing
    assert not next(i for i in (await inbox(client, d))["items"] if i["id"] == mine[0]["id"])["read"]
    assert (await client.post(f"/notifications/{mine[0]['id']}/read", headers=d)).status_code == 204
    assert next(i for i in (await inbox(client, d))["items"] if i["id"] == mine[0]["id"])["read"]
