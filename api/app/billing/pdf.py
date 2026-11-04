"""Invoice PDF: summary page + one appendix page per trip with its POD photo attached.
A client that rejects invoices without proof gets the proof in the same file. No consignee personal data is printed."""
import io
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.billing.periods import IST


@dataclass
class PdfTrip:
    trip_code: str
    lr_no: str
    eway_bill_no: str
    route: str
    vehicle: str
    delivered_on: str
    freight: Decimal
    image: bytes | None  # the POD photo; None if the file is missing


def _inr(v: Decimal) -> str:
    return f"Rs. {v:,.2f}"  # the built-in PDF font has no rupee glyph


def build_invoice_pdf(*, company: str, invoice_no: str, created_at: datetime, client: str,
                      period_label: str | None, trips: Sequence[PdfTrip]) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm,
                            bottomMargin=18 * mm, title=f"Invoice {invoice_no}", author=company)
    ss = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=ss["Title"], alignment=0, fontSize=20, spaceAfter=2)
    muted = ParagraphStyle("m", parent=ss["Normal"], textColor=colors.HexColor("#64748b"), fontSize=9)
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=10)
    total = sum((t.freight for t in trips), Decimal(0))

    story: list = [
        Paragraph(company, h),
        Paragraph("Freight invoice (draft for review - not yet sent)", muted),
        Spacer(1, 8 * mm),
        Paragraph(f"<b>Invoice no.</b> {invoice_no} &nbsp;&nbsp; <b>Date</b> {created_at.astimezone(IST):%d %b %Y}", body),
        Paragraph(f"<b>Billed to</b> {client}" + (f" &nbsp;&nbsp; <b>Period</b> {period_label}" if period_label else ""), body),
        Spacer(1, 6 * mm),
    ]
    rows = [["Trip", "LR no.", "E-way bill", "Route", "Delivered", "Freight"]]
    rows += [[t.trip_code, t.lr_no, t.eway_bill_no, t.route, t.delivered_on, _inr(t.freight)] for t in trips]
    rows.append(["", "", "", "", "Total", _inr(total)])
    table = Table(rows, repeatRows=1, colWidths=[24 * mm, 24 * mm, 30 * mm, 42 * mm, 24 * mm, 28 * mm])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#0f172a")),
        ("LINEBELOW", (0, 1), (-1, -2), 0.25, colors.HexColor("#e2e8f0")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.HexColor("#0f172a")),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story += [table, Spacer(1, 6 * mm),
              Paragraph("Proof of delivery for each trip is attached on the following pages. GST is not included in this draft.", muted)]

    max_w, max_h = A4[0] - 36 * mm, A4[1] - 70 * mm
    for t in trips:
        story += [PageBreak(), Paragraph(f"Proof of delivery - {t.trip_code}", ss["Heading2"]),
                  Paragraph(f"LR {t.lr_no} &nbsp;|&nbsp; E-way bill {t.eway_bill_no} &nbsp;|&nbsp; {t.route} &nbsp;|&nbsp; {t.vehicle}", muted),
                  Spacer(1, 4 * mm)]
        if t.image is None:
            story.append(Paragraph("POD image unavailable.", body))
            continue
        with Image.open(io.BytesIO(t.image)) as im:
            rgb = im.convert("RGB")  # JPEG-encode so every format (PNG/WebP) embeds reliably
            w, hgt = rgb.size
            out = io.BytesIO()
            rgb.save(out, "JPEG", quality=88)
        scale = min(max_w / w, max_h / hgt)
        out.seek(0)
        story.append(RLImage(out, width=w * scale, height=hgt * scale))

    doc.build(story)
    return buf.getvalue()
