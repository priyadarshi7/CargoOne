# Local AI reader (no cloud, no cost)

The POD reader can run entirely on your own machine. No photo leaves it, which keeps the DPDP story simple and costs nothing per photo.

## How it reads a photo

1. **PaddleOCR** reads every line of text and says where each line is on the photo (CPU, a few seconds).
2. **Qwen3-VL 4B** (run by Ollama, on the GPU, about 4 seconds) looks at the photo with those lines and answers what OCR cannot: is this a POD, is there a stamp, is there a signature, what do the remarks say, which lines hold the LR number, date and quantity.
3. **Checking.** The model is never trusted alone. The LR number is accepted only when OCR can see it on the paper (and then OCR's reading wins). A field gets a box only if the line the model points at really contains the value. A claim that cannot be checked gets no box, and an LR number the text reader never saw caps the confidence at 0.6, which sends the photo to a person. Stamp and signature boxes come from the model's own pointing (dashed in the screen).
4. The usual rules in `decision.py` (retakes capped at 2, low confidence goes to review, shortage goes to review) are unchanged.

Boxes are stored with the result as fractions of the photo (`boxes` in the AI result: field, x, y, w, h, text, conf, source), so they survive any zoom. Review shows them on the photo with a tag, links each to its form field, and lists what was and was not found.

## One-time setup

```
cd api
uv sync --extra local-ai          # PaddleOCR + PaddlePaddle (CPU), about 1 GB
ollama pull qwen3-vl:4b           # about 3.3 GB; Ollama must be running (the tray app, or `ollama serve`)
```

OCR models download themselves on first use (about 100 MB, once).

In `.env`:

```
AI_PROVIDER=local
AI_FALLBACKS=gemini        # optional: used only if the local reader fails; leave empty to keep everything on the machine
# optional
OLLAMA_MODEL=qwen3-vl:4b
OCR_LANGS=en               # en,devanagari to also read Hindi/Marathi print (slower)
OCR_MODELS=mobile          # or server: heavier, a little more exact
```

The first photo after starting is slow (models load); later ones are quick. If Ollama is not running the reader reports "local model is not running" and the photo goes to the fallback, or to a human if there is none. The driver is never blocked.

## Measuring it

```
uv run python -m app.devtools.evaluate --provider local --seeds 1 --variants original,phone --per-minute 0
```

First result (18 synthetic photos, original and phone-degraded, RTX 4050 laptop): 0 unsafe errors, 18 of 18 decisions correct, 0 good PODs sent back, every field 100% except LR number and date at 83%; median 36 s, slowest 96 s. The signature needed a second, slower look: without it only 39% of signatures were seen and every good POD went back for a retake.

Synthetic PODs flatter any model. Real accuracy has to be measured on real photos from the client with this same harness before trusting it.

## Known limits

- Handwriting (remarks, signatures), especially Marathi, is the weak spot of every open model. Expect more photos in the review queue than with a cloud model.
- 6 GB of GPU memory fits a 4B vision model comfortably and a 7B only with heavy compression. OCR runs on the CPU so it does not compete for the GPU.
- `enable_mkldnn=False` is set on purpose: Paddle 3's CPU acceleration crashes on some of its own models.
