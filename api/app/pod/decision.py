"""Deterministic routing of an AI extraction. The AI only reads; these rules decide.

- Not a POD / unreadable / no stamp / no signature / wrong LR  -> retake (while retakes remain),
  otherwise -> human review.
- Shortage or damage remark, low confidence                    -> human review (never auto-verified). A missing date is not a reason: the app records when the load was delivered.
- Everything clean                                              -> verified (still never auto-invoiced).
"""
import re
from dataclasses import dataclass
from enum import StrEnum

from app.ai.base import PodExtraction


class Decision(StrEnum):
    verified = "verified"
    needs_review = "needs_review"
    retake_requested = "retake_requested"


class Voice(StrEnum):
    """Which spoken prompt the driver app plays (localised on the client)."""
    ok = "ok"
    retake_blurry = "retake_blurry"
    retake_stamp = "retake_stamp"
    retake_signature = "retake_signature"
    retake_lr = "retake_lr"
    retake_not_pod = "retake_not_pod"
    review = "review"


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    reasons: list[str]
    voice: Voice


def _norm(s: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def decide(ex: PodExtraction, *, expected_lr_no: str, retake_count: int,
           threshold: float = 0.85, max_retakes: int = 2) -> DecisionResult:
    retake: list[tuple[str, Voice]] = []
    if not ex.is_document:
        retake.append(("not_a_pod", Voice.retake_not_pod))
    elif not ex.readable:
        retake.append(("unreadable", Voice.retake_blurry))
    else:
        if not ex.consignee_stamp_present:
            retake.append(("stamp_missing", Voice.retake_stamp))
        if not ex.signature_present:
            retake.append(("signature_missing", Voice.retake_signature))
        if _norm(ex.lr_no) != _norm(expected_lr_no):
            retake.append(("lr_mismatch", Voice.retake_lr))

    if retake:
        reasons = [r for r, _ in retake]
        if retake_count < max_retakes:
            return DecisionResult(Decision.retake_requested, reasons, retake[0][1])
        return DecisionResult(Decision.needs_review, [*reasons, "retake_cap_reached"], Voice.review)

    review: list[str] = []
    if ex.shortage_or_damage:
        review.append("shortage_or_damage")
    if ex.confidence < threshold:
        review.append("low_confidence")
    if review:
        return DecisionResult(Decision.needs_review, review, Voice.review)
    return DecisionResult(Decision.verified, [], Voice.ok)
