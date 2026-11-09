"""Three trips ready for a screen recording of the driver flow. DEV ONLY, fake data, safe to run again.

Each trip is already loaded, started and at the delivery point, so the driver app shows the one big POD photo button. The LR numbers match
printed benchmark sheets (docs/benchmark/photos), so photographing that sheet gives the outcome named below:

  DEMO-REC-1  LR/MH20/26-27/900001  sheet S01  clean                  -> verified
  DEMO-REC-2  LR/MH20/26-27/900002  sheet S02  no consignee stamp     -> retake asked (voice prompt)
  DEMO-REC-3  LR/MH20/26-27/900006  sheet S06  44 bags, remark short  -> goes to the review queue

Run:  uv run python -m app.devtools.demo_video            (add)
      uv run python -m app.devtools.demo_video --reset    (put them back as untouched, to record again)
"""
import asyncio
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal
from app.models import AuditLog, Client, PodStatus, PodSubmission, Trip, TripEvent, TripState, User, Vehicle

TRIPS = [
    ("DEMO-REC-1", "LR/MH20/26-27/900001", "Pune", "Company B", Decimal(38500)),
    ("DEMO-REC-2", "LR/MH20/26-27/900002", "Nagpur", "Company C", Decimal(26000)),
    ("DEMO-REC-3", "LR/MH20/26-27/900006", "Indore", "Company D", Decimal(41200)),
]


async def main(reset: bool) -> None:
    if get_settings().app_env not in ("dev", "test"):
        raise SystemExit("Demo data is for development only.")
    now = datetime.now(UTC)
    async with SessionLocal() as s:
        driver = await s.scalar(select(User).where(User.phone == "9000000001"))
        vehicle = await s.scalar(select(Vehicle).where(Vehicle.reg_no == "MH20 EL 4521"))
        if driver is None or vehicle is None:
            raise SystemExit("Run `uv run python -m app.seed` first.")
        for i, (code, lr, dest, client_name, freight) in enumerate(TRIPS):
            client = await s.scalar(select(Client).where(Client.name == client_name))
            trip = await s.scalar(select(Trip).where(Trip.trip_code == code))
            if trip is None:
                trip = Trip(trip_code=code, client_id=client.id, vehicle_id=vehicle.id, driver_id=driver.id, branch_id=driver.branch_id,
                            lr_no=lr, eway_bill_no=f"3410000001{i:02d}", origin="Chhatrapati Sambhajinagar", destination=dest,
                            freight_amount=freight, material="Packaged goods", packages=50, weight_tonnes=Decimal("2.5"),
                            consignee_name="Sharma Traders (demo)", consignee_phone="9000000999")
                s.add(trip)
                await s.flush()
            elif reset:
                await s.execute(delete(PodSubmission).where(PodSubmission.trip_id == trip.id))
                await s.execute(delete(TripEvent).where(TripEvent.trip_id == trip.id))
                await s.execute(delete(AuditLog).where(AuditLog.entity == "trip", AuditLog.entity_id == str(trip.id)))
            else:
                continue
            trip.state, trip.pod_status, trip.retake_count = TripState.in_transit, PodStatus.pending, 0
            trip.acknowledged_at, trip.loaded_at = now - timedelta(hours=9), now - timedelta(hours=8)
            trip.started_at, trip.arrived_at = now - timedelta(hours=7), now - timedelta(minutes=10)
            trip.delivery_code = None  # no receiver code, so the big photo button shows straight away
            trip.delivery_confirmed_at = trip.delivered_at = trip.pod_uploaded_at = trip.first_pod_at = trip.verified_at = None
            trip.invoice_id = trip.invoiced_at = None
        await s.commit()
    print("Ready: DEMO-REC-1, DEMO-REC-2, DEMO-REC-3 for the driver 9000000001 (PIN 1234).")


if __name__ == "__main__":
    asyncio.run(main("--reset" in sys.argv))
