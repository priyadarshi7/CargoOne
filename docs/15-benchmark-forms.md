# Benchmarking the POD reader on real paper

`docs/benchmark/lr_forms.pdf` has 16 sample Lorry Receipts (fake names and numbers). The top part is typed; the **Receiver's acknowledgement** at the bottom is empty. Print it single-sided on A4, fill each sheet as below, photograph it with a phone, and run every photo through each model.

Regenerate with `.venv/Scripts/python -m app.devtools.lr_form ../docs/benchmark` from `api/`. `answers.csv` holds the same table plus the expected stamp, signature, date, quantity and remark; the decisions are computed by the app's own rules (`pod/decision.py`), so they stay in step if the rules change.

## How to fill
- Use a real rubber stamp if you have one; otherwise draw a box and write "Om Sai Building Supplies - Received" in blue ink. Stamp inside the **Consignee's stamp** box.
- Sign with a different person or a different pen on a few sheets (blue and black ink, one scribbled signature).
- "Today" means today's date in any style you like (`8/11/26`, `08-11-2026`, `८.११.२६`). Vary it.
- Sheets S05 (wrong LR): the trip's LR is `BM-1099`, but the paper says `BM-1005`.

| Sheet | Fill in by hand | App should |
|---|---|---|
| S01 | Stamp, sign, write today's date, write 50 bags. No remark. | verified |
| S02 | Sign and write date + 50 bags. Do NOT stamp. | retake requested (stamp missing) |
| S03 | Stamp and write date + 50 bags. Do NOT sign. | retake requested (signature missing) |
| S04 | Fill nothing at all in the receiver part. | retake requested (stamp missing signature missing) |
| S05 | Fill everything correctly (as S01). The trip's LR is BM-1099, but this paper says another number. | retake requested (lr mismatch) |
| S06 | Stamp, sign, date. Quantity 44 bags. Remark: Short 6 bags | needs review (shortage or damage quantity mismatch) |
| S07 | Stamp, sign, date. Quantity 50 bags. Remark: 2 bags torn / damaged | needs review (shortage or damage) |
| S08 | Stamp, sign, date. Quantity 40 bags. NO remark. | needs review (quantity mismatch) |
| S09 | Stamp, sign, date. Quantity 18000 kg. No remark. | verified |
| S10 | Stamp, sign, date. Quantity 16000 kg. No remark. | needs review (quantity mismatch) |
| S11 | Stamp, sign, quantity 50 bags. Leave the date blank. | verified |
| S12 | Stamp, sign, date, 50 bags. Remark in Hindi: 3 बोरी फटी हुई है | needs review (shortage or damage) |
| S13 | Stamp, sign, date, 50 bags. Remark in Marathi: २ गोणी ओल्या झाल्या | needs review (shortage or damage) |
| S14 | Press the stamp lightly so it comes out pale, and let it run off the edge of the box. Sign, date, 50 bags. | verified * |
| S15 | Stamp over your signature AND over the date and quantity lines. Left-handed scribble is fine. 50 bags. | verified * |
| S16 | Stamp, sign, date, 50 bags. Remark: Received OK, thanks | verified |

\* A person could reasonably decide either way; the expectation is a recommendation, so read those results by eye.

## Photo conditions (use sheet S01, or any verified sheet)
Photograph S01 each of these ways. The first four should still verify; the last four should ask for a retake or send it to a person.

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
The model, what it read for each field against `answers.csv`, the decision the app gave, the time taken, and the cost. The three numbers that matter most are in `docs/06-ai-evaluation.md`: unsafe errors must be zero, then needless retakes, then field accuracy.
