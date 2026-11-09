"""DEMO DATA for dashboards. Fabricated and deterministic (trip codes TRP-70000 to TRP-70999). Nothing on a screen says so: it is ordinary trip data.

It tells an illustrative before/after story: older trips follow the client's legacy timings (PODs arrive after
8-18 days), recent ones follow the pilot target (most PODs within hours). It is NOT evidence of real
performance: say so wherever the figures are shown outside the demo.

  uv run python -m app.demo_data           # add ~240 demo trips (skips if already present)
  uv run python -m app.demo_data --remove  # delete them again
"""
import asyncio
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import IST, financial_year, period_of
from app.config import get_settings
from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render, truth_for
from app.models import (
    Branch,
    Client,
    Invoice,
    Payment,
    PodStatus,
    PodSubmission,
    Role,
    Trip,
    TripEvent,
    TripState,
    User,
    Vehicle,
)
from app.storage import get_storage

# The story the demo tells: the pilot has been running and the targets are met overall (80% of PODs in within a day, 4 days from POD to
# invoice, 0.5% lost). Older weeks start just under target and climb past it, so the weekly chart shows the improvement. One branch (Nagpur) still
# lags on purpose, so the dashboard also shows what "below target" looks like. All of it is fabricated and the dashboard says so in a banner.
FIRST_CODE, LAST_CODE = "TRP-70000", "TRP-70999"  # the demo trips live in this block of trip codes, so they can be told apart and removed
PILOT_DAYS = 28  # trips delivered within this many days ago follow the "now" regime; older ones the "getting there" regime
BRANCH_WITHIN_24H = {"Chhatrapati Sambhajinagar": 0.97, "Pune": 0.94, "Nagpur": 0.68}  # odds a POD is in within a day, in the last PILOT_DAYS
EARLIER_WITHIN_24H = {"Chhatrapati Sambhajinagar": 0.91, "Pune": 0.86, "Nagpur": 0.62}  # the weeks before
INVOICE_DAYS = {"Chhatrapati Sambhajinagar": (0.3, 2.2), "Pune": (0.3, 2.6), "Nagpur": (2.5, 5.0)}  # POD verified -> invoice made, in days
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
    """Delete the demo trips with everything that hangs off them: photos, invoices and payments."""
    ids = list((await session.scalars(select(Trip.id).where(Trip.trip_code.between(FIRST_CODE, LAST_CODE)))).all())
    if not ids:
        return 0
    invoices = list((await session.scalars(select(Trip.invoice_id).where(Trip.id.in_(ids), Trip.invoice_id.is_not(None)).distinct())).all())
    keys = list((await session.scalars(select(PodSubmission.storage_key).where(PodSubmission.trip_id.in_(ids)))).all())
    await session.execute(delete(PodSubmission).where(PodSubmission.trip_id.in_(ids)))
    await session.execute(delete(TripEvent).where(TripEvent.trip_id.in_(ids)))
    await session.execute(delete(Trip).where(Trip.id.in_(ids)))
    if invoices:
        await session.execute(delete(Invoice).where(Invoice.id.in_(invoices)))  # their payments go with them
    await session.execute(delete(Vehicle).where(Vehicle.reg_no.like("MH20 DM %"), ~Vehicle.id.in_(select(Trip.vehicle_id))))  # the old placeholder trucks, which had no vendor
    await session.commit()
    storage = get_storage()
    for key in keys:
        try:
            await storage.delete(key)
        except OSError:
            pass  # a photo already gone is fine
    return len(ids)


def _photo_for(status: PodStatus) -> tuple[str, str, str, list[str]]:
    """(scenario of the picture, the decision it led to, the voice prompt, the reasons) for a POD in this state."""
    if status == PodStatus.needs_review:
        return "shortage", "needs_review", "review", ["shortage_or_damage"]
    if status == PodStatus.retake_requested:
        return "no_stamp", "retake_requested", "retake_stamp", ["stamp_missing"]
    if status == PodStatus.rejected:
        return "shortage", "rejected", "review", ["shortage_or_damage"]
    return "clean", "verified", "ok", []


async def create(session: AsyncSession, n: int = 140, seed: int = 42) -> int:
    _guard()
    if await session.scalar(select(func.count()).select_from(Trip).where(Trip.trip_code.between(FIRST_CODE, LAST_CODE))):
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
    clients = list((await session.scalars(select(Client).where(Client.is_active.is_(True)))).all())
    fleet = list((await session.scalars(select(Vehicle).where(Vehicle.is_active.is_(True), Vehicle.reg_no.not_like("MH20 DM %")))).all())
    if len(fleet) < 8:
        raise SystemExit("Run `uv run python -m app.seed_fleet` first: the demo trips use its trucks, vendors and drivers.")
    own = [v for v in fleet if not v.is_hired]
    hired = [v for v in fleet if v.is_hired]
    driver_of = {u.assigned_vehicle_id: u for u in (await session.scalars(select(User).where(User.role == Role.driver, User.assigned_vehicle_id.is_not(None)))).all()}
    biller = await session.scalar(select(User).where(User.role == Role.billing).order_by(User.email))
    fy = f"{now.year % 100}-{(now.year + 1) % 100}" if now.month >= 4 else f"{(now.year - 1) % 100}-{now.year % 100}"
    trips: list[Trip] = []
    by_client = {c.id: c for c in clients}
    seen: dict[tuple[str, bool], int] = {}
    busy: dict[uuid.UUID, list[datetime]] = {}  # when each truck delivered, so no two of its trips overlap
    for vid, when in (await session.execute(select(Trip.vehicle_id, func.coalesce(Trip.delivered_at, Trip.arrived_at)).where(Trip.state != TripState.cancelled))).all():
        if when is not None:
            busy.setdefault(vid, []).append(when)  # trips already in the system (the brief's samples) count too

    def free_truck(pool: list[Vehicle], other: list[Vehicle], when: datetime) -> Vehicle:
        gap = lambda v: min((abs((when - d).total_seconds()) for d in busy.get(v.id, [])), default=9e9)
        for candidates in (pool, other):
            ok = [v for v in candidates if gap(v) >= 2.5 * 86400]
            if ok:
                return rnd.choice(ok)
        return max([*pool, *other], key=gap)  # every truck is busy then: take the one that is free the longest

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
        invoice_delay = timedelta(days=rnd.uniform(lo, hi) if recent else rnd.uniform(lo + 0.3, hi + 1.0))
        never = rnd.random() < (0.035 if recent else 0.015) and not lost
        first_pod = delivered + pod_delay
        verified = first_pod + timedelta(hours=rnd.uniform(0.5, 30))
        invoiced = verified + invoice_delay

        status, fp, ver, inv = PodStatus.billed, first_pod, verified, invoiced
        if lost:
            status, ver, inv = PodStatus.rejected, None, None
        elif never or first_pod > now:
            if rnd.random() < 0.25:  # a photo came, it was not good enough, and the driver has not sent a better one yet
                status, fp, ver, inv = PodStatus.retake_requested, min(delivered + timedelta(hours=rnd.uniform(2, 20)), now - timedelta(minutes=30)), None, None
            else:
                status, fp, ver, inv = PodStatus.pending, None, None, None
        elif rnd.random() < 0.04 or verified > now:
            status, ver, inv = PodStatus.needs_review, None, None
        elif invoiced > now or now - verified < timedelta(days=6):  # checked and good, the invoice has not been made yet: this is what fills the billing queue
            status, inv = PodStatus.verified, None
        client = rnd.choice(clients)
        mine, theirs = (own, hired) if rnd.random() < 0.55 else (hired, own)
        truck = free_truck(mine, theirs, delivered)
        busy.setdefault(truck.id, []).append(delivered)
        driver = driver_of.get(truck.id)
        weight, material, packages = _load(rnd, client.segment)
        freight = Decimal(min(52000, max(17000, round(rnd.gauss(32000, 8000), -2))))
        trips.append(Trip(
            id=uuid.uuid4(), trip_code=f"TRP-{70000 + i}", client_id=client.id, vehicle_id=truck.id,
            driver_id=driver.id if driver else None, branch_id=branches[branch_name].id,
            lr_no=f"LR/{branches[branch_name].code or 'MH20'}/{fy}/{100000 + i}", eway_bill_no=f"{rnd.randrange(10**11, 10**12)}", origin=branch_name,
            destination=rnd.choice([d for d in DESTINATIONS if d != branch_name]), freight_amount=freight,
            material=material, weight_tonnes=weight, packages=packages,
            consignee_name=rnd.choice(CONSIGNEES), consignee_phone=f"90005{rnd.randint(10000, 99999)}",
            delivered_at=delivered, pod_status=status, retake_count=1 if status == PodStatus.retake_requested else 0,
            first_pod_at=fp, pod_uploaded_at=fp, verified_at=ver, invoiced_at=inv,
            state=TripState.delivered,  # they were all delivered; a missing POD is a paperwork gap, not a truck still on the road
        ))
    session.add_all(trips)
    await session.flush()

    # every POD that reached the system has its photo, so a count on the Today tab always has records behind it (the review queue, the trip's POD view)
    storage = get_storage()
    for i, t in enumerate(trips):
        if t.first_pod_at is None:
            continue
        scenario, decision, voice, reasons = _photo_for(t.pod_status)
        png = render(SCENARIOS[scenario], t.lr_no, seed=i)
        truth = truth_for(SCENARIOS[scenario], t.lr_no).model_dump()
        truth["delivery_date"] = t.delivered_at.date().isoformat()
        sub_id = uuid.uuid4()
        key = f"pods/{t.id}/{sub_id}.png"
        await storage.put(key, png)
        session.add(PodSubmission(
            id=sub_id, trip_id=t.id, attempt=1, storage_key=key, size_bytes=len(png), captured_at=t.first_pod_at - timedelta(minutes=8),
            lat=round(19.8 + rnd.random() * 0.2, 5), lng=round(75.2 + rnd.random() * 0.2, 5), client_upload_id=f"seed-{t.trip_code}",
            ai_provider="mock", ai_result={**truth, "_voice": voice, "_place": {"distance_km": round(rnd.uniform(0.1, 1.2), 1)}},
            ai_confidence=truth["confidence"], decision=PodStatus(decision), decision_reasons=reasons,
        ))

    # invoices: a biller makes one per client for the PODs checked in the same few days, sends it by hand, and the money comes in weeks later
    groups: dict[tuple[uuid.UUID, int], list[Trip]] = {}
    for t in trips:
        if t.pod_status == PodStatus.billed and t.invoiced_at:
            groups.setdefault((t.client_id, int(t.invoiced_at.timestamp() // (4 * 86400))), []).append(t)
    for batch in sorted(groups.values(), key=lambda g: max(x.invoiced_at for x in g)):
        made_at = max(x.invoiced_at for x in batch)
        client = by_client[batch[0].client_id]
        labels = {period_of(client.billing_cycle, x.delivered_at)[1] for x in batch}
        seq = await session.scalar(text("select nextval('invoice_no_seq')"))
        total = sum((x.freight_amount for x in batch), Decimal(0))
        sent = made_at + timedelta(hours=rnd.uniform(3, 30))
        inv = Invoice(id=uuid.uuid4(), invoice_no=f"{get_settings().invoice_prefix}/{financial_year(made_at)}/{seq:05d}", client_id=client.id, total=total,
                      period_label=labels.pop() if len(labels) == 1 else "Multiple periods", created_at=made_at, exported_at=made_at + timedelta(hours=1))
        if sent <= now:
            inv.sent_at, inv.sent_by = sent, biller.id if biller else None
        session.add(inv)
        await session.flush()
        for x in batch:
            x.invoice_id, x.invoiced_at = inv.id, made_at
        if inv.sent_at and (now - inv.sent_at).days > 12 and rnd.random() < 0.82:  # most clients have paid by now; the rest are the ones billing chases
            paid_at = min(now - timedelta(hours=2), inv.sent_at + timedelta(days=rnd.uniform(5, 20)))
            session.add(Payment(invoice_id=inv.id, amount=total, paid_on=paid_at.astimezone(IST).date(), reference=f"UTR{rnd.randint(10**11, 10**12 - 1)}",
                                recorded_by=biller.id if biller else None, created_at=paid_at))
            inv.paid_at = paid_at
            for x in batch:
                x.closed_at = paid_at
    await session.commit()
    return len(trips)


async def main() -> None:
    async with SessionLocal() as session:
        if "--remove" in sys.argv:
            print(f"Removed {await remove(session)} demo trips.")
        else:
            n = await create(session)
            print(f"Created {n} demo trips." if n else "Demo trips already present (use --remove first).")


if __name__ == "__main__":
    asyncio.run(main())
