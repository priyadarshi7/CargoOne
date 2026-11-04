"""DEMO DATA for dashboards. Fabricated, deterministic, clearly labelled (trip codes start with DEMO-).

It tells an illustrative before/after story: older trips follow the client's legacy timings (PODs arrive after
8-18 days), recent ones follow the pilot target (most PODs within hours). It is NOT evidence of real
performance - the dashboard shows a banner whenever DEMO- trips are in the window.

  uv run python -m app.demo_data           # add ~240 demo trips (skips if already present)
  uv run python -m app.demo_data --remove  # delete them again
"""
import asyncio
import random
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal
from app.models import Branch, Client, PodStatus, Trip, TripState, User, Vehicle

PILOT_DAYS = 28  # trips delivered within this many days ago follow the "after" regime
BRANCH_WITHIN_24H = {"Chhatrapati Sambhajinagar": 0.88, "Pune": 0.78, "Nagpur": 0.52}  # pilot-regime POD-within-a-day odds
DESTINATIONS = ["Nagpur", "Pune", "Indore", "Nashik", "Mumbai", "Hyderabad", "Surat", "Raipur", "Ahmedabad"]


def _guard() -> None:
    if not get_settings().is_dev:
        raise RuntimeError("Refusing to create demo data: APP_ENV is not dev/test")


async def remove(session: AsyncSession) -> int:
    res = await session.execute(delete(Trip).where(Trip.trip_code.like("DEMO-%")))
    await session.commit()
    return res.rowcount or 0


async def create(session: AsyncSession, n: int = 240, seed: int = 42) -> int:
    _guard()
    if await session.scalar(select(func.count()).select_from(Trip).where(Trip.trip_code.like("DEMO-%"))):
        return 0
    rnd = random.Random(seed)
    now = datetime.now(UTC)
    branches = {}
    for name in BRANCH_WITHIN_24H:
        b = await session.scalar(select(Branch).where(Branch.name == name))
        if b is None:
            b = Branch(name=name)
            session.add(b)
            await session.flush()
        branches[name] = b
    clients = list((await session.scalars(select(Client))).all())
    vehicles = []
    for i in range(30):
        reg = f"MH20 DM {1000 + i}"
        v = await session.scalar(select(Vehicle).where(Vehicle.reg_no == reg))
        if v is None:
            v = Vehicle(reg_no=reg, is_hired=i % 3 == 0)
            session.add(v)
            await session.flush()
        vehicles.append(v)
    drivers = list((await session.scalars(select(User).where(User.phone == "9000000001"))).all())

    made = 0
    for i in range(n):
        branch_name = rnd.choices(list(BRANCH_WITHIN_24H), weights=[5, 3, 2])[0]
        delivered = now - timedelta(days=rnd.uniform(0.3, 75))
        recent = (now - delivered).days < PILOT_DAYS
        if recent:
            fast = rnd.random() < BRANCH_WITHIN_24H[branch_name]
            pod_delay = timedelta(hours=rnd.uniform(0.5, 22)) if fast else timedelta(days=rnd.uniform(1.2, 6))
            invoice_delay = timedelta(days=rnd.uniform(1.5, 7))
            never = rnd.random() < 0.07
        else:  # the "before" world
            pod_delay = timedelta(days=rnd.uniform(8, 18))
            invoice_delay = timedelta(days=rnd.uniform(11, 22))
            never = rnd.random() < 0.03
        first_pod = delivered + pod_delay
        verified = first_pod + timedelta(hours=rnd.uniform(0.5, 30))
        invoiced = verified + invoice_delay

        status, fp, ver, inv = PodStatus.billed, first_pod, verified, invoiced
        if never or first_pod > now:
            status, fp, ver, inv = (PodStatus.retake_requested if rnd.random() < 0.2 else PodStatus.pending), None, None, None
        elif rnd.random() < 0.012:
            status, ver, inv = PodStatus.rejected, None, None
        elif rnd.random() < 0.05:
            status, ver, inv = PodStatus.needs_review, None, None
        elif invoiced > now:  # verified but not yet invoiced: shown as billed-pending would pollute the real billing queue
            inv = None
            status = PodStatus.billed
            inv = min(invoiced, now - timedelta(hours=1))
            inv = max(inv, ver)
        session.add(Trip(
            trip_code=f"DEMO-{10000 + i}", client_id=rnd.choice(clients).id, vehicle_id=rnd.choice(vehicles).id,
            driver_id=drivers[0].id if drivers and rnd.random() < 0.1 else None, branch_id=branches[branch_name].id,
            lr_no=f"LR-D{10000 + i}", eway_bill_no=f"{rnd.randrange(10**11, 10**12)}", origin="Chhatrapati Sambhajinagar",
            destination=rnd.choice(DESTINATIONS), freight_amount=Decimal(rnd.randrange(18, 52) * 1000),
            delivered_at=delivered, pod_status=status, retake_count=1 if status == PodStatus.retake_requested else 0,
            first_pod_at=fp, state=TripState.delivered if fp else TripState.in_transit, pod_uploaded_at=fp, verified_at=ver, invoiced_at=inv,
        ))
        made += 1
    await session.commit()
    return made


async def main() -> None:
    async with SessionLocal() as session:
        if "--remove" in sys.argv:
            print(f"Removed {await remove(session)} demo trips.")
        else:
            n = await create(session)
            print(f"Created {n} demo trips." if n else "Demo trips already present (use --remove first).")


if __name__ == "__main__":
    asyncio.run(main())
