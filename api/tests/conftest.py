"""Tests run against their OWN database (<name>_test), created and migrated on demand, so test data can
never pollute the development database that demos run on."""
import os
import subprocess
import sys
from urllib.parse import urlsplit, urlunsplit


def _use_test_database() -> None:
    from app.config import Settings

    url = os.environ.get("DATABASE_URL") or Settings().database_url
    parts = urlsplit(url)
    name = parts.path.lstrip("/")
    test_name = name if name.endswith("_test") else f"{name}_test"
    os.environ["DATABASE_URL"] = urlunsplit(parts._replace(path=f"/{test_name}"))
    admin = urlunsplit(parts._replace(scheme="postgresql", path="/postgres"))
    import asyncio

    import asyncpg

    async def ensure() -> None:
        conn = await asyncpg.connect(admin)
        try:
            if not await conn.fetchval("select 1 from pg_database where datname = $1", test_name):
                await conn.execute(f'create database "{test_name}"')
        finally:
            await conn.close()

    asyncio.run(ensure())
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, capture_output=True)


# Tests must never reach a real AI provider (cost, flakiness, and photos leaving the machine),
# whatever the developer's .env says. Environment variables beat .env files.
os.environ.update({"AI_PROVIDER": "mock", "AI_FALLBACKS": "", "GEMINI_API_KEY": "", "APP_ENV": "test", "WHATSAPP_PROVIDER": "mock", "WHATSAPP_TOKEN": ""})
_use_test_database()  # must run before `app` is imported anywhere

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db import SessionLocal
from app.main import app
from app.seed import seed
from app.storage import LocalStorage, get_storage


@pytest.fixture(scope="session", autouse=True)
async def seeded() -> None:
    """Requires migrated Postgres (`alembic upgrade head`). Seed is idempotent."""
    async with SessionLocal() as session:
        # Earlier runs leave planned/cancelled trips behind; enough of them would push new ones off the planning board's page.
        await session.execute(text("delete from trips where state in ('planned', 'cancelled') and pod_status = 'pending'"))
        await session.commit()
        await seed(session)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, identifier: str, secret: str) -> dict[str, str]:
    res = await client.post("/auth/login", json={"identifier": identifier, "secret": secret})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture(autouse=True)
def tmp_storage(tmp_path: Path) -> Iterator[None]:
    """Uploads go to a throwaway folder, never the real storage dir."""
    app.dependency_overrides[get_storage] = lambda: LocalStorage(str(tmp_path))
    yield
    app.dependency_overrides.pop(get_storage, None)


@pytest.fixture
async def driver(client: AsyncClient) -> dict[str, str]:
    return await login(client, "9000000001", "1234")


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> Iterator[None]:
    from app.routers.auth import ident_failures, ip_failures
    from app.routers.client_view import bad_token_limiter as client_limiter
    from app.routers.links import bad_token_limiter, upload_limiter

    bad_token_limiter.reset()
    upload_limiter.reset()
    client_limiter.reset()
    ip_failures.reset()
    ident_failures.reset()
    from app.routers import onboard, requests

    for limiter in (requests.submit_limiter, requests.phone_limiter, requests.bad_token_limiter, onboard.bad_token_limiter):
        limiter.reset()
    yield
