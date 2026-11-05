import io
from datetime import date, timedelta

from httpx import AsyncClient
from PIL import Image

from tests.test_pin_reset import office
from tests.test_setup import D, mobile, new_licence, new_reg

PAST = (date.today() - timedelta(days=3)).isoformat()
FUTURE = (date.today() + timedelta(days=300)).isoformat()


def jpeg(size: int = 80) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (size, size), (200, 120, 40)).save(buf, "JPEG")
    return buf.getvalue()


async def make_truck(client: AsyncClient, ops: dict, **kw) -> dict:
    res = await client.post("/setup/vehicles", headers=ops, json={"reg_no": new_reg(), **kw})
    assert res.status_code == 201, res.text
    return res.json()


async def test_a_truck_records_the_rc_papers_and_availability(client: AsyncClient) -> None:
    ops = await office(client)
    v = await make_truck(client, ops, vehicle_type="Heavy truck", capacity_tonnes="25", owner_name="Company A", rc_no="MH20-RC-100200", chassis_no="CH123",
                         engine_no="EN456", insurance_no="POL-9", insurance_expiry=FUTURE, fitness_expiry=FUTURE, permit_expiry=FUTURE, puc_expiry=FUTURE,
                         registration_date="2021-04-01")
    assert v["owner_name"] == "Company A" and v["rc_no"] == "MH20-RC-100200" and v["puc_expiry"] == FUTURE and v["availability"] == "available"
    assert v["papers"] == "ok" and v["is_hired"] is False
    down = (await client.patch(f"/setup/vehicles/{v['id']}", headers=ops, json={"availability": "maintenance", "availability_note": "gearbox"})).json()
    assert down["availability"] == "maintenance" and down["availability_note"] == "gearbox"
    assert (await client.patch(f"/setup/vehicles/{v['id']}", headers=ops, json={"availability": "flying"})).status_code == 422
    # PUC counts towards the paper state like the other papers
    puc = (await client.patch(f"/setup/vehicles/{v['id']}", headers=ops, json={"puc_expiry": PAST})).json()
    assert puc["papers"] == "expired"


async def test_a_driver_needs_a_licence_and_an_employment_type(client: AsyncClient) -> None:
    ops = await office(client)
    truck = await make_truck(client, ops)
    ok = await client.post("/drivers", headers=ops, json=D(name="Rajesh Patil", assigned_vehicle_id=truck["id"], employment_type="company"))
    assert ok.status_code == 201, ok.text
    d = ok.json()["driver"]
    assert d["employment_type"] == "company" and d["assigned_vehicle"] == truck["reg_no"] and d["licence"] == "ok"
    assert (await client.post("/drivers", headers=ops, json={"name": "No Licence", "phone": mobile()})).status_code == 422
    assert (await client.post("/drivers", headers=ops, json=D(licence_expiry=PAST))).status_code == 422  # already expired
    assert (await client.post("/drivers", headers=ops, json=D(licence_no="12"))).status_code == 422
    assert (await client.post("/drivers", headers=ops, json=D(employment_type="hired"))).status_code == 422  # hired needs a vendor
    v = (await client.post("/setup/vendors", headers=ops, json={"name": f"Vendor {new_licence()}"})).json()
    assert (await client.post("/drivers", headers=ops, json=D(vendor_id=v["id"]))).status_code == 422  # a company driver has no vendor
    assert (await client.post("/drivers", headers=ops, json=D(assigned_vehicle_id="00000000-0000-0000-0000-000000000000"))).status_code == 422
    soon = (await client.patch(f"/drivers/{d['id']}", headers=ops, json={"licence_expiry": (date.today() + timedelta(days=9)).isoformat()})).json()
    assert soon["licence"] == "due_soon"
    gone = (await client.patch(f"/drivers/{d['id']}", headers=ops, json={"clear_vehicle": True})).json()
    assert gone["assigned_vehicle"] is None


async def test_papers_can_be_uploaded_replaced_viewed_and_removed(client: AsyncClient) -> None:
    ops = await office(client)
    truck = await make_truck(client, ops)
    drv = (await client.post("/drivers", headers=ops, json=D())).json()["driver"]
    pic = jpeg()
    up = await client.post("/documents", headers=ops, data={"owner_type": "driver", "owner_id": drv["id"], "kind": "licence"}, files={"file": ("l.jpg", pic, "image/jpeg")})
    assert up.status_code == 201, up.text
    first = up.json()
    got = await client.get(f"/documents/{first['id']}/file", headers=ops)
    assert got.status_code == 200 and got.content == pic and got.headers["content-type"] == "image/jpeg"
    again = (await client.post("/documents", headers=ops, data={"owner_type": "driver", "owner_id": drv["id"], "kind": "licence"}, files={"file": ("l.jpg", jpeg(90), "image/jpeg")})).json()
    listed = (await client.get("/documents", headers=ops, params={"owner_type": "driver", "owner_id": drv["id"]})).json()
    assert [x["id"] for x in listed] == [again["id"]]  # one current file per kind
    assert (await client.get(f"/documents/{first['id']}/file", headers=ops)).status_code == 404
    rc = await client.post("/documents", headers=ops, data={"owner_type": "vehicle", "owner_id": truck["id"], "kind": "rc"}, files={"file": ("rc.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert rc.status_code == 201 and rc.json()["mime"] == "application/pdf"
    assert (await client.delete(f"/documents/{rc.json()['id']}", headers=ops)).status_code == 204
    assert (await client.get(f"/documents/{rc.json()['id']}/file", headers=ops)).status_code == 404


async def test_document_upload_rules(client: AsyncClient) -> None:
    ops = await office(client)
    truck = await make_truck(client, ops)
    drv = (await client.post("/drivers", headers=ops, json=D())).json()["driver"]
    base = {"owner_type": "vehicle", "owner_id": truck["id"], "kind": "rc"}
    bad_kind = await client.post("/documents", headers=ops, data={**base, "kind": "licence"}, files={"file": ("a.jpg", jpeg(), "image/jpeg")})
    assert bad_kind.status_code == 422  # a licence is not a truck paper
    disguised = await client.post("/documents", headers=ops, data=base, files={"file": ("a.jpg", b"<html>not an image</html>", "image/jpeg")})
    assert disguised.status_code == 415  # the bytes decide, not the file name
    huge = await client.post("/documents", headers=ops, data=base, files={"file": ("a.pdf", b"%PDF-" + b"0" * (3 * 1024 * 1024), "application/pdf")})
    assert huge.status_code == 413
    ghost = await client.post("/documents", headers=ops, data={**base, "owner_id": "00000000-0000-0000-0000-000000000000"}, files={"file": ("a.jpg", jpeg(), "image/jpeg")})
    assert ghost.status_code == 404
    billing = await office(client, "billing@cargoone.dev")
    md = await office(client, "md@cargoone.dev")
    assert (await client.post("/documents", headers=billing, data=base, files={"file": ("a.jpg", jpeg(), "image/jpeg")})).status_code == 403  # billing reads, never writes
    ok = (await client.post("/documents", headers=ops, data=base, files={"file": ("a.jpg", jpeg(), "image/jpeg")})).json()
    assert (await client.get(f"/documents/{ok['id']}/file", headers=billing)).status_code == 200  # truck papers: billing may read
    assert (await client.get("/documents", headers=md, params={"owner_type": "vehicle", "owner_id": truck["id"]})).status_code == 403
    lic = (await client.post("/documents", headers=ops, data={"owner_type": "driver", "owner_id": drv["id"], "kind": "licence"}, files={"file": ("a.jpg", jpeg(), "image/jpeg")})).json()
    assert (await client.get(f"/documents/{lic['id']}/file", headers=billing)).status_code == 404  # a driver's licence: ops only
    assert (await client.get(f"/documents/{lic['id']}/file")).status_code == 401


async def test_planning_refuses_an_unavailable_truck_and_an_expired_licence(client: AsyncClient) -> None:
    from tests.test_planning import body, fresh_vehicle_and_driver, refs, t0

    ops = await office(client)
    r = await refs(client, ops)
    vid, did = await fresh_vehicle_and_driver()
    payload = body(r, vid, did, t0())
    await client.patch(f"/setup/vehicles/{vid}", headers=ops, json={"availability": "maintenance"})
    blocked = await client.post("/planning/trips", headers=ops, json=payload)
    assert blocked.status_code == 422 and "not available" in blocked.json()["detail"]
    await client.patch(f"/setup/vehicles/{vid}", headers=ops, json={"availability": "available", "insurance_expiry": PAST})
    assert "expired paper" in (await client.post("/planning/trips", headers=ops, json=payload)).json()["detail"]
    await client.patch(f"/setup/vehicles/{vid}", headers=ops, json={"insurance_expiry": FUTURE})
    assert (await client.post("/planning/trips", headers=ops, json=payload)).status_code == 201
    refs_now = await refs(client, ops)
    assert {"availability", "capacity_tonnes"} <= set(refs_now["vehicles"][0]) and "assigned_vehicle_id" in refs_now["drivers"][0]


async def test_attention_lists_licences_and_puc_that_are_due(client: AsyncClient) -> None:
    ops = await office(client)
    await client.post("/drivers", headers=ops, json=D(name="Due Licence", licence_expiry=(date.today() + timedelta(days=5)).isoformat()))
    await make_truck(client, ops, puc_expiry=(date.today() + timedelta(days=5)).isoformat())
    items = {i["key"]: i for i in (await client.get("/attention", headers=ops)).json()["items"]}
    assert items["licences"]["count"] >= 1 and any(x["name"] == "Due Licence" for x in items["licences"]["detail"])
    assert items["papers"]["count"] >= 1
