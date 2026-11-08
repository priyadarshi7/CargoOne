"""The lorry receipt (consignment note) as a PDF, generated from the trip. One A4 page.

It carries what a consignee and a police check need: the LR number, route, parties, vehicle and driver, goods, e-way bill. The
freight amount is left off on purpose (the consignee should not see what the client pays). The printed copy is what the consignee
signs and stamps at delivery, and the photo of that signed copy is the POD. Built-in PDF fonts only cover Latin text, so names typed in
Devanagari print as blanks: type party names in English letters."""
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.billing.periods import IST


@dataclass
class LrItem:
    """One line of the goods table: a good with its own packages and weight."""
    name: str
    packages: int | None = None
    weight_tonnes: Decimal | None = None


@dataclass
class LrData:
    company: str
    lr_no: str
    trip_code: str
    issued_at: datetime
    branch: str | None
    origin: str
    destination: str
    consignor: str  # the client booking the load
    consignee: str | None
    vehicle: str
    driver: str | None
    driver_phone: str | None
    material: str | None
    packages: int | None
    weight_tonnes: Decimal | None
    eway_bill_no: str
    planned_start: datetime | None
    items: list[LrItem] | None = None  # one row per good; a trip books one total, so it prints a single row from material, packages and weight


def _cell(text: str | None) -> str:
    return text if text else "-"


def lr_story(d: LrData) -> list:
    ss = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=ss["Title"], alignment=0, fontSize=18, spaceAfter=0)
    small = ParagraphStyle("s", parent=ss["Normal"], textColor=colors.HexColor("#64748b"), fontSize=8.5)
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=10, leading=13)
    lab = ParagraphStyle("l", parent=ss["Normal"], fontSize=8, textColor=colors.HexColor("#64748b"))

    def box(label: str, value: str | None) -> list:
        return [Paragraph(label, lab), Paragraph(f"<b>{_cell(value)}</b>", body)]

    when = d.issued_at.astimezone(IST)
    rows = [
        [box("LR number", d.lr_no), box("Date", f"{when:%d %b %Y}"), box("Trip", d.trip_code)],
        [box("Consignor (booked by)", d.consignor), box("Consignee (receiver)", d.consignee), box("Branch", d.branch)],
        [box("From", d.origin), box("To", d.destination), box("Planned start", f"{d.planned_start.astimezone(IST):%d %b %Y, %H:%M}" if d.planned_start else None)],
        [box("Vehicle number", d.vehicle), box("Driver", d.driver), box("Driver phone", d.driver_phone)],
        [box("E-way bill number", d.eway_bill_no), box("Freight", "As per booking"), box("Payment", "As agreed with consignor")],
    ]
    grid = Table(rows, colWidths=[60 * mm, 60 * mm, 54 * mm])
    grid.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                              ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    sign = Table([[Paragraph("Consignor signature", lab), Paragraph("Driver signature", lab), Paragraph("Consignee signature, name and stamp (on delivery)", lab)]],
                 colWidths=[50 * mm, 50 * mm, 74 * mm], rowHeights=[34 * mm])
    sign.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "BOTTOM")]))

    # The goods table: what was booked, row by row and in total, and an empty "Received" cell beside every row for the receiver to write what
    # actually arrived (the weight or count of that good). Remarks below are only for shortage or damage. The photo reader looks for these labels.
    items = d.items or [LrItem(d.material or "-", d.packages, d.weight_tonnes)]
    pk = sum(i.packages or 0 for i in items)
    wt = sum((i.weight_tonnes or Decimal(0) for i in items), Decimal(0))
    head = [Paragraph(h, lab) for h in ("No.", "Goods", "Packages", "Weight (t)", "RECEIVED: write what arrived")]
    body_rows = [[Paragraph(str(n), body), Paragraph(f"<b>{i.name}</b>", body), Paragraph(f"<b>{i.packages or '-'}</b>", body),
                  Paragraph(f"<b>{i.weight_tonnes if i.weight_tonnes else '-'}</b>", body), ""] for n, i in enumerate(items, 1)]
    total = [["", Paragraph("<b>Total</b>", body), Paragraph(f"<b>{pk or '-'}</b>", body), Paragraph(f"<b>{wt if wt else '-'}</b>", body), Paragraph("Total received:", lab)]]
    goods = Table([head, *body_rows, *total], colWidths=[10 * mm, 66 * mm, 22 * mm, 24 * mm, 52 * mm],
                  rowHeights=[8 * mm, *[13 * mm] * len(body_rows), 13 * mm])
    goods.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")), ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f8fafc")),
                               ("BOX", (4, 0), (4, -1), 1.2, colors.HexColor("#64748b"))]))
    recv = Table([[Paragraph("Date received", lab), Paragraph("Remarks: shortage or damage, if any", lab)]],
                 colWidths=[50 * mm, 124 * mm], rowHeights=[24 * mm])
    recv.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [
        Paragraph(d.company, title), Paragraph("LORRY RECEIPT / CONSIGNMENT NOTE", small), Spacer(1, 5 * mm), grid, Spacer(1, 4 * mm), goods, Spacer(1, 4 * mm),
        Paragraph("Received the goods above in apparent good condition, except as noted. The consignee must write what actually arrived against each good, "
                  "then sign and stamp this copy on delivery; the driver then photographs the signed copy in the CargoOne app.", body),
        Spacer(1, 4 * mm), recv, Spacer(1, 3 * mm), sign, Spacer(1, 4 * mm),
        Paragraph(f"Generated by CargoOne on {datetime.now(IST):%d %b %Y, %H:%M}. LR number {d.lr_no} is unique to this consignment.", small),
    ]


def build_lr_pdf(d: LrData) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=12 * mm,
                            title=f"LR {d.lr_no}", author=d.company)
    doc.build(lr_story(d))
    return buf.getvalue()
