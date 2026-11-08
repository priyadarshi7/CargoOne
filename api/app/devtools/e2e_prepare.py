"""Builds a fresh, isolated database for browser (Playwright) tests: drop -> create -> migrate -> seed + extra trips.

Uses DATABASE_URL (the E2E runner points it at <name>_e2e). Refuses anything not named *_e2e so it can never wipe
a real database.   Run: DATABASE_URL=...cargoone_e2e uv run python -m app.devtools.e2e_prepare
"""
import asyncio
import os
import subprocess
import sys
from decimal import Decimal
from urllib.parse import urlsplit, urlunsplit

import asyncpg
from sqlalchemy import select

from app.config import get_settings


def _names() -> tuple[str, str]:
    parts = urlsplit(get_settings().database_url)
    name = parts.path.lstrip("/")
    if not name.endswith("_e2e"):
        raise SystemExit(f"Refusing to reset database '{name}': name must end with _e2e")
    admin = urlunsplit(parts._replace(scheme="postgresql", path="/postgres"))
    return name, admin


async def _recreate(name: str, admin: str) -> None:
    conn = await asyncpg.connect(admin)
    try:
        await conn.execute(f'drop database if exists "{name}" with (force)')
        await conn.execute(f'create database "{name}"')
    finally:
        await conn.close()


async def _seed() -> None:
    from app.db import SessionLocal
    from app.models import Client, PodStatus, Role, Trip, User, Vehicle
    from app.seed import seed

    async with SessionLocal() as s:
        await seed(s)
        driver = await s.scalar(select(User).where(User.phone == "9000000001"))
        client = await s.scalar(select(Client).where(Client.name == "Company B"))
        veh = await s.scalar(select(Vehicle).where(Vehicle.reg_no == "MH20 EL 4521"))
        for code, lr, dest in [("TRP-E2E-1", "LR-E2E001", "Nashik"), ("TRP-E2E-2", "LR-E2E002", "Solapur")]:
            s.add(Trip(trip_code=code, client_id=client.id, vehicle_id=veh.id, driver_id=driver.id, branch_id=driver.branch_id,
                       lr_no=lr, eway_bill_no="341000000099", origin="Chhatrapati Sambhajinagar", destination=dest,
                       freight_amount=Decimal(21000), pod_status=PodStatus.pending))
        # a hired vehicle's trip: nobody has an account, so the office sends an upload link
        hired = await s.scalar(select(Vehicle).where(Vehicle.reg_no == "MH17 BY 3092"))
        s.add(Trip(trip_code="TRP-E2E-HIRED", client_id=client.id, vehicle_id=hired.id, driver_id=None, branch_id=driver.branch_id,
                   lr_no="LR-E2E003", eway_bill_no="341000000098", origin="Chhatrapati Sambhajinagar", destination="Latur",
                   freight_amount=Decimal(19000), pod_status=PodStatus.pending))
        # trips no driver test touches (those consume the demo driver's open trips): one delivered long ago with no POD, one for the SMS-link tests
        from datetime import UTC, datetime, timedelta

        from app.models import TripState

        s.add(Trip(trip_code="TRP-E2E-MISSING", client_id=client.id, vehicle_id=hired.id, driver_id=None, branch_id=driver.branch_id, lr_no="LR-E2E004",
                   eway_bill_no="341000000097", origin="Chhatrapati Sambhajinagar", destination="Beed", freight_amount=Decimal(18000), pod_status=PodStatus.pending,
                   state=TripState.delivered, delivered_at=datetime.now(UTC) - timedelta(days=5)))
        s.add(Trip(trip_code="TRP-E2E-SMS", client_id=client.id, vehicle_id=veh.id, driver_id=None, branch_id=driver.branch_id, lr_no="LR-E2E005",
                   eway_bill_no="341000000096", origin="Chhatrapati Sambhajinagar", destination="Jalna", freight_amount=Decimal(17000), pod_status=PodStatus.pending))
        # throw-away accounts for the password-change and lockout browser tests (the shared dev users must stay usable)
        from app.security import hash_secret

        for email in ('pwchange@cargoone.dev', 'locktest@cargoone.dev'):
            s.add(User(name=email.split('@')[0], email=email, role=Role.ops, password_hash=hash_secret('cargoone-dev'), language='en'))
        gps = User(name='GPS Test Driver', phone='9000000099', role=Role.driver, password_hash=hash_secret('4821'), language='en')
        s.add(gps)
        await s.flush()
        s.add(Trip(trip_code='TRP-E2E-GPS', client_id=client.id, vehicle_id=veh.id, driver_id=gps.id, lr_no='LR-E2EGPS', eway_bill_no='341000000055',
                   origin='Chhatrapati Sambhajinagar', destination='Nanded', freight_amount=Decimal(20000), pod_status=PodStatus.pending))
        money = User(name='Money Test Driver', phone='9000000066', role=Role.driver, password_hash=hash_secret('4821'), language='en')
        s.add(money)
        await s.flush()
        s.add(Trip(trip_code='TRP-E2E-MONEY', client_id=client.id, vehicle_id=veh.id, driver_id=money.id, lr_no='LR-E2EMONEY', eway_bill_no='341000000066',
                   origin='Chhatrapati Sambhajinagar', destination='Hingoli', freight_amount=Decimal(30000), pod_status=PodStatus.pending))
        s.add(User(name='Plan Test Driver', phone='9000000088', role=Role.driver, password_hash=hash_secret('4821'), language='en'))
        s.add(User(name='Journey Test Driver', phone='9000000055', role=Role.driver, password_hash=hash_secret('4821'), language='en'))
        s.add(Vehicle(reg_no='MH20 JR 0001', is_hired=False, capacity_tonnes=Decimal(20)))
        s.add(Vehicle(reg_no='MH20 HJ 0002', is_hired=True, capacity_tonnes=Decimal(18)))  # a hired truck for the private-link journey test
        s.add(Vehicle(reg_no='MH20 PL 0003', is_hired=False))  # the planning test's own truck: the import test leaves MH20 GT 7718 on the road
        s.add(User(name='PIN Test Driver', phone='9000000077', role=Role.driver, password_hash=hash_secret('4821'), language='en'))
        await s.commit()


def main() -> None:
    name, admin = _names()
    asyncio.run(_recreate(name, admin))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=os.environ.copy(), capture_output=True)
    asyncio.run(_seed())
    print(f"E2E database '{name}' ready.")


if __name__ == "__main__":
    main()
