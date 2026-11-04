import json

import httpx
import pytest

from app.ai.base import PodExtraction, ProviderError
from app.ai.providers.gemini import GeminiProvider
from app.ai.providers.mock import MockProvider
from app.ai.registry import AllProvidersFailed, build_chain, run_extraction
from app.config import Settings
from app.devtools.synthetic_pod import SCENARIOS, render
from app.pod.decision import Decision, decide

LR = "LR-88120"

# What the pipeline MUST decide for each synthetic scenario (first attempt, no retakes used).
EXPECTED = {
    "clean": Decision.verified,
    "no_stamp": Decision.retake_requested,
    "no_signature": Decision.retake_requested,
    "blurry": Decision.retake_requested,
    "shortage": Decision.needs_review,
    "damage": Decision.needs_review,
    "wrong_lr": Decision.retake_requested,
    "low_confidence": Decision.needs_review,
    "not_a_pod": Decision.retake_requested,
}


@pytest.mark.parametrize("name", list(SCENARIOS))
async def test_synthetic_pods_route_correctly_through_mock(name: str) -> None:
    out = await run_extraction(render(SCENARIOS[name], LR), "image/png", LR, chain=[MockProvider()])
    r = decide(out.extraction, expected_lr_no=LR, retake_count=0)
    assert r.decision == EXPECTED[name], (name, r)


class Failing:
    name = "failing"

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction:
        raise ProviderError("boom")


async def test_fallback_to_next_provider() -> None:
    out = await run_extraction(render(SCENARIOS["clean"], LR), "image/png", LR, chain=[Failing(), MockProvider()])
    assert out.provider == "mock"
    assert out.failures == ["failing: boom"]


async def test_all_providers_failing_raises_so_caller_can_queue_for_review() -> None:
    with pytest.raises(AllProvidersFailed) as e:
        await run_extraction(b"x", "image/png", LR, chain=[Failing(), Failing()])
    assert len(e.value.failures) == 2


def test_chain_built_from_settings_dedupes() -> None:
    chain = build_chain(Settings(ai_provider="gemini", ai_fallbacks="mock, gemini", gemini_api_key="k"))
    assert [p.name for p in chain] == ["gemini", "mock"]


def test_unknown_provider_is_a_config_error() -> None:
    with pytest.raises(ValueError, match="Unknown AI provider"):
        build_chain(Settings(ai_provider="skynet"))


def _gemini(handler) -> GeminiProvider:
    return GeminiProvider("test-key", "gemini-test", transport=httpx.MockTransport(handler))


async def test_gemini_parses_structured_output_and_sends_key_in_header() -> None:
    truth = {"is_document": True, "readable": True, "lr_no": LR, "consignee_stamp_present": True,
             "signature_present": True, "delivery_date": "2026-11-03", "shortage_or_damage": False,
             "confidence": 0.9}
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["key"] = req.headers["x-goog-api-key"]
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": json.dumps(truth)}]}}]})

    ex = await _gemini(handler).extract(b"img", "image/jpeg", LR)
    assert ex.lr_no == LR and ex.confidence == 0.9
    assert seen["key"] == "test-key" and "key=" not in seen["url"]  # key never in URL/logs


@pytest.mark.parametrize("response", [
    httpx.Response(500, text="oops"),
    httpx.Response(429, text="quota"),
    httpx.Response(200, json={"candidates": []}),
    httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "not json"}]}}]}),
])
async def test_gemini_failures_become_provider_errors(response: httpx.Response) -> None:
    with pytest.raises(ProviderError):
        await _gemini(lambda _req: response).extract(b"img", "image/jpeg", LR)


async def test_gemini_without_key_fails_cleanly() -> None:
    with pytest.raises(ProviderError, match="not configured"):
        await GeminiProvider("", "m").extract(b"i", "image/png", LR)
