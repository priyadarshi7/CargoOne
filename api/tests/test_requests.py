import re
import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Client, Message, TransportRequest, Trip
from app.routers.requests import gstin_ok, status_token
from tests.test_pin_reset import office
from tests.test_planning import body as plan_body
from tests.test_planning import fresh_vehicle_and_driver, refs, t0
from tests.test_setup import digits, mobile


def payload(**kw) -> dict:
    base = {
        "company_name": f"Acme Steel {digits()}", "contact_name": "Anil Mehta", "phone": mobile(), "email": "anil@acme.example", "language": "en",
        "origin": "Chhatrapati Sambhajinagar", "destination": "Pune", "material": "Steel coils", "weight_tonnes": "20", "truck_type": "Container 32 ft",
        "pickup_date": (date.today() + timedelta(days=5)).isoformat(), "notes": "Loading bay 3", "consent": True, "website": "",
    }
    return base | kw


async def submit(client: AsyncClient, **kw) -> dict:
    res = await client.post("/public/requests", json=payload(**kw))
    assert res.status_code == 201, res.text
    return res.json()


def token_of(sent: dict) -> str:
    return sent["status_url"].rsplit("/", 1)[1]


def test_gstin_rules() -> None:
    assert gstin_ok(" 27abcde1234f1z5 ") == "27ABCDE1234F1Z5"
    assert gstin_ok("") is None and gstin_ok(None) is None
    for bad in ("123", "27ABCDE1234F1Z", "ABCDEFGHIJKLMNO"):
        try:
            gstin_ok(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


async def test_anyone_can_ask_for_transport_and_is_told_it_arrived(client: AsyncClient) -> None:
    sent = await submit(client, language="hi")
    assert re.fullmatch(r"REQ-\d+", sent["reference"]) and "/request/REQ-" in sent["status_url"]
    assert sent["message_status"] == "simulated"  # honest: the WhatsApp sender is the recording mock
    async with SessionLocal() as s:
        m = await s.scalar(select(Message).where(Message.template == "request_received").order_by(Message.created_at.desc()))
        assert sent["reference"] in m.body and m.user_id is None and token_of(sent).split(".")[1] not in m.body  # the link's secret part is not kept in the log
    mine = (await client.get(f"/public/requests/{token_of(sent)}")).json()
    assert mine["status"] == "new" and mine["reference"] == sent["reference"] and mine["language"] == "hi"
    assert "phone" not in mine and "email" not in mine and "contact_name" not in mine  # no contact details on the public page


async def test_the_form_is_validated_and_guarded(client: AsyncClient) -> None:
    for bad in (
        {"consent": False}, {"phone": "12345"}, {"pickup_date": (date.today() - timedelta(days=1)).isoformat()},
        {"pickup_date": (date.today() + timedelta(days=400)).isoformat()}, {"gstin": "nonsense"}, {"weight_tonnes": "500"}, {"email": "not an email"},
        {"company_name": "x"}, {"material": ""},
    ):
        assert (await client.post("/public/requests", json=payload(**bad))).status_code == 422, bad
    before = await _count()
    fake = await client.post("/public/requests", json=payload(website="http://spam.example"))  # a bot fills the hidden field
    assert fake.status_code == 201 and fake.json()["reference"] == "REQ-0"
    assert await _count() == before  # and nothing was stored


async def _count() -> int:
    async with SessionLocal() as s:
        return len((await s.scalars(select(TransportRequest.id))).all())


async def test_a_flood_from_one_phone_or_address_is_throttled(client: AsyncClient) -> None:
    from app.routers.requests import phone_limiter, submit_limiter

    submit_limiter.reset()
    phone_limiter.reset()
    same = mobile()
    codes = [(await client.post("/public/requests", json=payload(phone=same))).status_code for _ in range(5)]
    assert codes == [201, 201, 201, 429, 429]  # three a day per number
    submit_limiter.reset()
    phone_limiter.reset()
    codes = [(await client.post("/public/requests", json=payload())).status_code for _ in range(7)]
    assert codes[:5] == [201] * 5 and codes[5:] == [429, 429]  # five an hour per address
    submit_limiter.reset()
    phone_limiter.reset()


async def test_status_links_cannot_be_guessed_or_forged(client: AsyncClient) -> None:
    sent = await submit(client)
    ref, sig = token_of(sent).split(".")
    assert (await client.get(f"/public/requests/{ref}.{'A' * len(sig)}")).status_code == 404  # right reference, wrong signature
    assert (await client.get(f"/public/requests/{ref}")).status_code == 404
    assert (await client.get("/public/requests/" + "z" * 40)).status_code == 404
    assert status_token(ref) == token_of(sent)  # deterministic: later messages can carry the same working link


async def test_ops_onboards_the_company_as_a_client_in_one_step(client: AsyncClient) -> None:
    ops = await office(client)
    sent = await submit(client, gstin="27ABCDE1234F1Z5", language="mr")
    listed = {r["reference"]: r for r in (await client.get("/requests", headers=ops)).json()}
    req = listed[sent["reference"]]
    assert req["status"] == "new" and req["phone"] and req["gstin"] == "27ABCDE1234F1Z5"
    res = await client.post(f"/requests/{req['id']}/accept", headers=ops, json={"quote_amount": "42000", "note": "Truck will be 32 ft"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "accepted" and res.json()["client"] == req["company_name"]
    async with SessionLocal() as s:
        c = await s.scalar(select(Client).where(Client.name == req["company_name"]))
        assert (c.contact_name, c.contact_phone, c.gstin) == ("Anil Mehta", req["phone"], "27ABCDE1234F1Z5") and c.is_active
        m = await s.scalar(select(Message).where(Message.template == "request_update").order_by(Message.created_at.desc()))
        assert sent["reference"] in m.body
    pub = (await client.get(f"/public/requests/{token_of(sent)}")).json()
    assert pub["status"] == "accepted" and pub["quote_amount"] == 42000.0 and pub["reply"] == "Truck will be 32 ft"
    assert (await client.post(f"/requests/{req['id']}/accept", headers=ops, json={})).status_code == 409  # only once


async def test_an_existing_company_is_not_duplicated(client: AsyncClient) -> None:
    ops = await office(client)
    name = f"Repeat Buyer {digits()}"
    first = await submit(client, company_name=name)
    second = await submit(client, company_name=name)
    ids = {r["reference"]: r["id"] for r in (await client.get("/requests", headers=ops)).json()}
    assert (await client.post(f"/requests/{ids[first['reference']]}/accept", headers=ops, json={})).status_code == 200
    clash = await client.post(f"/requests/{ids[second['reference']]}/accept", headers=ops, json={})
    assert clash.status_code == 409 and "already exists" in clash.json()["detail"]
    async with SessionLocal() as s:
        existing = (await s.scalar(select(Client).where(Client.name == name))).id
    ok = await client.post(f"/requests/{ids[second['reference']]}/accept", headers=ops, json={"client_id": str(existing)})
    assert ok.status_code == 200 and ok.json()["client_id"] == str(existing)
    assert (await client.post(f"/requests/{ids[second['reference']]}/accept", headers=ops, json={"client_id": str(uuid.uuid4())})).status_code == 409


async def test_declining_needs_a_reason_the_requester_can_read(client: AsyncClient) -> None:
    ops = await office(client)
    sent = await submit(client)
    rid = next(r["id"] for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == sent["reference"])
    assert (await client.post(f"/requests/{rid}/decline", headers=ops, json={"reason": ""})).status_code == 422
    assert (await client.post(f"/requests/{rid}/decline", headers=ops, json={"reason": "We do not run to that route"})).json()["status"] == "declined"
    pub = (await client.get(f"/public/requests/{token_of(sent)}")).json()
    assert pub["status"] == "declined" and pub["reply"] == "We do not run to that route" and pub["quote_amount"] is None
    assert sent["reference"] not in {r["reference"] for r in (await client.get("/requests", headers=ops)).json()}  # leaves the open list
    assert sent["reference"] in {r["reference"] for r in (await client.get("/requests?state=all", headers=ops)).json()}


async def test_a_trip_booked_from_the_request_closes_the_loop(client: AsyncClient) -> None:
    ops = await office(client)
    sent = await submit(client, destination="Nagpur", language="en")
    req = next(r for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == sent["reference"])
    vid, did = await fresh_vehicle_and_driver()
    r = await refs(client, ops)
    trip_body = plan_body(r, vid, did, t0(), request_id=req["id"], client_id=r["clients"][0]["id"])
    assert (await client.post("/planning/trips", headers=ops, json=trip_body)).status_code == 422  # not accepted yet, and not this client
    accepted = (await client.post(f"/requests/{req['id']}/accept", headers=ops, json={})).json()
    wrong = await client.post("/planning/trips", headers=ops, json=plan_body(r, vid, did, t0(), request_id=req["id"], client_id=next(c["id"] for c in r["clients"] if c["id"] != accepted["client_id"])))
    assert wrong.status_code == 422
    r = await refs(client, ops)
    ok = await client.post("/planning/trips", headers=ops, json=plan_body(r, vid, did, t0(), request_id=req["id"], client_id=accepted["client_id"]))
    assert ok.status_code == 201, ok.text
    pub = (await client.get(f"/public/requests/{token_of(sent)}")).json()
    assert pub["status"] == "booked" and pub["trip_code"] == ok.json()["trip_code"] and pub["planned_start"]
    async with SessionLocal() as s:
        assert (await s.scalar(select(Trip.id).where(Trip.trip_code == ok.json()["trip_code"]))) is not None
    again = await client.post("/planning/trips", headers=ops, json=plan_body(r, *await fresh_vehicle_and_driver(), t0(), request_id=req["id"], client_id=accepted["client_id"]))
    assert again.status_code == 422  # a request books one trip


async def test_only_the_office_sees_requests_and_only_ops_decides(client: AsyncClient, driver: dict) -> None:
    sent = await submit(client)
    ops = await office(client)
    billing = await office(client, "billing@cargoone.dev")
    md = await office(client, "md@cargoone.dev")
    rid = next(r["id"] for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == sent["reference"])
    assert (await client.get("/requests", headers=billing)).status_code == 200
    assert (await client.post(f"/requests/{rid}/accept", headers=billing, json={})).status_code == 403
    for h in (md, driver):
        assert (await client.get("/requests", headers=h)).status_code == 403
    assert (await client.get("/requests")).status_code == 401
    items = {i["key"]: i for i in (await client.get("/attention", headers=ops)).json()["items"]}
    assert items["requests_new"]["count"] >= 1  # shows on the dashboard until someone answers


async def test_clients_can_carry_a_gstin(client: AsyncClient) -> None:
    ops = await office(client)
    ok = await client.post("/setup/clients", headers=ops, json={"name": f"Gst Client {digits()}", "gstin": "27abcde1234f1z5"})
    assert ok.status_code == 201 and ok.json()["gstin"] == "27ABCDE1234F1Z5"
    assert (await client.post("/setup/clients", headers=ops, json={"name": f"Bad Gst {digits()}", "gstin": "123"})).status_code == 422
    cleared = await client.patch(f"/setup/clients/{ok.json()['id']}", headers=ops, json={"gstin": None})
    assert cleared.json()["gstin"] is None
