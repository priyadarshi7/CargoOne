# Local AI reader (no cloud, no cost)

The POD reader can run entirely on your own machine. No photo leaves it, which keeps the DPDP story simple and costs nothing per photo.

## How it reads a photo

1. **PaddleOCR's text models** read every line of text and say where each line is on the photo. They run through **ONNX Runtime** (`OCR_ENGINE=rapid`, the default): about 1 s on your RTX GPU (DirectML, no CUDA setup) and 1-2 s even on a CPU. Running PaddlePaddle itself (`OCR_ENGINE=paddle`) took about 20 s on the CPU, and there is no Paddle 3.x GPU build for Windows with Python 3.13, so that engine stays CPU-only and is kept only for reading Devanagari print.
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
OCR_ENGINE=rapid           # rapid (fast, GPU) or paddle (CPU, slow; the one that can read Devanagari)
OCR_LANGS=en               # en,devanagari to also read Hindi/Marathi print (needs OCR_ENGINE=paddle)
OCR_MODELS=mobile          # or server: heavier, a little more exact
```

The first photo after starting is slow (models load); later ones are quick. If Ollama is not running the reader reports "local model is not running" and the photo goes to the fallback, or to a human if there is none. The driver is never blocked.

## Measuring it

```
uv run python -m app.devtools.evaluate --provider local --seeds 1 --variants original,phone --per-minute 0
```

First result (18 synthetic photos, original and phone-degraded, RTX 4050 laptop): 0 unsafe errors, 18 of 18 decisions correct, 0 good PODs sent back, every field 100% except LR number and date at 83%; median 36 s, slowest 96 s. The signature needed a second, slower look: without it only 39% of signatures were seen and every good POD went back for a retake.

**Time per photo on a real eLR photo (1408x768, 46 lines), RTX 4050 laptop:** OCR 1 s + vision model 6-9 s = about 8-12 s (was 26-30 s with PaddlePaddle on the CPU). A photo where the first pass finds no signature takes longer (the model then looks again with thinking on: 30 s or more), which is why the synthetic test set, whose signatures are crude zigzags, still shows a median of about 32 s.

Synthetic PODs flatter any model. Real accuracy has to be measured on real photos from the client with this same harness before trusting it.

## Known limits

- Handwriting (remarks, signatures), especially Marathi, is the weak spot of every open model. Expect more photos in the review queue than with a cloud model.
- 6 GB of GPU memory fits a 4B vision model comfortably and a 7B only with heavy compression. OCR runs on the CPU so it does not compete for the GPU.
- OCR reads one photo at a time (a lock): starting or using the GPU engine from two threads at once crashed the process.
- `enable_mkldnn=False` (paddle engine only) is set on purpose: Paddle 3's CPU acceleration crashes on some of its own models.
