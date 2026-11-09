"""Three trips ready for a screen recording of the driver flow. DEV ONLY, fake data, safe to run again.

One driver and one truck, three trips that follow each other, so nothing overlaps: the Indore load was delivered four days ago and the paper is still
with the driver, the Nagpur load was delivered yesterday, and the Pune load has just reached the consignee. The driver app shows the truck on the road
first (the one big POD photo button) and the other two under "waiting for photo". The LR numbers match printed benchmark sheets
(docs/benchmark/photos), so photographing that sheet gives the outcome named below:

  TRP-70991   LR/MH20/26-27/900001  sheet S01  clean                  -> verified
  TRP-70992   LR/MH20/26-27/900002  sheet S02  no consignee stamp     -> retake asked (voice prompt)
  TRP-70993   LR/MH20/26-27/900006  sheet S06  44 bags, remark short  -> goes to the review queue

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

# (code, LR, destination, client, freight, hours ago the truck left, hours ago it reached the consignee; the last is "on the road, just arrived")
TRIPS = [
    ("TRP-70991", "LR/MH20/26-27/900001", "Pune", "Company B", Decimal(38500), 7, 0.2),
    ("TRP-70992", "LR/MH20/26-27/900002", "Nagpur", "Company C", Decimal(26000), 58, 30),
    ("TRP-70993", "LR/MH20/26-27/900006", "Indore", "Company D", Decimal(41200), 130, 98),
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
        for i, (code, lr, dest, client_name, freight, left_h, arrived_h) in enumerate(TRIPS):
            client = await s.scalar(select(Client).where(Client.name == client_name))
            trip = await s.scalar(select(Trip).where(Trip.trip_code == code))
            if trip is None:
                trip = Trip(trip_code=code, client_id=client.id, vehicle_id=vehicle.id, driver_id=driver.id, branch_id=driver.branch_id,
                            lr_no=lr, eway_bill_no=f"3410000001{i:02d}", origin="Chhatrapati Sambhajinagar", destination=dest,
                            freight_amount=freight, material="Packaged goods", packages=50, weight_tonnes=Decimal("2.5"),
                            consignee_name="Sharma Traders", consignee_phone="9000000999")
                s.add(trip)
                await s.flush()
            elif reset:
                await s.execute(delete(PodSubmission).where(PodSubmission.trip_id == trip.id))
                await s.execute(delete(TripEvent).where(TripEvent.trip_id == trip.id))
                await s.execute(delete(AuditLog).where(AuditLog.entity == "trip", AuditLog.entity_id == str(trip.id)))
            else:
                continue
            on_road = arrived_h < 1  # only the newest trip is still with the truck at the delivery point
            trip.pod_status, trip.retake_count = PodStatus.pending, 0
            trip.state = TripState.in_transit if on_road else TripState.delivered
            trip.started_at, trip.arrived_at = now - timedelta(hours=left_h), now - timedelta(hours=arrived_h)
            trip.acknowledged_at, trip.loaded_at = trip.started_at - timedelta(hours=2), trip.started_at - timedelta(hours=1)
            trip.planned_start, trip.planned_end = trip.started_at, trip.arrived_at
            trip.delivery_code = None  # no receiver code, so the big photo button shows straight away
            trip.delivered_at = None if on_road else trip.arrived_at
            trip.delivery_confirmed_at = None if on_road else trip.arrived_at
            trip.pod_uploaded_at = trip.first_pod_at = trip.verified_at = None
            trip.invoice_id = trip.invoiced_at = trip.closed_at = None
        await s.commit()
    print("Ready: TRP-70991, TRP-70992, TRP-70993 for the driver 9000000001 (PIN 1234).")


if __name__ == "__main__":
    asyncio.run(main("--reset" in sys.argv))
