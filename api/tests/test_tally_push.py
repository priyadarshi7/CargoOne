"""Pushing an invoice into Tally Prime over its HTTP/XML port. Tally itself is faked, answering the way a real one was seen to answer
(an HTTP 200 even for a refusal, the reason in LINEERROR, a duplicate voucher created without complaint, a summary element also named VOUCHER)."""
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from httpx import AsyncClient

from app.billing import tally_api
from app.config import get_settings
from tests.test_invoice_lifecycle import invoiced

SUMMARY = "<CMPINFO><COMPANY>0</COMPANY><LEDGER>3</LEDGER><VOUCHER>4</VOUCHER></CMPINFO>"  # real Tally counts things with elements of the same names


class FakeTally:
    def __init__(self, companies: list[str] | None = None, period_days: tuple[int, int] = (-300, 60)) -> None:
        now = datetime.now(UTC).date()
        self.companies = ["Test Co"] if companies is None else companies
        self.start, self.end = now + timedelta(days=period_days[0]), now + timedelta(days=period_days[1])
        self.ledgers = {"Existing Sales": "Sales Accounts"}
        self.vouchers: list[dict] = []
        self.down = False
        self.reject_with: str | None = None

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("refused")
        body = req.content.decode()
        if "<ID>COCompanies</ID>" in body:
            rows = "".join(f'<COMPANY NAME="{c}"><NAME>{c}</NAME><STARTINGFROM>{self.start:%Y%m%d}</STARTINGFROM><ENDINGAT>{self.end:%Y%m%d}</ENDINGAT></COMPANY>' for c in self.companies)
            return self._data(rows)
        if "<ID>COLedgers</ID>" in body:
            return self._data("".join(f'<LEDGER NAME="{n}"><PARENT>{p}</PARENT></LEDGER>' for n, p in self.ledgers.items()) + '<LEDGER NAME="Odd"><PARENT>&#4; Primary</PARENT></LEDGER>')
        if "<ID>COVouchers</ID>" in body:
            ref = re.search(r'\$Reference = "([^"]*)"', body).group(1)
            return self._data("".join(f"<VOUCHER><DATE>{v['date']}</DATE><VOUCHERNUMBER>{v['number']}</VOUCHERNUMBER></VOUCHER>" for v in self.vouchers if v["ref"] == ref))
        if "<ID>All Masters</ID>" in body:
            m = re.search(r'<LEDGER NAME="([^"]+)" ACTION="Create"><NAME>[^<]*</NAME><PARENT>([^<]*)</PARENT>', body)
            self.ledgers[m.group(1)] = m.group(2)
            return httpx.Response(200, text="<ENVELOPE><BODY><DATA><IMPORTRESULT><CREATED>1</CREATED><ERRORS>0</ERRORS></IMPORTRESULT></DATA></BODY></ENVELOPE>")
        v = ET.fromstring(body).find(".//VOUCHER")  # a voucher import
        party, ref, date = v.findtext("PARTYLEDGERNAME"), v.findtext("REFERENCE"), v.findtext("DATE")
        if self.reject_with:
            return self._refused(self.reject_with)
        for ledger in (party, *(e.findtext("LEDGERNAME") for e in v.findall("ALLLEDGERENTRIES.LIST"))):
            if ledger not in self.ledgers:
                return self._refused(f"Ledger '{ledger}' does not exist!")
        self.vouchers.append({"ref": ref, "date": date, "number": str(40 + len(self.vouchers)), "party": party, "amount": v.findall("ALLLEDGERENTRIES.LIST")[1].findtext("AMOUNT")})
        return httpx.Response(200, text="<RESPONSE><CREATED>1</CREATED><ALTERED>0</ALTERED><ERRORS>0</ERRORS><EXCEPTIONS>0</EXCEPTIONS></RESPONSE>")

    @staticmethod
    def _data(rows: str) -> httpx.Response:
        return httpx.Response(200, text=f"<ENVELOPE><HEADER><STATUS>1</STATUS></HEADER><BODY><DESC>{SUMMARY}</DESC><DATA><COLLECTION>{rows}</COLLECTION></DATA></BODY></ENVELOPE>")

    @staticmethod
    def _refused(why: str) -> httpx.Response:
        return httpx.Response(200, text=f"<RESPONSE><LINEERROR>{why}</LINEERROR><CREATED>0</CREATED><ERRORS>0</ERRORS><EXCEPTIONS>1</EXCEPTIONS></RESPONSE>")


@pytest.fixture
def tally(monkeypatch: pytest.MonkeyPatch) -> FakeTally:
    fake = FakeTally()
    monkeypatch.setattr(tally_api, "TRANSPORT", httpx.MockTransport(fake))
    s = get_settings()
    monkeypatch.setattr(s, "tally_company", "")
    monkeypatch.setattr(s, "tally_sales_ledger", "Existing Sales")
    return fake


async def test_status_says_whether_tally_is_there_and_which_company_it_would_use(client: AsyncClient, driver: dict, tally: FakeTally) -> None:
    h, _, _ = await invoiced(client, driver)
    ok = (await client.get("/billing/tally/status", headers=h)).json()
    assert ok["reachable"] is True and ok["company"] == "Test Co" and ok["period_start"] and ok["detail"] is None
    tally.down = True
    off = (await client.get("/billing/tally/status", headers=h)).json()
    assert off["reachable"] is False and "not reachable" in off["detail"]
    tally.down, tally.companies = False, []
    assert "no company is open" in (await client.get("/billing/tally/status", headers=h)).json()["detail"]
    tally.companies = ["A", "B"]
    assert "TALLY_COMPANY" in (await client.get("/billing/tally/status", headers=h)).json()["detail"]


async def test_pushing_asks_before_creating_ledgers_then_sends_one_voucher_and_a_second_click_adds_nothing(client: AsyncClient, driver: dict, tally: FakeTally) -> None:
    h, _, inv = await invoiced(client, driver)
    url = f"/billing/invoices/{inv['id']}/tally/push"
    needs = await client.post(url, headers=h)
    assert needs.status_code == 409
    detail = needs.json()["detail"]
    assert detail["code"] == "ledgers_missing" and detail["missing"][0]["group"] == "Sundry Debtors" and tally.vouchers == []  # nothing is made without a yes

    first = await client.post(url, headers=h, json={"create_missing": True})
    assert first.status_code == 200 and first.json()["already"] is False and first.json()["voucher_no"] == "40" and first.json()["created_ledgers"]
    assert len(tally.vouchers) == 1 and tally.vouchers[0]["ref"] == inv["invoice_no"] and float(tally.vouchers[0]["amount"]) == 1000.0
    again = await client.post(url, headers=h, json={"create_missing": True})
    assert again.status_code == 200 and again.json()["already"] is True and again.json()["voucher_no"] == "40"
    assert len(tally.vouchers) == 1  # Tally would have taken a second one; we did not send it

    row = next(i for i in (await client.get("/billing/invoices", headers=h)).json() if i["id"] == inv["id"])
    assert row["tally_pushed_at"] and row["tally_voucher_no"] == "40"


async def test_each_refusal_comes_back_in_words_a_person_can_act_on(client: AsyncClient, driver: dict, tally: FakeTally) -> None:
    h, _, inv = await invoiced(client, driver)
    url = f"/billing/invoices/{inv['id']}/tally/push"
    tally.down = True
    gone = await client.post(url, headers=h, json={"create_missing": True})
    assert gone.status_code == 502 and "not reachable" in gone.json()["detail"]
    tally.down = False

    tally.start, tally.end = tally.start - timedelta(days=900), tally.end - timedelta(days=700)  # a period that ended long ago
    late = await client.post(url, headers=h, json={"create_missing": True})
    assert late.status_code == 409 and late.json()["detail"]["code"] == "voucher_date" and "outside Test Co's period" in late.json()["detail"]["message"]
    tally.start, tally.end = tally.start + timedelta(days=900), tally.end + timedelta(days=700)

    tally.reject_with = "Voucher date is missing for: 'Sales' voucher"
    edu = await client.post(url, headers=h, json={"create_missing": True})
    assert edu.status_code == 409 and edu.json()["detail"]["code"] == "voucher_date" and "Educational mode" in edu.json()["detail"]["message"]
    tally.reject_with = "Something else Tally disliked"
    other = await client.post(url, headers=h, json={"create_missing": True})
    assert other.status_code == 502 and "Something else Tally disliked" in other.json()["detail"]
    assert tally.vouchers == []

    wrong = get_settings()
    wrong.tally_company = "Other Co"
    try:
        no_such = await client.post(url, headers=h, json={"create_missing": True})
        assert no_such.status_code == 502 and "'Other Co' is not open" in no_such.json()["detail"]
    finally:
        wrong.tally_company = ""


async def test_a_different_voucher_date_can_be_chosen_when_the_invoice_date_is_not_usable(client: AsyncClient, driver: dict, tally: FakeTally) -> None:
    h, _, inv = await invoiced(client, driver)
    url = f"/billing/invoices/{inv['id']}/tally/push"
    tally.start, tally.end = tally.start - timedelta(days=900), tally.end - timedelta(days=700)  # the period ended long ago
    refused = await client.post(url, headers=h, json={"create_missing": True})
    assert refused.status_code == 409 and refused.json()["detail"]["period_end"] == tally.end.isoformat()
    chosen = tally.end - timedelta(days=1)
    ok = await client.post(url, headers=h, json={"create_missing": True, "voucher_date": chosen.isoformat()})
    assert ok.status_code == 200 and tally.vouchers[0]["date"] == f"{chosen:%Y%m%d}"  # booked on the date the person picked
    assert tally.vouchers[0]["ref"] == inv["invoice_no"]  # and still findable by the invoice number


async def test_only_billing_can_use_the_tally_connection(client: AsyncClient, driver: dict, tally: FakeTally) -> None:
    _, _, inv = await invoiced(client, driver)
    assert (await client.post(f"/billing/invoices/{inv['id']}/tally/push", headers=driver)).status_code == 403
    assert (await client.get("/billing/tally/status", headers=driver)).status_code == 403
    assert (await client.get("/billing/tally/status")).status_code == 401
