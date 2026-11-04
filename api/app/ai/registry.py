"""Builds the provider chain from config and runs extraction with fallback + metrics."""
import logging
import time
from dataclasses import dataclass, field

from app.ai.base import PodExtraction, ProviderError, VisionProvider
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.mock import MockProvider
from app.config import Settings, get_settings

log = logging.getLogger("cargoone.ai")


@dataclass
class Outcome:
    provider: str
    extraction: PodExtraction
    latency_ms: int
    failures: list[str] = field(default_factory=list)  # providers tried before this one


class AllProvidersFailed(Exception):
    """Every provider failed. Caller must queue the POD for human review, never block the driver."""

    def __init__(self, failures: list[str]) -> None:
        super().__init__("; ".join(failures))
        self.failures = failures


def build_provider(name: str, s: Settings) -> VisionProvider:
    if name == "mock":
        return MockProvider()
    if name == "gemini":
        return GeminiProvider(s.gemini_api_key, s.gemini_model, s.ai_timeout_s)
    raise ValueError(f"Unknown AI provider '{name}' (available: mock, gemini)")


def build_chain(s: Settings | None = None) -> list[VisionProvider]:
    s = s or get_settings()
    names = [s.ai_provider, *[n.strip() for n in s.ai_fallbacks.split(",") if n.strip()]]
    return [build_provider(n, s) for n in dict.fromkeys(names)]  # de-duplicated, order kept


async def run_extraction(
    image: bytes, mime: str, expected_lr_no: str, chain: list[VisionProvider] | None = None
) -> Outcome:
    chain = chain if chain is not None else build_chain()
    failures: list[str] = []
    for provider in chain:
        started = time.perf_counter()
        try:
            extraction = await provider.extract(image, mime, expected_lr_no)
        except ProviderError as e:
            failures.append(f"{provider.name}: {e}")
            log.warning("ai provider failed: %s: %s", provider.name, e)  # never log image/PII
            continue
        latency = int((time.perf_counter() - started) * 1000)
        log.info("ai ok provider=%s latency_ms=%d confidence=%.2f", provider.name, latency, extraction.confidence)
        return Outcome(provider.name, extraction, latency, failures)
    raise AllProvidersFailed(failures)
