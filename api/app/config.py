from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_JWT_SECRET = "dev-only-insecure-secret-change-me-in-env-0123"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")  # repo-root .env, then api/.env overrides

    database_url: str = "postgresql+asyncpg://cargoone:cargoone@localhost:5432/cargoone"
    app_env: Literal["dev", "test", "staging", "production"] = "dev"
    jwt_secret: str = DEV_JWT_SECRET
    web_origin: str = "http://localhost:5173"
    storage_dir: str = "./storage"
    ai_provider: str = "mock"  # mock | gemini | anthropic | openai | local
    mock_scenario: str = ""  # mock provider only: answer every unlabeled photo as this synthetic scenario (E2E/demos)
    ai_fallbacks: str = ""  # comma separated provider names
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"  # configurable: model names change over time
    ai_timeout_s: float = 20.0
    ai_confidence_threshold: float = 0.85
    max_image_bytes: int = 300 * 1024
    max_retakes: int = 2
    # KPI targets and the baseline from the client brief (used by the dashboards)
    baseline_pod_to_invoice_days: float = 18.0
    target_pod_to_invoice_days: float = 4.0
    target_pod_within_24h_pct: float = 80.0
    baseline_lost_pct: float = 1.5
    target_lost_pct: float = 0.5
    interest_rate: float = 0.12  # cost of working capital
    company_name: str = "Company A (demo)"  # printed on invoices
    invoice_prefix: str = "CO"
    tally_company: str = ""  # exact Tally company name; blank = import into the currently open company
    tally_sales_ledger: str = "Freight Income"  # must already exist in Tally

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
