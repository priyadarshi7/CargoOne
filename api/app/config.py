from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-in-env-0123"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://cargoone:cargoone@localhost:5432/cargoone"
    app_env: Literal["dev", "test", "staging", "production"] = "dev"
    jwt_secret: str = DEV_JWT_SECRET
    web_origin: str = "http://localhost:5173"
    storage_dir: str = "./storage"
    ai_provider: str = "mock"  # mock | gemini | anthropic | openai | local
    ai_fallbacks: str = ""  # comma separated provider names
    gemini_api_key: str = ""
    ai_confidence_threshold: float = 0.85
    max_image_bytes: int = 300 * 1024
    max_retakes: int = 2

    @property
    def is_dev(self) -> bool:
        return self.app_env in ("dev", "test")

    @model_validator(mode="after")
    def _refuse_insecure_deployments(self) -> "Settings":
        if not self.is_dev and (self.jwt_secret == DEV_JWT_SECRET or len(self.jwt_secret) < 32):
            raise ValueError("JWT_SECRET must be set to a unique value of 32+ characters outside dev/test")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
