POD_PROMPT = """You are reading a photo of a freight Lorry Receipt (LR) that the receiver has filled in by hand at delivery. This is the proof of
delivery (POD). Text may be English, Hindi (Devanagari) or Marathi, printed or handwritten.

The paper has these parts:
- Printed at the top: LR number, date, parties, vehicle, route.
- A goods table with PRINTED booked columns (Packages, Weight) and a boxed column "RECEIVED: write what arrived" that the receiver fills in by
  hand, one cell per good, and a "Total received" cell under it. Never take the printed Packages or Weight columns as the received quantity.
- Below it: "Date received" and "Remarks: shortage or damage, if any", both handwritten.
- At the bottom, three boxes: "Consignor signature", "Driver signature" and "Consignee signature, name and stamp (on delivery)".

Return ONLY JSON matching the schema. Rules:
- is_document: false if the photo is not a transport receipt / POD paper.
- readable: false only if blur, darkness, glare or cropping make the LR number or the receiver's part unreadable. Untidy handwriting you can still read is readable.
- lr_no: the LR number as printed. The expected number is "{expected_lr_no}"; do not invent it - return what is actually printed, or null.
- consignee_stamp_present: an ink stamp or seal (round or square, any colour) is on the paper in the consignee's box.
- signature_present: handwriting by the RECEIVER (a signature, initials or a scribble) inside the box "Consignee signature, name and stamp". Signatures in
  the Consignor and Driver boxes are NOT the receiver's: ignore them. If the consignee's box has no handwriting, false.
- delivery_date: the handwritten "Date received" as ISO yyyy-mm-dd (day first: 8/11/26 is 2026-11-08), or null if it is blank. The printed LR date is not the delivery date.
- quantity_received: what the receiver wrote in the RECEIVED column, as written ("50 bags", "18000 kg"); for several goods all cells in one text
  ("Cement 2.5 t, Sand 1.5 t"). Null if the column is empty.
- items: when the receiver wrote one figure per good, one entry per RECEIVED cell: name (the good on that row), quantity (a number) and unit as written.
  Empty list when there is a single figure or none.
- total_quantity: the figure written in "Total received", only if something is written there, else null. Never add lines up yourself.
- remarks: the handwritten words in the Remarks box, verbatim. Null if the box is empty. The date is not a remark.
- shortage_or_damage: true if the remarks mention shortage, short, damage, damaged, leakage, broken, wet, torn, or the Hindi/Marathi words for them
  (kam, toot, phoot, nuksan, fatli, ole). A remark like "received OK" is false.
- confidence: 0..1 overall confidence in this extraction. Lower it when handwriting is unclear.
- issues: short English phrases for anything wrong (e.g. "stamp cut off").
Never guess a field you cannot see.
A black strip at the very bottom that reads "CargoOne" with a time and map position was added by the phone app: ignore it."""
