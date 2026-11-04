import io
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from decimal import Decimal

from PIL import Image

from app.billing.pdf import PdfTrip, build_invoice_pdf
from app.billing.periods import financial_year, period_of
from app.billing.tally import build_csv, build_tally_xml

D = lambda y, m, d, h=10: datetime(y, m, d, h, tzinfo=UTC)


def test_weekly_bucket_runs_monday_to_sunday() -> None:
    key_wed, label, _ = period_of("weekly", D(2026, 11, 4))  # Wed 4 Nov 2026
    key_sun, _, _ = period_of("weekly", D(2026, 11, 8))
    key_next_mon, _, _ = period_of("weekly", D(2026, 11, 9))
    assert key_wed == key_sun == "2026-11-02" and key_next_mon == "2026-11-09"
    assert label == "02 Nov – 08 Nov 2026"


def test_fortnightly_and_monthly_buckets() -> None:
    assert period_of("fortnightly", D(2026, 11, 15))[1] == "1–15 Nov 2026"
    assert period_of("fortnightly", D(2026, 11, 16))[1] == "16–30 Nov 2026"
    assert period_of("fortnightly", D(2026, 2, 20))[1] == "16–28 Feb 2026"
    assert period_of("monthly", D(2026, 11, 30))[1] == "November 2026"


def test_buckets_use_ist_not_utc() -> None:
    # 23:00 UTC on 15 Nov is already 16 Nov 04:30 in India
    assert period_of("fortnightly", D(2026, 11, 15, 23))[1] == "16–30 Nov 2026"


def test_indian_financial_year() -> None:
    assert financial_year(D(2026, 3, 31)) == "25-26"
    assert financial_year(D(2026, 4, 1)) == "26-27"
    assert financial_year(D(2026, 11, 5)) == "26-27"


def test_tally_xml_is_well_formed_balanced_and_escaped() -> None:
    xml = build_tally_xml(invoice_no="CO/26-27/00007", created_at=D(2026, 11, 5), party_ledger='Smith & Sons <Steel> "Ltd"',
                          sales_ledger="Freight Income", total=Decimal("64500.5"), lr_numbers=["LR-1", "LR-2"], company="Company A")
    root = ET.fromstring(xml.split("\n", 1)[1])  # parses => escaping is correct
    v = root.find(".//VOUCHER")
    assert v.get("VCHTYPE") == "Sales" and v.get("ACTION") == "Create"
    assert v.findtext("DATE") == "20261105" and v.findtext("VOUCHERNUMBER") == "CO/26-27/00007"
    assert v.findtext("PARTYLEDGERNAME") == 'Smith & Sons <Steel> "Ltd"'
    assert root.findtext(".//SVCURRENTCOMPANY") == "Company A"
    amounts = [Decimal(e.findtext("AMOUNT")) for e in v.findall("ALLLEDGERENTRIES.LIST")]
    assert amounts == [Decimal("-64500.50"), Decimal("64500.50")] and sum(amounts) == 0  # Dr party / Cr income


def test_tally_company_omitted_when_blank() -> None:
    xml = build_tally_xml(invoice_no="X", created_at=D(2026, 11, 5), party_ledger="P", sales_ledger="S",
                          total=Decimal(1), lr_numbers=["L"])
    assert "SVCURRENTCOMPANY" not in xml


def test_csv_neutralises_spreadsheet_formulas() -> None:
    out = build_csv([{"invoice_no": "I", "trip_code": "=HYPERLINK(\"http://evil\")", "lr_no": "+1", "freight": "10.00"}])
    assert "'=HYPERLINK" in out and "'+1" in out


def _jpeg() -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (300, 400), "white").save(b, "PNG")
    return b.getvalue()


def test_pdf_has_summary_plus_one_page_per_trip_and_survives_missing_image() -> None:
    trips = [PdfTrip("T1", "LR-1", "341000000001", "A to B", "MH20 AA 0001", "03 Nov 2026", Decimal(1000), _jpeg()),
             PdfTrip("T2", "LR-2", "341000000002", "A to C", "MH20 AA 0002", "03 Nov 2026", Decimal(2000), None)]
    pdf = build_invoice_pdf(company="Co", invoice_no="CO/26-27/00001", created_at=D(2026, 11, 5), client="Cl",
                            period_label="November 2026", trips=trips)
    assert pdf.startswith(b"%PDF")
    assert pdf.count(b"/Type /Page\n") + pdf.count(b"/Type /Page ") + pdf.count(b"/Type /Page>") >= 3
