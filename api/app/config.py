from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://cargoone:cargoone@localhost:5432/cargoone"
    jwt_secret: str = "dev-only-insecure-secret-change-me-in-env-0123"
    web_origin: str = "http://localhost:5173"
    storage_dir: str = "./storage"
    ai_provider: str = "mock"  # mock | gemini | anthropic | openai | local
    ai_fallbacks: str = ""  # comma separated provider names
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"  # configurable: model names change over time
    ai_timeout_s: float = 20.0
    ai_confidence_threshold: float = 0.85
    max_image_bytes: int = 300 * 1024
    max_retakes: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
