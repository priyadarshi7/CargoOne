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
import logging
import re
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import ClassVar

import httpx
from PIL import Image, ImageOps

from app.ai.base import Box, PodExtraction, PodItem, ProviderError

log = logging.getLogger("cargoone.ai")

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
- quantity_received: what the receiver wrote as received, as written (e.g. "54 cartons"; for several goods "Cement 2.5 t, Sand 1.5 t"), null if not visible. quantity_lines: ids. Not the booked quantity printed above. In the goods table a row reads "<no.> <good> <printed packages> <printed weight> <what the receiver wrote>": the receiver's handwriting is what comes AFTER the two printed numbers (for "1 PPC Cement 50 kg bags 50 2.5 40 bags" it is "40 bags"); the Total row works the same ("Total 50 2.5 Total received: 40 bags" means 40 bags).
- items: when the receiver wrote more than one good, one {{"name","quantity","unit"}} per line (quantity a number, unit as written); empty list otherwise.
- total_quantity: the total the receiver wrote (e.g. "4 t") only if one is written, else null. Never add lines up yourself.
- remarks: any handwritten remark, word for word, null if none. remarks_lines: ids.
- shortage_or_damage: true if the remarks mention shortage, short, damage, leakage, broken, wet, torn (or the Hindi/Marathi words).
- confidence: 0 to 1 for the whole answer; lower when handwriting is unclear.
- issues: short English phrases for anything wrong (for example "stamp cut off").
Never guess something you cannot see. Use only ids from the list.
A black strip at the very bottom of the photo that reads "CargoOne" with a time and map position was added by the phone app: it is not part of the paper. Ignore it (it is not a stamp, a signature, remarks or the delivery date)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "is_document": {"type": "boolean"}, "readable": {"type": "boolean"},
        "lr_no": {"type": ["string", "null"]}, "lr_lines": {"type": "array", "items": {"type": "integer"}},
        "stamp_present": {"type": "boolean"}, "stamp_box": {"type": ["array", "null"], "items": {"type": "number"}},
        "signature_present": {"type": "boolean"}, "signature_box": {"type": ["array", "null"], "items": {"type": "number"}},
        "delivery_date": {"type": ["string", "null"]}, "date_lines": {"type": "array", "items": {"type": "integer"}},
        "quantity_received": {"type": ["string", "null"]}, "quantity_lines": {"type": "array", "items": {"type": "integer"}},
        "items": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": ["string", "null"]}, "quantity": {"type": ["number", "null"]}, "unit": {"type": ["string", "null"]}}}},
        "total_quantity": {"type": ["string", "null"]},
        "remarks": {"type": ["string", "null"]}, "remarks_lines": {"type": "array", "items": {"type": "integer"}},
        "shortage_or_damage": {"type": "boolean"}, "confidence": {"type": "number"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
    # Every field is asked for. With only the first six required, a larger model answered the minimum and left the quantity, the date and the
    # remarks out (null) even when the text was plainly on the page; the optional ones are nullable, so "not there" is still an honest answer.
    "required": ["is_document", "readable", "lr_no", "stamp_present", "signature_present", "delivery_date", "quantity_received", "items", "total_quantity",
                 "remarks", "shortage_or_damage", "confidence"],
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
        self._lock = threading.Lock()  # one photo at a time (the engines are not safe to start or use from two threads at once)

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
            with self._lock:
                results = list(self._engine(lang).predict(arr))
            for res in results:
                texts, scores, polys = res["rec_texts"], res["rec_scores"], res["rec_polys"]
                for text, score, poly in zip(texts, scores, polys, strict=False):
                    if not str(text).strip():
                        continue
                    xs, ys = [float(p[0]) for p in poly], [float(p[1]) for p in poly]
                    x0, y0, x1, y1 = max(0.0, min(xs) / W), max(0.0, min(ys) / H), min(1.0, max(xs) / W), min(1.0, max(ys) / H)
                    found.append((str(text).strip(), float(score), (x0, y0, x1 - x0, y1 - y0)))
        return _lines(found)


def _lines(found: list[tuple[str, float, tuple[float, float, float, float]]]) -> list[Line]:
    """(text, confidence, (x, y, w, h)) in reading order, one reading per place."""
    found = _drop_overlaps(found)
    found.sort(key=lambda f: (round(f[2][1] * 40), f[2][0]))  # top to bottom, then left to right
    return [Line(i, t, c, *b) for i, (t, c, b) in enumerate(found)]


class OllamaOcr:
    """A document-reading model run through Ollama as the text reader (glm-ocr). It returns plain text, not boxes, so each line gets the
    slice of the page it would fill if the text were spread evenly: enough for the answering model to cite lines, not a real position."""

    def __init__(self, url: str, model: str, timeout_s: float) -> None:
        self._url, self._model, self._timeout = url.rstrip("/"), model, timeout_s

    def __call__(self, image: bytes) -> list[Line]:
        body = {"model": self._model, "stream": False, "keep_alive": "30m", "options": {"temperature": 0},
                "messages": [{"role": "user", "content": "Text Recognition:", "images": [base64.b64encode(jpeg(prepare(image))).decode()]}]}
        try:
            res = httpx.post(f"{self._url}/api/chat", json=body, timeout=self._timeout)
            res.raise_for_status()
            text = res.json()["message"]["content"]
        except httpx.ConnectError as e:
            raise ProviderError("local model is not running (start Ollama)") from e
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"ollama http {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"ollama error: {type(e).__name__}") from e
        except (KeyError, ValueError) as e:
            raise ProviderError(f"local OCR returned unusable output: {type(e).__name__}") from e
        rows = [re.sub(r"\s*\|\s*", " ", ln).strip(" #*-") for ln in text.splitlines()]
        rows = [r for r in rows if r and not re.fullmatch(r"[-:| ]+", r)]  # drop empty lines and markdown table rules
        n = max(len(rows), 1)
        return [Line(id=i, text=r, conf=0.9, x=0.0, y=i / n, w=1.0, h=1 / n) for i, r in enumerate(rows)]


class RapidReader:
    """The same PaddleOCR text models, run through ONNX Runtime: about 30 times faster than PaddlePaddle on a CPU, and it uses the GPU
    (DirectML on Windows, so no CUDA setup) when there is one. Reads English print; for Devanagari use the paddle engine."""

    def __init__(self, langs: str) -> None:
        self._engine = None
        self._lock = threading.Lock()  # one photo at a time: starting or using the GPU engine from two threads at once crashed the process
        if "devanagari" in langs:
            log.warning("OCR_ENGINE=rapid reads English print only; set OCR_ENGINE=paddle to read Devanagari")

    def _get(self):
        if self._engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as e:
                raise ProviderError("local OCR is not installed (uv sync --extra local-ai)") from e
            try:
                self._engine = RapidOCR(params={"EngineConfig.onnxruntime.use_dml": True})  # the GPU, when onnxruntime has a way to reach it
            except Exception as e:  # noqa: BLE001
                log.warning("OCR on the GPU unavailable (%s): using the CPU", type(e).__name__)
                self._engine = RapidOCR(params={"EngineConfig.onnxruntime.use_dml": False})
        return self._engine

    def __call__(self, image: bytes) -> list[Line]:
        import numpy as np

        im = prepare(image)
        W, H = im.size
        with self._lock:
            out = self._get()(np.array(im)[:, :, ::-1])  # BGR, like the other reader
        if out.txts is None or out.boxes is None:
            return []
        found = []
        for text, score, poly in zip(out.txts, out.scores, out.boxes, strict=False):
            if not str(text).strip():
                continue
            xs, ys = [float(p[0]) for p in poly], [float(p[1]) for p in poly]
            x0, y0, x1, y1 = max(0.0, min(xs) / W), max(0.0, min(ys) / H), min(1.0, max(xs) / W), min(1.0, max(ys) / H)
            found.append((str(text).strip(), float(score), (x0, y0, x1 - x0, y1 - y0)))
        return _lines(found)


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
            "model": model, "stream": False, "format": SCHEMA, "think": False, "options": {"temperature": 0}, "keep_alive": "30m",
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


SIGN_QUESTION = ("Look ONLY at the box labelled \"Consignee signature, name and stamp\" (the receiver's box, bottom right of this delivery receipt). Is there a handwritten pen mark "
                 "(signature, initials or scribble) in it? Signatures in the \"Consignor signature\" and \"Driver signature\" boxes do not count, nor do printed text and the round stamp. Answer JSON: "
                 '{"signature_present": true or false, "signature_box": [left, top, right, bottom] each 0 to 1000, or null}')
SIGN_SCHEMA = {"type": "object", "properties": {"signature_present": {"type": "boolean"}, "signature_box": {"type": ["array", "null"], "items": {"type": "number"}}},
               "required": ["signature_present"]}

Sign = Callable[[bytes], Awaitable[dict]]


def ollama_signature(url: str, model: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None) -> Sign:
    """A second, narrow look for the receiver's pen mark. This model misses crude scribbles unless it thinks first, so this question
    runs with thinking on (and a generous length cap). It only runs when the first pass found none, so a clear signature costs nothing extra."""
    async def ask(image: bytes) -> dict:
        body = {"model": model, "stream": False, "format": SIGN_SCHEMA, "think": True, "options": {"temperature": 0, "num_predict": 3500}, "keep_alive": "30m",
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


LOCATE_SCHEMA = {"type": "object", "properties": {"found": {"type": "boolean"}, "box": {"type": ["array", "null"], "items": {"type": "number"}}}, "required": ["found", "box"]}
LOCATE = {
    "stamp": "Find the rubber stamp or seal (an ink stamp, often a frame with the word STAMP, initials or a company name) on this receipt.",
    "signature": "Find the handwritten signature in the box labelled \"Receiver's (Consignee) Signature\" at the bottom of this receipt, or the nearest pen signature to it.",
}

Locate = Callable[[bytes, str], Awaitable[dict]]


def ollama_locate(url: str, model: str, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None) -> Locate:
    """When the model says a stamp or signature is there but gives no place for it, ask only for the place. The answer is a box around
    it on a 0 to 1000 scale. The box is only for the person reviewing; whether the thing is present was already decided."""
    async def ask(image: bytes, what: str) -> dict:
        question = (f"{LOCATE[what]} Give a tight bounding box as [left, top, right, bottom], each 0 to 1000 relative to the whole picture. "
                    'JSON: {"found": true or false, "box": [...] or null}')
        body = {"model": model, "stream": False, "format": LOCATE_SCHEMA, "think": False, "options": {"temperature": 0}, "keep_alive": "30m",
                "messages": [{"role": "user", "content": question, "images": [base64.b64encode(jpeg(prepare(image))).decode()]}]}
        try:
            async with httpx.AsyncClient(timeout=timeout_s, transport=transport) as http:
                res = await http.post(f"{url.rstrip('/')}/api/chat", json=body)
            res.raise_for_status()
            msg = res.json()["message"]
            return json.loads(msg.get("content") or msg.get("thinking") or "")
        except (httpx.HTTPError, KeyError, ValueError):
            return {}  # no box: the photo is still judged on present / not present

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


PROBLEM_WORDS = re.compile(r"short|damag|leak|broken|wet|torn|missing|कम|टूट|खराब|लीक|कमी|तुट|फाट", re.IGNORECASE)


def remarks_from_text(lines: list[Line]) -> list[Line]:
    """The handwriting under the printed "Remarks" label, found from the text reader alone: the lines just below it, in its column,
    that are not themselves printed labels (those end in a colon)."""
    label = next((ln for ln in lines if "remark" in ln.text.lower()), None)
    if label is None:
        return []
    top, bottom = label.y + label.h * 0.5, label.y + 0.1
    found = [ln for ln in lines if ln is not label and top < ln.y <= bottom and ln.x < label.x + 0.45 and not ln.text.strip().endswith(":")
             and "special" not in ln.text.lower()]
    return found[:3]


def _text(v: object) -> str | None:
    return v.strip()[:60] or None if isinstance(v, str) else None


def _items(raw: object) -> list[PodItem]:
    """The model's per-good lines, kept only when they are well formed: a bad line is dropped, never guessed."""
    out: list[PodItem] = []
    for it in raw[:12] if isinstance(raw, list) else []:
        if not isinstance(it, dict):
            continue
        q = it.get("quantity")
        out.append(PodItem(name=_text(it.get("name")), quantity=float(q) if isinstance(q, (int, float)) and not isinstance(q, bool) and q >= 0 else None, unit=_text(it.get("unit"))))
    return out


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
    if remarks and not re.search(r"[^\W\d_]", remarks):  # only digits and dashes: the model copied the date written beside it, which is not a remark
        remarks = None
        boxes = [b for b in boxes if b.field != "remarks"]
    if not remarks and (under := remarks_from_text(lines)):  # the model skipped it, but the text is plainly there under the label
        remarks = " ".join(ln.text for ln in under)
        x, y, w, h = _union(under)
        boxes.append(Box(field="remarks", x=x, y=y, w=w, h=h, text=remarks, conf=min(ln.conf for ln in under), source="ocr"))
    shortage = bool(raw.get("shortage_or_damage")) or bool(remarks and PROBLEM_WORDS.search(remarks))

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
        signature_present=sign, delivery_date=delivery, quantity_received=qty, items=_items(raw.get("items")), total_quantity=_text(raw.get("total_quantity")), remarks=remarks,
        shortage_or_damage=shortage, confidence=conf, issues=issues, boxes=boxes,
    )


# ------------------------------------------------------------------ provider

class LocalProvider:
    name = "local"

    def __init__(self, url: str, model: str, timeout_s: float, langs: str = "en", ocr_models: str = "mobile", ocr_engine: str = "rapid", *, ocr: Ocr | None = None, vlm: Vlm | None = None,
                 sign: Sign | None = None, locate: Locate | None = None) -> None:
        self._ocr = ocr or (OllamaOcr(url, ocr_models, timeout_s) if ocr_engine == "glm" else RapidReader(langs) if ocr_engine == "rapid" else PaddleReader(langs, ocr_models))
        self._vlm = vlm or ollama_vlm(url, model, timeout_s)
        self._url, self._model = url, model
        self._sign = sign or (ollama_signature(url, model, timeout_s) if vlm is None else None)
        self._locate = locate or (ollama_locate(url, model, timeout_s) if vlm is None else None)

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
        if self._locate and raw.get("is_document"):
            for present, key, what in (("stamp_present", "stamp_box", "stamp"), ("signature_present", "signature_box", "signature")):
                if raw.get(present) and _box_from_model(raw.get(key), what, 0) is None:
                    got = await self._locate(image, what)
                    if got.get("found") is True:
                        raw = {**raw, key: got.get("box")}
        return merge(raw, lines, expected_lr_no)

    async def warm(self) -> None:
        """Load both models now, so the first real photo does not pay for it. Best effort: failure here changes nothing."""
        blank = io.BytesIO()
        Image.new("RGB", (320, 240), "white").save(blank, "JPEG")
        try:
            await asyncio.to_thread(self._ocr, blank.getvalue())
            async with httpx.AsyncClient(timeout=120) as http:  # no prompt: Ollama just loads the model and keeps it for 30 minutes
                await http.post(f"{self._url.rstrip('/')}/api/generate", json={"model": self._model, "keep_alive": "30m"})
        except Exception as e:  # noqa: BLE001
            log.warning("local AI warm-up skipped: %s", type(e).__name__)
