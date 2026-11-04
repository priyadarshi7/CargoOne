import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models import PodSubmission, Trip


async def _trip(session) -> Trip:
    return await session.scalar(select(Trip).where(Trip.trip_code == "TRP-66120"))


async def test_retake_cap_enforced_by_database() -> None:
    async with SessionLocal() as session:
        trip = await _trip(session)
        with pytest.raises(IntegrityError):
            await session.execute(update(Trip).where(Trip.id == trip.id).values(retake_count=3))
        await session.rollback()


async def test_image_over_300kb_rejected_by_database() -> None:
    async with SessionLocal() as session:
        trip = await _trip(session)
        session.add(PodSubmission(
            trip_id=trip.id, storage_key="x", size_bytes=300 * 1024 + 1,
            captured_at=datetime.now(UTC), client_upload_id=uuid.uuid4().hex,
        ))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


async def test_upload_is_idempotent_by_client_upload_id() -> None:
    async with SessionLocal() as session:
        trip = await _trip(session)
        key = uuid.uuid4().hex
        kw = {"trip_id": trip.id, "storage_key": "x", "size_bytes": 1000, "captured_at": datetime.now(UTC)}
        session.add(PodSubmission(client_upload_id=key, **kw))
        await session.flush()
        session.add(PodSubmission(client_upload_id=key, **kw))
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
