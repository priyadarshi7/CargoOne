from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import SessionLocal
from app.main import app
from app.seed import seed


@pytest.fixture(scope="session", autouse=True)
async def seeded() -> None:
    """Requires migrated Postgres (`alembic upgrade head`). Seed is idempotent."""
    async with SessionLocal() as session:
        await seed(session)


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, identifier: str, secret: str) -> dict[str, str]:
    res = await client.post("/auth/login", json={"identifier": identifier, "secret": secret})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}
