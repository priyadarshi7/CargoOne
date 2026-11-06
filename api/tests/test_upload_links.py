import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import Text, cast, func, select, update

from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.models import AccessLink, AuditLog, PodStatus, PodSubmission, Trip
from app.notify.sms import get_sms
from tests.conftest import login
from tests.test_pod_upload import make_trip


async def biller(client: AsyncClient) -> dict:
    return await login(client, "billing@cargoone.dev", "cargoone-dev")


async def new_link(client: AsyncClient, trip_id: str, **body) -> dict:
    res = await client.post(f"/trips/{trip_id}/upload-link", headers=await biller(client), json=body)
    assert res.status_code == 201, res.text
    return res.json()


def token_of(link: dict) -> str:
    return link["url"].split("/u/")[1].split("?")[0]


def photo_form(lr: str, scenario: str = "clean", upload_id: str | None = None) -> dict:
    return {
        "files": {"file": ("p.png", render(SCENARIOS[scenario], lr), "image/png")},
        "data": {"client_upload_id": upload_id or uuid.uuid4().hex, "captured_at": datetime.now(UTC).isoformat(), "lat": "21.1458", "lng": "79.0882"},
    }


async def test_link_flow_without_login_verifies_the_trip(client: AsyncClient) -> None:
    trip_id, lr = await make_trip(assigned=False)  # a hired driver's trip: nobody has an account
    link = await new_link(client, trip_id, lang="mr")
    assert "/u/" in link["url"] and link["url"].endswith("?l=mr") and link["sms_sent"] is False

    t = token_of(link)
    info = (await client.get(f"/u/{t}")).json()  # no Authorization header at all
    assert info["destination"] == "B" and info["status"] == "pending" and info["retakes_left"] == 2

    res = await client.post(f"/u/{t}/pod", **photo_form(lr))
    assert res.status_code == 200, res.text
    assert res.json()["decision"] == "verified" and res.json()["voice"] == "ok"
    async with SessionLocal() as s:
        trip = await s.get(Trip, uuid.UUID(trip_id))
        sub = await s.scalar(select(PodSubmission).where(PodSubmission.trip_id == trip.id))
        assert trip.pod_status == PodStatus.verified and sub.source == "sms_link"
        audit = await s.scalar(select(AuditLog).where(AuditLog.entity_id == trip_id, AuditLog.action == "pod.upload"))
        assert audit.actor_id is None and audit.meta["source"] == "sms_link"


async def test_only_a_hash_of_the_token_is_stored(client: AsyncClient) -> None:
    trip_id, _ = await make_trip(assigned=False)
    t = token_of(await new_link(client, trip_id))
    async with SessionLocal() as s:
        stored = (await s.scalars(select(AccessLink.token).where(AccessLink.trip_id == uuid.UUID(trip_id)))).all()
    assert t not in stored and len(stored) == 1 and len(stored[0]) == 64


async def test_public_page_reveals_no_commercial_or_personal_data(client: AsyncClient) -> None:
    trip_id, _ = await make_trip(assigned=False)
    t = token_of(await new_link(client, trip_id))
    text = (await client.get(f"/u/{t}")).text
    for forbidden in ("Company", "freight", "1000", "Demo Consignee", "9000000099", "eway", "lr_no"):
        assert forbidden not in text


async def test_unknown_expired_and_revoked_links(client: AsyncClient) -> None:
    assert (await client.get("/u/" + "x" * 43)).status_code == 404
    assert (await client.get("/u/short")).status_code == 404

    trip_id, lr = await make_trip(assigned=False)
    first = token_of(await new_link(client, trip_id))
    second = token_of(await new_link(client, trip_id))  # a new link revokes the older one
    assert (await client.get(f"/u/{first}")).status_code == 410
    assert (await client.get(f"/u/{second}")).status_code == 200

    async with SessionLocal() as s:  # expire it
        await s.execute(update(AccessLink).where(AccessLink.trip_id == uuid.UUID(trip_id), AccessLink.revoked.is_(False))
                        .values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
        await s.commit()
    assert (await client.get(f"/u/{second}")).status_code == 410
    assert (await client.post(f"/u/{second}/pod", **photo_form(lr))).status_code == 410


async def test_office_can_revoke_a_link(client: AsyncClient) -> None:
    trip_id, _ = await make_trip(assigned=False)
    t = token_of(await new_link(client, trip_id))
    assert (await client.delete(f"/trips/{trip_id}/upload-link", headers=await biller(client))).status_code == 204
    assert (await client.get(f"/u/{t}")).status_code == 410


async def test_link_upload_is_idempotent_and_retakes_are_counted_once(client: AsyncClient) -> None:
    trip_id, lr = await make_trip(assigned=False)
    t = token_of(await new_link(client, trip_id))
    form = photo_form(lr, "no_stamp", upload_id=f"smslink{uuid.uuid4().hex[:12]}")
    a = (await client.post(f"/u/{t}/pod", **form)).json()
    b = (await client.post(f"/u/{t}/pod", **form)).json()
    assert a["decision"] == "retake_requested" and b["duplicate"] is True and b["submission_id"] == a["submission_id"]
    async with SessionLocal() as s:
        assert (await s.get(Trip, uuid.UUID(trip_id))).retake_count == 1


async def test_no_link_for_finished_trips_and_no_upload_after_verification(client: AsyncClient) -> None:
    trip_id, lr = await make_trip(assigned=False)
    t = token_of(await new_link(client, trip_id))
    assert (await client.post(f"/u/{t}/pod", **photo_form(lr))).json()["decision"] == "verified"
    assert (await client.post(f"/u/{t}/pod", **photo_form(lr))).status_code == 409
    res = await client.post(f"/trips/{trip_id}/upload-link", headers=await biller(client), json={})
    assert res.status_code == 409


async def test_only_ops_and_billing_can_create_links(client: AsyncClient, driver: dict) -> None:
    trip_id, _ = await make_trip(assigned=False)
    md = await login(client, "md@cargoone.dev", "cargoone-dev")
    for h in (driver, md):
        assert (await client.post(f"/trips/{trip_id}/upload-link", headers=h, json={})).status_code == 403
    assert (await client.post(f"/trips/{trip_id}/upload-link", json={})).status_code == 401
    assert (await client.post(f"/trips/{uuid.uuid4()}/upload-link", headers=await biller(client), json={})).status_code == 404


async def test_sms_is_sent_with_the_link_and_phone_is_masked_in_audit(client: AsyncClient) -> None:
    get_sms().outbox.clear()
    trip_id, _ = await make_trip(assigned=False)
    link = await new_link(client, trip_id, phone="9876543210", lang="hi")
    assert link["sms_sent"] is True
    phone, text = get_sms().outbox[-1]
    assert phone == "9876543210" and link["url"] in text and "B" in text
    async with SessionLocal() as s:
        meta = (await s.scalar(select(AuditLog.meta).where(AuditLog.entity_id == trip_id, AuditLog.action == "link.create")))
        n_raw = await s.scalar(select(func.count()).select_from(AuditLog).where(cast(AuditLog.meta, Text).contains("9876543210")))
    assert meta["sms_to"] == "******3210" and n_raw == 0
    bad = await client.post(f"/trips/{trip_id}/upload-link", headers=await biller(client), json={"phone": "12ab"})
    assert bad.status_code == 422


async def test_token_guessing_and_photo_flooding_are_rate_limited(client: AsyncClient) -> None:
    for _ in range(30):
        assert (await client.get("/u/" + "g" * 43)).status_code == 404
    assert (await client.get("/u/" + "g" * 43)).status_code == 429  # 31st guess from the same address

    trip_id, _ = await make_trip(assigned=False)
    t = token_of(await new_link(client, trip_id))
    # ...but the same address can still use a VALID link (carrier NAT: many real drivers share one IP)
    assert (await client.get(f"/u/{t}")).status_code == 200
    codes = [(await client.post(f"/u/{t}/pod", files={"file": ("p.png", b"x", "image/png")},
                                data={"client_upload_id": uuid.uuid4().hex, "captured_at": datetime.now(UTC).isoformat(), "lat": "21.1458", "lng": "79.0882"})).status_code
             for _ in range(13)]
    assert codes[:12] == [415] * 12 and codes[12] == 429


async def test_a_hired_driver_enters_the_receivers_code_on_the_link_before_the_photo(client: AsyncClient) -> None:
    trip_id, lr = await make_trip(assigned=False)
    async with SessionLocal() as s:  # this trip was made without a code: give it one, as planning does
        (await s.get(Trip, uuid.UUID(trip_id))).delivery_code = "4821"
        await s.commit()
    t = token_of(await new_link(client, trip_id))
    assert (await client.get(f"/u/{t}")).json()["needs_code"] is True
    blocked = await client.post(f"/u/{t}/pod", **photo_form(lr))
    assert blocked.status_code == 409 and "code" in blocked.text
    assert (await client.post(f"/u/{t}/deliver", json={"code": "0000"})).status_code == 422
    assert (await client.post(f"/u/{t}/deliver", json={"code": "4821", "shortage_or_damage": True})).status_code == 422  # say what was short
    assert (await client.post(f"/u/{t}/deliver", json={"code": "4821", "shortage_or_damage": True, "note": "1 box torn"})).status_code == 200
    assert (await client.get(f"/u/{t}")).json()["needs_code"] is False
    assert (await client.post(f"/u/{t}/pod", **photo_form(lr))).status_code == 200
