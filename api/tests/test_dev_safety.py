import pytest
from pydantic import ValidationError

from app.config import DEV_JWT_SECRET, Settings
from app.db import SessionLocal
from app.seed import seed


def test_default_or_short_jwt_secret_rejected_outside_dev() -> None:
    for env in ("staging", "production"):
        with pytest.raises(ValidationError):
            Settings(app_env=env, jwt_secret=DEV_JWT_SECRET, _env_file=None)
        with pytest.raises(ValidationError):
            Settings(app_env=env, jwt_secret="short", _env_file=None)
        with pytest.raises(ValidationError):
            Settings(app_env=env, jwt_secret=DEV_JWT_SECRET, _env_file=None)
    assert Settings(app_env="production", jwt_secret="x" * 40).app_env == "production"


def test_dev_defaults_still_work() -> None:
    assert Settings().is_dev


async def test_seed_refuses_outside_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.seed.get_settings", lambda: Settings(app_env="production", jwt_secret="x" * 40))
    async with SessionLocal() as session:
        with pytest.raises(RuntimeError, match="Refusing to seed"):
            await seed(session)
