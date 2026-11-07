"""Tally Prime import files. One Sales voucher per invoice: party ledger (Dr) / freight income ledger (Cr).

Checked by importing into a real Tally Prime (see tally_api.py and docs/13-tally-setup.md); Company A's own ledger names are still to be confirmed.
Ledger names (client `tally_ledger`, TALLY_SALES_LEDGER) must exist in Tally with identical spelling.
GST is not included; the accountant adds tax in Tally or we extend this once GST treatment is agreed.
"""
import csv
import io
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from app.billing.periods import IST


def _amount(v: Decimal) -> str:
    return f"{v:.2f}"


def build_tally_xml(*, invoice_no: str, created_at: datetime, party_ledger: str, sales_ledger: str,
                    total: Decimal, lr_numbers: Sequence[str], company: str = "") -> str:
    env = ET.Element("ENVELOPE")
    ET.SubElement(ET.SubElement(env, "HEADER"), "TALLYREQUEST").text = "Import Data"
    importdata = ET.SubElement(ET.SubElement(env, "BODY"), "IMPORTDATA")
    desc = ET.SubElement(importdata, "REQUESTDESC")
    ET.SubElement(desc, "REPORTNAME").text = "Vouchers"
    if company:
        ET.SubElement(ET.SubElement(desc, "STATICVARIABLES"), "SVCURRENTCOMPANY").text = company
    msg = ET.SubElement(ET.SubElement(importdata, "REQUESTDATA"), "TALLYMESSAGE", {"xmlns:UDF": "TallyUDF"})
    v = ET.SubElement(msg, "VOUCHER", {"VCHTYPE": "Sales", "ACTION": "Create", "OBJVIEW": "Accounting Voucher View"})
    ET.SubElement(v, "DATE").text = created_at.astimezone(IST).strftime("%Y%m%d")
    ET.SubElement(v, "VOUCHERTYPENAME").text = "Sales"
    ET.SubElement(v, "VOUCHERNUMBER").text = invoice_no
    ET.SubElement(v, "REFERENCE").text = invoice_no
    ET.SubElement(v, "PARTYLEDGERNAME").text = party_ledger
    ET.SubElement(v, "NARRATION").text = f"Freight for {len(lr_numbers)} LR: " + ", ".join(lr_numbers)[:900]

    def entry(ledger: str, positive: bool, amount: Decimal, party: bool = False) -> None:
        e = ET.SubElement(v, "ALLLEDGERENTRIES.LIST")
        ET.SubElement(e, "LEDGERNAME").text = ledger
        ET.SubElement(e, "ISDEEMEDPOSITIVE").text = "Yes" if positive else "No"
        if party:
            ET.SubElement(e, "ISPARTYLEDGER").text = "Yes"
        ET.SubElement(e, "AMOUNT").text = _amount(-amount if positive else amount)  # debit is negative in Tally

    entry(party_ledger, True, total, party=True)
    entry(sales_ledger, False, total)
    ET.indent(env)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(env, encoding="unicode")


def build_csv(rows: Sequence[dict]) -> str:
    cols = ["invoice_no", "trip_code", "lr_no", "eway_bill_no", "vehicle", "origin", "destination", "delivered_on", "freight"]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=cols, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        # Spreadsheet formula injection guard: values starting with = + - @ are prefixed with a quote.
        w.writerow({k: (f"'{v}" if isinstance(v, str) and v[:1] in "=+-@" else v) for k, v in r.items()})
    return out.getvalue()
