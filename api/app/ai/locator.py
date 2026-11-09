"""Where on the photo the AI's findings are, for readers that only return values (Groq, Gemini, the test reader).

The local reader draws its own boxes while it reads. For the others, the review screen asks this module once: the local text reader
(RapidOCR, no network) finds the lines of text, and each value the main AI read is matched to the line that holds it. The stamp and
the signature are pointed out by the local vision model if Ollama is running. The boxes are only for the person reviewing: what was found
and what was decided stays exactly as the main AI said. A box that cannot be matched is simply left out, so the screen shows "not found
on the photo" rather than a guess."""
import asyncio
import logging
import re
from datetime import date

from app.ai.base import Box
from app.ai.providers.local import (
    Line,
    RapidReader,
    _box_from_model,
    _key,
    _union,
    ollama_locate,
    remarks_from_text,
)
from app.config import Settings

log = logging.getLogger(__name__)


_READERS: dict[str, RapidReader] = {}


def _reader(langs: str) -> RapidReader:
    """One shared text reader. It holds a lock and loads its models once; a new one per request let several review pages start the GPU
    engine at the same moment, which crashed the whole API process."""
    return _READERS.setdefault(langs, RapidReader(langs))


def _numbers(text: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def _box(field: str, lines: list[Line]) -> Box | None:
    if not lines:
        return None
    x, y, w, h = _union(lines)
    return Box(field=field, x=x, y=y, w=w, h=h, text=" ".join(ln.text for ln in lines)[:120], conf=min(ln.conf for ln in lines), source="ocr")


def place(ai: dict, lines: list[Line], expected_lr_no: str) -> list[Box]:
    """Boxes for the text findings, from the lines OCR found. Pure and quick, so it is easy to test."""
    out: list[Box] = []

    want = _key(str(ai.get("lr_no") or expected_lr_no))
    if want and (hit := next((ln for ln in lines if want in _key(ln.text)), None)):
        out.append(_box("lr_no", [hit]))

    if isinstance(ai.get("delivery_date"), str):
        try:
            d = date.fromisoformat(ai["delivery_date"])
        except ValueError:
            d = None
        if d:
            def has_date(t: str) -> bool:
                nums = re.findall(r"\d+", t)
                return {d.day, d.month} <= {int(n) for n in nums if len(n) <= 2} and (d.year in {int(n) for n in nums} or d.year % 100 in {int(n) for n in nums})
            if hit := next((ln for ln in lines if has_date(ln.text)), None):
                out.append(_box("delivery_date", [hit]))

    items = ai.get("items") if isinstance(ai.get("items"), list) else []
    figures = {n for it in items if isinstance(it, dict) and isinstance(it.get("quantity"), int | float) for n in _numbers(f"{it['quantity']:g}")}
    figures |= _numbers(str(ai.get("quantity_received") or "")) | _numbers(str(ai.get("total_quantity") or ""))
    if figures:
        # the receiver's figures sit in the lower part of the paper, below the printed booking; the lowest lines that hold one of them
        holders = [ln for ln in lines if _numbers(ln.text) & figures and ln.y > 0.3 and ln.y < 0.92]
        if holders:
            top = max(ln.y for ln in holders)
            near = [ln for ln in holders if top - ln.y <= 0.14][:4]
            out.append(_box("quantity_received", near))

    if ai.get("remarks") and (under := remarks_from_text(lines)):
        out.append(_box("remarks", under))
    return [b for b in out if b]


async def locate(image: bytes, ai: dict, expected_lr_no: str, s: Settings) -> list[Box] | None:
    """All boxes we can place for this photo; never raises, since a missing box only means fewer labels on the photo. None when the text
    reader itself failed, so the caller tries again next time instead of remembering 'no boxes'."""
    if not ai.get("is_document"):
        return []
    try:
        lines = await asyncio.to_thread(_reader(s.ocr_langs), image)
    except Exception as e:  # noqa: BLE001 - the text reader raises many kinds of error
        log.warning("box placement skipped (text reader): %s", type(e).__name__)
        return None
    boxes = place(ai, lines, expected_lr_no)
    ask = ollama_locate(s.ollama_url, s.ollama_model, s.local_ai_timeout_s)
    for present, what in (("consignee_stamp_present", "stamp"), ("signature_present", "signature")):
        if ai.get(present) is True:
            try:
                got = await ask(image, what)
            except Exception as e:  # noqa: BLE001
                log.warning("box placement skipped (%s): %s", what, type(e).__name__)
                continue
            if got.get("found") is True and (b := _box_from_model(got.get("box"), what, 0)):
                boxes.append(b)
    return boxes
