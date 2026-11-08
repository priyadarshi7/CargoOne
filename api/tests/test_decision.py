import pytest

from app.ai.base import PodExtraction, PodItem
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


@pytest.mark.parametrize(("got", "differs"), [
    ("50 bags", False), ("50", False), ("40 bags", True), ("1,200", True),
    ("10 t", False), ("10.3 tonnes", False), ("9 MT", True), ("10000 kg", False), ("8000 kg", True),
])
def test_quantity_is_compared_with_the_booking(got: str, differs: bool) -> None:
    packages = 1200 if got == "1,200" else 50
    tonnes = 10.0 if any(u in got.lower() for u in ("t", "kg", "mt")) and "bags" not in got else None
    if tonnes:
        packages = None
    r = decide(ex(quantity_received=got), expected_lr_no=LR, retake_count=0, expected_packages=packages if got != "1,200" else 50,
              expected_weight_tonnes=tonnes)
    assert ("quantity_mismatch" in r.reasons) is differs
    assert r.decision == (Decision.needs_review if differs else Decision.verified)


def test_quantity_is_not_checked_when_nothing_was_booked_or_nothing_was_read() -> None:
    assert run(ex(quantity_received="40 bags")).decision == Decision.verified
    assert decide(ex(quantity_received=None), expected_lr_no=LR, retake_count=0, expected_packages=50).decision == Decision.verified


def multi(items: list[tuple[str, float | None, str]], total: str | None = None, text: str | None = None, **book) -> list[str]:
    e = ex(items=[PodItem(name=n, quantity=q, unit=u) for n, q, u in items], total_quantity=total, quantity_received=text)
    return decide(e, expected_lr_no=LR, retake_count=0, **book).reasons


def test_several_goods_are_added_up_and_compared_with_the_booked_total() -> None:
    sand = [("Cement", 2.5, "t"), ("Sand", 1.5, "t")]
    assert multi(sand, expected_weight_tonnes=4.0) == []
    assert multi(sand, total="4 t", expected_weight_tonnes=4.0) == []
    assert multi([("Cement", 2.5, "t"), ("Sand", 1000, "kg")], expected_weight_tonnes=4.0) == ["quantity_mismatch"]  # 3.5 t arrived
    assert multi([("Cement", 25, "bags"), ("Sand", 25, "bags")], expected_packages=50) == []
    assert multi([("Cement", 25, "bags"), ("Sand", 20, "bags")], expected_packages=50) == ["quantity_mismatch"]


def test_several_goods_that_cannot_be_compared_go_to_a_person_without_a_retake() -> None:
    assert multi([("Cement", 50, "bags"), ("Sand", 1.5, "t")], expected_packages=50, expected_weight_tonnes=4.0) == ["quantity_unclear"]
    assert multi([("Cement", 2.5, "t"), ("Sand", 1.5, "t")], total="5 t", expected_weight_tonnes=5.0) == ["quantity_unclear"]  # lines do not add up to the total
    assert multi([("Cement", 2.5, "t"), ("Sand", None, "t")], expected_weight_tonnes=4.0) == ["quantity_unclear"]
    assert multi([], text="48/50", expected_packages=50) == ["quantity_unclear"]


def test_several_goods_written_as_one_line_of_text_work_too() -> None:
    assert multi([], text="Cement 2.5 t, Sand 1.5 t", expected_weight_tonnes=4.0) == []
    assert multi([], text="Cement 2.5 t, Sand 1.5 t. Total 4 t", expected_weight_tonnes=4.0) == []
    assert multi([], text="Cement 2.5 t, Sand 1.0 t, Total 3.5 t", expected_weight_tonnes=4.0) == ["quantity_mismatch"]
    assert multi([], text="1,200 bags", expected_packages=1200) == []


def test_nothing_is_flagged_when_nothing_was_booked() -> None:
    assert multi([("Cement", 2.5, "t"), ("Sand", 1.5, "t")]) == []
