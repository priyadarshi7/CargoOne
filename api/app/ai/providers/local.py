"""The local reader: nothing leaves the machine. Two steps.

1. OCR (PaddleOCR) reads every line of text and says where it is on the photo.
2. A small vision model (Qwen-VL, run by Ollama) looks at the photo with those lines and answers the questions OCR cannot:
   is this a POD, is there a stamp, is there a signature, what do the remarks say, which lines are the LR number, date, quantity.

The model is not trusted on its own. Every field it claims is checked against what OCR read; a box is only drawn from a line that
really contains the value, and the LR number is accepted only when OCR can see it on the paper. Anything that cannot be checked
lowers the confidence, which sends the photo to a person (never an auto-verify on an unchecked guess).
"""
import asyncio
import base64
import difflib
import io
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import ClassVar

import httpx
from PIL import Image, ImageOps

from app.ai.base import Box, PodExtraction, ProviderError

MAX_SIDE = 1600  # longest side handed to OCR; phone photos are already small (300 KB cap)


@dataclass(frozen=True)
class Line:
    """One line of text OCR found. Position as fractions of the photo."""

    id: int
    text: str
    conf: float
    x: float
    y: float
    w: float
    h: float


Ocr = Callable[[bytes], list[Line]]  # blocking; runs in a thread
Vlm = Callable[[bytes, list[Line], str], Awaitable[dict]]

PROMPT = """You are reading a photo of an Indian freight Lorry Receipt (LR) / Proof of Delivery (POD) signed at the consignee's gate.
Text may be English, Hindi or Marathi, printed or handwritten. A text reader already read these lines (id: text):

{lines}

Answer ONLY with JSON. Rules:
- is_document: false if this is not a transport receipt / POD paper.
- readable: false if blur, darkness, glare or cropping make the key fields unreadable.
- lr_no: the LR / consignment number as printed (expected: "{expected}"). null if not visible. Never invent it.
- lr_lines: ids of the lines above that hold it.
- stamp_present: a company / consignee rubber stamp or seal is on the receiving block. stamp_box: [x1,y1,x2,y2] around it on the photo, each 0 to 1000 (left, top, right, bottom). null if none.
- signature_present: true if there is ANY handwritten pen mark by the receiver in the receiving block: a signature, initials, a squiggle or a scribble, even if you cannot read it or it looks crude. Printed text and the round stamp are not signatures. signature_box: the same kind of box around it. null if none.
- delivery_date: date of receipt as yyyy-mm-dd, null if not visible. date_lines: ids of its lines.
- quantity_received: as written (e.g. "54 cartons"), null if not visible. quantity_lines: ids.
- remarks: any handwritten remark, word for word, null if none. remarks_lines: ids.
- shortage_or_damage: true if the remarks mention shortage, short, damage, leakage, broken, wet, torn (or the Hindi/Marathi words).
- confidence: 0 to 1 for the whole answer; lower when handwriting is unclear.
- issues: short English phrases for anything wrong (for example "stamp cut off").
Never guess something you cannot see. Use only ids from the list."""

SCHEMA = {
    "type": "object",
    "properties": {
        "is_document": {"type": "boolean"}, "readable": {"type": "boolean"},
        "lr_no": {"type": ["string", "null"]}, "lr_lines": {"type": "array", "items": {"type": "integer"}},
        "stamp_present": {"type": "boolean"}, "stamp_box": {"type": ["array", "null"], "items": {"type": "number"}},
        "signature_present": {"type": "boolean"}, "signature_box": {"type": ["array", "null"], "items": {"type": "number"}},
        "delivery_date": {"type": ["string", "null"]}, "date_lines": {"type": "array", "items": {"type": "integer"}},
        "quantity_received": {"type": ["string", "null"]}, "quantity_lines": {"type": "array", "items": {"type": "integer"}},
        "remarks": {"type": ["string", "null"]}, "remarks_lines": {"type": "array", "items": {"type": "integer"}},
        "shortage_or_damage": {"type": "boolean"}, "confidence": {"type": "number"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["is_document", "readable", "stamp_present", "signature_present", "shortage_or_damage", "confidence"],
}


# ------------------------------------------------------------------ pictures

def prepare(image: bytes) -> Image.Image:
    """Upright (the phone's rotation flag applied), RGB, not larger than OCR needs. Boxes are measured on this, as fractions."""
    with Image.open(io.BytesIO(image)) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE))
    return im


def jpeg(im: Image.Image) -> bytes:
    out = io.BytesIO()
    im.save(out, "JPEG", quality=90)
    return out.getvalue()


# ------------------------------------------------------------------ OCR (PaddleOCR)

class PaddleReader:
    """Loads once, on first use (a few seconds), and is reused. One recogniser per language pack."""

    MOBILE_REC: ClassVar[dict[str, str]] = {"en": "PP-OCRv5_mobile_rec", "devanagari": "devanagari_PP-OCRv5_mobile_rec"}

    def __init__(self, langs: str, models: str = "mobile") -> None:
        self._langs = [x.strip() for x in langs.split(",") if x.strip()] or ["en"]
        self._light = models == "mobile"  # light models: about 3x faster on a CPU, a little less exact than the "server" ones
        self._engines: dict[str, object] = {}

    def _engine(self, lang: str):
        if lang not in self._engines:
            try:
                from paddleocr import PaddleOCR
            except ImportError as e:
                raise ProviderError("local OCR is not installed (uv sync --extra local-ai)") from e
            # enable_mkldnn=False: Paddle 3's CPU acceleration crashes on some models ("ConvertPirAttribute2RuntimeAttribute")
            kw: dict = {"use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": False, "enable_mkldnn": False}
            if self._light and lang in self.MOBILE_REC:
                kw |= {"text_detection_model_name": "PP-OCRv5_mobile_det", "text_recognition_model_name": self.MOBILE_REC[lang]}
            else:
                kw["lang"] = lang
            self._engines[lang] = PaddleOCR(**kw)
        return self._engines[lang]

    def __call__(self, image: bytes) -> list[Line]:
        import numpy as np

        im = prepare(image)
        arr = np.array(im)[:, :, ::-1]  # PaddleOCR expects BGR
        W, H = im.size
        found: list[tuple[str, float, tuple[float, float, float, float]]] = []
        for lang in self._langs:
            for res in self._engine(lang).predict(arr):
                texts, scores, polys = res["rec_texts"], res["rec_scores"], res["rec_polys"]
                for text, score, poly in zip(texts, scores, polys, strict=False):
                    if not str(text).strip():
                        continue
                    xs, ys = [float(p[0]) for p in poly], [float(p[1]) for p in poly]
                    x0, y0, x1, y1 = max(0.0, min(xs) / W), max(0.0, min(ys) / H), min(1.0, max(xs) / W), min(1.0, max(ys) / H)
                    found.append((str(text).strip(), float(score), (x0, y0, x1 - x0, y1 - y0)))
        found = _drop_overlaps(found)
        found.sort(key=lambda f: (round(f[2][1] * 40), f[2][0]))  # top to bottom, then left to right
        return [Line(i, t, c, *b) for i, (t, c, b) in enumerate(found)]


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ix = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _drop_overlaps(found: list[tuple[str, float, tuple[float, float, float, float]]]) -> list[tuple[str, float, tuple[float, float, float, float]]]:
    """Two language packs read the same words twice; keep the more confident reading of each place."""
    keep: list[tuple[str, float, tuple[float, float, float, float]]] = []
    for item in sorted(found, key=lambda f: -f[1]):
        if all(_iou(item[2], k[2]) < 0.5 for k in keep):
            keep.append(item)
    return keep


# ------------------------------------------------------------------ the vision model (Ollama)

def ollama_vlm(url: str, model: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None) -> Vlm:
    async def ask(image: bytes, lines: list[Line], expected: str) -> dict:
        listing = "\n".join(f"{ln.id}: {ln.text}" for ln in lines) or "(no text was found)"
        body = {
            "model": model, "stream": False, "format": SCHEMA, "think": False, "options": {"temperature": 0},
            "messages": [{"role": "user", "content": PROMPT.format(lines=listing, expected=expected),
                          "images": [base64.b64encode(jpeg(prepare(image))).decode()]}],
        }
        try:
            async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as http:
                res = await http.post(f"{url.rstrip('/')}/api/chat", json=body)
                if res.status_code == 400:  # a model without a "thinking" switch refuses the field: ask again without it
                    body.pop("think")
                    res = await http.post(f"{url.rstrip('/')}/api/chat", json=body)
            res.raise_for_status()
            msg = res.json()["message"]
            # Some Ollama versions put the structured answer in "thinking" for Qwen3-VL even with thinking switched off.
            return json.loads(msg.get("content") or msg.get("thinking") or "")
        except httpx.ConnectError as e:
            raise ProviderError("local model is not running (start Ollama)") from e
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"ollama http {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"ollama error: {type(e).__name__}") from e
        except (KeyError, ValueError) as e:
            raise ProviderError(f"local model returned unusable output: {type(e).__name__}") from e

    return ask


SIGN_QUESTION = ("Look at the receiving block at the bottom of this delivery receipt. Is there a handwritten pen mark (signature, initials or "
                 "scribble) made by a person? Printed text and the round stamp do not count. Answer JSON: "
                 '{"signature_present": true or false, "signature_box": [left, top, right, bottom] each 0 to 1000, or null}')
SIGN_SCHEMA = {"type": "object", "properties": {"signature_present": {"type": "boolean"}, "signature_box": {"type": ["array", "null"], "items": {"type": "number"}}},
               "required": ["signature_present"]}

Sign = Callable[[bytes], Awaitable[dict]]


def ollama_signature(url: str, model: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None) -> Sign:
    """A second, narrow look for the receiver's pen mark. This model misses crude scribbles unless it thinks first, so this question
    runs with thinking on (and a generous length cap). It only runs when the first pass found none, so a clear signature costs nothing extra."""
    async def ask(image: bytes) -> dict:
        body = {"model": model, "stream": False, "format": SIGN_SCHEMA, "think": True, "options": {"temperature": 0, "num_predict": 3500},
                "messages": [{"role": "user", "content": SIGN_QUESTION, "images": [base64.b64encode(jpeg(prepare(image))).decode()]}]}
        try:
            async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as http:
                res = await http.post(f"{url.rstrip('/')}/api/chat", json=body)
            res.raise_for_status()
            msg = res.json()["message"]
            return json.loads(msg.get("content") or "")
        except (httpx.HTTPError, KeyError, ValueError):
            return {}  # no second opinion: the first pass's "none found" stands (the safe side)

    return ask


# ------------------------------------------------------------------ checking the model against the text

def _key(s: str) -> str:
    """Compare LR numbers the way people mean them: no case, no spaces or dashes, and the usual OCR mix-ups (O and 0, I and 1) removed."""
    return re.sub(r"[^A-Z0-9]", "", s.upper()).replace("O", "0").replace("I", "1").replace("L", "1")


def _contains(hay: str, needle: str) -> bool:
    if not needle:
        return False
    if needle in hay:
        return True
    n = len(needle)
    return n >= 5 and any(difflib.SequenceMatcher(None, hay[i:i + n], needle).ratio() >= 0.88 for i in range(max(1, len(hay) - n + 1)))


def _union(lines: list[Line]) -> tuple[float, float, float, float]:
    x0, y0 = min(ln.x for ln in lines), min(ln.y for ln in lines)
    x1, y1 = max(ln.x + ln.w for ln in lines), max(ln.y + ln.h for ln in lines)
    return x0, y0, x1 - x0, y1 - y0


def _pick(ids: object, by_id: dict[int, Line]) -> list[Line]:
    return [by_id[i] for i in (ids if isinstance(ids, list) else []) if isinstance(i, int) and i in by_id]


def _box_from_model(coords: object, field: str, conf: float) -> Box | None:
    """The model gives [left, top, right, bottom] on a 0 to 1000 scale. Anything else, or an empty box, is thrown away."""
    if not (isinstance(coords, list) and len(coords) == 4 and all(isinstance(c, int | float) for c in coords)):
        return None
    x0, y0, x1, y1 = (min(1.0, max(0.0, float(c) / 1000)) for c in coords)
    if x1 - x0 < 0.01 or y1 - y0 < 0.01:
        return None
    return Box(field=field, x=x0, y=y0, w=x1 - x0, h=y1 - y0, conf=conf, source="vlm")


def merge(raw: dict, lines: list[Line], expected_lr_no: str) -> PodExtraction:
    by_id = {ln.id: ln for ln in lines}
    boxes: list[Box] = []
    issues = [str(i)[:120] for i in raw.get("issues") or [] if isinstance(i, str)][:6]
    conf = float(min(1.0, max(0.0, raw.get("confidence") or 0)))
    seen_text = _key(" ".join(ln.text for ln in lines))

    # LR number: believed only when OCR can see it on the paper.
    want = _key(expected_lr_no)
    said = raw.get("lr_no") if isinstance(raw.get("lr_no"), str) and raw.get("lr_no") else None
    lr_no, hit = said, None
    for ln in lines:
        if _contains(_key(ln.text), want):
            hit = ln
            break
    if hit is not None:  # the number is printed on this paper: that beats whatever the model made of it
        lr_no = expected_lr_no
        boxes.append(Box(field="lr_no", x=hit.x, y=hit.y, w=hit.w, h=hit.h, text=hit.text, conf=hit.conf, source="ocr"))
    elif said is not None:
        near = _pick(raw.get("lr_lines"), by_id)
        if near and _contains(_key(" ".join(ln.text for ln in near)), _key(said)):
            x, y, w, h = _union(near)
            boxes.append(Box(field="lr_no", x=x, y=y, w=w, h=h, text=" ".join(ln.text for ln in near), conf=min(ln.conf for ln in near), source="ocr"))
        if want and _key(said) == want and not _contains(seen_text, want):
            conf = min(conf, 0.6)  # the model "read" the number that was expected, but the text reader never saw it: do not trust
            issues.append("LR number not confirmed by text reader")

    def checked(field: str, value: object, ids_key: str, ok: Callable[[str, str], bool]) -> str | None:
        if not isinstance(value, str) or not value.strip():
            return None
        near = _pick(raw.get(ids_key), by_id)
        joined = " ".join(ln.text for ln in near)
        if near and ok(joined, value):
            x, y, w, h = _union(near)
            boxes.append(Box(field=field, x=x, y=y, w=w, h=h, text=joined, conf=min(ln.conf for ln in near), source="ocr"))
        return value.strip()

    def digits(a: str, b: str) -> bool:
        return bool(set(re.findall(r"\d+", a)) & set(re.findall(r"\d+", b))) or not re.findall(r"\d", b)

    def words(a: str, b: str) -> bool:
        wa, wb = set(re.findall(r"\w+", a.lower())), set(re.findall(r"\w+", b.lower()))
        return not wb or len(wa & wb) / len(wb) >= 0.4

    delivery = checked("delivery_date", raw.get("delivery_date"), "date_lines", lambda _a, _b: True)
    if delivery:
        try:
            date.fromisoformat(delivery)
        except ValueError:
            issues.append("delivery date not understood")
            delivery = None
            boxes = [b for b in boxes if b.field != "delivery_date"]
    qty = checked("quantity_received", raw.get("quantity_received"), "quantity_lines", digits)
    remarks = checked("remarks", raw.get("remarks"), "remarks_lines", words)

    stamp = bool(raw.get("stamp_present"))
    sign = bool(raw.get("signature_present"))
    for present, key, field in ((stamp, "stamp_box", "stamp"), (sign, "signature_box", "signature")):
        if present and (b := _box_from_model(raw.get(key), field, conf)):
            boxes.append(b)

    readable = bool(raw.get("readable")) and len(lines) >= 3  # almost no text found: nothing for a person to rely on either
    if len(lines) < 3 and "little text found" not in issues:
        issues.append("little text found")
    return PodExtraction(
        is_document=bool(raw.get("is_document")), readable=readable, lr_no=lr_no, consignee_stamp_present=stamp,
        signature_present=sign, delivery_date=delivery, quantity_received=qty, remarks=remarks,
        shortage_or_damage=bool(raw.get("shortage_or_damage")), confidence=conf, issues=issues, boxes=boxes,
    )


# ------------------------------------------------------------------ provider

class LocalProvider:
    name = "local"

    def __init__(self, url: str, model: str, timeout_s: float, langs: str = "en", ocr_models: str = "mobile", *, ocr: Ocr | None = None, vlm: Vlm | None = None,
                 sign: Sign | None = None) -> None:
        self._ocr = ocr or PaddleReader(langs, ocr_models)
        self._vlm = vlm or ollama_vlm(url, model, timeout_s)
        self._sign = sign or (ollama_signature(url, model, timeout_s) if vlm is None else None)

    async def extract(self, image: bytes, mime: str, expected_lr_no: str) -> PodExtraction:
        try:
            lines = await asyncio.to_thread(self._ocr, image)
        except ProviderError:
            raise
        except Exception as e:  # the OCR library raises many kinds of error
            raise ProviderError(f"local OCR failed: {type(e).__name__}") from e
        raw = await self._vlm(image, lines, expected_lr_no)
        if self._sign and raw.get("is_document") and not raw.get("signature_present"):
            second = await self._sign(image)
            if second.get("signature_present") is True:
                raw = {**raw, "signature_present": True, "signature_box": second.get("signature_box")}
        return merge(raw, lines, expected_lr_no)
