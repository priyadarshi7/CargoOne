import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.ai.registry import AllProvidersFailed
from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import AuditLog, Client, PodStatus, PodSubmission, Trip, User, Vehicle
from tests.conftest import login


async def make_trip(*, assigned: bool = True, client_name: str = "Company B", freight: int = 1000) -> tuple[str, str]:
    """A fresh trip per test (tests share one database). Returns (trip_id, lr_no)."""
    lr = f"LR-{uuid.uuid4().hex[:6].upper()}"
    async with SessionLocal() as s:
        client = await s.scalar(select(Client).where(Client.name == client_name))
        veh = await s.scalar(select(Vehicle).where(Vehicle.reg_no == "MH20 EL 4521"))
        drv = await s.scalar(select(User).where(User.phone == "9000000001"))
        t = Trip(trip_code=f"T-{lr}", client_id=client.id, vehicle_id=veh.id, driver_id=drv.id if assigned else None,
                 lr_no=lr, eway_bill_no="341000000000", origin="A", destination="B",
                 freight_amount=Decimal(freight), pod_status=PodStatus.pending)
        s.add(t)
        await s.commit()
        return str(t.id), lr


async def post(client: AsyncClient, headers: dict, trip_id: str, image: bytes, *, upload_id: str | None = None, **extra):
    return await client.post(
        f"/trips/{trip_id}/pod", headers=headers,
        files={"file": ("pod.png", image, "image/png")},
        data={"client_upload_id": upload_id or uuid.uuid4().hex, "captured_at": datetime.now(UTC).isoformat(), **extra},
    )


async def trip_row(trip_id: str) -> Trip:
    async with SessionLocal() as s:
        return await s.get(Trip, uuid.UUID(trip_id))


async def test_clean_pod_is_verified(client: AsyncClient, driver: dict) -> None:
    trip_id, lr = await make_trip()
    res = await post(client, driver, trip_id, render(SCENARIOS["clean"], lr), lat="19.87", lng="75.34")
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["decision"], body["voice"], body["attempt"], body["retakes_left"]) == ("verified", "ok", 1, 2)
    t = await trip_row(trip_id)
    assert t.pod_status == PodStatus.verified and t.verified_at is not None


async def test_retakes_capped_at_two_then_human_review(client: AsyncClient, driver: dict) -> None:
    trip_id, lr = await make_trip()
    img = render(SCENARIOS["no_stamp"], lr)
    first = (await post(client, driver, trip_id, img)).json()
    second = (await post(client, driver, trip_id, img)).json()
    third = (await post(client, driver, trip_id, img)).json()
    assert [first["decision"], second["decision"], third["decision"]] == [
        "retake_requested", "retake_requested", "needs_review"]
    assert (first["retakes_left"], second["retakes_left"], third["retakes_left"]) == (1, 0, 0)
    assert "retake_cap_reached" in third["reasons"] and first["voice"] == "retake_stamp"
    assert (await trip_row(trip_id)).retake_count == 2


async def test_shortage_goes_to_review_not_verified(client: AsyncClient, driver: dict) -> None:
    trip_id, lr = await make_trip()
    body = (await post(client, driver, trip_id, render(SCENARIOS["shortage"], lr))).json()
    assert body["decision"] == "needs_review" and "shortage_or_damage" in body["reasons"]


async def test_duplicate_upload_is_idempotent(client: AsyncClient, driver: dict) -> None:
    trip_id, lr = await make_trip()
    img, uid = render(SCENARIOS["no_stamp"], lr), uuid.uuid4().hex
    a = (await post(client, driver, trip_id, img, upload_id=uid)).json()
    b = (await post(client, driver, trip_id, img, upload_id=uid)).json()
    assert b["duplicate"] is True and b["submission_id"] == a["submission_id"] and b["voice"] == a["voice"]
    async with SessionLocal() as s:
        n = await s.scalar(select(func.count()).select_from(PodSubmission).where(PodSubmission.trip_id == uuid.UUID(trip_id)))
    assert n == 1 and (await trip_row(trip_id)).retake_count == 1  # retake not double counted


async def test_rejects_oversize_and_non_images(client: AsyncClient, driver: dict) -> None:
    trip_id, _ = await make_trip()
    assert (await post(client, driver, trip_id, b"x" * (300 * 1024 + 1))).status_code == 413
    assert (await post(client, driver, trip_id, b"not an image")).status_code == 415
    assert (await post(client, driver, trip_id, render(SCENARIOS["clean"], "LR-1"), lat="200")).status_code == 422


async def test_driver_cannot_upload_to_someone_elses_trip(client: AsyncClient, driver: dict) -> None:
    trip_id, lr = await make_trip(assigned=False)
    assert (await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))).status_code == 404
    assert (await trip_row(trip_id)).pod_status == PodStatus.pending


async def test_no_new_photo_once_verified(client: AsyncClient, driver: dict) -> None:
    trip_id, lr = await make_trip()
    await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))
    assert (await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))).status_code == 409


async def test_ai_outage_parks_pod_for_review_instead_of_blocking(
    client: AsyncClient, driver: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def down(*_a, **_k):
        raise AllProvidersFailed(["gemini: down"])

    monkeypatch.setattr("app.routers.pods.run_extraction", down)
    trip_id, lr = await make_trip()
    res = await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))
    assert res.status_code == 200
    assert (res.json()["decision"], res.json()["reasons"]) == ("needs_review", ["ai_unavailable"])


async def test_image_access_is_role_checked_and_audited(client: AsyncClient, driver: dict) -> None:
    trip_id, lr = await make_trip()
    sub_id = (await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))).json()["submission_id"]
    assert (await client.get(f"/pods/{sub_id}/image")).status_code == 401
    billing = await login(client, "billing@cargoone.dev", "cargoone-dev")
    res = await client.get(f"/pods/{sub_id}/image", headers=billing)
    assert res.status_code == 200 and res.headers["cache-control"] == "private, no-store"
    assert res.content[:4] == b"\x89PNG"
    async with SessionLocal() as s:
        n = await s.scalar(select(func.count()).select_from(AuditLog).where(
            AuditLog.action == "pod.view", AuditLog.entity_id == sub_id))
    assert n == 1


async def test_missing_image_file_is_404_not_500(client: AsyncClient, driver: dict, monkeypatch) -> None:
    trip_id, lr = await make_trip()
    sub_id = (await post(client, driver, trip_id, render(SCENARIOS["clean"], lr))).json()["submission_id"]

    async def gone(self, key):
        raise FileNotFoundError(key)

    monkeypatch.setattr("app.storage.LocalStorage.get", gone)
    assert (await client.get(f"/pods/{sub_id}/image", headers=driver)).status_code == 404
