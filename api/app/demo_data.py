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
from app.models import Branch, Client, PodStatus, Role, Trip, TripState, User, Vehicle

# The story the demo tells: the pilot has been running and the targets are met overall (80% of PODs in within a day, 4 days from POD to
# invoice, 0.5% lost). Older weeks start just under target and climb past it, so the weekly chart shows the improvement. One branch (Nagpur) still
# lags on purpose, so the dashboard also shows what "below target" looks like. All of it is fabricated and the dashboard says so in a banner.
PILOT_DAYS = 28  # trips delivered within this many days ago follow the "now" regime; older ones the "getting there" regime
BRANCH_WITHIN_24H = {"Chhatrapati Sambhajinagar": 0.97, "Pune": 0.94, "Nagpur": 0.68}  # odds a POD is in within a day, in the last PILOT_DAYS
EARLIER_WITHIN_24H = {"Chhatrapati Sambhajinagar": 0.91, "Pune": 0.86, "Nagpur": 0.62}  # the weeks before
INVOICE_DAYS = {"Chhatrapati Sambhajinagar": (1.5, 4.0), "Pune": (1.5, 4.5), "Nagpur": (4.0, 7.0)}  # POD verified -> invoice made, in days
CONSIGNEES = ["Sharma Traders", "Gupta Steel Depot", "Jain Building Materials", "Patel Distributors", "Kulkarni Enterprises", "Reddy Cement Agency", "Singh Wholesale",
              "Agrawal Stores", "Deshmukh Traders", "Naik Super Mart", "Bansal Hardware", "Mehta Foods Depot", "Chauhan Infra", "Pillai Distributors"]


def _load(rnd: random.Random, segment: str | None) -> tuple[Decimal, str, int | None]:
    """What a truck of this client's kind carries: cement in 50 kg bags, steel by weight, packaged goods in cartons."""
    if segment == "cement":
        w = rnd.randint(24, 32)
        return Decimal(w), "Cement (PPC), 50 kg bags", w * 20
    if segment == "steel":
        return Decimal(rnd.randint(18, 30)), rnd.choice(["TMT bars", "HR coils", "MS plates", "Steel pipes"]), None
    w = rnd.randint(8, 18)
    return Decimal(w), "Packaged goods, cartons", w * 60


DESTINATIONS = ["Nagpur", "Pune", "Indore", "Nashik", "Mumbai", "Hyderabad", "Surat", "Raipur", "Ahmedabad", "Solapur", "Latur", "Jalgaon", "Bhopal", "Chhatrapati Sambhajinagar"]


def _guard() -> None:
    if not get_settings().is_dev:
        raise RuntimeError("Refusing to create demo data: APP_ENV is not dev/test")


async def remove(session: AsyncSession) -> int:
    res = await session.execute(delete(Trip).where(Trip.trip_code.like("DEMO-%")))
    await session.execute(delete(Vehicle).where(Vehicle.reg_no.like("MH20 DM %"), ~Vehicle.id.in_(select(Trip.vehicle_id))))  # the old placeholder trucks, which had no vendor
    await session.commit()
    return res.rowcount or 0


async def create(session: AsyncSession, n: int = 140, seed: int = 42) -> int:
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
    fleet = list((await session.scalars(select(Vehicle).where(Vehicle.is_active.is_(True), Vehicle.reg_no.not_like("MH20 DM %")))).all())
    if len(fleet) < 8:
        raise SystemExit("Run `uv run python -m app.seed_fleet` first: the demo trips use its trucks, vendors and drivers.")
    own = [v for v in fleet if not v.is_hired]
    hired = [v for v in fleet if v.is_hired]
    driver_of = {u.assigned_vehicle_id: u for u in (await session.scalars(select(User).where(User.role == Role.driver, User.assigned_vehicle_id.is_not(None)))).all()}
    fy = f"{now.year % 100}-{(now.year + 1) % 100}" if now.month >= 4 else f"{(now.year - 1) % 100}-{now.year % 100}"
    made = 0
    seen: dict[tuple[str, bool], int] = {}
    for i in range(n):
        branch_name = rnd.choices(list(BRANCH_WITHIN_24H), weights=[5, 3, 2])[0]
        lost = i == 7 and n >= 250  # one lost POD in the earlier weeks (about 0.4% of a big run); a small demo has none, so the loss rate reads 0%
        delivered = now - timedelta(days=rnd.uniform(0.3, 75) if not lost else rnd.uniform(40, 70))
        recent = (now - delivered).days < PILOT_DAYS
        odds = (BRANCH_WITHIN_24H if recent else EARLIER_WITHIN_24H)[branch_name]
        k = seen.get((branch_name, recent), 0)
        seen[(branch_name, recent)] = k + 1
        fast = int((k + 1) * odds) > int(k * odds)  # not luck: each branch gets exactly its share of quick PODs, so a small demo still tells the story
        pod_delay = timedelta(hours=rnd.uniform(0.5, 20)) if fast else timedelta(days=rnd.uniform(1.2, 4))
        lo, hi = INVOICE_DAYS[branch_name]
        invoice_delay = timedelta(days=rnd.uniform(lo, hi) if recent else rnd.uniform(lo + 0.5, hi + 1.5))
        never = rnd.random() < (0.035 if recent else 0.015) and not lost
        first_pod = delivered + pod_delay
        verified = first_pod + timedelta(hours=rnd.uniform(0.5, 30))
        invoiced = verified + invoice_delay

        status, fp, ver, inv = PodStatus.billed, first_pod, verified, invoiced
        if lost:
            status, ver, inv = PodStatus.rejected, None, None
        elif never or first_pod > now:
            status, fp, ver, inv = (PodStatus.retake_requested if rnd.random() < 0.2 else PodStatus.pending), None, None, None
        elif rnd.random() < 0.04 or verified > now:
            status, ver, inv = PodStatus.needs_review, None, None
        elif invoiced > now:  # verified but not yet invoiced: shown as billed-pending would pollute the real billing queue
            inv = None
            status = PodStatus.billed
            inv = min(invoiced, now - timedelta(hours=1))
            inv = max(inv, ver)
        client = rnd.choice(clients)
        truck = rnd.choice(own if rnd.random() < 0.55 else hired)  # 140 own trucks and about 200 hired ones
        driver = driver_of.get(truck.id)
        origin = branch_name
        weight, material, packages = _load(rnd, client.segment)
        freight = Decimal(min(52000, max(17000, round(rnd.gauss(32000, 8000), -2))))
        session.add(Trip(
            trip_code=f"DEMO-{10000 + i}", client_id=client.id, vehicle_id=truck.id,
            driver_id=driver.id if driver else None, branch_id=branches[branch_name].id,
            lr_no=f"LR/{branches[branch_name].code or 'MH20'}/{fy}/{100000 + i}", eway_bill_no=f"{rnd.randrange(10**11, 10**12)}", origin=origin,
            destination=rnd.choice([d for d in DESTINATIONS if d != origin]), freight_amount=freight,
            material=material, weight_tonnes=weight, packages=packages,
            consignee_name=f"{rnd.choice(CONSIGNEES)} (demo)", consignee_phone=f"90005{rnd.randint(10000, 99999)}",
            delivered_at=delivered, pod_status=status, retake_count=1 if status == PodStatus.retake_requested else 0,
            first_pod_at=fp, pod_uploaded_at=fp, verified_at=ver, invoiced_at=inv,
            state=TripState.delivered,  # they were all delivered; a missing POD is a paperwork gap, not a truck still on the road (the live map shows only real trips)
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
