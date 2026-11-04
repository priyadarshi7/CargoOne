"""The MD's digest: the dashboard's own numbers on one printable page, in plain language.
Takes the dict `compute()` already returns, so the PDF can never disagree with the screen. Aggregates only, no
consignee personal data. (The built-in PDF font has no rupee glyph, hence "Rs.")"""
import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

INK, MUTED, LINE = colors.HexColor("#0f172a"), colors.HexColor("#64748b"), colors.HexColor("#e2e8f0")
OK, BAD = colors.HexColor("#15803d"), colors.HexColor("#b91c1c")


def _rs(v: float | None) -> str:
    if v is None:
        return "-"
    if v >= 1e7:
        return f"Rs. {v / 1e7:.2f} crore"
    if v >= 1e5:
        return f"Rs. {v / 1e5:.1f} lakh"
    return f"Rs. {v:,.0f}"


def _num(v: float | None, unit: str = "") -> str:
    return "-" if v is None else f"{v:g}{unit}"


def _status(value: float | None, target: float, *, lower_is_better: bool) -> tuple[str, colors.Color]:
    if value is None:
        return "no data yet", MUTED
    good = value <= target if lower_is_better else value >= target
    return ("on target", OK) if good else ("off target", BAD)


def build_digest_pdf(d: dict, *, company: str) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"{company} - POD digest", author=company)
    base = getSampleStyleSheet()["Normal"]
    h1 = ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=INK)
    h2 = ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=14, textColor=INK, spaceBefore=14, spaceAfter=4)
    small = ParagraphStyle("small", parent=base, fontSize=9, leading=12, textColor=MUTED)
    body = ParagraphStyle("body", parent=base, fontSize=10, leading=14, textColor=INK)

    k, t, wc, miss, pipe = d["kpis"], d["targets"], d["working_capital"], d["missing"], d["pipeline"]
    as_of = datetime.fromisoformat(d["as_of"]).strftime("%d %b %Y")
    out = [Paragraph(f"{company}", small), Paragraph("POD digest", h1),
           Paragraph(f"Last {d['window_days']} days, as of {as_of}. {k['trips_in_window']} trips delivered"
                     f"{' (includes demo data)' if d.get('includes_demo_data') else ''}.", small)]

    # Headline in a sentence a busy person can act on
    d24, days = k["within_24h_pct"], k["pod_to_invoice_days"]
    if d24 is not None and days is not None:
        out += [Spacer(1, 8), Paragraph(
            f"<b>{d24:g}%</b> of PODs reached the system within 24 hours (target {t['within_24h_pct']:g}%). "
            f"Invoices went out <b>{days:g} days</b> after delivery on average (was {t['baseline_pod_to_invoice_days']:g}, target {t['pod_to_invoice_days']:g}).", body)]

    rows = [["Measure", "Now", "Target", ""]]
    marks: list[tuple[int, colors.Color]] = []
    for i, (label, val, target, unit, lower) in enumerate([
        ("PODs in system within 24 h", k["within_24h_pct"], t["within_24h_pct"], "%", False),
        ("POD to invoice (days)", k["pod_to_invoice_days"], t["pod_to_invoice_days"], "", True),
        ("Lost or disputed PODs", k["lost_pct"], t["lost_pct"], "%", True),
    ], start=1):
        text, col = _status(val, target, lower_is_better=lower)
        rows.append([label, _num(val, unit), _num(target, unit), text])
        marks.append((i, col))
    kt = Table(rows, colWidths=[78 * mm, 28 * mm, 28 * mm, 40 * mm])
    style = [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9.5), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("ALIGN", (1, 0), (2, -1), "RIGHT"), ("ALIGN", (3, 0), (3, -1), "RIGHT"),
             ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    style += [("TEXTCOLOR", (3, i), (3, i), col) for i, col in marks]
    kt.setStyle(TableStyle(style))
    out += [Paragraph("Against target", h2), kt]

    out += [Paragraph("Money", h2), Paragraph(
        f"Working capital released by faster billing: <b>{_rs(wc['released'])}</b> a year"
        + (f" (about {_rs(wc['interest_saved_per_year'])} saved in interest at {wc['interest_rate'] * 100:g}%)." if wc["interest_saved_per_year"] else ".")
        + f"<br/>Ready to bill now: <b>{pipe['ready_to_bill']}</b> trips worth <b>{_rs(pipe['ready_to_bill_amount'])}</b>. "
        f"Waiting for a person to review: <b>{pipe['awaiting_review']}</b>.", body)]

    out += [Paragraph("Missing PODs", h2), Paragraph(
        f"<b>{miss['total']}</b> deliveries have no accepted POD yet, worth <b>{_rs(miss['amount'])}</b>. "
        f"<b>{_rs(miss['at_risk_amount'])}</b> is at risk (missing for over a week, or lost).", body), Spacer(1, 4)]
    bt = Table([[b["label"] for b in miss["buckets"]], [str(b["count"]) for b in miss["buckets"]]], colWidths=[28 * mm] * len(miss["buckets"]), hAlign="LEFT")
    bt.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, 0), 8.5), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED), ("FONTSIZE", (0, 1), (-1, 1), 14),
                            ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"), ("ALIGN", (0, 0), (-1, -1), "LEFT")]))
    out.append(bt)

    if d["branches"]:
        rows = [["Branch", "Trips", "In 24 h", "To invoice", "Missing", "Missing value"]] + [
            [b["branch"], str(b["trips"]), _num(b["within_24h_pct"], "%"), _num(b["pod_to_invoice_days"], " d"), str(b["missing"]), _rs(b["missing_amount"])]
            for b in d["branches"]]
        bt2 = Table(rows, colWidths=[45 * mm, 16 * mm, 22 * mm, 26 * mm, 20 * mm, 45 * mm])
        bt2.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                                 ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                                 ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        out += [Paragraph("Branches", h2), bt2]

    if d["oldest_missing"]:
        rows = [["Trip", "Client", "Branch", "Days", "Value"]] + [
            [m["trip_code"], m["client"], m["branch"], str(m["age_days"]), _rs(m["freight"])] for m in d["oldest_missing"][:5]]
        ot = Table(rows, colWidths=[28 * mm, 50 * mm, 40 * mm, 16 * mm, 40 * mm])
        ot.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 9), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                                ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("ALIGN", (3, 0), (4, -1), "RIGHT"),
                                ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        out += [Paragraph("Oldest missing PODs (chase these first)", h2), ot]

    out += [Spacer(1, 14), Paragraph("Figures are computed from delivered trips in the period. Working capital uses the annualised freight of those trips.", small)]
    doc.build(out)
    return buf.getvalue()
