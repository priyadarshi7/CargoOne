"""DPDP: retention removes people from old trips, a person can see and erase what is held, and cloud AI waits for the owner's say-so."""
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import select

from app.ai.registry import build_chain
from app.config import Settings
from app.db import SessionLocal
from app.models import AuditLog, PodSubmission, Trip
from app.privacy import purge_expired
from app.storage import LocalStorage
from tests.conftest import login
from tests.test_pod_upload import make_trip


async def with_person(trip_id: str, phone: str, **more) -> None:
    async with SessionLocal() as s:
        t = await s.get(Trip, uuid.UUID(trip_id))
        t.consignee_name, t.consignee_phone, t.consignee_email = "Ramesh Patil", phone, "ramesh@example.com"
        for k, v in more.items():
            setattr(t, k, v)
        await s.commit()


async def test_old_closed_trips_lose_their_people_and_photos(tmp_path: Path) -> None:
    trip_id, _ = await make_trip()
    storage = LocalStorage(str(tmp_path))
    await storage.put("pods/old.jpg", b"x")
    await with_person(trip_id, "9811111111", closed_at=datetime.now(UTC) - timedelta(days=365 * 9))
    async with SessionLocal() as s:
        s.add(PodSubmission(trip_id=uuid.UUID(trip_id), storage_key="pods/old.jpg", size_bytes=1, captured_at=datetime.now(UTC),
                            client_upload_id=uuid.uuid4().hex, ai_result={"remarks": "Ramesh"}))
        await s.commit()
        done = await purge_expired(s, storage)
        t = await s.get(Trip, uuid.UUID(trip_id))
        sub = await s.scalar(select(PodSubmission).where(PodSubmission.trip_id == t.id))
    assert done["trips"] >= 1 and done["photos"] >= 1
    assert (t.consignee_name, t.consignee_phone, t.consignee_email) == (None, None, None) and t.personal_data_erased_at
    assert sub.storage_key == "" and sub.ai_result is None and t.lr_no  # the trip itself stays
    assert not (tmp_path / "pods" / "old.jpg").exists()


async def test_a_recent_trip_keeps_its_people(tmp_path: Path) -> None:
    trip_id, _ = await make_trip()
    await with_person(trip_id, "9822222222", closed_at=datetime.now(UTC) - timedelta(days=365 * 2))
    async with SessionLocal() as s:
        await purge_expired(s, LocalStorage(str(tmp_path)))
        t = await s.get(Trip, uuid.UUID(trip_id))
    assert t.consignee_phone == "9822222222" and t.personal_data_erased_at is None


async def test_a_person_can_be_shown_and_erased_by_phone(client: AsyncClient) -> None:
    trip_id, lr = await make_trip()
    await with_person(trip_id, "9833333333")
    admin = await login(client, "admin@cargoone.dev", "cargoone-dev")
    seen = (await client.post("/privacy/access", headers=admin, json={"phone": "+91 98333 33333"})).json()
    assert [t["lr_no"] for t in seen["trips"]] == [lr] and seen["trips"][0]["consignee_name"] == "Ramesh Patil"
    assert (await client.post("/privacy/erase", headers=admin, json={"phone": "9833333333"})).json()["trips"] == 1
    again = (await client.post("/privacy/access", headers=admin, json={"phone": "9833333333"})).json()
    assert again["trips"] == []
    async with SessionLocal() as s:
        t = await s.get(Trip, uuid.UUID(trip_id))
        log = (await s.scalars(select(AuditLog).where(AuditLog.action == "privacy.erase").order_by(AuditLog.id.desc()).limit(1))).one()
    assert t.consignee_name is None and t.lr_no == lr
    assert "9833333333" not in str(log.meta) and log.meta["phone"] == "******3333"


async def test_only_the_privacy_officers_can_use_it(client: AsyncClient) -> None:
    assert (await client.post("/privacy/access", json={"phone": "9833333333"})).status_code == 401
    ops = await login(client, "ops@cargoone.dev", "cargoone-dev")
    assert (await client.post("/privacy/erase", headers=ops, json={"phone": "9833333333"})).status_code == 403


def test_cloud_ai_waits_for_the_owner_outside_dev() -> None:
    prod = {"app_env": "production", "jwt_secret": "x" * 40, "ai_provider": "groq", "ai_fallbacks": "local,mock"}
    names = lambda **more: [p.name for p in build_chain(Settings(**prod, **more))]
    assert names() == ["local", "mock"]
    assert names(cloud_ai_confirmed=True) == ["groq", "local", "mock"]
    assert [p.name for p in build_chain(Settings(app_env="dev", ai_provider="groq", ai_fallbacks="mock"))] == ["groq", "mock"]
