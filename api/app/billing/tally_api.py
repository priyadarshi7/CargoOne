"""Talks to a running Tally Prime over its HTTP/XML port (9000 by default, F1 Help > Settings > Connectivity), so billing can push an invoice
as a Sales voucher with one click instead of downloading a file and importing it by hand.

Everything here was checked against a real Tally Prime (Educational mode). What Tally does, which the code relies on:
- A bad import still answers HTTP 200; the reason is in <LINEERROR> and <CREATED> stays 0.
- It does NOT refuse a duplicate: the same voucher sent twice is created twice. So we look the voucher up by its Reference (our invoice number) first.
- A Sales voucher type set to auto-numbering ignores the number we send and uses its own. Our invoice number is kept in the voucher's Reference field.
- Vouchers must fall in the company's financial period; in Educational mode only the 1st, 2nd and last day of a month are accepted."""
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, time
from xml.sax.saxutils import escape

import httpx

from app.config import get_settings

TRANSPORT: httpx.AsyncBaseTransport | None = None  # tests put a fake Tally here
PARTY_GROUP = "Sundry Debtors"
SALES_GROUP = "Sales Accounts"


class TallyError(Exception):
    pass


class DateRejected(TallyError):
    """The voucher date cannot be used: outside the company's period, or a day Tally's Educational mode does not allow. The person can pick another date."""

    def __init__(self, message: str, period: tuple[date, date]) -> None:
        super().__init__(message)
        self.period = period


class LedgersMissing(TallyError):
    def __init__(self, missing: list[dict]) -> None:
        super().__init__("These ledgers are not in Tally yet: " + ", ".join(m["name"] for m in missing))
        self.missing = missing


async def _post(xml: str) -> ET.Element:
    url = get_settings().tally_url
    try:
        async with httpx.AsyncClient(timeout=25, transport=TRANSPORT) as http:
            r = await http.post(url, content=xml.encode("utf-8"), headers={"Content-Type": "text/xml; charset=utf-8"})
        r.raise_for_status()
    except httpx.HTTPError:
        raise TallyError(f"Tally is not reachable at {url}. Open Tally Prime with a company loaded and switch the connection on (F1 Help > Settings > Connectivity).") from None
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", r.content.decode("utf-8", "replace"))
    text = re.sub(r"&#(?:x0*[0-9a-fA-F]|x0*1[0-9a-fA-F]|0*[0-9]|0*1[0-9]|0*2[0-9]|0*3[01]);", "", text)  # Tally writes internal markers as &#4; (invalid XML)
    try:
        return ET.fromstring(text)
    except ET.ParseError:
        raise TallyError("Tally sent an answer we could not read") from None


def _d(v: str | None) -> date | None:
    try:
        return datetime.strptime((v or "").strip(), "%Y%m%d").date()
    except ValueError:
        return None


def _q(s: str) -> str:
    """A value placed inside a TDL formula string."""
    if '"' in s:
        raise TallyError("A name with a double quote cannot be sent to Tally")
    return escape(s)


def _collection(name: str, kind: str, fields: list[str], company: str | None, formula: str | None = None, period: tuple[date, date] | None = None) -> str:
    vars_ = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
    if company:
        vars_ += f"<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY>"
    if period:
        vars_ += f"<SVFROMDATE>{period[0]:%Y%m%d}</SVFROMDATE><SVTODATE>{period[1]:%Y%m%d}</SVTODATE>"
    native = "".join(f"<NATIVEMETHOD>{f}</NATIVEMETHOD>" for f in fields)
    filt = "<FILTER>COFilter</FILTER>" if formula else ""
    sysf = f'<SYSTEM TYPE="Formulae" NAME="COFilter">{formula}</SYSTEM>' if formula else ""
    return (f'<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>{name}</ID></HEADER><BODY><DESC>'
            f'<STATICVARIABLES>{vars_}</STATICVARIABLES><TDL><TDLMESSAGE><COLLECTION NAME="{name}" ISMODIFY="No"><TYPE>{kind}</TYPE>{native}{filt}</COLLECTION>{sysf}</TDLMESSAGE></TDL>'
            f'</DESC></BODY></ENVELOPE>')


async def companies() -> list[dict]:
    root = await _post(_collection("COCompanies", "Company", ["Name", "StartingFrom", "EndingAt"], None))
    out = []
    for c in root.iterfind(".//DATA//COMPANY"):
        name = (c.findtext("NAME") or c.get("NAME") or "").strip()
        if name:
            out.append({"name": name, "start": _d(c.findtext("STARTINGFROM")), "end": _d(c.findtext("ENDINGAT"))})
    return out


async def resolve_company() -> dict:
    """The company vouchers go into: TALLY_COMPANY if set, otherwise the only company that is open."""
    found, want = await companies(), get_settings().tally_company.strip()
    if not found:
        raise TallyError("Tally is running but no company is open. Open the company in Tally Prime first.")
    if want:
        hit = next((c for c in found if c["name"].lower() == want.lower()), None)
        if hit is None:
            raise TallyError(f"The company '{want}' is not open in Tally. Open companies: {', '.join(c['name'] for c in found)}.")
        return hit
    if len(found) > 1:
        raise TallyError("Several companies are open in Tally: set TALLY_COMPANY in .env to the one invoices belong in.")
    return found[0]


async def ledgers(company: str) -> dict[str, str]:
    """Lower-case name -> parent group."""
    root = await _post(_collection("COLedgers", "Ledger", ["Name", "Parent"], company))
    return {(le.get("NAME") or "").strip().lower(): (le.findtext("PARENT") or "").strip() for le in root.iterfind(".//DATA//LEDGER") if le.get("NAME")}


async def vouchers_with_reference(company: str, reference: str, period: tuple[date, date]) -> list[dict]:
    """Vouchers already in Tally carrying this reference (our invoice number)."""
    root = await _post(_collection("COVouchers", "Voucher", ["Reference", "VoucherNumber", "Date"], company, f'$Reference = "{_q(reference)}"', period))
    return [{"number": (v.findtext("VOUCHERNUMBER") or "").strip(), "date": _d(v.findtext("DATE"))} for v in root.iterfind(".//DATA//VOUCHER")]


async def create_ledger(company: str, name: str, parent: str) -> None:
    xml = ('<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Import</TALLYREQUEST><TYPE>Data</TYPE><ID>All Masters</ID></HEADER><BODY><DESC><STATICVARIABLES>'
           f'<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY></STATICVARIABLES></DESC><DATA><TALLYMESSAGE xmlns:UDF="TallyUDF">'
           f'<LEDGER NAME="{escape(name, {chr(34): "&quot;"})}" ACTION="Create"><NAME>{escape(name)}</NAME><PARENT>{escape(parent)}</PARENT></LEDGER></TALLYMESSAGE></DATA></BODY></ENVELOPE>')
    root = await _post(xml)
    if int(root.findtext(".//CREATED") or 0) < 1:
        raise TallyError(f"Tally would not create the ledger '{name}': {root.findtext('.//LINEERROR') or 'no reason given'}")


async def import_voucher(xml: str, voucher_date: date, period: tuple[date, date]) -> None:
    root = await _post(xml)
    if int(root.findtext("CREATED") or 0) >= 1:
        return
    why = (root.findtext("LINEERROR") or "").strip()
    if "date" in why.lower():
        raise DateRejected(f"Tally did not accept the voucher date {voucher_date:%d-%b-%Y}. It must be inside the company's period ({period[0]:%d-%b-%Y} to {period[1]:%d-%b-%Y}); "
               "in Tally's Educational mode only the 1st, 2nd and last day of a month are allowed.", period)
    raise TallyError(why or "Tally did not create the voucher")


async def status() -> dict:
    """For the Billing page: is Tally there, and which company would an invoice go into."""
    try:
        c = await resolve_company()
    except TallyError as e:
        return {"reachable": False, "company": None, "period_start": None, "period_end": None, "detail": str(e), "url": get_settings().tally_url}
    return {"reachable": True, "company": c["name"], "period_start": c["start"], "period_end": c["end"], "detail": None, "url": get_settings().tally_url}


async def push_invoice(*, invoice_no: str, created_at: datetime, party: str, sales: str, total, lr_numbers: list[str], create_missing: bool, voucher_date: date | None = None) -> dict:
    """One Sales voucher in Tally for an invoice, sent once. Returns {voucher_no, already, created}. Raises TallyError (LedgersMissing when the
    party or sales ledger must be made first and the person has not said yes)."""
    from app.billing.periods import IST
    from app.billing.tally import build_tally_xml

    company = await resolve_company()
    when = voucher_date or created_at.astimezone(IST).date()  # the invoice's own date unless the person picked another
    if not (company["start"] and company["end"]):
        raise TallyError("Tally did not say what period the company covers")
    period = (company["start"], company["end"])
    if not (period[0] <= when <= period[1]):
        raise DateRejected(f"The voucher date {when:%d-%b-%Y} is outside {company['name']}'s period ({period[0]:%d-%b-%Y} to {period[1]:%d-%b-%Y}). Pick a date inside it, or open the right company in Tally.", period)

    already = await vouchers_with_reference(company["name"], invoice_no, period)
    if already:  # Tally does not refuse a duplicate, so the second click must not create one
        return {"voucher_no": already[0]["number"], "already": True, "created": [], "company": company["name"]}

    have = await ledgers(company["name"])
    need = [{"name": n, "group": g} for n, g in ((party, PARTY_GROUP), (sales, SALES_GROUP)) if n.lower() not in have]
    if need and not create_missing:
        raise LedgersMissing(need)
    for m in need:
        await create_ledger(company["name"], m["name"], m["group"])

    xml = build_tally_xml(invoice_no=invoice_no, created_at=datetime.combine(when, time(12), tzinfo=IST), party_ledger=party, sales_ledger=sales, total=total, lr_numbers=lr_numbers, company=company["name"])
    await import_voucher(xml, when, period)
    made = await vouchers_with_reference(company["name"], invoice_no, period)
    return {"voucher_no": made[0]["number"] if made else "", "already": False, "created": [m["name"] for m in need], "company": company["name"]}
