"""Printable Lorry Receipt sheets for benchmarking the POD reader on real paper.

Prints one A4 page per test case. The consignor part is typed (like a real LR); the receiver's part at the bottom
is left empty on purpose: a person fills it by hand (stamp, signature, date, quantity, remark) as the guide says,
then photographs the sheet. `answers.csv` holds what a perfect reader should find and what the app should then do.
ALL NAMES, NUMBERS AND GSTINS ARE FAKE.

Run: .venv/Scripts/python -m app.devtools.lr_form ../docs/benchmark
"""
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from app.ai.base import PodExtraction
from app.pod.decision import decide

W, H = A4
M = 26  # page margin
INK = (0.1, 0.1, 0.1)
GRID = (0.45, 0.45, 0.45)


@dataclass(frozen=True)
class Sheet:
    id: str
    title: str
    do: str  # what the person fills in by hand
    stamp: bool = True
    sign: bool = True
    date: str | None = "today"  # what to write; None = leave blank
    qty: str | None = "match"  # "match" = the booked quantity; None = leave blank; or the exact text
    remark: str | None = None
    printed_lr: str | None = None  # defaults to BM-10<nn>
    expected_lr: str | None = None  # the trip's LR when it differs from the sheet (wrong-LR case)
    cargo: str = "bags"  # "bags" (counted) or "coils" (weighed)
    judgement: bool = False  # a human could reasonably decide either way; the expectation is a recommendation
    flags_shortage: bool = False  # does the remark mean shortage or damage


CARGO = {
    "bags": {"goods": "PPC Cement 50 kg bags", "packages": 50, "unit": "Bags", "weight": 2.5, "invoice": "INV/26-27/0412", "route": ("Chhatrapati Sambhajinagar", "Ahilyanagar")},
    "coils": {"goods": "MS Coils (HR)", "packages": 6, "unit": "Coils", "weight": 18.0, "invoice": "INV/26-27/0977", "route": ("Jalna", "Pune - Chakan")},
}

SHEETS = [
    Sheet("S01", "Clean, everything right", "Stamp, sign, write today's date, write 50 bags. No remark.", stamp=True, sign=True),
    Sheet("S02", "No stamp", "Sign and write date + 50 bags. Do NOT stamp.", stamp=False),
    Sheet("S03", "No signature", "Stamp and write date + 50 bags. Do NOT sign.", sign=False),
    Sheet("S04", "Receiver part left empty", "Fill nothing at all in the receiver part.", stamp=False, sign=False, date=None, qty=None),
    Sheet("S05", "Wrong LR number", "Fill everything correctly (as S01). The trip's LR is BM-1099, but this paper says another number.", expected_lr="BM-1099"),
    Sheet("S06", "Shortage remark and short count", "Stamp, sign, date. Quantity 44 bags. Remark: Short 6 bags", qty="44 bags", remark="Short 6 bags", flags_shortage=True),
    Sheet("S07", "Damage remark, full count", "Stamp, sign, date. Quantity 50 bags. Remark: 2 bags torn / damaged", remark="2 bags torn / damaged", flags_shortage=True),
    Sheet("S08", "Short count, nobody wrote a remark", "Stamp, sign, date. Quantity 40 bags. NO remark.", qty="40 bags"),
    Sheet("S09", "Weighed load, kg matches", "Stamp, sign, date. Quantity 18000 kg. No remark.", cargo="coils", qty="18000 kg"),
    Sheet("S10", "Weighed load, kg is much less", "Stamp, sign, date. Quantity 16000 kg. No remark.", cargo="coils", qty="16000 kg"),
    Sheet("S11", "Date left blank", "Stamp, sign, quantity 50 bags. Leave the date blank.", date=None),
    Sheet("S12", "Remark in Hindi handwriting", "Stamp, sign, date, 50 bags. Remark in Hindi: 3 बोरी फटी हुई है", remark="3 बोरी फटी हुई है", flags_shortage=True),
    Sheet("S13", "Remark in Marathi handwriting", "Stamp, sign, date, 50 bags. Remark in Marathi: २ गोणी ओल्या झाल्या", remark="२ गोणी ओल्या झाल्या", flags_shortage=True),
    Sheet("S14", "Faint, half-cut stamp", "Press the stamp lightly so it comes out pale, and let it run off the edge of the box. Sign, date, 50 bags.", judgement=True),
    Sheet("S15", "Messy: stamp over the signature and date", "Stamp over your signature AND over the date and quantity lines. Left-handed scribble is fine. 50 bags.", judgement=True),
    Sheet("S16", "A remark that is NOT a problem", "Stamp, sign, date, 50 bags. Remark: Received OK, thanks", remark="Received OK, thanks"),
]


def booked(sh: Sheet) -> dict:
    return CARGO[sh.cargo]


def lr_of(i: int, sh: Sheet) -> str:
    return sh.printed_lr or f"BM-{1000 + i + 1}"


def qty_text(sh: Sheet) -> str | None:
    if sh.qty == "match":
        return f"{booked(sh)['packages']} {booked(sh)['unit'].lower()}"
    return sh.qty


def expected_extraction(i: int, sh: Sheet) -> PodExtraction:
    return PodExtraction(
        is_document=True, readable=True, lr_no=lr_of(i, sh), consignee_stamp_present=sh.stamp, signature_present=sh.sign,
        delivery_date=None if sh.date is None else "(today)", quantity_received=qty_text(sh), remarks=sh.remark,
        shortage_or_damage=sh.flags_shortage, confidence=0.95,
    )


def verdict(i: int, sh: Sheet):
    b = booked(sh)
    return decide(expected_extraction(i, sh), expected_lr_no=sh.expected_lr or lr_of(i, sh), retake_count=0,
                  expected_packages=b["packages"], expected_weight_tonnes=b["weight"])


# --- drawing -----------------------------------------------------------------------------------------------

def box(c: Canvas, x: float, y: float, w: float, h: float, label: str = "", value: str = "", *, big: bool = False) -> None:
    c.setStrokeColorRGB(*GRID)
    c.setLineWidth(0.8)
    c.rect(x, y, w, h)
    if label:
        c.setFont("Helvetica", 6.8)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.drawString(x + 4, y + h - 9, label.upper())
    if value:
        c.setFillColorRGB(*INK)
        c.setFont("Helvetica-Bold" if big else "Helvetica", 15 if big else 10.5)
        c.drawString(x + 5, y + 6 if h < 30 else y + h / 2 - 8, value)


def page(c: Canvas, i: int, sh: Sheet) -> None:
    b = booked(sh)
    lr = lr_of(i, sh)
    origin, dest = b["route"]
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(1.6)
    c.rect(M, M, W - 2 * M, H - 2 * M)
    x0, wid = M + 6, W - 2 * M - 12

    # header
    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(x0 + 2, H - M - 32, "DEMO ROADLINES")
    c.setFont("Helvetica", 8)
    c.drawString(x0 + 2, H - M - 45, "Full Truck Load Contractors  |  Fleet Owners & Transport Agents")
    c.drawString(x0 + 2, H - M - 56, "Plot 14, MIDC Waluj, Chhatrapati Sambhajinagar 431136")
    c.drawString(x0 + 2, H - M - 67, "Ph 0240-0000000  |  GSTIN 27AAAAA0000A1Z5 (sample)")
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x0 + 2, H - M - 85, "LORRY RECEIPT / CONSIGNMENT NOTE")
    c.setFont("Helvetica", 8)
    c.drawString(x0 + 2, H - M - 97, "CONSIGNEE'S COPY (to be returned with the signed receipt)")

    top = H - M - 108
    # LR number
    box(c, x0 + wid - 190, H - M - 100, 190, 44, "LR No.", lr, big=True)

    # consignment details
    y = top - 36
    rows = [
        [("Date of LR", "03-11-2026"), ("Vehicle no.", "MH 20 GC 4821"), ("Driver", "Ramesh Yadav")],
        [("From", origin), ("To", dest), ("Freight", "To be billed")],
    ]
    for row in rows:
        cw = wid / 3
        for k, (lab, val) in enumerate(row):
            box(c, x0 + k * cw, y, cw, 32, lab, val)
        y -= 32
    box(c, x0, y - 32, wid / 2, 32, "Consignor (sender)", "Shree Samarth Traders, Waluj")
    box(c, x0 + wid / 2, y - 32, wid / 2, 32, "Consignee (receiver)", "Om Sai Building Supplies")
    y -= 32
    box(c, x0, y - 32, wid / 2, 32, "Invoice no.", b["invoice"])
    box(c, x0 + wid / 2, y - 32, wid / 2, 32, "E-way bill no.", "281 0 4417 2209")
    y -= 32

    # goods table
    cols = [("Packages", 70), ("Kind", 70), ("Description of goods", wid - 70 - 70 - 90 - 90), ("Actual weight", 90), ("Said to contain", 90)]
    x = x0
    c.setFont("Helvetica-Bold", 8)
    for name, cw in cols:
        box(c, x, y - 18, cw, 18)
        c.setFillColorRGB(*INK)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(x + 4, y - 12, name.upper())
        x += cw
    y -= 18
    vals = [str(b["packages"]), b["unit"], b["goods"], f"{b['weight']:.2f} t", "As per invoice"]
    x = x0
    for (name, cw), v in zip(cols, vals):
        box(c, x, y - 34, cw, 34)
        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(*INK)
        c.drawString(x + 5, y - 22, v)
        x += cw
    y -= 34
    c.setFont("Helvetica", 6.5)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawString(x0 + 2, y - 10, "Goods are carried at owner's risk. Subject to Chhatrapati Sambhajinagar jurisdiction. Please check the goods before signing.")
    y -= 20

    # receiver's acknowledgement (left empty for hand filling)
    c.setStrokeColorRGB(*INK)
    c.setLineWidth(1.4)
    c.line(x0, y, x0 + wid, y)
    c.setFillColorRGB(*INK)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x0 + 2, y - 15, "RECEIVER'S ACKNOWLEDGEMENT")
    c.setFont("Helvetica", 8.5)
    c.drawString(x0 + 2, y - 28, "Received the above goods in good order and condition, except as noted below.")
    y -= 36
    half = wid * 0.54
    rowh = 58
    for lab in ("Date received", "Quantity received"):
        box(c, x0, y - rowh, half, rowh, lab)
        y -= rowh
    box(c, x0, y - 3 * rowh, half, 3 * rowh, "Remarks (shortage / damage, if any)")
    c.setStrokeColorRGB(0.8, 0.8, 0.8)
    c.setLineWidth(0.6)
    for k in range(1, 3):
        c.line(x0 + 6, y - k * rowh, x0 + half - 6, y - k * rowh)
    # stamp and signature boxes to the right, as tall as the three boxes on the left together
    rx, rw = x0 + half + 6, wid - half - 6
    top_y = y + 2 * rowh
    box(c, rx, top_y - 170, rw, 170, "Consignee's stamp")
    box(c, rx, top_y - 5 * rowh, rw, 5 * rowh - 170, "Receiver's name and signature")

    c.setFont("Helvetica", 6.5)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    c.drawString(x0 + 2, M + 8, "Transporter's copy: LR book  |  Consignor's copy  |  Consignee's copy (this)")


def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(out / "lr_forms.pdf"), pagesize=A4)
    c.setTitle("Lorry Receipt benchmark sheets (sample data)")
    for i, sh in enumerate(SHEETS):
        page(c, i, sh)
        c.showPage()
    c.save()
    with open(out / "answers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sheet", "case", "lr_on_paper", "trips_expected_lr", "booked", "write_by_hand", "expected_stamp", "expected_signature",
                    "expected_date", "expected_quantity", "expected_remark", "expected_decision", "expected_reasons", "judgement_call"])
        for i, sh in enumerate(SHEETS):
            b, v = booked(sh), verdict(i, sh)
            w.writerow([sh.id, sh.title, lr_of(i, sh), sh.expected_lr or lr_of(i, sh), f"{b['packages']} {b['unit'].lower()} / {b['weight']} t",
                        sh.do, sh.stamp, sh.sign, "blank" if sh.date is None else "today", qty_text(sh) or "blank", sh.remark or "none",
                        v.decision.value, " ".join(v.reasons), "yes" if sh.judgement else ""])


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "benchmark"))
    print(f"Wrote {len(SHEETS)} sheets")
