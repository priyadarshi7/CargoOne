"""Live updates: who is told, who is not, and that a bad sign-in gets nothing."""
import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.db import SessionLocal
from app.devtools.synthetic_pod import SCENARIOS, render
from app.live import Conn, hub
from app.models import Client, Role, User
from app.routers.live import authenticate
from app.security import create_token
from tests.conftest import login
from tests.test_pod_upload import make_trip, post


async def conn_for(email: str | None = None, phone: str | None = None) -> Conn:
    async with SessionLocal() as s:
        u = await s.scalar(select(User).where(User.email == email) if email else select(User).where(User.phone == phone))
        c = await authenticate(f"Bearer {create_token(u)}")
        assert c is not None
        return c


def drain(c: Conn) -> list[dict]:
    out = []
    while not c.queue.empty():
        out.append(c.queue.get_nowait())
    return out


async def test_an_upload_tells_the_office_and_that_driver_but_not_another_driver(client: AsyncClient, driver: dict) -> None:
    ops = await conn_for("ops@cargoone.dev")
    md = await conn_for("md@cargoone.dev")
    mine = await conn_for(phone="9000000001")
    other = Conn(user_id=uuid.uuid4(), role=Role.driver)  # a driver with no part in this trip
    for c in (ops, md, mine, other):
        assert hub.add(c)
    try:
        tid, lr = await make_trip()
        drain(ops), drain(md), drain(mine)
        assert (await post(client, driver, tid, render(SCENARIOS["clean"], lr))).status_code == 200
        for c in (ops, md):
            assert any("trips" in e["topics"] for e in drain(c)), c.role
        assert any("trips" in e["topics"] for e in drain(mine))
        assert drain(other) == []
    finally:
        for c in (ops, md, mine, other):
            hub.remove(c)


async def test_a_client_hears_only_about_its_own_trips() -> None:
    async with SessionLocal() as s:
        names = [c.id for c in (await s.scalars(select(Client).order_by(Client.name).limit(2))).all()]
    mine, theirs = Conn(user_id=uuid.uuid4(), role=Role.client, client_id=names[0]), Conn(user_id=uuid.uuid4(), role=Role.client, client_id=names[1])
    hub.add(mine), hub.add(theirs)
    try:
        hub.publish({("trips", names[0], None)})
        assert len(drain(mine)) == 1 and drain(theirs) == []
        hub.publish({("review", names[0], None)})  # the review queue is not a client's business
        assert drain(mine) == []
    finally:
        hub.remove(mine), hub.remove(theirs)


async def test_a_slow_screen_gets_one_catch_up_message() -> None:
    c = Conn(user_id=uuid.uuid4(), role=Role.ops)
    hub.add(c)
    try:
        for _ in range(60):
            hub.publish({("trips", None, None)})
        events = drain(c)
        assert len(events) <= 21 and any(e["topics"] == ["*"] for e in events)
    finally:
        hub.remove(c)


async def test_only_a_real_sign_in_is_let_in(client: AsyncClient) -> None:
    assert await authenticate("") is None
    assert await authenticate("Bearer not-a-token") is None
    assert await authenticate("Link " + "x" * 40) is None
    assert await authenticate("Basic abc") is None
    await login(client, "ops@cargoone.dev", "cargoone-dev")  # a good one works
    assert await conn_for("ops@cargoone.dev") is not None


async def test_five_screens_per_person_is_the_limit() -> None:
    uid = uuid.uuid4()
    conns = [Conn(user_id=uid, role=Role.ops) for _ in range(6)]
    added = [hub.add(c) for c in conns]
    for c in conns:
        hub.remove(c)
    assert added == [True] * 5 + [False]
