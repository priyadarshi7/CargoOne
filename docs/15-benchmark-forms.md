# Benchmarking the POD reader on real paper

`docs/benchmark/lr_forms.pdf` has 22 sample Lorry Receipts, one per page. Each page is the app's own printed LR (the same layout as the PDF the app issues from a trip), with fake names and numbers. The typed part carries the LR number, parties, route, goods, packages and weight. The **receiver's part is empty**: date received, quantity / weight received, remarks, and the stamp and signature boxes. Print single-sided on A4, fill each sheet as below, photograph it with a phone, and run every photo through each model.

**LR numbers** follow the app's format, `LR/<branch>/<financial year>/<serial>` (for example `LR/MH20/26-27/900001`). The serials start at 900001, far above anything the app will issue, so a test sheet cannot be mistaken for a real one. To run a photo through the app itself, create a trip whose LR number is the one on the sheet; to run it through the evaluation harness, pass that number as the expected LR.

Regenerate with `.venv/Scripts/python -m app.devtools.lr_form ../docs/benchmark` from `api/`. `answers.csv` holds the same table plus the expected stamp, signature, date, quantity text, line items, total and remark. The decisions in it are computed by the app's own rules (`pod/decision.py`), so they stay in step if the rules change.

## Where the received weight is written
In the **goods table** on the LR. It has one row per good (number, goods, booked packages, booked weight) and a bold **RECEIVED** column with an empty cell beside every row, plus a **Total** row whose received cell is for the total. The receiver writes what actually arrived against each good, then the total. **Remarks** is only for shortage or damage. The reader returns the whole text, each row (name, number, unit) and the written total; the app adds the rows up and compares them with the booked total weight (or package count).

## How to fill
- Use a real rubber stamp if you have one; otherwise draw a box and write "Om Sai Building Supplies - Received" in blue ink. Stamp inside the **Consignee signature, name and stamp** box.
- Sign with a different person or pen on a few sheets (blue and black ink, one scribbled signature).
- "Date" means today's date in any style you like (`8/11/26`, `08-11-2026`, `८.११.२६`). Vary it.
- The goods are booked with one total: 2.5 t / 50 bags (S01 to S16), 18 t / 6 coils (S09, S10), 4 t for two goods (S17 to S21: PPC Cement 2.5 t and River Sand 1.5 t), and 50 packages / 4 t for mixed units (S22: Cement 50 packages 2.5 t, Sand 1.5 t).

| Sheet | Case | Write and do by hand | The app should |
|---|---|---|---|
| S01 | Clean, everything right | Write the date, 50 bags, then stamp and sign. | verified |
| S02 | No stamp | Write the date and 50 bags, sign. Do NOT stamp. | retake requested (stamp missing) |
| S03 | No signature | Write the date and 50 bags, stamp. Do NOT sign. | retake requested (signature missing) |
| S04 | Receiver part left empty | Fill nothing at all in the receiver part. | retake requested (stamp missing signature missing) |
| S05 | Wrong LR number | Fill everything correctly (as S01). The trip's LR ends 900099, but this paper carries another number. | retake requested (lr mismatch) |
| S06 | Shortage remark and short count | Date, quantity 44 bags, remark: Short 6 bags. Stamp, sign. | needs review (shortage or damage quantity mismatch) |
| S07 | Damage remark, full count | Date, quantity 50 bags, remark: 2 bags torn / damaged. Stamp, sign. | needs review (shortage or damage) |
| S08 | Short count, nobody wrote a remark | Date, quantity 40 bags, NO remark. Stamp, sign. | needs review (quantity mismatch) |
| S09 | Weighed load, kg matches | Date, quantity 18000 kg. Stamp, sign. | verified |
| S10 | Weighed load, kg is much less | Date, quantity 16000 kg, no remark. Stamp, sign. | needs review (quantity mismatch) |
| S11 | Date left blank | Quantity 50 bags. Stamp, sign. Leave the date blank. | verified |
| S12 | Remark in Hindi handwriting | Date, 50 bags, remark in Hindi: 3 बोरी फटी हुई है. Stamp, sign. | needs review (shortage or damage) |
| S13 | Remark in Marathi handwriting | Date, 50 bags, remark in Marathi: २ गोणी ओल्या झाल्या. Stamp, sign. | needs review (shortage or damage) |
| S14 | Faint, half-cut stamp | Date, 50 bags, sign. Press the stamp lightly so it is pale, and let it run off the edge of its box. | verified * |
| S15 | Messy: stamp over the signature and date | Date, 50 bags, sign, then stamp OVER the signature, the date and the quantity. | verified * |
| S16 | A remark that is NOT a problem | Date, 50 bags, remark: Received OK, thanks. Stamp, sign. | verified |
| S17 | Two goods, each weight written, total matches | Date. Received column: row 1 write 2.5 t, row 2 write 1.5 t, Total received 4 t. Stamp, sign. | verified |
| S18 | Two goods, one short, honest total | Date. Received: row 1 2.5 t, row 2 1.0 t, total 3.5 t. No remark. Stamp, sign. | needs review (quantity mismatch) |
| S19 | Two goods, one short, with a remark | Date. Received: row 1 2.5 t, row 2 1.0 t, total 3.5 t. Remark: Sand short 0.5 t. Stamp, sign. | needs review (shortage or damage quantity mismatch) |
| S20 | Two goods, lines do not add up to the total | Date. Received: row 1 2.5 t, row 2 1.5 t, total 5 t (a wrong total, as a rushed receiver might write). Stamp, sign. | needs review (quantity unclear) |
| S21 | Two goods in kilograms | Date. Received: row 1 2500 kg, row 2 1500 kg, total 4000 kg. Stamp, sign. | verified |
| S22 | Two goods in different units | Date. Received: row 1 50 bags, row 2 1.5 t, leave the total blank. Stamp, sign. | needs review (quantity unclear) * |

\* A person could reasonably decide either way; the expectation is a recommendation, so read those results by eye.

## Several goods
The booking holds one total, not a list per good. The app compares the received lines, added up, with it:
- All lines in weight units (t, kg, quintal): the tonnes are added and compared with the booked weight (5% either way is fine).
- All lines counts (bags, cartons): the counts are added and compared with the booked packages.
- Lines that do not add up to the written total, mixed units, an unreadable line, or "48/50": **quantity unclear**, so a person looks at the photo. It is never a retake.

## Photo conditions (use sheet S01, or any verified sheet)
Photograph S01 each of these ways. The first three should still verify; the rest should ask for a retake or go to a person.

| Photo | Expected |
|---|---|
| Flat, daylight, whole sheet | verified |
| Held at an angle (about 30 degrees) | verified |
| Dim room, no flash | verified |
| Flash glare across the stamp | verified or review |
| Crumpled paper, shadow across it | verified or review |
| Out of focus / shaken | retake (unreadable) |
| One corner of the sheet cut off (the LR number or the stamp not in the frame) | retake |
| Something that is not a POD (a table, a wall) | retake (not a POD) |

## What to record for each photo
The model, what it read for each field against `answers.csv`, the decision the app gave, the time taken, and the cost. The measures that matter most are in `docs/06-ai-evaluation.md`: unsafe errors must be zero, then needless retakes, then field accuracy.

## Running the benchmark; the "AI benchmark" tab
Put the photographs in `docs/benchmark/photos/` named `S01_flat.jpeg`, `S01_angle.jpeg`, ... `S02.jpeg` ... `S22.jpeg`. From `api/`:

```
.venv/Scripts/python -m app.devtools.benchmark --photos ../docs/benchmark/photos --provider local --label qwen-run3 --title "Qwen3-VL 4B · run 3" --note "what changed"
.venv/Scripts/python -m app.devtools.benchmark --photos ../docs/benchmark/photos --provider gemini --label gemini-run1 --title "Gemini 2.5 Flash · run 1" --pace 8
```

Each run is saved in `docs/benchmark/results/<label>.json` and is resumable. The office app's **AI benchmark** tab (sidebar, Fleet and admin; ops, billing and MD) shows them straight away: a table of every run (model, date, pass rate, unsafe, needless retakes, fields right, time), the headline numbers and a warning when any sheet that should have been stopped would have been verified, how each field was read, the pass rate by kind of test, what should have happened against what happened, and every photo labelled with what was expected, what the app decided and why, with the field-by-field comparison. `GET /benchmark/runs` and `GET /benchmark/photos/<name>` feed it (set `BENCHMARK_DIR` to keep the files elsewhere). `--rescore <label> --require-quantity` judges an earlier run's readings again with a changed rule without running a model. A 28-photo run takes about 6 minutes with the local model.

**What the tab counts.** *Unsafe*: a sheet that should not be verified (missing stamp or signature, wrong LR, a shortage or different quantity) would have been. It must be 0. *Needless retake*: a good sheet sent back. *Safe, but different*: sent to a person where a retake was expected, or the reverse. Photo-condition shots and the judgement-call sheets (S14, S15, S22) accept more than one answer.

## Results so far (28 photos)
| Run | Model | Pass rate | Unsafe | Needless |
|---|---|---|---|---|
| Qwen3-VL 4B, run 1 (first prompt and rules) | local, Ollama + OCR | 67.9% | 5 | 2 |
| Qwen3-VL 4B, run 2 (current code) | local, Ollama + OCR | 71.4% | 3 | 3 |
| Qwen3-VL 4B, run 2 with `POD_REQUIRE_QUANTITY` (same readings) | local | 64.3% | 2 | 6 |
| **Qwen3.8 27B on Groq** (LR-aware prompt) | cloud, free tier | **89.3%** | 2 | 1 |

**Local 4B.** Run 2 still verified S03 (the consignor's and driver's signatures were taken for the receiver's), S10 (the quantity was not found) and S13 (a Marathi shortage remark was misread). The model is sensitive to its prompt: a longer instruction about which signature counts made it stop reading the quantity altogether, so that wording was reverted. `POD_REQUIRE_QUANTITY` (a booked quantity that the reader cannot find goes to a person) removes one more unsafe case at the price of more reviews of good sheets; it is off by default.

**Groq, Qwen3.8 27B.** Much better on every field. It still verified S01_cut (a corner of the sheet cut off, which it called readable) and S13 (the Marathi remark was misread, so the shortage was not flagged). The free tier allows 7,000 input tokens a minute, about 3 photos a minute, so a run takes about 10 minutes and it cannot serve real traffic; a paid plan is needed for that.

**Not run yet.** Gemini 2.5 Flash: the key works but Google answers "the free tier is not available for this project", so billing has to be switched on in AI Studio. Local Ollama models (Qwen3-VL 7B, MiniCPM-V 4.5, Llama 3.2 Vision 11B, glm-ocr) are not installed on this machine yet, and drive C: has under 9 GB free.
