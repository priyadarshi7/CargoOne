import uuid
import xml.etree.ElementTree as ET

from httpx import AsyncClient
from sqlalchemy import func, select

from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import AuditLog, Invoice, PodStatus, Trip
from tests.conftest import login
from tests.test_pod_upload import make_trip, post


async def verified_trip(client: AsyncClient, driver: dict, **kw) -> str:
    trip_id, lr = await make_trip(**kw)
    res = await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))
    assert res.json()["decision"] == "verified", res.text
    return trip_id


async def biller(client: AsyncClient) -> dict:
    return await login(client, "billing@cargoone.dev", "cargoone-dev")


async def queue_ids(client: AsyncClient, h: dict) -> set[str]:
    return {t["id"] for g in (await client.get("/billing/queue", headers=h)).json() for t in g["trips"]}


async def test_verified_trips_appear_in_queue_grouped_by_client(client: AsyncClient, driver: dict) -> None:
    a = await verified_trip(client, driver, client_name="Company B", freight=40000)
    b = await verified_trip(client, driver, client_name="Company C", freight=26000)
    h = await biller(client)
    groups = (await client.get("/billing/queue", headers=h)).json()
    ga = next(g for g in groups if any(t["id"] == a for t in g["trips"]))
    gb = next(g for g in groups if any(t["id"] == b for t in g["trips"]))
    assert ga["client"] == "Company B" and ga["billing_cycle"] == "weekly"
    assert gb["client"] == "Company C" and gb["billing_cycle"] == "fortnightly"
    assert ga["total"] >= 40000 and ga["period_label"]


async def test_unverified_trips_are_not_billable(client: AsyncClient, driver: dict) -> None:
    trip_id, lr = await make_trip()
    await post(client, driver, trip_id, render(SCENARIOS["shortage"], lr))  # -> needs_review
    h = await biller(client)
    assert trip_id not in await queue_ids(client, h)
    res = await client.post("/billing/invoices", headers=h, json={"trip_ids": [trip_id]})
    assert res.status_code == 409


async def test_create_invoice_bills_trips_and_cannot_double_bill(client: AsyncClient, driver: dict) -> None:
    a = await verified_trip(client, driver, freight=40000)
    b = await verified_trip(client, driver, freight=2500)
    h = await biller(client)
    res = await client.post("/billing/invoices", headers=h, json={"trip_ids": [a, b]})
    assert res.status_code == 201, res.text
    inv = res.json()
    assert inv["total"] == 42500 and inv["trip_count"] == 2 and inv["client"] == "Company B"
    assert inv["invoice_no"].startswith("CO/") and inv["exported_at"] is None
    async with SessionLocal() as s:
        t = await s.get(Trip, uuid.UUID(a))
        assert t.pod_status == PodStatus.billed and t.invoice_id is not None
        n = await s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "invoice.create", AuditLog.entity_id == inv["id"]))
        assert n == 1
    assert {a, b}.isdisjoint(await queue_ids(client, h))
    again = await client.post("/billing/invoices", headers=h, json={"trip_ids": [a]})
    assert again.status_code == 409


async def test_invoice_numbers_are_unique_and_increasing(client: AsyncClient, driver: dict) -> None:
    h = await biller(client)
    nos = []
    for _ in range(2):
        t = await verified_trip(client, driver)
        nos.append((await client.post("/billing/invoices", headers=h, json={"trip_ids": [t]})).json()["invoice_no"])
    assert nos[0] != nos[1] and int(nos[1].rsplit("/", 1)[1]) > int(nos[0].rsplit("/", 1)[1])


async def test_one_invoice_cannot_mix_clients(client: AsyncClient, driver: dict) -> None:
    a = await verified_trip(client, driver, client_name="Company B")
    b = await verified_trip(client, driver, client_name="Company C")
    res = await client.post("/billing/invoices", headers=await biller(client), json={"trip_ids": [a, b]})
    assert res.status_code == 422
    assert {a, b} <= await queue_ids(client, await biller(client))  # nothing was changed


async def test_unknown_trip_and_empty_request(client: AsyncClient) -> None:
    h = await biller(client)
    assert (await client.post("/billing/invoices", headers=h, json={"trip_ids": [str(uuid.uuid4())]})).status_code == 404
    assert (await client.post("/billing/invoices", headers=h, json={"trip_ids": []})).status_code == 422


async def test_only_billing_and_ops_may_bill(client: AsyncClient, driver: dict) -> None:
    for h in (driver, await login(client, "md@cargoone.dev", "cargoone-dev")):
        assert (await client.get("/billing/queue", headers=h)).status_code == 403
        assert (await client.post("/billing/invoices", headers=h, json={"trip_ids": [str(uuid.uuid4())]})).status_code == 403
    assert (await client.get("/billing/queue")).status_code == 401


async def test_exports_tally_csv_pdf_and_stamp_exported(client: AsyncClient, driver: dict) -> None:
    t = await verified_trip(client, driver, freight=40000)
    h = await biller(client)
    inv = (await client.post("/billing/invoices", headers=h, json={"trip_ids": [t]})).json()

    xml = await client.get(f"/billing/invoices/{inv['id']}/tally", headers=h)
    assert xml.status_code == 200 and "attachment" in xml.headers["content-disposition"]
    v = ET.fromstring(xml.text.split("\n", 1)[1]).find(".//VOUCHER")
    assert v.findtext("VOUCHERNUMBER") == inv["invoice_no"] and v.findtext("PARTYLEDGERNAME") == "Company B"

    csv = await client.get(f"/billing/invoices/{inv['id']}/csv", headers=h)
    assert csv.status_code == 200 and "40000.00" in csv.text and csv.text.startswith("invoice_no")

    pdf = await client.get(f"/billing/invoices/{inv['id']}/pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and len(pdf.content) > 3000

    listed = next(i for i in (await client.get("/billing/invoices", headers=h)).json() if i["id"] == inv["id"])
    assert listed["exported_at"] is not None and listed["trip_count"] == 1
    async with SessionLocal() as s:
        actions = set((await s.scalars(select(AuditLog.action).where(AuditLog.entity_id == inv["id"]))).all())
        assert {"invoice.create", "invoice.export.tally", "invoice.export.csv", "invoice.export.pdf"} <= actions
        assert (await s.get(Invoice, uuid.UUID(inv["id"]))).exported_at is not None


async def test_unknown_invoice_404(client: AsyncClient) -> None:
    h = await biller(client)
    for kind in ("tally", "csv", "pdf"):
        assert (await client.get(f"/billing/invoices/{uuid.uuid4()}/{kind}", headers=h)).status_code == 404
