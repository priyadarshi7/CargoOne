import asyncio
import io

from PIL import Image

from app.ai.base import PodExtraction, ProviderError
from app.ai.providers.mock import LABEL_KEY, MockProvider
from app.devtools.evaluate import (
    Case,
    Throttle,
    call_with_retry,
    degrade,
    evaluate,
    expected_decision,
    report,
)
from app.devtools.synthetic_pod import SCENARIOS, render
from app.pod.decision import Decision


class OptimisticReader:
    """A reader that sees a perfect POD in every image: exactly the failure that would verify bad paperwork."""
    name = "optimist"

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction:
        return PodExtraction(is_document=True, readable=True, lr_no=expected_lr_no, consignee_stamp_present=True, signature_present=True,
                             delivery_date="2026-11-03", confidence=0.99)


class Flaky:
    name = "flaky"

    def __init__(self, fail_times: int, message: str) -> None:
        self.left, self.message, self.calls = fail_times, message, 0

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction:
        self.calls += 1
        if self.left > 0:
            self.left -= 1
            raise ProviderError(self.message)
        return PodExtraction(is_document=True, readable=True, confidence=0.9)


def test_the_mock_scores_perfectly_and_the_report_says_so() -> None:
    cases = asyncio.run(evaluate(MockProvider(), seeds=2, variants=("original",)))
    text, stats = report("mock", cases)
    assert stats["false_verify"] == 0 and stats["decision_accuracy"] == 1.0 and stats["errors"] == 0
    assert "Unsafe errors (bad POD would be auto-verified): 0" in text and len(cases) == 2 * len(SCENARIOS)


def test_a_reader_that_trusts_everything_is_caught_as_unsafe() -> None:
    cases = asyncio.run(evaluate(OptimisticReader(), seeds=1, variants=("original",)))
    _, stats = report("optimist", cases)
    unsafe = {c.scenario for c in cases if c.unsafe}
    assert {"no_stamp", "no_signature", "wrong_lr", "shortage", "damage"} <= unsafe  # every bad POD it waved through
    assert "clean" not in unsafe and stats["false_verify"] >= 5


def test_friction_is_a_good_pod_that_is_not_verified() -> None:
    assert Case("clean", "original", 0, Decision.verified, got=Decision.retake_requested).friction
    assert not Case("clean", "original", 0, Decision.verified, got=Decision.verified).friction
    assert Case("no_stamp", "original", 0, Decision.retake_requested, got=Decision.verified).unsafe


def test_expected_decisions_follow_the_business_rules() -> None:
    want = {"clean": Decision.verified, "low_confidence": Decision.verified,  # confidence is not an image property for a real model
            "no_stamp": Decision.retake_requested, "wrong_lr": Decision.retake_requested, "blurry": Decision.retake_requested,
            "shortage": Decision.needs_review, "damage": Decision.needs_review}
    for name, decision in want.items():
        assert expected_decision(name, "LR-1")[1] == decision, name
    assert expected_decision("low_confidence", "LR-1", scripted=True)[1] == Decision.needs_review  # the mock replays its script


def test_phone_and_dark_variants_are_degraded_jpegs_without_the_label() -> None:
    png = render(SCENARIOS["clean"], "LR-9")
    for variant in ("phone", "dark"):
        data, mime = degrade(png, variant, 1)
        assert mime == "image/jpeg" and data[:2] == b"\xff\xd8"
        assert LABEL_KEY not in Image.open(io.BytesIO(data)).info  # the model must read pixels, not a hidden label
    assert degrade(png, "original", 0) == (png, "image/png")


def test_rate_limits_are_waited_out_not_counted_as_misses(monkeypatch) -> None:
    async def no_sleep(_: float) -> None: ...
    monkeypatch.setattr(asyncio, "sleep", no_sleep)
    f = Flaky(2, "gemini http 429")
    got = asyncio.run(call_with_retry(f, b"x", "image/png", "LR-1", Throttle(0)))
    assert got.is_document and f.calls == 3
    hard = Flaky(5, "gemini http 500")  # other failures are not retried
    try:
        asyncio.run(call_with_retry(hard, b"x", "image/png", "LR-1", Throttle(0)))
    except ProviderError:
        assert hard.calls == 1
    else:
        raise AssertionError("expected a ProviderError")
