"""Role home numbers: office roles only, and the MD never sees the freight total."""
from httpx import AsyncClient

from tests.test_pin_reset import office


async def test_home_counts_for_each_office_role(client: AsyncClient) -> None:
    for who in ("ops@cargoone.dev", "billing@cargoone.dev"):
        res = await client.get("/home", headers=await office(client, who))
        assert res.status_code == 200
        body = res.json()
        assert {"planned", "in_transit", "pod_missing", "awaiting_review", "requests_new", "ready_to_bill", "ready_amount"} <= body.keys()
        assert body["ready_amount"] is not None


async def test_md_gets_counts_without_the_freight_total(client: AsyncClient) -> None:
    res = await client.get("/home", headers=await office(client, "md@cargoone.dev"))
    assert res.status_code == 200
    assert res.json()["ready_amount"] is None


async def test_home_needs_an_office_login(client: AsyncClient) -> None:
    assert (await client.get("/home")).status_code == 401


async def test_a_truck_on_a_trip_is_not_available(client) -> None:
    import uuid
    from decimal import Decimal

    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Client, PodStatus, Trip, TripState, Vehicle
    from tests.conftest import login

    h = await login(client, "ops@cargoone.dev", "cargoone-dev")
    free = lambda: client.get("/home", headers=h)
    before = (await free()).json()["trucks_available"]
    async with SessionLocal() as s:
        v = Vehicle(reg_no=f"MH20 TA {uuid.uuid4().hex[:8].upper()}", is_hired=False)
        s.add(v)
        await s.flush()
        assert (await free()).json()["trucks_available"] == before  # not committed yet: nothing changed
        c = await s.scalar(select(Client).limit(1))
        t = Trip(trip_code=f"T-{uuid.uuid4().hex[:6].upper()}", client_id=c.id, vehicle_id=v.id, lr_no=f"LR-{uuid.uuid4().hex[:6]}", eway_bill_no="341000000000",
                 origin="A", destination="B", freight_amount=Decimal(1000), pod_status=PodStatus.pending, state=TripState.delivered)
        s.add(t)
        await s.commit()
        assert (await free()).json()["trucks_available"] == before + 1  # a new truck, free
        t.state = TripState.in_transit
        await s.commit()
        assert (await free()).json()["trucks_available"] == before  # on the road: not available
        row = next(x for x in (await client.get("/setup/vehicles", headers=h)).json() if x["id"] == str(v.id))
        assert row["on_trip"] == t.trip_code
