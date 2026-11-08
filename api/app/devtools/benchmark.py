"""Runs the POD reader over the photographed benchmark sheets and scores it against the answer key (docs/benchmark/answers.csv).

  .venv/Scripts/python -m app.devtools.benchmark --photos ../docs/benchmark/photos --provider local --label qwen3-vl-4b
  .venv/Scripts/python -m app.devtools.benchmark --photos ... --provider local --ollama-model llava:7b --label llava-7b

Results are written one file per model to docs/benchmark/results/<label>.json and are resumable (photos already done are skipped).
The office app's "AI benchmark" tab (ops, billing, MD) shows every run, so there is nothing to build afterwards. Nothing here touches the database or the app's storage.
"""
import argparse
import asyncio
import csv
import difflib
import json
import re
import statistics
import time
from dataclasses import dataclass
from pathlib import Path

from app.ai.base import PodExtraction, ProviderError
from app.ai.registry import build_provider
from app.config import get_settings
from app.pod.decision import _norm, decide

TODAY = "2026-11-08"  # the date written by hand on the sheets
KEY = Path(__file__).resolve().parents[3] / "docs" / "benchmark" / "answers.csv"

# the S01 sheet photographed in different conditions: what the reader should do with each
VARIANTS = {
    "flat": ("Flat, daylight", {"verified"}, "verified"),
    "angle": ("Held at an angle", {"verified"}, "verified"),
    "dim": ("Dim room", {"verified"}, "verified"),
    "glare": ("Glare across the stamp", {"verified", "needs_review"}, "verified"),
    "crumple": ("Crumpled, shadow", {"verified", "needs_review"}, "verified"),
    "blur": ("Out of focus", {"retake_requested"}, "retake_requested"),
    "cut": ("Corner cut off", {"retake_requested"}, "retake_requested"),
}
ACCEPT_OVERRIDE = {"S14": {"verified", "needs_review"}, "S15": {"verified", "needs_review"}, "S22": {"needs_review"}}
TAGS = {
    "S01": ["clean"], "S02": ["stamp"], "S03": ["signature", "hard"], "S04": ["stamp", "signature", "empty"], "S05": ["lr-number"],
    "S06": ["quantity", "remark"], "S07": ["remark"], "S08": ["quantity"], "S09": ["weight"], "S10": ["weight", "quantity"],
    "S11": ["date"], "S12": ["remark", "hindi"], "S13": ["remark", "marathi"], "S14": ["stamp", "hard"], "S15": ["stamp", "signature", "hard"],
    "S16": ["remark", "false-alarm"], "S17": ["multi-item"], "S18": ["multi-item", "quantity"], "S19": ["multi-item", "quantity", "remark"],
    "S20": ["multi-item", "hard"], "S21": ["multi-item", "weight"], "S22": ["multi-item", "hard"],
}
FIELDS = ("lr_no", "stamp", "signature", "date", "quantity", "items", "total", "remarks", "shortage_flag")


@dataclass
class Expect:
    sheet: str
    title: str
    do: str
    lr_paper: str
    lr_trip: str
    packages: int | None
    weight: float | None
    stamp: bool
    sign: bool
    date_written: bool
    qty: str
    items: list[float]
    total: float | None
    remark: str
    decision: str
    reasons: list[str]
    accept: set[str]
    judgement: bool


def _nums(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", (text or "").replace(",", ""))]


def load_key() -> dict[str, dict]:
    return {r["sheet"]: r for r in csv.DictReader(open(KEY, encoding="utf-8"))}


def expectation(photo_stem: str, key: dict[str, dict]) -> tuple[Expect, str, list[str]] | None:
    """(what a perfect reader would produce, the tag for the photo condition, tags) for a file name like S06 or S01_glare."""
    m = re.fullmatch(r"(S\d\d)(?:_(\w+))?", photo_stem)
    if not m or m.group(1) not in key:
        return None
    sheet, variant = m.groups()
    r = key[sheet]
    pk, wt = (x.strip() for x in r["booked"].split("/"))
    qty = "" if r["expected_quantity_text"] == "blank" else r["expected_quantity_text"]
    e = Expect(
        sheet, r["case"], r["write_by_hand"], r["lr_on_paper"], r["trips_expected_lr"], None if pk.startswith("-") else int(pk.split()[0]), float(wt.split()[0]),
        r["expected_stamp"] == "True", r["expected_signature"] == "True", r["expected_date"] != "blank", qty,
        [float(x) for seg in r["expected_items"].split(";") if seg.strip() for x in _nums(seg)[:1]],
        (_nums(r["expected_total"]) or [None])[0], "" if r["expected_remark"] == "none" else r["expected_remark"],
        r["expected_decision"], r["expected_reasons"].split(), {r["expected_decision"]}, r["judgement_call"] == "yes",
    )
    if sheet in ACCEPT_OVERRIDE:
        e.accept = ACCEPT_OVERRIDE[sheet]
    tags = list(TAGS[sheet])
    cond = "flat"
    if variant:
        if sheet != "S01" or variant not in VARIANTS:
            return None
        label, e.accept, e.decision = VARIANTS[variant]
        e.title, cond = f"Clean sheet, {label.lower()}", variant
        tags = ["photo-condition"]
        if variant in ("blur", "cut"):
            e.reasons = ["unreadable"] if variant == "blur" else []
    return e, cond, tags


def score_fields(e: Expect, got: PodExtraction, cond: str) -> dict[str, bool | None]:
    """True/False for each field a perfect reader should have read; None where the field does not apply to this photo."""
    if cond in ("blur", "cut"):
        return dict.fromkeys(FIELDS)  # nothing on the paper is expected to be readable
    res: dict[str, bool | None] = {}
    res["lr_no"] = _norm(got.lr_no) == _norm(e.lr_paper)
    res["stamp"] = got.consignee_stamp_present == e.stamp
    res["signature"] = got.signature_present == e.sign
    res["date"] = (got.delivery_date == TODAY) if e.date_written else not got.delivery_date
    got_text = " ".join(filter(None, [got.quantity_received, got.total_quantity, *[f"{i.quantity:g} {i.unit or ''}" for i in got.items if i.quantity is not None]]))
    res["quantity"] = (not got_text.strip()) if not e.qty else all(n in _nums(got_text) for n in _nums(e.qty))
    res["items"] = (sorted(i.quantity for i in got.items if i.quantity is not None) == sorted(e.items)) if e.items else None
    res["total"] = (bool(got.total_quantity) and e.total in _nums(got.total_quantity)) if e.total is not None else None
    rem = (got.remarks or "").strip()
    res["remarks"] = (not rem) if not e.remark else difflib.SequenceMatcher(None, rem.lower(), e.remark.lower()).ratio() >= 0.6
    res["shortage_flag"] = got.shortage_or_damage == bool(e.remark and e.decision == "needs_review" and ("shortage_or_damage" in e.reasons))
    return res


def classify(e: Expect, got_decision: str) -> str:
    if got_decision in e.accept:
        return "pass"
    if got_decision == "verified":
        return "unsafe"  # a sheet that should not be verified would have been
    if e.accept == {"verified"} or "verified" in e.accept:
        return "friction"  # a good sheet sent back or to a person
    return "different"  # safe, but not what was expected (a retake where a person should look, or the reverse)


async def run(provider, photos: Path, out: Path, label: str, pace: float, require_quantity: bool = False) -> None:
    key = load_key()
    done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {"label": label, "provider": provider.name, "cases": {}}
    files = sorted(p for p in photos.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    for p in files:
        exp = expectation(p.stem, key)
        if exp is None or p.stem in done["cases"]:
            continue
        e, cond, tags = exp
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        started = time.perf_counter()
        error = None
        got: PodExtraction | None = None
        try:
            got = await provider.extract(p.read_bytes(), mime, e.lr_trip)
        except ProviderError as ex:
            error = str(ex)[:160]
        ms = int((time.perf_counter() - started) * 1000)
        if got is not None:
            verdict = decide(got, expected_lr_no=e.lr_trip, retake_count=0, expected_packages=e.packages, expected_weight_tonnes=e.weight,
                             require_quantity=require_quantity)
            decision, reasons = verdict.decision.value, verdict.reasons
        else:  # a failed model sends the sheet to a person: safe, but not counted as a correct read
            decision, reasons = "needs_review", ["ai_unavailable"]
        status = classify(e, decision) if got is not None else "error"
        done["cases"][p.stem] = {
            "photo": p.name, "sheet": e.sheet, "cond": cond, "title": e.title, "tags": tags, "do": e.do, "judgement": e.judgement,
            "expected": {"decision": e.decision, "accept": sorted(e.accept), "reasons": e.reasons, "lr": e.lr_paper, "trip_lr": e.lr_trip, "stamp": e.stamp,
                         "signature": e.sign, "date": TODAY if e.date_written else None, "quantity": e.qty, "items": e.items, "total": e.total, "remarks": e.remark,
                         "booked": {"packages": e.packages, "weight_t": e.weight}},
            "got": None if got is None else got.model_dump(exclude={"boxes"}),
            "decision": decision, "reasons": reasons, "status": status, "error": error, "ms": ms,
            "fields": score_fields(e, got, cond) if got is not None else dict.fromkeys(FIELDS),
        }
        out.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{p.stem:12} {status:9} expected {e.decision:17} got {decision:17} {ms / 1000:5.1f}s {error or ''}", flush=True)
        if pace:
            await asyncio.sleep(pace)
    ms = [c["ms"] for c in done["cases"].values() if not c["error"]]
    if ms:
        print(f"median {statistics.median(ms) / 1000:.1f}s over {len(ms)} photos")


def rescore(src: Path, out: Path, title: str, require_quantity: bool) -> None:
    """The same readings, judged again with the current rules (no model is run): shows what a rule change would have done."""
    key = load_key()
    d = json.loads(src.read_text(encoding="utf-8"))
    d["label"] = title
    for stem, c in d["cases"].items():
        if not c["got"]:
            continue
        e, _cond, _ = expectation(stem, key)
        got = PodExtraction.model_validate(c["got"])
        v = decide(got, expected_lr_no=e.lr_trip, retake_count=0, expected_packages=e.packages, expected_weight_tonnes=e.weight, require_quantity=require_quantity)
        c["decision"], c["reasons"], c["status"] = v.decision.value, v.reasons, classify(e, v.decision.value)
    out.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"rescored {len(d['cases'])} photos -> {out.name}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--photos", required=True)
    ap.add_argument("--provider", default="local", help="local | gemini | mock")
    ap.add_argument("--ollama-model", default=None)
    ap.add_argument("--model", default=None, help="the cloud model to use (gemini or groq); default: the one in settings")
    ap.add_argument("--label", required=True)
    ap.add_argument("--title", default=None, help="the name shown on the dashboard (default: the label)")
    ap.add_argument("--require-quantity", action="store_true", help="a booked quantity that was not found on the receipt goes to review")
    ap.add_argument("--rescore", default=None, help="label of an earlier run to judge again with the current rules instead of running a model")
    ap.add_argument("--note", default="", help="one line saying what changed in this run")
    ap.add_argument("--pace", type=float, default=0, help="seconds to wait between photos (free tiers are rate limited)")
    ap.add_argument("--results", default=str(KEY.parent / "results"))
    a = ap.parse_args()
    s = get_settings()
    if a.ollama_model:
        s = s.model_copy(update={"ollama_model": a.ollama_model})
    if a.model:
        s = s.model_copy(update={"gemini_model" if a.provider == "gemini" else "groq_model": a.model})
    out = Path(a.results)
    out.mkdir(parents=True, exist_ok=True)
    if a.rescore:
        rescore(out / f"{a.rescore}.json", out / f"{a.label}.json", a.title or a.label, a.require_quantity)
        return
    provider = build_provider(a.provider, s)

    async def go() -> None:
        if (warm := getattr(provider, "warm", None)) is not None:
            await warm()
        path = out / f"{a.label}.json"
        await run(provider, Path(a.photos), path, a.title or a.label, a.pace, a.require_quantity)
        meta = json.loads(path.read_text(encoding="utf-8"))
        meta.update(model=s.ollama_model if a.provider == "local" else s.gemini_model if a.provider == "gemini" else s.groq_model if a.provider == "groq" else a.provider,
                    when=time.strftime("%Y-%m-%d %H:%M"), note=a.note)
        path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    asyncio.run(go())


if __name__ == "__main__":
    main()
