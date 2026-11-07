"""The invoice reaches the client (an emailed private link, and the client's own login), and the client can say "I have paid" for billing to confirm."""
import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import Client, Invoice, Message, Role, Trip, User
from tests.test_attention import item
from tests.test_invoice_lifecycle import invoiced, today
from tests.test_pin_reset import office
from tests.test_portal import choose_password, new_client_login
from tests.test_setup import digits
from tests.test_shipments import tokens


async def client_of(invoice_id: str) -> str:
    async with SessionLocal() as s:
        return str((await s.get(Invoice, uuid.UUID(invoice_id))).client_id)


async def give_email(client: AsyncClient, ops: dict, client_id: str, email: str | None = None) -> str:
    email = email or f"accounts{digits()}@client.example"
    assert (await client.patch(f"/setup/clients/{client_id}", headers=ops, json={"email": email})).status_code == 200
    return email


async def no_address_on_file(client_id: str) -> None:
    """Tests share one client company: take away the address (and the logins' addresses) that earlier tests gave it."""
    async with SessionLocal() as s:
        await s.execute(update(Client).where(Client.id == uuid.UUID(client_id)).values(email=None))
        await s.execute(update(User).where(User.client_id == uuid.UUID(client_id), User.role == Role.client).values(is_active=False))
        await s.commit()


async def login_for(client: AsyncClient, ops: dict, client_id: str) -> dict:
    made = await client.post(f"/setup/clients/{client_id}/portal", headers=ops, json={"name": "Accounts", "email": f"login{digits()}@client.example"})
    assert made.status_code == 201, made.text
    return await choose_password(client, made.json()["link"], f"Better-pass-{digits(6)}")


async def emails_for(trip_id: str) -> list[Message]:
    async with SessionLocal() as s:
        return list((await s.scalars(select(Message).where(Message.trip_id == uuid.UUID(trip_id), Message.channel == "email", Message.template == "invoice_sent").order_by(Message.created_at))).all())


async def test_billing_sends_the_invoice_by_email_with_a_private_link_and_only_then_can_the_client_open_it(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    ops = await office(client)
    cid = await client_of(inv["id"])
    t = await tokens(client, ops, tid)
    await no_address_on_file(cid)
    assert (await client.get(f"/public/shipments/{t['client']}/invoice")).status_code == 404  # a draft is the office's business

    no_address = await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)
    assert no_address.status_code == 422 and "email" in no_address.text and (await emails_for(tid)) == []  # nothing goes anywhere without an address

    listed = next(i for i in (await client.get("/billing/invoices", headers=h)).json() if i["id"] == inv["id"])
    assert listed["client_has_email"] is False
    await give_email(client, ops, cid)
    assert next(i for i in (await client.get("/billing/invoices", headers=h)).json() if i["id"] == inv["id"])["client_has_email"] is True

    sent = await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)
    assert sent.status_code == 200 and sent.json()["sent_at"], sent.text
    mails = await emails_for(tid)
    assert len(mails) == 1 and "/s/" in mails[0].body and mails[0].body.count("•••") == 1  # the private address is cut out of the stored copy
    assert inv["invoice_no"] in mails[0].body

    pdf = await client.get(f"/public/shipments/{t['client']}/invoice")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["cache-control"] == "private, no-store"
    assert (await client.get(f"/public/shipments/{t['receiver']}/invoice")).status_code == 404  # the receiver never sees money
    again = await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)  # a second click sends it again, and marks nothing twice
    assert again.json()["sent_at"] == sent.json()["sent_at"] and len(await emails_for(tid)) == 2


async def test_a_client_login_lists_its_sent_invoices_and_opens_the_pdf_but_never_another_clients(client: AsyncClient, driver: dict) -> None:
    h, _, inv = await invoiced(client, driver)
    ops = await office(client)
    cid = await client_of(inv["id"])
    mine = await login_for(client, ops, cid)
    assert [i["invoice_no"] for i in (await client.get("/portal/invoices", headers=mine)).json() if i["invoice_no"] == inv["invoice_no"]] == []  # not sent yet
    assert (await client.get(f"/portal/invoices/{inv['id']}/pdf", headers=mine)).status_code == 404
    await give_email(client, ops, cid)
    assert (await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)).status_code == 200

    rows = (await client.get("/portal/invoices", headers=mine)).json()
    row = next(i for i in rows if i["invoice_no"] == inv["invoice_no"])
    assert row["total"] == 1000.0 and row["balance"] == 1000.0 and row["paid_at"] is None and row["claims"] == []
    pdf = await client.get(f"/portal/invoices/{inv['id']}/pdf", headers=mine)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    stranger = await new_client_login(client, ops)  # a different company's own login
    assert (await client.get(f"/portal/invoices/{inv['id']}/pdf", headers=stranger["headers"])).status_code == 404  # looks like no invoice at all
    assert (await client.get("/portal/invoices", headers=stranger["headers"])).json() == []
    assert (await client.post(f"/portal/invoices/{inv['id']}/claims", headers=stranger["headers"], json={"amount": "10", "paid_on": today(), "reference": "UTR-X"})).status_code == 404
    assert (await client.get("/portal/invoices", headers=h)).status_code == 403  # billing staff are not clients


async def test_a_client_says_it_paid_and_billing_confirms_it_as_a_payment(client: AsyncClient, driver: dict) -> None:
    h, _, inv = await invoiced(client, driver)
    ops = await office(client)
    cid = await client_of(inv["id"])
    mine = await login_for(client, ops, cid)
    claim_url = f"/portal/invoices/{inv['id']}/claims"
    good = {"amount": "400", "paid_on": today(), "reference": "UTR400"}
    assert (await client.post(claim_url, headers=mine, json=good)).status_code == 404  # not sent yet
    await give_email(client, ops, cid)
    await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)
    before = (await item(client, "payment_claims") or {"count": 0})["count"]

    assert (await client.post(claim_url, headers=mine, json={**good, "amount": "5000"})).status_code == 422  # more than the balance
    assert (await client.post(claim_url, headers=mine, json={**good, "paid_on": (datetime.now(UTC) + timedelta(days=3)).date().isoformat()})).status_code == 422
    assert (await client.post(claim_url, headers=mine, json={**good, "reference": "x"})).status_code == 422  # billing needs something to find in the bank
    made = await client.post(claim_url, headers=mine, json=good)
    assert made.status_code == 201 and made.json()["claims"][0]["status"] == "pending"
    # nothing has changed on the invoice yet: a claim is only the client's word
    row = next(i for i in (await client.get("/billing/invoices", headers=h)).json() if i["id"] == inv["id"])
    assert row["paid_amount"] == 0 and row["pending_claims"] == 1
    assert (await item(client, "payment_claims"))["count"] == before + 1

    queue = (await client.get("/billing/claims", headers=h)).json()
    claim = next(c for c in queue if c["invoice_id"] == inv["id"])
    assert claim["amount"] == 400.0 and claim["reference"] == "UTR400" and claim["balance"] == 1000.0
    ok = await client.post(f"/billing/claims/{claim['id']}/confirm", headers=h)
    assert ok.status_code == 200 and ok.json()["paid_amount"] == 400.0 and ok.json()["balance"] == 600.0 and ok.json()["paid_at"] is None
    assert (await client.post(f"/billing/claims/{claim['id']}/confirm", headers=h)).status_code == 409  # decided once
    assert (await item(client, "payment_claims") or {"count": 0})["count"] == before
    view = next(i for i in (await client.get("/portal/invoices", headers=mine)).json() if i["id"] == inv["id"])
    assert view["claims"][0]["status"] == "confirmed" and view["payments"][0]["reference"] == "UTR400" and view["balance"] == 600.0

    last = await client.post(claim_url, headers=mine, json={"amount": "600", "paid_on": today(), "reference": "UTR600"})
    final = next(c for c in (await client.get("/billing/claims", headers=h)).json() if c["invoice_id"] == inv["id"])
    done = await client.post(f"/billing/claims/{final['id']}/confirm", headers=h)
    assert last.status_code == 201 and done.json()["paid_at"] and done.json()["balance"] == 0  # the last payment closes the invoice, as billing's own entry does
    assert (await client.post(claim_url, headers=mine, json=good)).status_code == 409  # nothing left to pay


async def test_billing_can_correct_the_amount_and_can_turn_a_claim_down_with_a_reason_the_client_reads(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    ops = await office(client)
    cid = await client_of(inv["id"])
    mine = await login_for(client, ops, cid)
    await give_email(client, ops, cid)
    assert (await client.patch(f"/setup/clients/{cid}", headers=ops, json={"contact_phone": "9000000777"})).status_code == 200  # so the WhatsApp note has somewhere to go
    await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)
    claim_url = f"/portal/invoices/{inv['id']}/claims"
    await client.post(claim_url, headers=mine, json={"amount": "1000", "paid_on": today(), "reference": "UTR-WRONG"})
    c1 = next(c for c in (await client.get("/billing/claims", headers=h)).json() if c["invoice_id"] == inv["id"])
    assert (await client.post(f"/billing/claims/{c1['id']}/reject", headers=h, json={"reason": "x"})).status_code == 422  # a reason the client can read
    rej = await client.post(f"/billing/claims/{c1['id']}/reject", headers=h, json={"reason": "No such reference in our bank statement"})
    assert rej.status_code == 200 and rej.json()["paid_amount"] == 0
    seen = next(i for i in (await client.get("/portal/invoices", headers=mine)).json() if i["id"] == inv["id"])
    assert seen["claims"][0]["status"] == "rejected" and "bank statement" in seen["claims"][0]["reject_reason"]
    async with SessionLocal() as s:
        note = (await s.scalars(select(Message).where(Message.trip_id == uuid.UUID(tid), Message.template == "shipment_update").order_by(Message.created_at.desc()).limit(1))).one()
    assert "could not match" in note.body and "Rs 1,000" in note.body  # the client is told on WhatsApp too

    await client.post(claim_url, headers=mine, json={"amount": "1000", "paid_on": today(), "reference": "UTR-RIGHT"})  # they tell us again
    c2 = next(c for c in (await client.get("/billing/claims", headers=h)).json() if c["invoice_id"] == inv["id"])
    part = await client.post(f"/billing/claims/{c2['id']}/confirm", headers=h, json={"amount": "900"})  # only 900 reached the bank
    assert part.status_code == 200 and part.json()["paid_amount"] == 900.0 and part.json()["balance"] == 100.0 and part.json()["paid_at"] is None
    assert len((await client.get("/billing/claims?state=rejected", headers=h)).json()) >= 1


async def test_the_client_can_also_say_it_paid_from_the_private_shipment_page_and_the_receiver_cannot(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    ops = await office(client)
    await give_email(client, ops, await client_of(inv["id"]))
    t = await tokens(client, ops, tid)
    body = {"amount": "250", "paid_on": today(), "reference": "NEFT-250"}
    assert (await client.post(f"/public/shipments/{t['client']}/claims", json=body)).status_code == 404  # before it was sent
    await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)
    assert (await client.post(f"/public/shipments/{t['receiver']}/claims", json=body)).status_code == 404
    made = await client.post(f"/public/shipments/{t['client']}/claims", json=body)
    assert made.status_code == 201 and made.json()["claims"][0]["reference"] == "NEFT-250"
    page = (await client.get(f"/public/shipments/{t['client']}")).json()["invoice"]
    assert page["balance"] == 1000.0 and page["claims"][0]["status"] == "pending"
    mine = next(c for c in (await client.get("/billing/claims", headers=h)).json() if c["invoice_id"] == inv["id"])
    assert mine["via"] == "link"
    assert (await client.get("/billing/claims", headers=await office(client))).status_code in (200, 403)  # ops may look; the client may not
    assert (await client.get("/billing/claims")).status_code == 401


async def test_a_trip_row_for_the_invoice_is_untouched_by_a_claim(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    ops = await office(client)
    cid = await client_of(inv["id"])
    mine = await login_for(client, ops, cid)
    await give_email(client, ops, cid)
    await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)
    await client.post(f"/portal/invoices/{inv['id']}/claims", headers=mine, json={"amount": "1000", "paid_on": today(), "reference": "UTR-ALL"})
    async with SessionLocal() as s:
        trip = await s.get(Trip, uuid.UUID(tid))
        assert trip.closed_at is None  # only billing confirming closes the trip
