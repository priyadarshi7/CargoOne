import uuid
from datetime import UTC, date, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select, update

from app.db import SessionLocal
from app.models import AuditLog, PodStatus, Trip, TripState, Vehicle
from app.notify.sms import _mock, reminder_text
from tests.test_pin_reset import office
from tests.test_tracking import driver_with_trip


async def item(client: AsyncClient, key: str, who: str = "ops@cargoone.dev") -> dict | None:
    body = (await client.get("/attention", headers=await office(client, who))).json()
    return next((i for i in body["items"] if i["key"] == key), None)


async def make_overdue(trip_id: str, days: int = 3) -> None:
    async with SessionLocal() as s:
        await s.execute(update(Trip).where(Trip.id == uuid.UUID(trip_id)).values(
            state=TripState.delivered, pod_status=PodStatus.pending, delivered_at=datetime.now(UTC) - timedelta(days=days)))
        await s.commit()


async def test_a_delivered_trip_without_a_pod_shows_up_and_clears_when_it_arrives(client: AsyncClient) -> None:
    _, trip = await driver_with_trip(client)
    before = (await item(client, "missing_pod") or {"count": 0})["count"]
    await make_overdue(trip, days=3)
    now = await item(client, "missing_pod")
    assert now and now["count"] == before + 1 and now["oldest_days"] >= 3 and now["to"] == "/office"
    async with SessionLocal() as s:
        await s.execute(update(Trip).where(Trip.id == uuid.UUID(trip)).values(pod_status=PodStatus.verified))
        await s.commit()
    after = await item(client, "missing_pod")
    assert (after["count"] if after else 0) == before


async def test_a_truck_with_papers_due_is_counted_and_the_list_is_soonest_first(client: AsyncClient) -> None:
    before = (await item(client, "papers") or {"count": 0})["count"]
    async with SessionLocal() as s:
        s.add(Vehicle(reg_no=f"MH20 AT {uuid.uuid4().hex[:10].upper()}", insurance_expiry=date.today() - timedelta(days=2)))
        await s.commit()
    papers = await item(client, "papers")
    assert papers["count"] == before + 1 and papers["to"].endswith("tab=trucks")
    assert papers["detail"] == sorted(papers["detail"], key=lambda p: p["days"]) and len(papers["detail"]) <= 5  # the screen shows the worst few


async def test_inactive_trucks_are_not_nagged_about(client: AsyncClient) -> None:
    before = (await item(client, "papers") or {"count": 0})["count"]
    async with SessionLocal() as s:
        s.add(Vehicle(reg_no=f"MH20 IX {uuid.uuid4().hex[:10].upper()}", insurance_expiry=date.today() - timedelta(days=400), is_active=False))
        await s.commit()
    assert (await item(client, "papers") or {"count": 0})["count"] == before  # a retired truck adds nothing


async def test_reminders_text_the_driver_once_a_day_and_never_log_the_number(client: AsyncClient) -> None:
    h, trip = await driver_with_trip(client)
    phone = (await client.get("/auth/me", headers=h)).json()  # id only; the phone is on the user row
    await make_overdue(trip)
    ops = await office(client)
    _mock.outbox.clear()
    first = (await client.post("/attention/remind-drivers", headers=ops)).json()
    assert first["sent"] >= 1
    texts = [t for _, t in _mock.outbox]
    assert any("pending" in t or "बाकी" in t for t in texts)
    again = (await client.post("/attention/remind-drivers", headers=ops)).json()
    assert again["sent"] == 0 and again["skipped_recent"] >= first["sent"]  # pressing twice does not spam
    async with SessionLocal() as s:
        logged = (await s.scalars(select(AuditLog).where(AuditLog.action == "reminder.sent", AuditLog.entity_id == trip))).all()
    assert len(logged) == 1 and "*" in logged[0].meta["to"] and phone["id"]  # masked in the audit trail


def test_reminder_wording_in_three_languages() -> None:
    for lang in ("en", "hi", "mr"):
        assert "Pune" in reminder_text(lang, "Pune")


async def test_who_can_see_and_send(client: AsyncClient, driver: dict) -> None:
    assert (await client.get("/attention", headers=await office(client, "md@cargoone.dev"))).status_code == 200  # the MD reads
    assert (await client.get("/attention", headers=driver)).status_code == 403
    assert (await client.get("/attention")).status_code == 401
    assert (await client.post("/attention/remind-drivers", headers=await office(client, "md@cargoone.dev"))).status_code == 403  # MD cannot send
    assert (await client.post("/attention/remind-drivers", headers=driver)).status_code == 403
