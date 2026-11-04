"""Synthetic POD image generator for development and evaluation (no real PODs exist yet).

Draws a fake LR/POD with optional stamp, signature, handwritten-style remark, blur and glare, and embeds the
ground-truth label in PNG metadata so the mock provider and evaluation harness can use it.
ALL TEXT IS FAKE. Run: uv run python -m app.devtools.synthetic_pod out_dir
"""
import io
import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.ai.base import PodExtraction
from app.ai.providers.mock import LABEL_KEY

W, H = 900, 1200


@dataclass(frozen=True)
class Scenario:
    name: str
    stamp: bool = True
    signature: bool = True
    remark: str | None = None
    blur: float = 0
    wrong_lr: bool = False
    not_document: bool = False
    confidence: float = 0.95


SCENARIOS = {s.name: s for s in [
    Scenario("clean"),
    Scenario("no_stamp", stamp=False),
    Scenario("no_signature", signature=False),
    Scenario("blurry", blur=6, confidence=0.4),
    Scenario("shortage", remark="Short by 6 cartons"),
    Scenario("damage", remark="2 bags torn / damaged"),
    Scenario("wrong_lr", wrong_lr=True),
    Scenario("low_confidence", confidence=0.6),
    Scenario("not_a_pod", not_document=True, stamp=False, signature=False, confidence=0.9),
]}


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size)


def truth_for(scenario: Scenario, lr_no: str) -> PodExtraction:
    """What a perfect reader would extract from this scenario's image (also used as a scripted mock answer)."""
    shown_lr = "LR-00000" if scenario.wrong_lr else lr_no
    return PodExtraction(
        is_document=not scenario.not_document,
        readable=scenario.blur < 3,
        lr_no=None if scenario.not_document else shown_lr,
        consignee_stamp_present=scenario.stamp and not scenario.not_document,
        signature_present=scenario.signature and not scenario.not_document,
        delivery_date=None if scenario.not_document else "2026-11-03",
        quantity_received=None if scenario.not_document else "240 bags",
        remarks=scenario.remark,
        shortage_or_damage=scenario.remark is not None,
        confidence=scenario.confidence,
    )


def render(scenario: Scenario, lr_no: str, seed: int = 0) -> bytes:
    rnd = random.Random(seed)
    img = Image.new("RGB", (W, H), (250, 248, 240))
    d = ImageDraw.Draw(img)
    shown_lr = "LR-00000" if scenario.wrong_lr else lr_no

    if scenario.not_document:
        for _ in range(40):
            x, y = rnd.randint(0, W), rnd.randint(0, H)
            d.ellipse([x, y, x + 120, y + 120], fill=tuple(rnd.randint(60, 200) for _ in range(3)))
    else:
        d.text((40, 40), "DEMO TRANSPORT CO. - LORRY RECEIPT", fill=(20, 20, 20), font=_font(34))
        d.text((40, 110), f"LR No: {shown_lr}", fill=(20, 20, 20), font=_font(30))
        d.text((40, 160), "Consignor: Demo Consignor   Consignee: Demo Consignee Pvt Ltd", fill=(40, 40, 40), font=_font(22))
        d.text((40, 210), "Goods: 240 bags (cement)   Vehicle: MH20 XX 0000", fill=(40, 40, 40), font=_font(22))
        d.rectangle([40, 700, W - 40, 1100], outline=(80, 80, 80), width=3)
        d.text((60, 715), "RECEIVED IN GOOD ORDER / CONDITION", fill=(60, 60, 60), font=_font(20))
        d.text((60, 760), "Date: 2026-11-03", fill=(30, 30, 90), font=_font(28))
        if scenario.remark:
            d.text((60, 820), f"Remark: {scenario.remark}", fill=(150, 20, 20), font=_font(28))
        if scenario.stamp:
            d.ellipse([520, 780, 800, 1060], outline=(30, 60, 170), width=6)
            d.text((565, 905), "DEMO CONSIGNEE", fill=(30, 60, 170), font=_font(26))
        if scenario.signature:
            pts = [(80 + i * 14, 1020 + rnd.randint(-18, 18)) for i in range(18)]
            d.line(pts, fill=(10, 10, 10), width=4)
    if scenario.blur:
        img = img.filter(ImageFilter.GaussianBlur(scenario.blur))

    truth = truth_for(scenario, lr_no)
    from PIL.PngImagePlugin import PngInfo
    meta = PngInfo()
    meta.add_text(LABEL_KEY, json.dumps(truth.model_dump()))
    buf = io.BytesIO()
    img.save(buf, "PNG", pnginfo=meta)
    return buf.getvalue()


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "synthetic_pods")
    out.mkdir(parents=True, exist_ok=True)
    for i, sc in enumerate(SCENARIOS.values()):
        (out / f"{sc.name}.png").write_bytes(render(sc, "LR-88120", seed=i))
    print(f"Wrote {len(SCENARIOS)} images to {out}")
