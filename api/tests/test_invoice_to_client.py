"""The invoice reaches the client (an emailed private link, and the client's own login), and the client can say "I have paid" for billing to confirm."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import Client, Invoice, Message, Role, User
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
    assert row["total"] == 1000.0 and row["balance"] == 1000.0 and row["paid_at"] is None
    pdf = await client.get(f"/portal/invoices/{inv['id']}/pdf", headers=mine)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    stranger = await new_client_login(client, ops)  # a different company's own login
    assert (await client.get(f"/portal/invoices/{inv['id']}/pdf", headers=stranger["headers"])).status_code == 404  # looks like no invoice at all
    assert (await client.get("/portal/invoices", headers=stranger["headers"])).json() == []
    assert (await client.post(f"/portal/invoices/{inv['id']}/claims", headers=stranger["headers"], json={"amount": "10", "paid_on": today(), "reference": "UTR-X"})).status_code == 404
    assert (await client.get("/portal/invoices", headers=h)).status_code == 403  # billing staff are not clients


async def test_a_payment_billing_records_by_hand_shows_on_the_clients_invoice_and_the_client_has_no_way_to_claim_one(client: AsyncClient, driver: dict) -> None:
    h, tid, inv = await invoiced(client, driver)
    ops = await office(client)
    cid = await client_of(inv["id"])
    mine = await login_for(client, ops, cid)
    await give_email(client, ops, cid)
    t = await tokens(client, ops, tid)
    await client.post(f"/billing/invoices/{inv['id']}/send", headers=h)
    body = {"amount": "400", "paid_on": today(), "reference": "UTR400"}
    assert (await client.post(f"/portal/invoices/{inv['id']}/claims", headers=mine, json=body)).status_code in (404, 405)  # the client does not tell us they paid
    assert (await client.post(f"/public/shipments/{t['client']}/claims", json=body)).status_code in (404, 405)
    assert (await client.get("/billing/claims", headers=h)).status_code in (404, 405)

    cash = await client.post(f"/billing/invoices/{inv['id']}/payments", headers=h, json={**body, "reference": "Cash, receipt 12"})
    assert cash.status_code == 201 and cash.json()["balance"] == 600.0
    view = next(i for i in (await client.get("/portal/invoices", headers=mine)).json() if i["id"] == inv["id"])
    assert view["paid_amount"] == 400.0 and view["balance"] == 600.0 and view["payments"][0]["reference"] == "Cash, receipt 12" and "claims" not in view
    page = (await client.get(f"/public/shipments/{t['client']}")).json()["invoice"]
    assert page["balance"] == 600.0 and page["payments"][0]["amount"] == 400.0
