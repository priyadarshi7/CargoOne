import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Client, Trip, TripEvent
from tests.conftest import login
from tests.test_pin_reset import office
from tests.test_planning import body as plan_body
from tests.test_planning import fresh_vehicle_and_driver, refs
from tests.test_requests import submit, token_of
from tests.test_setup import digits


async def new_client_login(client: AsyncClient, ops: dict, *, name: str | None = None, change: bool = True) -> dict:
    """A fresh client company with its own login. Returns {client_id, email, password, headers}."""
    company = name or f"Portal Co {digits()}"
    created = await client.post("/setup/clients", headers=ops, json={"name": company, "contact_name": "Rekha", "contact_phone": f"9{digits(9)}"})
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    email = f"rekha{digits()}@client.example"
    made = await client.post(f"/setup/clients/{cid}/portal", headers=ops, json={"name": "Rekha Shah", "email": email})
    assert made.status_code == 201, made.text
    pw = made.json()["password"]
    headers = await login(client, email, pw)
    if change:  # until the temporary password is replaced nothing else works: do what the person must do first
        new = f"Better-pass-{digits(6)}"
        res = await client.post("/auth/change-secret", headers=headers, json={"current": pw, "new": new})
        assert res.status_code == 200, res.text
        headers, pw = {"Authorization": f"Bearer {res.json()['access_token']}"}, new
    return {"client_id": cid, "email": email, "password": pw, "headers": headers, "company": company, "user_id": made.json()["login"]["id"]}


async def trip_for(client: AsyncClient, ops: dict, client_id: str) -> dict:
    r = await refs(client, ops)
    v, d = await fresh_vehicle_and_driver()
    res = await client.post("/planning/trips", headers=ops, json=plan_body(r, v, d, datetime.now(UTC) + timedelta(days=9), client_id=client_id))
    assert res.status_code == 201, res.text
    return res.json()


async def test_a_client_login_sees_only_its_own_shipments_and_requests(client: AsyncClient) -> None:
    ops = await office(client)
    mine = await new_client_login(client, ops)
    other = await new_client_login(client, ops)
    t1 = await trip_for(client, ops, mine["client_id"])
    t2 = await trip_for(client, ops, other["client_id"])
    seen = (await client.get("/portal/shipments", headers=mine["headers"])).json()
    assert [s["trip_code"] for s in seen] == [t1["trip_code"]] and t2["trip_code"] not in str(seen)
    assert seen[0]["stage"] == "booked" and seen[0]["token"].startswith(t1["trip_code"] + ".c")
    # the address it hands over opens that client's page, and only that trip
    page = (await client.get(f"/public/shipments/{seen[0]['token']}")).json()
    assert page["audience"] == "client" and page["trip_code"] == t1["trip_code"]
    me = (await client.get("/portal/me", headers=mine["headers"])).json()
    assert me["company"] == mine["company"]


async def test_a_client_login_reaches_nothing_else(client: AsyncClient) -> None:
    ops = await office(client)
    mine = await new_client_login(client, ops)
    h = mine["headers"]
    for path in ("/trips", "/requests", "/planning/board", "/billing/queue", "/billing/invoices", "/setup/clients", "/review", "/tracking/live", "/expenses", "/dashboard/summary"):
        res = await client.get(path, headers=h)
        assert res.status_code in (403, 404), (path, res.status_code)
    assert (await client.get("/portal/shipments", headers=ops)).status_code in (403, 200)  # the office has its own screens; admin may look
    driver_like = await login(client, "billing@cargoone.dev", "cargoone-dev")
    assert (await client.get("/portal/shipments", headers=driver_like)).status_code == 403
    assert (await client.get("/portal/shipments")).status_code == 401


async def test_the_login_must_change_its_password_and_can_be_switched_off(client: AsyncClient) -> None:
    ops = await office(client)
    c = await new_client_login(client, ops, change=False)
    me = (await client.get("/auth/me", headers=c["headers"])).json()
    assert me["role"] == "client" and me["must_change_secret"] is True
    assert (await client.get("/portal/me", headers=c["headers"])).status_code == 403  # nothing works until the password is replaced
    changed = await client.post("/auth/change-secret", headers=c["headers"], json={"current": c["password"], "new": f"A-better-pass-{digits(6)}"})
    assert changed.status_code == 200
    c["headers"] = {"Authorization": f"Bearer {changed.json()['access_token']}"}
    assert (await client.get("/portal/me", headers=c["headers"])).status_code == 200
    off = await client.patch(f"/setup/clients/{c['client_id']}/portal/{c['user_id']}", headers=ops, json={"is_active": False})
    assert off.json()["is_active"] is False
    assert (await client.get("/portal/me", headers=c["headers"])).status_code == 401  # signed out at once
    assert (await client.post("/auth/login", json={"identifier": c["email"], "secret": c["password"]})).status_code == 401
    reset = await client.post(f"/setup/clients/{c['client_id']}/portal/{c['user_id']}/reset-password", headers=ops)
    assert reset.status_code == 200 and reset.json()["password"]
    assert (await client.post(f"/setup/clients/{c['client_id']}/portal", headers=ops, json={"name": "Dup", "email": c["email"]})).status_code == 409


async def test_only_the_ops_head_can_make_client_logins(client: AsyncClient) -> None:
    ops = await office(client)
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    cid = (await client.get("/setup/clients", headers=ops)).json()[0]["id"]
    assert (await client.post(f"/setup/clients/{cid}/portal", headers=billing, json={"name": "X Y", "email": f"x{digits()}@c.example"})).status_code == 403
    assert (await client.get(f"/setup/clients/{cid}/portal", headers=billing)).status_code == 200  # billing may look


async def test_a_client_asks_for_the_next_truck_from_its_login(client: AsyncClient) -> None:
    ops = await office(client)
    c = await new_client_login(client, ops)
    when = (date.today() + timedelta(days=4)).isoformat()
    body = {"origin": "Chhatrapati Sambhajinagar", "destination": "Nashik", "material": "Cotton bales", "weight_tonnes": "12", "pickup_date": when}
    made = await client.post("/portal/requests", headers=c["headers"], json=body)
    assert made.status_code == 201, made.text
    listed = (await client.get("/portal/requests", headers=c["headers"])).json()
    assert [r["reference"] for r in listed] == [made.json()["reference"]] and listed[0]["status"] == "new"
    # it reaches the office already linked to this client
    open_ones = (await client.get("/requests", headers=ops)).json()
    mine = next(r for r in open_ones if r["reference"] == made.json()["reference"])
    assert mine["client_id"] == c["client_id"] and mine["company_name"] == c["company"]
    assert (await client.post("/portal/requests", headers=c["headers"], json={**body, "pickup_date": "2020-01-01"})).status_code == 422
    accepted = await client.post(f"/requests/{mine['id']}/accept", headers=ops, json={})  # no client chosen: the request's own client is kept
    assert accepted.status_code == 200 and accepted.json()["client_id"] == c["client_id"]


async def test_the_quote_is_accepted_online_before_the_trip_can_be_booked(client: AsyncClient) -> None:
    ops = await office(client)
    sent = await submit(client)
    rid = next(r["id"] for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == sent["reference"])
    acc = (await client.post(f"/requests/{rid}/accept", headers=ops, json={"quote_amount": "42000"})).json()
    tok = token_of(sent)
    page = (await client.get(f"/public/requests/{tok}")).json()
    assert page["quote_amount"] == 42000.0 and page["can_respond"] is True and page["quote_accepted"] is False

    r = await refs(client, ops)
    v, d = await fresh_vehicle_and_driver()
    start = datetime.now(UTC) + timedelta(days=6)
    attempt = await client.post("/planning/trips", headers=ops, json=plan_body(r, v, d, start, request_id=rid, client_id=acc["client_id"]))
    assert attempt.status_code == 422 and "not accepted the quote" in attempt.text  # no booking before the yes

    yes = await client.post(f"/public/requests/{tok}/quote", json={"decision": "accept"})
    assert yes.status_code == 200 and yes.json()["quote_accepted"] is True
    assert (await client.post(f"/public/requests/{tok}/quote", json={"decision": "accept"})).status_code == 409  # nothing waiting now
    assert (await client.get(f"/public/requests/{tok}")).json()["can_respond"] is False
    seen = next(x for x in (await client.get("/requests", headers=ops)).json() if x["id"] == rid)
    assert seen["quote_accepted_via"] == "online" and seen["quote_accepted_at"]
    ok = await client.post("/planning/trips", headers=ops, json=plan_body(r, v, d, start, request_id=rid, client_id=acc["client_id"]))
    assert ok.status_code == 201, ok.text


async def test_a_quote_can_be_turned_down_or_confirmed_by_phone(client: AsyncClient) -> None:
    ops = await office(client)
    a = await submit(client)
    rid = next(r["id"] for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == a["reference"])
    await client.post(f"/requests/{rid}/accept", headers=ops, json={"quote_amount": "30000"})
    no = await client.post(f"/public/requests/{token_of(a)}/quote", json={"decision": "decline", "reason": "Too expensive"})
    assert no.json()["status"] == "declined"
    page = (await client.get(f"/public/requests/{token_of(a)}")).json()
    assert page["status"] == "declined" and "Too expensive" in page["reply"]

    b = await submit(client)
    bid = next(r["id"] for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == b["reference"])
    assert (await client.post(f"/requests/{bid}/quote-confirmed", headers=ops, json={})).status_code == 409  # not quoted yet
    await client.post(f"/requests/{bid}/accept", headers=ops, json={"quote_amount": "30000"})
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    assert (await client.post(f"/requests/{bid}/quote-confirmed", headers=billing, json={})).status_code == 403
    done = await client.post(f"/requests/{bid}/quote-confirmed", headers=ops, json={"note": "Mr Mehta called"})
    assert done.status_code == 200 and done.json()["quote_accepted_via"] == "phone"
    assert (await client.get(f"/public/requests/{token_of(b)}")).json()["can_respond"] is False


async def test_a_request_without_a_quote_needs_no_answer(client: AsyncClient) -> None:
    ops = await office(client)
    sent = await submit(client)
    rid = next(r["id"] for r in (await client.get("/requests", headers=ops)).json() if r["reference"] == sent["reference"])
    acc = (await client.post(f"/requests/{rid}/accept", headers=ops, json={})).json()
    assert (await client.get(f"/public/requests/{token_of(sent)}")).json()["can_respond"] is False
    r = await refs(client, ops)
    v, d = await fresh_vehicle_and_driver()
    ok = await client.post("/planning/trips", headers=ops, json=plan_body(r, v, d, datetime.now(UTC) + timedelta(days=7), request_id=rid, client_id=acc["client_id"]))
    assert ok.status_code == 201, ok.text
    async with SessionLocal() as s:
        t = await s.scalar(select(Trip).where(Trip.trip_code == ok.json()["trip_code"]))
        assert (await s.scalar(select(Client.id).where(Client.id == t.client_id))) is not None
        assert uuid.UUID(ok.json()["id"]) == t.id
        assert {e.kind for e in (await s.scalars(select(TripEvent).where(TripEvent.trip_id == t.id))).all()} >= {"booked"}


async def test_a_client_with_no_phone_saved_is_asked_for_one(client: AsyncClient) -> None:
    ops = await office(client)
    company = f"No Phone Co {digits()}"
    cid = (await client.post("/setup/clients", headers=ops, json={"name": company})).json()["id"]
    email = f"nophone{digits()}@client.example"
    pw = (await client.post(f"/setup/clients/{cid}/portal", headers=ops, json={"name": "Sunil Rao", "email": email})).json()["password"]
    first = await login(client, email, pw)
    new = f"Better-pass-{digits(6)}"
    h = {"Authorization": f"Bearer {(await client.post('/auth/change-secret', headers=first, json={'current': pw, 'new': new})).json()['access_token']}"}
    assert (await client.get("/portal/me", headers=h)).json()["has_phone"] is False
    body = {"origin": "Pune", "destination": "Nagpur", "material": "Tiles", "pickup_date": (date.today() + timedelta(days=3)).isoformat()}
    assert (await client.post("/portal/requests", headers=h, json=body)).status_code == 422
    assert (await client.post("/portal/requests", headers=h, json={**body, "phone": f"9{digits(9)}"})).status_code == 201
