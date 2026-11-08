"""Printable Lorry Receipt sheets for benchmarking the POD reader on real paper.

Each page is the app's own LR (`app.lrdoc`), numbered like the app numbers them (LR/<branch>/<financial year>/<serial>), with the
receiver's part left empty: a person fills it by hand (quantity or weight received, remarks, stamp, signature) as the guide says, then
photographs the sheet. The serials start at 900001, far above anything the app will issue, so a test sheet can never be mistaken for a real LR.
`answers.csv` holds what a perfect reader should find and what the app should then do.
ALL NAMES, NUMBERS AND GSTINS ARE FAKE.

Run (from api/): .venv/Scripts/python -m app.devtools.lr_form ../docs/benchmark
"""
import csv
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, SimpleDocTemplate

from app.ai.base import PodExtraction, PodItem
from app.billing.periods import financial_year
from app.config import get_settings
from app.lr import lr_format
from app.lrdoc import LrData, LrItem, lr_story
from app.pod.decision import decide

FIRST_SERIAL = 900001
WRONG_TRIP_SERIAL = 900099  # the trip's number on the "wrong LR" sheet, which is not the number printed on the paper
ISSUED = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)


@dataclass(frozen=True)
class Booking:
    material: str
    packages: int | None
    weight_tonnes: float
    origin: str
    destination: str
    rows: tuple[tuple[str, int | None, float], ...] = ()  # (good, packages, tonnes) when the load has several goods


BOOKINGS = {
    "bags": Booking("PPC Cement 50 kg bags", 50, 2.5, "Chhatrapati Sambhajinagar", "Ahilyanagar"),
    "coils": Booking("MS Coils (HR)", 6, 18.0, "Jalna", "Pune - Chakan"),
    "two": Booking("PPC Cement + River Sand", None, 4.0, "Chhatrapati Sambhajinagar", "Beed", (("PPC Cement", None, 2.5), ("River Sand", None, 1.5))),
    "mixed": Booking("PPC Cement + River Sand", 50, 4.0, "Chhatrapati Sambhajinagar", "Beed", (("PPC Cement", 50, 2.5), ("River Sand", None, 1.5))),
}


@dataclass(frozen=True)
class Sheet:
    id: str
    title: str
    do: str  # what the person writes and does by hand
    stamp: bool = True
    sign: bool = True
    date: bool = True  # False = leave the date blank
    cargo: str = "bags"
    qty: str | None = "50 bags"  # the quantity text as written; None = left blank
    items: tuple[tuple[str, float, str], ...] = ()  # the same, line by line, when several goods
    total: str | None = None  # the written total, when there is one
    remark: str | None = None
    wrong_lr: bool = False  # the paper carries a different number from the trip's
    shortage_remark: bool = False
    judgement: bool = False  # a person could reasonably decide either way: the expectation is a recommendation


SHEETS = [
    Sheet("S01", "Clean, everything right", "Write the date, 50 bags, then stamp and sign."),
    Sheet("S02", "No stamp", "Write the date and 50 bags, sign. Do NOT stamp.", stamp=False),
    Sheet("S03", "No signature", "Write the date and 50 bags, stamp. Do NOT sign.", sign=False),
    Sheet("S04", "Receiver part left empty", "Fill nothing at all in the receiver part.", stamp=False, sign=False, date=False, qty=None),
    Sheet("S05", "Wrong LR number", "Fill everything correctly (as S01). The trip's LR ends 900099, but this paper carries another number.", wrong_lr=True),
    Sheet("S06", "Shortage remark and short count", "Date, quantity 44 bags, remark: Short 6 bags. Stamp, sign.", qty="44 bags", remark="Short 6 bags", shortage_remark=True),
    Sheet("S07", "Damage remark, full count", "Date, quantity 50 bags, remark: 2 bags torn / damaged. Stamp, sign.", remark="2 bags torn / damaged", shortage_remark=True),
    Sheet("S08", "Short count, nobody wrote a remark", "Date, quantity 40 bags, NO remark. Stamp, sign.", qty="40 bags"),
    Sheet("S09", "Weighed load, kg matches", "Date, quantity 18000 kg. Stamp, sign.", cargo="coils", qty="18000 kg"),
    Sheet("S10", "Weighed load, kg is much less", "Date, quantity 16000 kg, no remark. Stamp, sign.", cargo="coils", qty="16000 kg"),
    Sheet("S11", "Date left blank", "Quantity 50 bags. Stamp, sign. Leave the date blank.", date=False),
    Sheet("S12", "Remark in Hindi handwriting", "Date, 50 bags, remark in Hindi: 3 बोरी फटी हुई है. Stamp, sign.", remark="3 बोरी फटी हुई है", shortage_remark=True),
    Sheet("S13", "Remark in Marathi handwriting", "Date, 50 bags, remark in Marathi: २ गोणी ओल्या झाल्या. Stamp, sign.", remark="२ गोणी ओल्या झाल्या", shortage_remark=True),
    Sheet("S14", "Faint, half-cut stamp", "Date, 50 bags, sign. Press the stamp lightly so it is pale, and let it run off the edge of its box.", judgement=True),
    Sheet("S15", "Messy: stamp over the signature and date", "Date, 50 bags, sign, then stamp OVER the signature, the date and the quantity.", judgement=True),
    Sheet("S16", "A remark that is NOT a problem", "Date, 50 bags, remark: Received OK, thanks. Stamp, sign.", remark="Received OK, thanks"),
    Sheet("S17", "Two goods, each weight written, total matches", "Date. Received column: row 1 write 2.5 t, row 2 write 1.5 t, Total received 4 t. Stamp, sign.", cargo="two",
          qty="Cement 2.5 t, Sand 1.5 t, Total 4 t", items=(("Cement", 2.5, "t"), ("Sand", 1.5, "t")), total="4 t"),
    Sheet("S18", "Two goods, one short, honest total", "Date. Received: row 1 2.5 t, row 2 1.0 t, total 3.5 t. No remark. Stamp, sign.", cargo="two",
          qty="Cement 2.5 t, Sand 1.0 t, Total 3.5 t", items=(("Cement", 2.5, "t"), ("Sand", 1.0, "t")), total="3.5 t"),
    Sheet("S19", "Two goods, one short, with a remark", "Date. Received: row 1 2.5 t, row 2 1.0 t, total 3.5 t. Remark: Sand short 0.5 t. Stamp, sign.", cargo="two",
          qty="Cement 2.5 t, Sand 1.0 t, Total 3.5 t", items=(("Cement", 2.5, "t"), ("Sand", 1.0, "t")), total="3.5 t", remark="Sand short 0.5 t", shortage_remark=True),
    Sheet("S20", "Two goods, lines do not add up to the total", "Date. Received: row 1 2.5 t, row 2 1.5 t, total 5 t (a wrong total, as a rushed receiver might write). Stamp, sign.", cargo="two",
          qty="Cement 2.5 t, Sand 1.5 t, Total 5 t", items=(("Cement", 2.5, "t"), ("Sand", 1.5, "t")), total="5 t"),
    Sheet("S21", "Two goods in kilograms", "Date. Received: row 1 2500 kg, row 2 1500 kg, total 4000 kg. Stamp, sign.", cargo="two",
          qty="Cement 2500 kg, Sand 1500 kg, Total 4000 kg", items=(("Cement", 2500, "kg"), ("Sand", 1500, "kg")), total="4000 kg"),
    Sheet("S22", "Two goods in different units", "Date. Received: row 1 50 bags, row 2 1.5 t, leave the total blank. Stamp, sign.", cargo="mixed",
          qty="Cement 50 bags, Sand 1.5 t", items=(("Cement", 50, "bags"), ("Sand", 1.5, "t")), judgement=True),
]


def _lr(serial: int) -> str:
    return lr_format(get_settings().default_branch_code.upper(), financial_year(ISSUED), serial)


def trips_lr(i: int, sh: Sheet) -> str:
    return _lr(WRONG_TRIP_SERIAL if sh.wrong_lr else FIRST_SERIAL + i)


def paper_lr(i: int, sh: Sheet) -> str:
    return _lr(FIRST_SERIAL + 100 + i if sh.wrong_lr else FIRST_SERIAL + i)


def expected_extraction(sh: Sheet, lr: str) -> PodExtraction:
    return PodExtraction(
        is_document=True, readable=True, lr_no=lr, consignee_stamp_present=sh.stamp, signature_present=sh.sign,
        delivery_date="(today)" if sh.date else None, quantity_received=sh.qty, total_quantity=sh.total,
        items=[PodItem(name=n, quantity=q, unit=u) for n, q, u in sh.items], remarks=sh.remark, shortage_or_damage=sh.shortage_remark, confidence=0.95,
    )


def verdict(i: int, sh: Sheet):
    b = BOOKINGS[sh.cargo]
    return decide(expected_extraction(sh, paper_lr(i, sh)), expected_lr_no=trips_lr(i, sh), retake_count=0,
                  expected_packages=b.packages, expected_weight_tonnes=b.weight_tonnes)


def data(i: int, sh: Sheet) -> LrData:
    b = BOOKINGS[sh.cargo]
    return LrData(company="Demo Roadlines", lr_no=paper_lr(i, sh), trip_code=f"TRP-B{i + 1:03d}", issued_at=ISSUED, branch=get_settings().default_branch_code.upper(),
                  origin=b.origin, destination=b.destination, consignor="Shree Samarth Traders, Waluj", consignee="Om Sai Building Supplies",
                  vehicle="MH20 GC 4821", driver="Ramesh Yadav", driver_phone="9876500000", material=b.material, packages=b.packages,
                  weight_tonnes=Decimal(str(b.weight_tonnes)), eway_bill_no="281044172209", planned_start=None,
                  items=[LrItem(n, p, Decimal(str(w))) for n, p, w in b.rows] or None)


def build(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(out / "lr_forms.pdf"), pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=12 * mm,
                            title="Lorry Receipt benchmark sheets (sample data)")
    story: list = []
    for i, sh in enumerate(SHEETS):
        story += [*lr_story(data(i, sh)), PageBreak()]
    doc.build(story[:-1])
    with open(out / "answers.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sheet", "case", "lr_on_paper", "trips_expected_lr", "booked", "write_by_hand", "expected_stamp", "expected_signature",
                    "expected_date", "expected_quantity_text", "expected_items", "expected_total", "expected_remark", "expected_decision",
                    "expected_reasons", "judgement_call"])
        for i, sh in enumerate(SHEETS):
            b, v = BOOKINGS[sh.cargo], verdict(i, sh)
            booked = f"{b.packages or '-'} packages / {b.weight_tonnes} t"
            w.writerow([sh.id, sh.title, paper_lr(i, sh), trips_lr(i, sh), booked, sh.do, sh.stamp, sh.sign, "today" if sh.date else "blank",
                        sh.qty or "blank", "; ".join(f"{n} {q:g} {u}" for n, q, u in sh.items), sh.total or "", sh.remark or "none",
                        v.decision.value, " ".join(v.reasons), "yes" if sh.judgement else ""])


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "benchmark"))
    print(f"Wrote {len(SHEETS)} sheets")
