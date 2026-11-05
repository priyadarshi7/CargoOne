# POD reader evaluation

How we know the AI reading of a POD is good enough to trust. Run it after any change to the prompt, the model, or the decision rules, and again on the client's own PODs in the pilot.

## What it measures

The AI only *reads* the photo; deterministic rules then decide (`app/pod/decision.py`). The harness checks the whole chain, in the order that matters to the business:

1. **Unsafe errors**: a bad POD (no stamp, no signature, wrong LR number, a shortage remark, not a POD at all) that the pipeline would have **verified**. This must be **zero**. One of these means paperwork is billed that should not be.
2. **Friction**: a good POD that is sent back for a retake or to a human. This costs driver and office time but never money.
3. **Field accuracy**: how often each field (LR number, stamp, signature, shortage flag, date, readable, is-a-document) is read correctly.
4. **Latency and failures**: how long a read takes, and how often the provider fails (those PODs go to a human, never blocking the driver).

## How it works

It renders labelled synthetic PODs (every word is fake), degrades them like a phone camera (a slight rotation, JPEG compression, dim light; the hidden label is dropped so a model must read the pixels), runs the provider, applies the same decision rules the app uses, and compares with what a perfect reader would do.

```
cd api
uv run python -m app.devtools.evaluate --provider mock                      # pipeline self-check, instant, free
uv run python -m app.devtools.evaluate --provider gemini --out eval_reports/gemini-latest.md
uv run python -m app.devtools.evaluate --provider gemini --seeds 3 --max-false-verify 0 --min-decision-accuracy 0.9
```

- The second form uses the real model and the API key from `.env`. It sends only fake synthetic images. It is rate-limited to 8 calls a minute by default (free tiers are strict) and waits out a `429` instead of counting it as a miss; use `--per-minute` to change that.
- The last form is a **gate**: the exit code is 1 if more bad PODs than `--max-false-verify` would be verified, or the decision accuracy falls below `--min-decision-accuracy`. Use it before switching model or prompt.
- With `--provider mock` only the original images are used, because the mock reads the label that the degraded copies no longer carry.

## Limits you must keep in mind

- Synthetic PODs are clean and tidy. Real PODs have crumpled paper, overlapping stamps, handwriting in Hindi/Marathi and shadows. A good score here is necessary, not sufficient.
- The expected answers come from the same generator that draws the image, so they are exact, but they only cover the situations the generator can draw (nine today).
- **Pilot week 1:** collect 100-200 real PODs, label them (what a clerk would say for each field), and extend the harness to read them from a folder. Until then, treat the figures as a regression check, not as a promise to the client.

## Results

See the most recent run in `api/eval_reports/` and the figures recorded in the roadmap (Phase 4).
