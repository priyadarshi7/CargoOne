"""Trip import (CSV/XLSX). `dry_run=true` validates and reports exactly what WOULD happen, then rolls back.
Re-importing the same file is safe: trips are matched by Trip ID, and a trip that already has POD activity is never
changed (its LR number is evidence). Unknown vehicles and branches are created; unknown clients only on request."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.imports.trips import TEMPLATE_CSV, ImportFileError, parse, read_rows, reg_key
from app.lr import next_lr_no
from app.models import AuditLog, Branch, Client, PodStatus, Role, Trip, TripState, User, Vehicle
from app.security import require_roles

router = APIRouter(prefix="/imports", tags=["imports"])
Importer = Annotated[User, Depends(require_roles(Role.ops, Role.billing))]
Session = Annotated[AsyncSession, Depends(get_session)]


class Issue(BaseModel):
    row: int
    trip_code: str | None
    message: str


class ImportReport(BaseModel):
    dry_run: bool
    total: int
    created: int
    updated: int
    unchanged: int
    skipped: int
    errors: list[Issue]
    warnings: list[Issue]
    new_clients: list[str]
    new_branches: list[str]
    new_vehicles: int


@router.get("/trips/template")
async def template(_: Importer) -> Response:
    return Response(TEMPLATE_CSV, media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="trips-template.csv"'})


@router.post("/trips", response_model=ImportReport)
async def import_trips(
    file: UploadFile, user: Importer, session: Session,
    dry_run: Annotated[bool, Query()] = True,
    create_clients: Annotated[bool, Query()] = False,
) -> ImportReport:
    data = await file.read(3 * 1024 * 1024)
    try:
        rows = read_rows(data, file.filename or "")
    except ImportFileError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    parsed = parse(rows)

    clients = {c.name.lower(): c for c in (await session.scalars(select(Client))).all()}
    vehicles = {reg_key(v.reg_no): v for v in (await session.scalars(select(Vehicle))).all()}
    branches = {b.name.lower(): b for b in (await session.scalars(select(Branch))).all()}
    drivers = {u.phone[-10:]: u for u in (await session.scalars(select(User).where(User.role == Role.driver))).all() if u.phone}
    existing = {t.trip_code: t for t in (await session.scalars(
        select(Trip).where(Trip.trip_code.in_([t.trip_code for t in parsed.trips])))).all()}
    with_pod = set((await session.scalars(select(Trip.id).where(Trip.pod_status != PodStatus.pending))).all())

    taken_ewb = {e: c for e, c in (await session.execute(select(Trip.eway_bill_no, Trip.trip_code).where(Trip.state != TripState.cancelled))).all()}
    taken_lr = {lr: c for lr, c in (await session.execute(select(Trip.lr_no, Trip.trip_code).where(Trip.state != TripState.cancelled))).all()}
    errors = [Issue(row=e.row, trip_code=e.trip_code, message=e.message) for e in parsed.errors]
    warnings: list[Issue] = []
    new_clients: list[str] = []
    new_branches: list[str] = []
    new_vehicles = created = updated = unchanged = skipped = 0
    s = get_settings()

    for p in parsed.trips:
        if (other := taken_ewb.get(p.eway_bill_no)) and other != p.trip_code:
            errors.append(Issue(row=p.row, trip_code=p.trip_code, message=f"E-way bill {p.eway_bill_no} is already on {other}. One e-way bill covers one consignment."))
            continue
        if p.lr_no and (other := taken_lr.get(p.lr_no)) and other != p.trip_code:
            errors.append(Issue(row=p.row, trip_code=p.trip_code, message=f"LR number {p.lr_no} is already on {other}."))
            continue
        taken_ewb[p.eway_bill_no] = p.trip_code
        if p.lr_no:
            taken_lr[p.lr_no] = p.trip_code
        client = clients.get(p.client.lower()) or clients.get(p.client_raw.lower())
        if client is None:
            if not create_clients:
                errors.append(Issue(row=p.row, trip_code=p.trip_code,
                                    message=f"Unknown client '{p.client}' (tick \"Create clients that do not exist yet\" or add the client first)"))
                continue
            client = Client(name=p.client, billing_cycle="weekly")
            session.add(client)
            await session.flush()
            clients[p.client.lower()] = client
            new_clients.append(p.client)

        vehicle = vehicles.get(reg_key(p.vehicle))
        if vehicle is None:
            vehicle = Vehicle(reg_no=p.vehicle, is_hired=p.is_hired)
            session.add(vehicle)
            await session.flush()
            vehicles[reg_key(p.vehicle)] = vehicle
            new_vehicles += 1
        elif p.is_hired and not vehicle.is_hired:
            vehicle.is_hired = True  # the sheet is the more recent source of truth for ownership

        branch = None
        if p.branch:
            branch = branches.get(p.branch.lower())
            if branch is None:
                branch = Branch(name=p.branch)
                session.add(branch)
                await session.flush()
                branches[p.branch.lower()] = branch
                new_branches.append(p.branch)
        driver = drivers.get(p.driver_phone) if p.driver_phone else None

        values = {
            "client_id": client.id, "vehicle_id": vehicle.id, **({"lr_no": p.lr_no} if p.lr_no else {}), "eway_bill_no": p.eway_bill_no,
            "origin": p.origin or s.default_origin, "destination": p.destination, "freight_amount": p.freight,
        }
        optional = {"branch_id": branch.id if branch else None, "driver_id": driver.id if driver else None,
                    "delivered_at": p.delivered_at, "consignee_name": p.consignee_name, "consignee_phone": p.consignee_phone}
        values |= {k: v for k, v in optional.items() if v is not None}  # blank cells never erase existing data

        trip = existing.get(p.trip_code)
        if trip is None:
            if "lr_no" not in values:
                values["lr_no"] = await next_lr_no(session, branch)  # the sheet had none: issue one
            session.add(Trip(trip_code=p.trip_code, pod_status=PodStatus.pending, **values))
            created += 1
        elif trip.id in with_pod:
            skipped += 1
            warnings.append(Issue(row=p.row, trip_code=p.trip_code,
                                  message="Already has POD activity - left unchanged (its LR number is evidence)"))
        elif any(getattr(trip, k) != v for k, v in values.items()):
            for k, v in values.items():
                setattr(trip, k, v)
            updated += 1
        else:
            unchanged += 1

    if dry_run:
        await session.rollback()
    else:
        session.add(AuditLog(actor_id=user.id, action="import.trips", entity="import", entity_id=None, meta={
            "file": (file.filename or "")[:80], "created": created, "updated": updated, "unchanged": unchanged,
            "skipped": skipped, "errors": len(errors)}))
        await session.commit()
    errors.sort(key=lambda i: i.row)
    return ImportReport(dry_run=dry_run, total=parsed.total, created=created, updated=updated, unchanged=unchanged,
                        skipped=skipped, errors=errors, warnings=warnings, new_clients=new_clients,
                        new_branches=new_branches, new_vehicles=new_vehicles)

