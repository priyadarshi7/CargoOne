"""Daily trip import: parse + validate a CSV/XLSX of trips (pure functions, no database).

Accepted headers are forgiving (case, spaces, symbols ignored; common aliases). The client's own sample sheet
("Trip ID, Client, Vehicle, To, Freight ₹, POD Status, Remarks") imports as-is:
  - "Company B (cement)"   -> client "Company B"
  - "MH17 BY 3092 (hired)" -> vehicle MH17 BY 3092, marked hired
  - "POD Status" / "Remarks" are ignored (status is decided by the system from the actual POD photo)
"""
import csv
import io
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from app.billing.periods import IST

MAX_ROWS = 5000
MAX_BYTES = 2 * 1024 * 1024

ALIASES: dict[str, set[str]] = {
    "trip_code": {"tripid", "tripcode", "trip", "tripno", "tripnumber"},
    "client": {"client", "customer", "party", "clientname"},
    "vehicle": {"vehicle", "vehicleno", "vehiclenumber", "truck", "truckno", "regno", "registration"},
    "origin": {"origin", "from", "source"},
    "destination": {"destination", "to", "dest"},
    "freight": {"freight", "freightamount", "amount", "freightrs", "freightinr"},
    "lr_no": {"lrno", "lr", "lrnumber", "lrnum"},
    "eway_bill_no": {"ewaybillno", "ewaybill", "ewb", "ewbno", "ewaybillnumber"},
    "delivered_at": {"deliveredat", "deliverydate", "delivereddate", "delivered", "deliveredon"},
    "branch": {"branch", "branchname"},
    "driver_phone": {"driverphone", "drivermobile", "drivermob"},
    "consignee_name": {"consigneename", "consignee"},
    "consignee_phone": {"consigneephone", "consigneemobile"},
}
REQUIRED = ["trip_code", "client", "vehicle", "destination", "freight", "lr_no", "eway_bill_no"]
_BY_ALIAS = {a: field_ for field_, aliases in ALIASES.items() for a in aliases}

REG = re.compile(r"^([A-Z]{2})(\d{1,2})([A-Z]{1,3})(\d{4})$")
BH_REG = re.compile(r"^\d{2}BH\d{4}[A-Z]{1,2}$")


class ImportFileError(ValueError):
    """The file as a whole cannot be used (wrong type, too big, missing columns)."""


@dataclass
class ParsedTrip:
    row: int
    trip_code: str
    client: str
    client_raw: str
    vehicle: str  # normalised "MH20 EL 4521"
    is_hired: bool
    origin: str | None
    destination: str
    freight: Decimal
    lr_no: str
    eway_bill_no: str
    delivered_at: datetime | None = None
    branch: str | None = None
    driver_phone: str | None = None
    consignee_name: str | None = None
    consignee_phone: str | None = None


@dataclass
class RowError:
    row: int
    message: str
    trip_code: str | None = None


@dataclass
class ParseResult:
    trips: list[ParsedTrip] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    total: int = 0


def _key(header: str) -> str:
    return re.sub(r"[^a-z0-9]", "", header.lower())


def read_rows(data: bytes, filename: str) -> list[dict[str, str]]:
    """File bytes -> list of {canonical_field: text}. Raises ImportFileError for unusable files."""
    if len(data) > MAX_BYTES:
        raise ImportFileError("File is larger than 2 MB")
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        raw_rows = _xlsx(data)
    elif name.endswith((".csv", ".txt")):
        raw_rows = _csv(data)
    else:
        raise ImportFileError("Upload a .csv or .xlsx file")
    if not raw_rows:
        raise ImportFileError("The file is empty")
    header, body = raw_rows[0], raw_rows[1:]
    mapping = {i: _BY_ALIAS[_key(h)] for i, h in enumerate(header) if _key(h) in _BY_ALIAS}
    missing = [f for f in REQUIRED if f not in mapping.values()]
    if missing:
        raise ImportFileError("Missing column(s): " + ", ".join(missing))
    body = [r for r in body if any(c.strip() for c in r)]
    if len(body) > MAX_ROWS:
        raise ImportFileError(f"More than {MAX_ROWS} rows; split the file")
    return [{f: (r[i].strip() if i < len(r) else "") for i, f in mapping.items()} for r in body]


def _csv(data: bytes) -> list[list[str]]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("latin-1")
    sample = text[:2048]
    dialect = csv.excel_tab if sample.count("\t") > sample.count(",") else csv.excel
    return [list(r) for r in csv.reader(io.StringIO(text), dialect)]


def _xlsx(data: bytes) -> list[list[str]]:
    from openpyxl import load_workbook  # lazy: only needed for Excel files

    try:
        ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).active
    except Exception as e:  # corrupt or not an xlsx
        raise ImportFileError("Could not read the Excel file") from e
    out = []
    for row in ws.iter_rows(values_only=True):
        out.append(["" if c is None else (c.isoformat(sep=" ") if isinstance(c, datetime) else str(c)) for c in row])
    return out


def normalize_vehicle(text: str) -> tuple[str, bool] | None:
    """'mh17 by 3092 (hired)' -> ('MH17 BY 3092', True). None if it is not a plausible registration."""
    hired = bool(re.search(r"\(\s*hired\s*\)", text, re.IGNORECASE))
    core = re.sub(r"\(.*?\)", "", text)
    core = re.sub(r"[\s\-]", "", core).upper()
    if BH_REG.match(core):
        return core, hired
    m = REG.match(core)
    return (f"{m[1]}{m[2]} {m[3]} {m[4]}", hired) if m else None


def reg_key(reg: str) -> str:
    return re.sub(r"\s", "", reg).upper()


def _date(text: str) -> datetime | None:
    text = text.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=IST).astimezone(UTC)
        except ValueError:
            continue
    try:
        d = datetime.fromisoformat(text)
        return (d if d.tzinfo else d.replace(tzinfo=IST)).astimezone(UTC)
    except ValueError:
        raise ValueError(f"Date '{text}' not understood (use dd/mm/yyyy or yyyy-mm-dd)") from None


def _phone(text: str) -> str | None:
    digits = re.sub(r"\D", "", text)
    if not digits:
        return None
    digits = digits[-10:] if len(digits) > 10 else digits
    if len(digits) != 10:
        raise ValueError(f"Phone '{text}' must be a 10-digit mobile number")
    return digits


def parse(rows: list[dict[str, str]]) -> ParseResult:
    """Validate each row. Never raises for bad data: errors are collected per row (row numbers match the sheet:
    the header is row 1, so the first data row is row 2)."""
    res = ParseResult(total=len(rows))
    seen: dict[str, int] = {}
    for i, r in enumerate(rows):
        n = i + 2
        code = r.get("trip_code", "").strip()
        problems: list[str] = []
        if not code:
            problems.append("Trip ID is empty")
        elif code in seen:
            problems.append(f"Trip ID {code} appears twice in the file (first on row {seen[code]})")
        elif len(code) > 24:
            problems.append("Trip ID is longer than 24 characters")
        if code:
            seen.setdefault(code, n)

        client_raw = r.get("client", "")
        client = re.sub(r"\s*\(.*?\)\s*$", "", client_raw).strip()
        if not client:
            problems.append("Client is empty")
        veh = normalize_vehicle(r.get("vehicle", ""))
        if veh is None:
            problems.append(f"Vehicle '{r.get('vehicle', '')}' is not a valid registration (e.g. MH20 EL 4521)")
        if not r.get("destination", "").strip():
            problems.append("Destination is empty")
        freight = None
        try:
            freight = Decimal(re.sub(r"[,₹\s]|rs\.?", "", r.get("freight", ""), flags=re.IGNORECASE))
            if freight <= 0 or freight > Decimal(10000000):
                problems.append("Freight must be between 1 and 1,00,00,000")
        except InvalidOperation:
            problems.append(f"Freight '{r.get('freight', '')}' is not a number")
        lr = r.get("lr_no", "").strip()
        if not lr:
            problems.append("LR number is empty")
        elif len(lr) > 40:
            problems.append("LR number is longer than 40 characters")
        ewb = re.sub(r"\D", "", r.get("eway_bill_no", ""))
        if len(ewb) != 12:
            problems.append(f"E-way bill number must be 12 digits (got '{r.get('eway_bill_no', '')}')")

        optional: dict[str, object] = {}
        for name, parser in (("delivered_at", _date), ("driver_phone", _phone), ("consignee_phone", _phone)):
            try:
                optional[name] = parser(r.get(name, "")) if r.get(name, "") else None
            except ValueError as e:
                problems.append(str(e))

        if problems:
            res.errors.append(RowError(row=n, trip_code=code or None, message="; ".join(problems)))
            continue
        assert veh is not None and freight is not None
        res.trips.append(ParsedTrip(
            row=n, trip_code=code, client=client, client_raw=client_raw, vehicle=veh[0], is_hired=veh[1],
            origin=r.get("origin", "").strip() or None, destination=r["destination"].strip(), freight=freight,
            lr_no=lr, eway_bill_no=ewb, delivered_at=optional.get("delivered_at"),  # type: ignore[arg-type]
            branch=r.get("branch", "").strip() or None, driver_phone=optional.get("driver_phone"),  # type: ignore[arg-type]
            consignee_name=r.get("consignee_name", "").strip() or None,
            consignee_phone=optional.get("consignee_phone"),  # type: ignore[arg-type]
        ))
    return res


TEMPLATE_CSV = (
    "Trip ID,Client,Vehicle,Origin,Destination,Freight,LR No,E-way Bill No,Delivery Date,Branch,Driver Phone\n"
    "TRP-70001,Company B,MH20 EL 4521,Chhatrapati Sambhajinagar,Nagpur,38500,LR-90001,341009000011,,Chhatrapati Sambhajinagar,9000000001\n"
    "TRP-70002,Company D,MH17 BY 3092 (hired),Chhatrapati Sambhajinagar,Indore,41200,LR-90002,341009000022,05/11/2026,Pune,\n"
)
