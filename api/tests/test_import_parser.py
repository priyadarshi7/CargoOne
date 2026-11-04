import io

import pytest
from openpyxl import Workbook

from app.imports.trips import ImportFileError, normalize_vehicle, parse, read_rows

# The client's own sample sheet, exactly as given in the brief
CLIENT_SHEET = (
    "Trip ID,Client,Vehicle,To,Freight ₹,POD Status,Remarks\n"
    "TRP-66120,Company B (cement),MH20 EL 4521,Nagpur,38500,Verified,None\n"
    "TRP-66134,Company C (steel),MH20 GT 7718,Pune,26000,Retake requested,Stamp not visible\n"
    "TRP-66141,Company D (packaged foods),MH17 BY 3092 (hired),Indore,41200,Needs review,Short by 6 cartons\n"
)


def with_lr_ewb(csv_text: str) -> bytes:
    """The client's sheet has no LR / e-way bill columns; the daily file must (brief: 'with LR and e-way bill numbers')."""
    lines = csv_text.strip().split("\n")
    out = [lines[0] + ",LR No,E-way Bill"]
    for i, ln in enumerate(lines[1:]):
        out.append(f"{ln},LR-9{i:04d},34100000{i:04d}")
    return ("\n".join(out) + "\n").encode()


def test_client_sample_sheet_imports_as_is() -> None:
    res = parse(read_rows(with_lr_ewb(CLIENT_SHEET), "trips.csv"))
    assert res.errors == [] and len(res.trips) == 3
    a, _, c = res.trips
    assert (a.client, a.vehicle, a.destination, str(a.freight)) == ("Company B", "MH20 EL 4521", "Nagpur", "38500")
    assert (c.client, c.vehicle, c.is_hired) == ("Company D", "MH17 BY 3092", True)  # "(hired)" recognised and stripped


def test_missing_lr_and_eway_columns_are_reported_clearly() -> None:
    with pytest.raises(ImportFileError, match=r"Missing column\(s\): lr_no, eway_bill_no"):
        read_rows(CLIENT_SHEET.encode(), "trips.csv")


@pytest.mark.parametrize(("raw", "expected"), [
    ("MH20 EL 4521", ("MH20 EL 4521", False)),
    ("mh20el4521", ("MH20 EL 4521", False)),
    ("MH-20-EL-4521", ("MH20 EL 4521", False)),
    ("MH9 A 1234 (hired)", ("MH9 A 1234", True)),
    ("22BH1234AA", ("22BH1234AA", False)),
])
def test_vehicle_normalisation(raw: str, expected: tuple[str, bool]) -> None:
    assert normalize_vehicle(raw) == expected


@pytest.mark.parametrize("raw", ["", "TRUCK-1", "MH20EL45", "12345678"])
def test_invalid_vehicles_rejected(raw: str) -> None:
    assert normalize_vehicle(raw) is None


def rows(**override) -> list[dict[str, str]]:
    base = {"trip_code": "TRP-1", "client": "Company B", "vehicle": "MH20 EL 4521", "destination": "Nagpur",
            "freight": "38500", "lr_no": "LR-1", "eway_bill_no": "341000000001"}
    return [{**base, **override}]


@pytest.mark.parametrize(("override", "fragment"), [
    ({"trip_code": ""}, "Trip ID is empty"),
    ({"client": ""}, "Client is empty"),
    ({"vehicle": "banana"}, "not a valid registration"),
    ({"destination": " "}, "Destination is empty"),
    ({"freight": "abc"}, "not a number"),
    ({"freight": "0"}, "between 1"),
    ({"freight": "-5"}, "between 1"),
    ({"lr_no": ""}, "LR number is empty"),
    ({"eway_bill_no": "12345"}, "12 digits"),
    ({"eway_bill_no": ""}, "12 digits"),
    ({"delivered_at": "yesterday"}, "not understood"),
    ({"driver_phone": "123"}, "10-digit"),
])
def test_each_bad_field_gives_a_specific_message(override: dict, fragment: str) -> None:
    res = parse(rows(**override))
    assert res.trips == [] and len(res.errors) == 1 and fragment in res.errors[0].message
    assert res.errors[0].row == 2  # header is row 1


def test_all_problems_in_a_row_are_reported_together() -> None:
    res = parse(rows(client="", freight="x", eway_bill_no="1"))
    assert res.errors[0].message.count(";") == 2


def test_duplicate_trip_ids_in_one_file_flagged_on_the_second_row() -> None:
    res = parse(rows() + rows(lr_no="LR-2"))
    assert len(res.trips) == 1 and res.errors[0].row == 3 and "twice" in res.errors[0].message


def test_formats_dates_phones_amounts() -> None:
    res = parse(rows(freight="₹ 38,500.50", eway_bill_no="3410 0000 0001", delivered_at="05/11/2026",
                     driver_phone="+91 98765-43210", consignee_phone="9000000099"))
    t = res.trips[0]
    assert str(t.freight) == "38500.50" and t.eway_bill_no == "341000000001"
    assert t.driver_phone == "9876543210" and t.delivered_at.isoformat() == "2026-11-04T18:30:00+00:00"  # 00:00 IST


def test_header_aliases_and_blank_rows_and_excel() -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["Trip No", "Customer", "Truck No", "Dest", "Amount", "L.R.", "EWB No"])
    ws.append(["T-9", "Company C", "MH20 GT 7718", "Pune", 26000, "LR-9", 341000000009])
    ws.append([None] * 7)  # blank spacer row is ignored
    buf = io.BytesIO()
    wb.save(buf)
    res = parse(read_rows(buf.getvalue(), "daily.xlsx"))
    assert res.errors == [] and res.trips[0].trip_code == "T-9" and res.trips[0].eway_bill_no == "341000000009"


@pytest.mark.parametrize(("data", "name", "fragment"), [
    (b"", "t.csv", "empty"),
    (b"a,b\n1,2\n", "t.pdf", ".csv or .xlsx"),
    (b"x" * (2 * 1024 * 1024 + 1), "t.csv", "2 MB"),
    (b"not an excel file", "t.xlsx", "Excel"),
])
def test_unusable_files(data: bytes, name: str, fragment: str) -> None:
    with pytest.raises(ImportFileError, match=fragment):
        read_rows(data, name)


def test_tab_separated_and_latin1_files_work() -> None:
    tsv = "Trip ID\tClient\tVehicle\tTo\tFreight\tLR\tEWB\nT1\tCompany B\tMH20 EL 4521\tNagpur\t100\tL1\t341000000001\n"
    assert parse(read_rows(tsv.encode(), "t.csv")).trips[0].trip_code == "T1"
    legacy = tsv.replace("Nagpur", "Nagpür").encode("latin-1")  # old Excel "CSV" exports are not UTF-8
    res = parse(read_rows(legacy, "t.csv"))
    assert res.errors == [] and res.trips[0].destination == "Nagpür"
