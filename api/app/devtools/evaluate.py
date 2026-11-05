"""Accuracy harness for the POD reader. Measures what matters to the business, not just "is the model clever":

  1. UNSAFE errors   - a bad POD (no stamp, wrong LR, shortage...) that the pipeline would have VERIFIED. Must be zero.
  2. Friction        - a good POD that the pipeline sends back for a retake or to a human. Costs driver time.
  3. Field accuracy  - how often each field (LR no., stamp, signature, shortage flag...) is read right.

It renders labelled synthetic PODs (all text fake; see synthetic_pod.py), degrades them like a phone camera would, runs the
chosen provider on each, applies the SAME deterministic decision rules the app uses, and compares with what a perfect
reader would produce. Synthetic PODs are an optimistic test: real accuracy must be re-measured on the client's own PODs
in the pilot (roadmap Phase 4), with this same harness fed their labelled images.

  uv run python -m app.devtools.evaluate                       # provider from settings (default mock)
  uv run python -m app.devtools.evaluate --provider gemini     # the real model (uses the API key from .env; costs a few calls)
  uv run python -m app.devtools.evaluate --seeds 4 --out report.md --max-false-verify 0 --min-decision-accuracy 0.9

Exit code 1 when a gate fails, so it can guard a prompt/model change."""
import argparse
import asyncio
import io
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field

from PIL import Image, ImageEnhance, ImageFilter

from app.ai.base import PodExtraction, ProviderError, VisionProvider
from app.ai.registry import build_provider
from app.config import get_settings
from app.devtools.synthetic_pod import SCENARIOS, render, truth_for
from app.pod.decision import Decision, _norm, decide

FIELDS = ("is_document", "readable", "lr_no", "consignee_stamp_present", "signature_present", "shortage_or_damage", "delivery_date")
VARIANTS = ("original", "phone", "dark")


def degrade(png: bytes, variant: str, seed: int) -> tuple[bytes, str]:
    """Make the clean render look like a driver's photo. The PNG label is dropped on purpose: a model must read pixels."""
    if variant == "original":
        return png, "image/png"
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if variant == "phone":
        im = im.rotate(2.0 if seed % 2 else -2.0, resample=Image.BICUBIC, expand=False, fillcolor=(120, 118, 112))
        im = ImageEnhance.Brightness(im).enhance(0.85).filter(ImageFilter.GaussianBlur(0.8))
        q = 62
    else:  # dark
        im = ImageEnhance.Brightness(im).enhance(0.45)
        q = 70
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q)
    return buf.getvalue(), "image/jpeg"


def expected_decision(scenario_name: str, lr_no: str, scripted: bool = False) -> tuple[PodExtraction, Decision]:
    """What a perfect reader + the app's rules would do. For a real model confidence is set high: the scenario's scripted
    confidence is a mock-only device, the image itself is what a real model is judged on. The mock replays the script."""
    truth = truth_for(SCENARIOS[scenario_name], lr_no)
    if not scripted:
        truth = truth.model_copy(update={"confidence": 0.95})
    return truth, decide(truth, expected_lr_no=lr_no, retake_count=0).decision


@dataclass
class Case:
    scenario: str
    variant: str
    seed: int
    expected: Decision
    got: Decision | None = None
    reasons: list[str] = field(default_factory=list)
    field_ok: dict[str, bool] = field(default_factory=dict)
    latency_ms: int = 0
    error: str | None = None

    @property
    def unsafe(self) -> bool:
        return self.got == Decision.verified and self.expected != Decision.verified

    @property
    def friction(self) -> bool:
        return self.expected == Decision.verified and self.got is not None and self.got != Decision.verified


def _same(name: str, got: PodExtraction, truth: PodExtraction) -> bool:
    if name == "lr_no":
        return _norm(got.lr_no) == _norm(truth.lr_no)
    return getattr(got, name) == getattr(truth, name)


class Throttle:
    """Spaces calls out (free API tiers allow only a handful per minute) and waits out a 429 instead of counting it as a miss."""

    def __init__(self, per_minute: float) -> None:
        self.gap = 60.0 / per_minute if per_minute > 0 else 0.0
        self._next = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.gap
        if delay:
            await asyncio.sleep(delay)


async def call_with_retry(provider: VisionProvider, image: bytes, mime: str, lr_no: str, throttle: Throttle) -> PodExtraction:
    for attempt in range(4):
        await throttle.wait()
        try:
            return await provider.extract(image, mime, lr_no)
        except ProviderError as e:
            if "429" not in str(e) or attempt == 3:
                raise
            await asyncio.sleep(20 * (attempt + 1))  # rate limited: back off, then try the same image again
    raise AssertionError("unreachable")


async def run_case(provider: VisionProvider, scenario: str, variant: str, seed: int, sem: asyncio.Semaphore, throttle: Throttle) -> Case:
    scripted = provider.name == "mock"
    lr_no = f"LR-{70000 + seed * 37 + len(scenario)}"
    truth, expected = expected_decision(scenario, lr_no, scripted)
    case = Case(scenario, variant, seed, expected)
    image, mime = degrade(render(SCENARIOS[scenario], lr_no, seed=seed), variant, seed)
    async with sem:
        started = time.perf_counter()
        try:
            got = await call_with_retry(provider, image, mime, lr_no, throttle)
        except ProviderError as e:
            case.error = str(e)[:120]  # in production this POD goes to a human: neither safe-by-luck nor counted as a wrong read
            case.got = Decision.needs_review
            return case
        finally:
            case.latency_ms = int((time.perf_counter() - started) * 1000)
    result = decide(got, expected_lr_no=lr_no, retake_count=0)
    case.got, case.reasons = result.decision, result.reasons
    case.field_ok = {f: _same(f, got, truth) for f in FIELDS}
    return case


def pct(n: int, d: int) -> str:
    return "n/a" if d == 0 else f"{100 * n / d:.1f}%"


def report(provider_name: str, cases: list[Case]) -> tuple[str, dict]:
    scored = [c for c in cases if c.error is None]
    errors = [c for c in cases if c.error]
    agree = sum(c.got == c.expected for c in cases)
    unsafe = [c for c in cases if c.unsafe]
    friction = [c for c in cases if c.friction]
    good = [c for c in cases if c.expected == Decision.verified]
    lat = sorted(c.latency_ms for c in scored) or [0]
    p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
    stats = {"cases": len(cases), "decision_accuracy": agree / len(cases) if cases else 0.0, "false_verify": len(unsafe), "friction": len(friction),
             "errors": len(errors)}

    lines = [f"# POD reader evaluation - provider `{provider_name}`", "",
             (f"{len(cases)} synthetic PODs ({len(SCENARIOS)} situations x {len({c.variant for c in cases})} photo conditions x seeds). "
              "Synthetic PODs are optimistic: re-run on the client's own labelled PODs in the pilot."), "",
             "## Headline", "",
             f"- **Unsafe errors (bad POD would be auto-verified): {len(unsafe)}**  (must be 0)",
             f"- Friction (good POD sent back to retake/review): {len(friction)} of {len(good)} good ones = {pct(len(friction), len(good))}",
             f"- Decision matches a perfect reader: {agree} of {len(cases)} = {pct(agree, len(cases))}",
             f"- Provider failures (sent to human review): {len(errors)}",
             f"- Latency: median {int(statistics.median(lat))} ms, 95th percentile {p95} ms", "", "## Per field", "", "| Field | Read correctly |", "|---|---|"]
    for f in FIELDS:
        ok = sum(c.field_ok.get(f, False) for c in scored)
        lines.append(f"| {f} | {pct(ok, len(scored))} ({ok}/{len(scored)}) |")
    lines += ["", "## By photo condition", "", "| Condition | Decision correct | Unsafe | Friction |", "|---|---|---|---|"]
    for v in VARIANTS:
        vc = [c for c in cases if c.variant == v]
        if vc:
            lines.append(f"| {v} | {pct(sum(c.got == c.expected for c in vc), len(vc))} | {sum(c.unsafe for c in vc)} | {sum(c.friction for c in vc)} |")
    lines += ["", "## By situation", "", "| Situation | Expected | Decision correct | Unsafe |", "|---|---|---|---|"]
    for name in SCENARIOS:
        sc = [c for c in cases if c.scenario == name]
        if sc:
            lines.append(f"| {name} | {sc[0].expected.value} | {pct(sum(c.got == c.expected for c in sc), len(sc))} | {sum(c.unsafe for c in sc)} |")
    confusion = Counter((c.expected.value, c.got.value if c.got else "none") for c in cases)
    lines += ["", "## Expected vs got", "", "| Expected | Got | Count |", "|---|---|---|"] + [f"| {e} | {g} | {n} |" for (e, g), n in sorted(confusion.items())]
    if unsafe:
        lines += ["", "## Unsafe cases (investigate first)", ""] + [f"- {c.scenario} / {c.variant} / seed {c.seed}: expected {c.expected.value}, would have been verified" for c in unsafe]
    if errors:
        lines += ["", "## Provider failures", ""] + [f"- {c.scenario} / {c.variant} / seed {c.seed}: {c.error}" for c in errors[:10]]
    return "\n".join(lines) + "\n", stats


async def evaluate(provider: VisionProvider, seeds: int, variants: tuple[str, ...], concurrency: int = 2, per_minute: float = 0) -> list[Case]:
    sem = asyncio.Semaphore(concurrency)
    throttle = Throttle(per_minute)
    jobs = [run_case(provider, sc, v, s, sem, throttle) for sc in SCENARIOS for v in variants for s in range(seeds)]
    return list(await asyncio.gather(*jobs))


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate the POD reader on labelled synthetic PODs.")
    ap.add_argument("--provider", default=None, help="mock | gemini (default: AI_PROVIDER from settings)")
    ap.add_argument("--seeds", type=int, default=None, help="images per situation and condition (default 3 for mock, 1 for a real model)")
    ap.add_argument("--per-minute", type=float, default=None, help="max calls per minute (default 8 for a real model: free tiers are strict)")
    ap.add_argument("--variants", default=None, help="comma list of original,phone,dark (default: all for a real model, original for mock)")
    ap.add_argument("--out", default=None, help="also write the report to this file")
    ap.add_argument("--max-false-verify", type=int, default=None, help="fail (exit 1) if more bad PODs than this would be verified")
    ap.add_argument("--min-decision-accuracy", type=float, default=None, help="fail if the decision accuracy is below this (0-1)")
    a = ap.parse_args()

    s = get_settings()
    name = a.provider or s.ai_provider
    provider = build_provider(name, s)
    # The mock reads a label from PNG metadata, which a degraded JPEG no longer has: only the original means anything for it.
    variants = tuple(a.variants.split(",")) if a.variants else (("original",) if name == "mock" else VARIANTS)
    seeds = a.seeds if a.seeds is not None else (3 if name == "mock" else 1)
    per_minute = a.per_minute if a.per_minute is not None else (0 if name == "mock" else 8)
    cases = asyncio.run(evaluate(provider, seeds, variants, per_minute=per_minute))
    text, stats = report(name, cases)
    sys.stdout.reconfigure(encoding="utf-8")
    print(text)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)

    failed = []
    if a.max_false_verify is not None and stats["false_verify"] > a.max_false_verify:
        failed.append(f"unsafe errors {stats['false_verify']} > {a.max_false_verify}")
    if a.min_decision_accuracy is not None and stats["decision_accuracy"] < a.min_decision_accuracy:
        failed.append(f"decision accuracy {stats['decision_accuracy']:.3f} < {a.min_decision_accuracy}")
    if failed:
        print("GATE FAILED: " + "; ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
