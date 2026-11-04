"""Idempotent dev seed. ALL DATA IS FAKE (names, phones, e-way bills) — never put real PII here.

Run: uv run python -m app.seed
Dev logins: ops@cargoone.dev / billing@cargoone.dev / md@cargoone.dev / admin@cargoone.dev (password: cargoone-dev)
            driver phone 9000000001 (PIN 1234)
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.mock import MockProvider
from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import Branch, Client, PodStatus, PodSubmission, Role, Trip, User, Vehicle
from app.security import hash_secret
from app.storage import get_storage

DEV_PASSWORD = "cargoone-dev"


async def get_or_create(session: AsyncSession, model, key: dict, **values):
    obj = await session.scalar(select(model).filter_by(**key))
    if obj is None:
        obj = model(**key, **values)
        session.add(obj)
        await session.flush()
    return obj


async def seed(session: AsyncSession) -> None:
    hq = await get_or_create(session, Branch, {"name": "Chhatrapati Sambhajinagar"})
    pune = await get_or_create(session, Branch, {"name": "Pune"})

    cb = await get_or_create(session, Client, {"name": "Company B"}, segment="cement", billing_cycle="weekly")
    cc = await get_or_create(session, Client, {"name": "Company C"}, segment="steel", billing_cycle="fortnightly")
    cd = await get_or_create(session, Client, {"name": "Company D"}, segment="packaged foods", billing_cycle="monthly")

    v1 = await get_or_create(session, Vehicle, {"reg_no": "MH20 EL 4521"}, is_hired=False)
    v2 = await get_or_create(session, Vehicle, {"reg_no": "MH20 GT 7718"}, is_hired=False)
    v3 = await get_or_create(session, Vehicle, {"reg_no": "MH17 BY 3092"}, is_hired=True)

    pw = hash_secret(DEV_PASSWORD)
    for email, name, role in [
        ("ops@cargoone.dev", "Ops Head (demo)", Role.ops),
        ("billing@cargoone.dev", "Billing Exec (demo)", Role.billing),
        ("md@cargoone.dev", "Managing Director (demo)", Role.md),
        ("admin@cargoone.dev", "Admin (demo)", Role.admin),
    ]:
        await get_or_create(session, User, {"email": email}, name=name, role=role,
                            password_hash=pw, language="en", branch_id=hq.id)
    driver = await get_or_create(session, User, {"phone": "9000000001"}, name="Ramesh (demo driver)",
                                 role=Role.driver, password_hash=hash_secret("1234"),
                                 language="mr", branch_id=hq.id)

    now = datetime.now(UTC)
    rows = [  # client's three sample trips
        ("TRP-66120", cb, v1, hq, driver, "LR-88120", "341008812045", "Nagpur", 38500, PodStatus.verified, 6, 0),
        ("TRP-66134", cc, v2, pune, driver, "LR-88134", "341008813477", "Pune", 26000, PodStatus.retake_requested, 3, 1),
        ("TRP-66141", cd, v3, hq, None, "LR-88141", "341008814120", "Indore", 41200, PodStatus.needs_review, 2, 0),
    ]
    for code, client, veh, branch, drv, lr, eway, dest, freight, status, days_ago, retakes in rows:
        await get_or_create(
            session, Trip, {"trip_code": code},
            client_id=client.id, vehicle_id=veh.id, branch_id=branch.id,
            driver_id=drv.id if drv else None, lr_no=lr, eway_bill_no=eway,
            origin="Chhatrapati Sambhajinagar", destination=dest, freight_amount=Decimal(freight),
            consignee_name="Demo Consignee Pvt Ltd", consignee_phone="9000000099",  # fake
            pod_status=status, retake_count=retakes, delivered_at=now - timedelta(days=days_ago),
        )
    await session.flush()

    # A synthetic photo per sample trip so the review queue / viewer have something real to show.
    samples = {"TRP-66120": ("clean", []), "TRP-66134": ("no_stamp", ["stamp_missing"]),
               "TRP-66141": ("shortage", ["shortage_or_damage"])}
    for code, (scenario, reasons) in samples.items():
        trip = await session.scalar(select(Trip).where(Trip.trip_code == code))
        if await session.scalar(select(PodSubmission.id).where(PodSubmission.trip_id == trip.id)):
            continue
        png = render(SCENARIOS[scenario], trip.lr_no, seed=1)
        extraction = await MockProvider().extract(png, "image/png", trip.lr_no)
        sub_id = uuid.uuid4()
        key = f"pods/{trip.id}/{sub_id}.png"
        await get_storage().put(key, png)
        session.add(PodSubmission(
            id=sub_id, trip_id=trip.id, attempt=1, storage_key=key, size_bytes=len(png),
            captured_at=trip.delivered_at, lat=19.8762, lng=75.3433, client_upload_id=f"seed-{code}",
            ai_provider="mock", ai_result={**extraction.model_dump(), "_voice": "review"},
            ai_confidence=extraction.confidence, decision=trip.pod_status, decision_reasons=reasons,
        ))
    await session.commit()


async def main() -> None:
    async with SessionLocal() as session:
        await seed(session)
    print("Seeded.")


if __name__ == "__main__":
    asyncio.run(main())
