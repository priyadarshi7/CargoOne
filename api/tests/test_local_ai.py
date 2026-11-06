"""The local reader's checking logic: what the vision model says is only kept when the text reader backs it up."""
import io
import json

import httpx
import pytest
from PIL import Image

from app.ai.base import ProviderError
from app.ai.providers.local import Line, LocalProvider, merge, ollama_vlm, prepare

LINES = [
    Line(0, "LORRY RECEIPT", 0.97, 0.10, 0.05, 0.50, 0.04),
    Line(1, "LR No: LR-88134", 0.95, 0.10, 0.12, 0.40, 0.04),
    Line(2, "Received 54 cartons in good order", 0.92, 0.10, 0.50, 0.60, 0.04),
    Line(3, "Date 12/11/2026", 0.90, 0.10, 0.60, 0.30, 0.04),
    Line(4, "short by 6 cartons", 0.80, 0.10, 0.70, 0.40, 0.04),
]


def raw(**kw) -> dict:
    base = {"is_document": True, "readable": True, "lr_no": "LR-88134", "lr_lines": [1], "stamp_present": True,
            "stamp_box": [600, 750, 900, 900], "signature_present": True, "signature_box": [100, 780, 400, 900],
            "delivery_date": "2026-11-12", "date_lines": [3], "quantity_received": "54 cartons", "quantity_lines": [2],
            "remarks": "short by 6 cartons", "remarks_lines": [4], "shortage_or_damage": True, "confidence": 0.9, "issues": []}
    return {**base, **kw}


def by_field(res) -> dict:
    return {b.field: b for b in res.boxes}


def test_every_checked_field_gets_a_box_with_its_text() -> None:
    res = merge(raw(), LINES, "LR-88134")
    boxes = by_field(res)
    assert set(boxes) == {"lr_no", "delivery_date", "quantity_received", "remarks", "stamp", "signature"}
    assert boxes["lr_no"].source == "ocr" and boxes["lr_no"].text == "LR No: LR-88134"
    assert (boxes["lr_no"].x, boxes["lr_no"].y) == (0.10, 0.12)
    assert boxes["stamp"].source == "vlm" and boxes["stamp"].x == pytest.approx(0.6) and boxes["stamp"].w == pytest.approx(0.3)
    assert res.lr_no == "LR-88134" and res.confidence == 0.9 and res.readable


def test_the_expected_lr_number_must_be_seen_by_the_text_reader() -> None:
    lines = [ln for ln in LINES if ln.id != 1]  # OCR never read the LR line
    res = merge(raw(), lines, "LR-88134")
    assert "lr_no" not in by_field(res)
    assert res.confidence <= 0.6 and "LR number not confirmed by text reader" in res.issues


def test_a_misread_lr_number_is_repaired_from_the_text_but_a_wrong_one_stays_wrong() -> None:
    fixed = merge(raw(lr_no="LR-B8I34"), LINES, "LR-88134")
    assert fixed.lr_no == "LR-88134"  # OCR saw the real number on the paper
    wrong = [Line(1, "LR No: LR-99999", 0.95, 0.1, 0.12, 0.4, 0.04), *LINES[2:]]
    res = merge(raw(lr_no="LR-99999", lr_lines=[1]), [LINES[0], *wrong], "LR-88134")
    assert res.lr_no == "LR-99999"  # different paper: the decision step will ask for a retake


def test_ocr_confusions_do_not_break_the_match() -> None:
    lines = [Line(0, "LR No: LR-88I34", 0.9, 0, 0, 0.5, 0.1), *LINES[2:]]  # an I read for the 1
    res = merge(raw(lr_lines=[0], lr_no="LR-88I34"), lines, "LR-88134")
    assert res.lr_no == "LR-88134" and "lr_no" in by_field(res)


def test_claims_with_no_support_in_the_text_get_no_box() -> None:
    res = merge(raw(quantity_received="900 bags", remarks="all fine today", remarks_lines=[2], quantity_lines=[2]), LINES, "LR-88134")
    boxes = by_field(res)
    assert "quantity_received" not in boxes and "remarks" not in boxes  # lines named by the model do not contain those words
    assert res.quantity_received == "900 bags"  # still reported: a person sees the photo and decides


def test_bad_ids_and_bad_boxes_are_ignored_not_crashed_on() -> None:
    res = merge(raw(date_lines=[99, "x"], stamp_box=[5, 5], signature_box=[400, 400, 400, 400]), LINES, "LR-88134")
    boxes = by_field(res)
    assert "delivery_date" not in boxes and "stamp" not in boxes and "signature" not in boxes


def test_an_impossible_date_is_dropped_with_a_note() -> None:
    res = merge(raw(delivery_date="2026-13-45"), LINES, "LR-88134")
    assert res.delivery_date is None and "delivery date not understood" in res.issues and "delivery_date" not in by_field(res)


def test_no_stamp_means_no_stamp_box() -> None:
    res = merge(raw(stamp_present=False, stamp_box=[600, 750, 900, 900]), LINES, "LR-88134")
    assert not res.consignee_stamp_present and "stamp" not in by_field(res)


def test_almost_no_text_makes_the_photo_unreadable() -> None:
    res = merge(raw(), LINES[:2], "LR-88134")
    assert not res.readable and "little text found" in res.issues


def png(size=(200, 100), orientation: int | None = None) -> bytes:
    out = io.BytesIO()
    im = Image.new("RGB", size, "white")
    exif = Image.Exif()
    if orientation:
        exif[0x0112] = orientation
    im.save(out, "JPEG", exif=exif)
    return out.getvalue()


def test_a_sideways_phone_photo_is_stood_upright_before_reading() -> None:
    assert prepare(png((200, 100), orientation=6)).size == (100, 200)
    assert prepare(png((3000, 2000))).size[0] == 1600


async def test_the_provider_runs_ocr_then_the_model_then_checks() -> None:
    async def vlm(image, lines, expected):
        assert lines == LINES and expected == "LR-88134"
        return raw()

    res = await LocalProvider("", "", 1, ocr=lambda _: LINES, vlm=vlm).extract(png(), "image/jpeg", "LR-88134")
    assert res.lr_no == "LR-88134" and len(res.boxes) == 6


async def test_ocr_crash_becomes_a_provider_error_so_the_chain_can_fall_back() -> None:
    def boom(_):
        raise RuntimeError("gpu on fire")

    with pytest.raises(ProviderError, match="local OCR failed"):
        await LocalProvider("", "", 1, ocr=boom, vlm=None).extract(png(), "image/jpeg", "LR-1")


def ollama(handler):
    return ollama_vlm("http://ollama.test", "m", 5, transport=httpx.MockTransport(handler))


async def test_ollama_answer_is_read_and_a_missing_server_is_a_clear_error() -> None:
    seen = []

    def ok(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": json.dumps(raw())}})

    assert (await ollama(ok)(png(), LINES, "LR-88134"))["lr_no"] == "LR-88134"
    assert seen[0]["options"]["temperature"] == 0 and "1: LR No: LR-88134" in seen[0]["messages"][0]["content"]

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError, match="not running"):
        await ollama(down)(png(), LINES, "LR-1")


async def test_a_model_without_a_thinking_switch_is_asked_again_without_it() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append("think" in body)
        if "think" in body:
            return httpx.Response(400, json={"error": "does not support thinking"})
        return httpx.Response(200, json={"message": {"content": json.dumps(raw())}})

    assert (await ollama(handler)(png(), LINES, "LR-88134"))["is_document"] is True
    assert calls == [True, False]


async def test_garbage_from_the_model_is_a_provider_error() -> None:
    bad = lambda r: httpx.Response(200, json={"message": {"content": "not json"}})
    with pytest.raises(ProviderError, match="unusable"):
        await ollama(bad)(png(), LINES, "LR-1")


def test_the_ocr_engine_reads_one_photo_at_a_time() -> None:
    """Starting or using the GPU engine from two threads at once crashed the whole process, so access is serialised."""
    import threading
    import time
    from types import SimpleNamespace

    import numpy as np

    from app.ai.providers.local import RapidReader

    inside = 0
    most = 0
    guard = threading.Lock()

    def fake_engine(_img):
        nonlocal inside, most
        with guard:
            inside += 1
            most = max(most, inside)
        time.sleep(0.05)
        with guard:
            inside -= 1
        return SimpleNamespace(txts=("LR No: LR-1",), scores=(0.99,), boxes=np.array([[[10, 10], [90, 10], [90, 30], [10, 30]]]))

    reader = RapidReader("en")
    reader._engine = fake_engine
    reader._get = lambda: fake_engine  # skip loading the real models
    photo = png()
    threads = [threading.Thread(target=reader, args=(photo,)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert most == 1
    lines = reader(photo)
    assert lines[0].text == "LR No: LR-1" and 0 <= lines[0].x < 1 and lines[0].w > 0


FORM = [
    Line(0, "LRNO:LR-88134", 0.95, 0.60, 0.06, 0.30, 0.03),
    Line(1, "Remarks / Special Instructions:", 0.95, 0.01, 0.60, 0.35, 0.02),
    Line(2, "Perfect shipment", 0.90, 0.02, 0.62, 0.20, 0.03),
    Line(3, "Other Charges:", 0.95, 0.48, 0.60, 0.20, 0.02),
    Line(4, "Terms & Conditions", 0.90, 0.00, 0.78, 0.30, 0.02),
]


def test_remarks_the_model_skipped_are_read_from_under_their_label() -> None:
    res = merge(raw(remarks=None, remarks_lines=[], shortage_or_damage=False), FORM, "LR-88134")
    assert res.remarks == "Perfect shipment" and not res.shortage_or_damage
    assert by_field(res)["remarks"].source == "ocr" and by_field(res)["remarks"].y == pytest.approx(0.62)
    worse = FORM[:2] + [Line(2, "short by 6 cartons", 0.9, 0.02, 0.62, 0.2, 0.03)]
    assert merge(raw(remarks=None, remarks_lines=[], shortage_or_damage=False), worse, "LR-88134").shortage_or_damage  # the words decide, not only the model
    assert merge(raw(remarks=None, remarks_lines=[]), LINES, "LR-88134").remarks is None  # no label, nothing invented


async def test_a_stamp_and_signature_without_a_place_are_looked_for_again() -> None:
    async def vlm(image, lines, expected):
        return raw(stamp_box=None, signature_box=None, remarks=None, remarks_lines=[])

    asked: list[str] = []

    async def locate(image, what):
        asked.append(what)
        return {"found": True, "box": [480, 800, 630, 900]} if what == "stamp" else {"found": False, "box": None}

    res = await LocalProvider("", "", 1, ocr=lambda _: LINES, vlm=vlm, locate=locate).extract(png(), "image/jpeg", "LR-88134")
    assert asked == ["stamp", "signature"] and by_field(res)["stamp"].x == pytest.approx(0.48)
    assert "signature" not in by_field(res) and res.signature_present  # present is still the model's call; only the box is missing
