"""Deterministic routing of an AI extraction. The AI only reads; these rules decide.

- Not a POD / unreadable / no stamp / no signature / wrong LR  -> retake (while retakes remain),
  otherwise -> human review.
- Shortage or damage remark, low confidence, a quantity that differs from the booking -> human review (never auto-verified). A missing date is not a reason: the app records when the load was delivered.
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


_UNIT = r"kgs?|kilo\w*|qtl|quintals?|mt|tonnes?|tons?|t|टन|किलो|क्विंटल"
_LINE = re.compile(rf"(\d+(?:\.\d+)?)\s*({_UNIT}\b|[^\W\d_]+)?", re.IGNORECASE)
_WEIGHT_WORD = re.compile(rf"^(?:{_UNIT})$", re.IGNORECASE)
_TOTAL = re.compile(r"\b(?:grand\s+)?total\b|कुल|एकूण", re.IGNORECASE)
_RATIO = re.compile(r"\d\s*/\s*\d")


def _tonnes(value: float, word: str) -> float:
    w = word.lower()
    if w.startswith("k") or w == "किलो":
        return value / 1000
    if w in ("qtl", "क्विंटल") or w.startswith("quintal"):
        return value / 10
    return value


def _line(value: float, unit: str | None) -> tuple[str, float]:
    """('weight', tonnes) for a weight unit, otherwise ('count', the number): bags, cartons, coils or no unit at all."""
    if unit and _WEIGHT_WORD.match(unit.strip()):
        return "weight", _tonnes(value, unit.strip())
    return "count", value


def _from_text(text: str) -> list[tuple[str, float]]:
    return [_line(float(v), u or None) for v, u in _LINE.findall(re.sub(r"(?<=\d),(?=\d{3}\b)", "", text))]


def _reduce(lines: list[tuple[str, float]]) -> tuple[str, float] | None:
    """One figure for a list of lines: every line a weight (add the tonnes) or every line a count (add the counts). Mixed lists have none."""
    kinds = {k for k, _ in lines}
    return (kinds.pop(), sum(v for _, v in lines)) if len(kinds) == 1 else None


def _worse(a: float, b: float, tol: float) -> bool:
    return abs(a - b) > max(b * tol, 1e-9)


Source = tuple[list[tuple[str, float]], tuple[str, float] | None]  # (the lines, the written total if there is one)


def _judge(src: Source, packages: int | None, weight_tonnes: float | None, tol: float) -> tuple[str | None, tuple[str, float] | None]:
    """(flag, the one figure the lines and total come to) for one reading of the receipt."""
    lines, stated = src
    if stated is None and not lines:
        return None, None
    total = stated or _reduce(lines)
    if stated and lines and (summed := _reduce(lines)) and summed[0] == stated[0] and _worse(summed[1], stated[1], tol):
        return "quantity_unclear", total  # the lines do not add up to the written total
    if total is None:  # packages and weight both written (one good "50 bags, 2.5 t", or several goods in different units)
        count = sum(v for k, v in lines if k == "count")
        weight = sum(v for k, v in lines if k == "weight")
        agrees = [count == packages if packages else None, not _worse(weight, weight_tonnes, tol) if weight_tonnes else None]
        return (None if True in agrees and False not in agrees else "quantity_unclear"), None
    kind, value = total
    if kind == "weight":
        return ("quantity_mismatch" if weight_tonnes and _worse(value, weight_tonnes, tol) else None), total
    return ("quantity_mismatch" if packages and value != packages else None), total


def quantity_flag(ex: PodExtraction, *, packages: int | None, weight_tonnes: float | None, tol: float = 0.05, require: bool = False) -> str | None:
    """Compares what the receiver wrote with the booking, which holds ONE total (a weight, a package count, or both).
    - quantity_mismatch: the receipt clearly gives a total that is different from the booked one.
    - quantity_unclear: several goods or mixed units that cannot be reduced to one comparable figure, lines that do not add up to the
      written total, or the model's lines and its quoted text disagreeing. A person looks at the photo; nothing is retaken.
    The receipt is read two ways, from the model's per-good lines and from the text it quoted, and ANY disagreement with the booking counts:
    a model that copies the printed booked figure into its lines must not hide a different handwritten one.
    Nothing is flagged when nothing was booked to compare with. When nothing was read, nothing is flagged either, unless `require` is on: then it is
    quantity_not_read (a person looks), because a reader that misses the handwriting must not let a short delivery through."""
    if not packages and not weight_tonnes:
        return None
    sources: list[Source] = []
    if ex.items:
        lines = [_line(i.quantity, i.unit) for i in ex.items if i.quantity is not None]
        if len(lines) < len(ex.items):  # a line whose number was not read
            return "quantity_unclear"
        one = _from_text(ex.total_quantity) if ex.total_quantity else []
        sources.append((lines, one[0] if len(one) == 1 else None))
    if text := ex.quantity_received or ex.total_quantity:
        if _RATIO.search(text):
            return "quantity_unclear"  # "48/50": which one is the received count?
        if (m := _TOTAL.search(text)) and (tail := _from_text(text[m.end():])):
            sources.append((_from_text(text[:m.start()]), tail[0]))
        else:
            sources.append((_from_text(text), None))
    if not sources:
        return "quantity_not_read" if require else None
    judged = [_judge(src, packages, weight_tonnes, tol) for src in sources]
    flags = [f for f, _ in judged if f]
    if flags:
        return "quantity_mismatch" if "quantity_mismatch" in flags else flags[0]
    figs = [fig for _, fig in judged if fig]
    if len(figs) == 2 and figs[0][0] == figs[1][0] and _worse(figs[0][1], figs[1][1], tol):
        return "quantity_unclear"  # the lines and the quoted text say different totals
    return None


def decide(ex: PodExtraction, *, expected_lr_no: str, retake_count: int,
           threshold: float = 0.85, max_retakes: int = 2, place_reasons: list[str] | None = None,
           expected_packages: int | None = None, expected_weight_tonnes: float | None = None, require_quantity: bool = False) -> DecisionResult:
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

    review: list[str] = list(place_reasons or [])  # where the photo was taken is checked by the caller; a person looks when it is off
    if ex.shortage_or_damage:
        review.append("shortage_or_damage")
    if flag := quantity_flag(ex, packages=expected_packages, weight_tonnes=expected_weight_tonnes, require=require_quantity):
        review.append(flag)  # a different total than booked, or several goods that cannot be compared: a person decides
    if ex.confidence < threshold:
        review.append("low_confidence")
    if review:
        return DecisionResult(Decision.needs_review, review, Voice.review)
    return DecisionResult(Decision.verified, [], Voice.ok)
