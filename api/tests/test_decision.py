import pytest

from app.ai.base import PodExtraction
from app.pod.decision import Decision, Voice, decide

LR = "LR-88120"


def ex(**kw) -> PodExtraction:
    base = {"is_document": True, "readable": True, "lr_no": LR, "consignee_stamp_present": True,
            "signature_present": True, "delivery_date": "2026-11-03", "shortage_or_damage": False,
            "confidence": 0.95}
    return PodExtraction(**{**base, **kw})


def run(e: PodExtraction, retakes: int = 0):
    return decide(e, expected_lr_no=LR, retake_count=retakes)


def test_clean_pod_is_verified() -> None:
    r = run(ex())
    assert (r.decision, r.reasons, r.voice) == (Decision.verified, [], Voice.ok)


def test_lr_match_ignores_case_and_punctuation() -> None:
    assert run(ex(lr_no="lr 88120")).decision == Decision.verified


@pytest.mark.parametrize(("kw", "reason", "voice"), [
    ({"is_document": False}, "not_a_pod", Voice.retake_not_pod),
    ({"readable": False}, "unreadable", Voice.retake_blurry),
    ({"consignee_stamp_present": False}, "stamp_missing", Voice.retake_stamp),
    ({"signature_present": False}, "signature_missing", Voice.retake_signature),
    ({"lr_no": "LR-99999"}, "lr_mismatch", Voice.retake_lr),
    ({"lr_no": None}, "lr_mismatch", Voice.retake_lr),
])
def test_retake_reasons(kw, reason, voice) -> None:
    r = run(ex(**kw))
    assert r.decision == Decision.retake_requested
    assert reason in r.reasons
    assert r.voice == voice


def test_retake_cap_sends_to_human_review() -> None:
    r = run(ex(consignee_stamp_present=False), retakes=2)
    assert r.decision == Decision.needs_review
    assert "retake_cap_reached" in r.reasons and "stamp_missing" in r.reasons
    assert run(ex(consignee_stamp_present=False), retakes=1).decision == Decision.retake_requested


@pytest.mark.parametrize(("kw", "reason"), [
    ({"shortage_or_damage": True, "remarks": "short by 6 cartons"}, "shortage_or_damage"),
    ({"confidence": 0.84}, "low_confidence"),
])
def test_review_reasons_never_auto_verified(kw, reason) -> None:
    r = run(ex(**kw))
    assert r.decision == Decision.needs_review
    assert reason in r.reasons


def test_confidence_at_threshold_passes() -> None:
    assert run(ex(confidence=0.85)).decision == Decision.verified


def test_shortage_with_stamp_missing_prefers_retake_first() -> None:
    r = run(ex(consignee_stamp_present=False, shortage_or_damage=True))
    assert r.decision == Decision.retake_requested


def test_a_paper_with_no_delivery_date_is_still_verified_when_everything_else_checks_out() -> None:
    # many LR forms have no date field for the receiver; the app already records when the load was delivered
    r = run(ex(delivery_date=None))
    assert r.decision == Decision.verified and r.reasons == []
