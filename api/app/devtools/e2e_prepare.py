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
    from app.models import Client, PodStatus, Trip, User, Vehicle
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
        await s.commit()


def main() -> None:
    name, admin = _names()
    asyncio.run(_recreate(name, admin))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=os.environ.copy(), capture_output=True)
    asyncio.run(_seed())
    print(f"E2E database '{name}' ready.")


if __name__ == "__main__":
    main()
