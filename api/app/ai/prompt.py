POD_PROMPT = """You are reading a photo of an Indian freight Lorry Receipt (LR) / Proof of Delivery (POD)
signed at the consignee's gate. Text may be English, Hindi (Devanagari) or Marathi, printed or handwritten.

Return ONLY JSON matching the schema. Rules:
- is_document: false if the photo is not a transport receipt / POD paper.
- readable: false if blurry, cropped, dark or glare makes the key fields unreadable.
- lr_no: the LR / consignment note number as written. The expected number is "{expected_lr_no}"; do not
  invent it - return what is actually printed, or null.
- consignee_stamp_present: a company / consignee rubber stamp or seal is visible on the receiving block.
- signature_present: a handwritten signature or initials of the receiver is visible.
- delivery_date: date of receipt as ISO yyyy-mm-dd, or null if not visible.
- quantity_received: quantity as written (e.g. "240 bags", "54 cartons"), or null.
- remarks: any handwritten remark verbatim (e.g. "short by 6 cartons"), or null.
- shortage_or_damage: true if remarks mention shortage, short, damage, damaged, leakage, broken, wet, torn
  (also Hindi/Marathi equivalents such as kam, toot, phoot, nuksan).
- confidence: 0..1 overall confidence in this extraction. Lower it when handwriting is unclear.
- issues: short English phrases for anything wrong (e.g. "stamp cut off").
Never guess a field you cannot see.
A black strip at the very bottom that reads "CargoOne" with a time and map position was added by the phone app: ignore it."""
