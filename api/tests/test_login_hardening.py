import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import Text, cast, func, select, update

from app.auth_policy import check_secret
from app.db import SessionLocal
from app.models import AuditLog, Role, User
from app.routers.auth import ident_failures, ip_failures
from app.security import hash_secret

PW = "correct horse battery"


async def make_user(role: Role = Role.ops, secret: str = PW) -> User:
    tag = uuid.uuid4().hex[:8]
    async with SessionLocal() as s:
        u = User(name=f"T {tag}", email=f"t{tag}@example.test", role=role, password_hash=hash_secret(secret), language="en")
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def attempt(client: AsyncClient, ident: str, secret: str):
    return await client.post("/auth/login", json={"identifier": ident, "secret": secret})


async def test_five_wrong_passwords_lock_the_account_even_for_the_right_one(client: AsyncClient) -> None:
    u = await make_user()
    for _ in range(5):
        assert (await attempt(client, u.email, "wrong-password")).status_code == 401
    ident_failures.reset()  # isolate the DATABASE lock from the in-memory one
    ip_failures.reset()
    locked = await attempt(client, u.email, PW)
    assert locked.status_code == 429 and "Try again in" in locked.json()["detail"] and "Retry-After" in locked.headers

    async with SessionLocal() as s:  # lock expires -> works again and the counter resets
        await s.execute(update(User).where(User.id == u.id).values(locked_until=datetime.now(UTC) - timedelta(seconds=1)))
        await s.commit()
    assert (await attempt(client, u.email, PW)).status_code == 200
    async with SessionLocal() as s:
        row = await s.get(User, u.id)
        assert row.failed_logins == 0 and row.locked_until is None


async def test_success_resets_the_failure_count(client: AsyncClient) -> None:
    u = await make_user()
    for _ in range(4):
        await attempt(client, u.email, "nope-nope")
    assert (await attempt(client, u.email, PW)).status_code == 200
    ident_failures.reset()
    for _ in range(4):
        await attempt(client, u.email, "nope-nope")
    assert (await attempt(client, u.email, PW)).status_code == 200  # 4 + 4 failures never added up to 5


async def test_unknown_accounts_look_exactly_like_known_ones(client: AsyncClient) -> None:
    ghost = f"ghost{uuid.uuid4().hex[:6]}@example.test"
    first = await attempt(client, ghost, "whatever-1")
    assert first.status_code == 401 and first.json()["detail"] == "Invalid credentials"
    for _ in range(4):
        last = await attempt(client, ghost, "whatever-1")
    assert last.status_code == 401
    assert (await attempt(client, ghost, "whatever-1")).status_code == 429  # same throttle as a real account


async def test_one_address_cannot_guess_across_many_accounts(client: AsyncClient) -> None:
    for i in range(30):
        await attempt(client, f"spray{i}@example.test", "password-123")
    assert (await attempt(client, "another@example.test", "password-123")).status_code == 429


async def test_attempts_are_audited_without_secrets_or_full_identifiers(client: AsyncClient) -> None:
    u = await make_user()
    await attempt(client, u.email, "Wrong-Secret-9")
    await attempt(client, u.email, PW)
    async with SessionLocal() as s:
        actions = (await s.scalars(select(AuditLog.action).where(AuditLog.actor_id == u.id))).all()
        leaked = await s.scalar(select(func.count()).select_from(AuditLog).where(
            cast(AuditLog.meta, Text).contains("Wrong-Secret-9") | AuditLog.entity_id.contains(u.email)))
    assert "login.failed" in actions and "login.success" in actions and leaked == 0


async def test_changing_the_password_signs_other_sessions_out(client: AsyncClient) -> None:
    u = await make_user()
    old = (await attempt(client, u.email, PW)).json()["access_token"]
    new_pw = "a brand new passphrase"
    res = await client.post("/auth/change-secret", headers={"Authorization": f"Bearer {old}"}, json={"current": PW, "new": new_pw})
    assert res.status_code == 200
    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {old}"})).status_code == 401  # old session void
    assert (await client.get("/auth/me", headers={"Authorization": f"Bearer {res.json()['access_token']}"})).status_code == 200
    assert (await attempt(client, u.email, PW)).status_code == 401
    assert (await attempt(client, u.email, new_pw)).status_code == 200


async def test_change_secret_checks_current_and_policy(client: AsyncClient) -> None:
    u = await make_user()
    h = {"Authorization": f"Bearer {(await attempt(client, u.email, PW)).json()['access_token']}"}
    assert (await client.post("/auth/change-secret", headers=h, json={"current": "not mine", "new": "a fine new passphrase"})).status_code == 403
    for bad in ("short1", "1234567890123", PW):
        assert (await client.post("/auth/change-secret", headers=h, json={"current": PW, "new": bad})).status_code == 422
    assert (await client.post("/auth/change-secret", json={"current": PW, "new": "a fine new passphrase"})).status_code == 401


async def test_drivers_change_a_pin_not_a_password(client: AsyncClient) -> None:
    u = await make_user(Role.driver, "4821")
    h = {"Authorization": f"Bearer {(await attempt(client, u.email, '4821')).json()['access_token']}"}
    assert (await client.post("/auth/change-secret", headers=h, json={"current": "4821", "new": "1234"})).status_code == 422
    assert (await client.post("/auth/change-secret", headers=h, json={"current": "4821", "new": "a long password"})).status_code == 422
    assert (await client.post("/auth/change-secret", headers=h, json={"current": "4821", "new": "902817"})).status_code == 200


@pytest.mark.parametrize(("secret", "pin", "ok"), [
    ("4821", True, True), ("1111", True, False), ("1234", True, False), ("4321", True, False), ("123", True, False), ("48a1", True, False),
    ("a long enough phrase", False, True), ("short", False, False), ("0123456789012", False, False), ("Cargoone-Dev", False, False),
])
def test_policy(secret: str, pin: bool, ok: bool) -> None:
    assert (check_secret(secret, is_pin=pin) is None) is ok


def test_password_may_not_start_with_own_email_name() -> None:
    assert check_secret("priyadarshi-2026", is_pin=False, email="priyadarshi@example.com") is not None
