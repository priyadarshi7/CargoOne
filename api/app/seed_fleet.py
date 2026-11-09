"""A realistic fleet for demos and recordings. ALL DATA IS FABRICATED: invented company names, invented people, invented numbers.
Nothing here belongs to a real person, vehicle or business, and the phone numbers are in a block we use only for fake data. Dev/test only.

A small, believable company (the brief describes 140 own and about 200 hired trucks; this is the same shape at a size you can follow by eye): 8 own
trucks and 8 hired ones from 6 transporters, their drivers with licence numbers and expiry dates, 5 clients with a billing contact, GSTIN and Tally
ledger, and a few more office people. Some papers expire soon and a few have expired,
so the document alerts have something to show.

  uv run python -m app.seed       # first: branches, the three brief clients, the demo logins
  uv run python -m app.seed_fleet # this: the fleet, vendors, drivers, more clients (safe to run again)
"""
import asyncio
import random
import string
import sys
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal
from app.models import Branch, Client, Role, Trip, User, Vehicle, Vendor
from app.security import hash_secret

OWN, HIRED = 8, 8  # a small company that is easy to follow: 8 own trucks and 8 hired ones (the brief's real fleet is 140 and about 200)
FIRST = ["Ramesh", "Suresh", "Mahesh", "Ganesh", "Dinesh", "Rajesh", "Santosh", "Prakash", "Anil", "Sunil", "Vijay", "Sanjay", "Ajay", "Ashok", "Deepak",
         "Kailas", "Bhaskar", "Nitin", "Sachin", "Rahul", "Vishal", "Pravin", "Yogesh", "Amol", "Datta", "Balaji", "Sandeep", "Manoj", "Rakesh", "Mukesh",
         "Gopal", "Harish", "Kishor", "Laxman", "Namdev", "Omkar", "Pandurang", "Shivaji", "Tukaram", "Uttam", "Vikram", "Waman", "Raju", "Jagdish", "Imran", "Farooq"]
LAST = ["Patil", "Jadhav", "Shinde", "Pawar", "More", "Gaikwad", "Kale", "Deshmukh", "Chavan", "Bhosale", "Kadam", "Salunke", "Wagh", "Thorat", "Sonawane",
        "Yadav", "Singh", "Sharma", "Verma", "Khan", "Shaikh", "Ansari", "Rathod", "Pathan", "Mane", "Jagtap", "Nikam", "Kharat", "Gawande", "Borse"]
VENDORS = ["Shree Ganesh Roadlines", "Jai Bhavani Transport", "Maa Tulja Carriers", "Sai Krupa Logistics", "Bhagyashree Roadways", "Khandoba Transport Co.",
           "Om Sai Cargo", "Renuka Roadlines", "Ambika Transport", "Vitthal Carriers", "Gajanan Logistics", "Mahalaxmi Road Carriers", "Siddhivinayak Transport",
           "Balaji Cargo Movers", "Hanuman Roadways", "Datta Transport Service", "Yash Logistics", "Pratik Roadlines", "Kailash Transport", "Laxmi Narayan Carriers",
           "New Punjab Roadways", "Rajdhani Transport Co.", "Marwar Cargo", "Deccan Freight Lines"]
TYPES = [("Open truck 10 t", 10), ("Open truck 16 t", 16), ("10-wheeler 25 t", 25), ("Trailer 32 t", 32), ("Container 32 ft", 18), ("Tipper 20 t", 20)]
HIRED_STATES = ["MH20"] * 8 + ["MH17", "MH14", "MH12", "MH26", "MH31", "MH04", "MH15"] * 2 + ["MP09", "GJ05", "TG09", "CG04", "KA25", "RJ14"]
CLIENTS = [  # the brief names B, C, D; three more of the same kinds
    ("Company B", "cement", "weekly", "Anita Kulkarni"), ("Company C", "steel", "fortnightly", "Vivek Joshi"), ("Company D", "packaged foods", "monthly", "Meera Nair"),
    ("Company E", "cement", "weekly", "Rohit Agarwal"), ("Company F", "steel", "weekly", "Sunita Rao"), ("Company G", "packaged goods", "fortnightly", "Imran Qureshi"),
]
OFFICE = [  # (email, name, role, branch code)
    ("ops.pune@cargoone.dev", "Kavita Deshpande", Role.ops, "MH12"), ("ops.nagpur@cargoone.dev", "Rajendra Bhoyar", Role.ops, "MH11"),
    ("billing.pune@cargoone.dev", "Nilesh Gokhale", Role.billing, "MH12"), ("billing.hq@cargoone.dev", "Pooja Mundada", Role.billing, "MH20"),
    ("billing.nagpur@cargoone.dev", "Satish Wankhede", Role.billing, "MH11"),
]


def _guard() -> None:
    if not get_settings().is_dev:
        raise RuntimeError("Refusing to create demo fleet: APP_ENV is not dev/test")


def _name(rnd: random.Random) -> str:
    return f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"


def _code(rnd: random.Random, n: int, alphabet: str = string.ascii_uppercase + string.digits) -> str:
    return "".join(rnd.choice(alphabet) for _ in range(n))


def _expiry(rnd: random.Random, today: date) -> date:
    """Mostly comfortably in the future; some due within a month; a few already past (so the alerts have something to show)."""
    roll = rnd.random()
    if roll < 0.01:
        return today - timedelta(days=rnd.randint(2, 40))
    if roll < 0.045:
        return today + timedelta(days=rnd.randint(1, 28))
    return today + timedelta(days=rnd.randint(60, 700))


def _reg(rnd: random.Random, state: str, taken: set[str]) -> str:
    while True:
        reg = f"{state} {rnd.choice(string.ascii_uppercase)}{rnd.choice(string.ascii_uppercase)} {rnd.randint(1000, 9999)}"
        if reg not in taken:
            taken.add(reg)
            return reg


def _papers(rnd: random.Random, today: date, reg: str, owner: str) -> dict:
    kind, cap = rnd.choice(TYPES)
    return {
        "vehicle_type": kind, "capacity_tonnes": Decimal(cap), "owner_name": owner, "rc_no": reg.replace(" ", ""),
        "registration_date": today - timedelta(days=rnd.randint(300, 3800)), "chassis_no": "MAT" + _code(rnd, 14), "engine_no": _code(rnd, 12),
        "insurance_no": f"POL/{today.year}/{rnd.randint(10**7, 10**8 - 1)}", "insurance_expiry": _expiry(rnd, today), "fitness_expiry": _expiry(rnd, today),
        "permit_expiry": _expiry(rnd, today), "puc_expiry": _expiry(rnd, today),
    }


def _licence(rnd: random.Random, today: date, rto: str) -> dict:
    issued = rnd.randint(2008, 2023)
    return {"licence_no": f"{rto[:2]}{rto[2:]}{issued}{rnd.randint(10**6, 10**7 - 1)}", "licence_expiry": _expiry(rnd, today) if rnd.random() < 0.9 else today + timedelta(days=rnd.randint(900, 5000))}


async def seed_fleet(session: AsyncSession) -> dict:
    _guard()
    rnd = random.Random(2026)
    today = date.today()
    branches = {b.code: b for b in (await session.scalars(select(Branch))).all() if b.code}
    if not branches:
        raise SystemExit("Run `uv run python -m app.seed` first.")
    hq = branches.get("MH20") or next(iter(branches.values()))
    order = [branches.get(c) or hq for c in ("MH20", "MH12", "MH11")]
    pin = hash_secret("1234")
    made = {"vendors": 0, "own": 0, "hired": 0, "drivers": 0, "clients": 0, "office": 0}

    for name, segment, cycle, contact in CLIENTS[:5]:
        c = await session.scalar(select(Client).where(Client.name == name))
        fields = {"segment": segment, "billing_cycle": cycle, "contact_name": contact, "contact_phone": f"90003{rnd.randint(10000, 99999)}",
                      "email": f"accounts@{name.lower().replace(' ', '')}.example", "gstin": f"27{_code(rnd, 5, string.ascii_uppercase)}{rnd.randint(1000, 9999)}{rnd.choice(string.ascii_uppercase)}1Z{rnd.randint(1, 9)}",
                      "tally_ledger": name, "language": "en"}
        if c is None:
            session.add(Client(name=name, **fields))
            made["clients"] += 1
        else:
            for k, v in fields.items():
                if getattr(c, k) in (None, ""):
                    setattr(c, k, v)

    for email, name, role, code in OFFICE:
        if await session.scalar(select(User).where(User.email == email)) is None:
            session.add(User(email=email, name=name, role=role, password_hash=hash_secret("cargoone-dev"), language="en", branch_id=(branches.get(code) or hq).id))
            made["office"] += 1

    vendors: list[Vendor] = []
    for v in VENDORS[:6]:
        row = await session.scalar(select(Vendor).where(Vendor.name == v))
        if row is None:
            row = Vendor(name=v, contact_name=_name(rnd), phone=f"90004{rnd.randint(10000, 99999)}",
                         notes=rnd.choice(["Pays in 30 days", "Pays in 15 days", "Regular on the Nagpur and Pune routes", "Mostly cement loads", "Open trucks and trailers", None]))
            session.add(row)
            made["vendors"] += 1
        vendors.append(row)
    await session.flush()

    taken = set((await session.scalars(select(Vehicle.reg_no))).all())
    existing_own = (await session.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.is_hired.is_(False), Vehicle.reg_no.not_like("MH20 DM %")))) or 0
    existing_hired = (await session.scalar(select(func.count()).select_from(Vehicle).where(Vehicle.is_hired.is_(True), Vehicle.reg_no.not_like("MH20 DM %")))) or 0

    # the vehicles the brief's sample trips use: give them the same papers and a vendor / driver
    for reg in ("MH20 EL 4521", "MH20 GT 7718", "MH17 BY 3092"):
        v = await session.scalar(select(Vehicle).where(Vehicle.reg_no == reg))
        if v is None:
            continue
        if v.is_hired and v.vendor_id is None:
            v.vendor_id = vendors[0].id
        for k, val in _papers(rnd, today, reg, "Company A" if not v.is_hired else vendors[0].name).items():
            if getattr(v, k) in (None, ""):
                setattr(v, k, val)
    ramesh = await session.scalar(select(User).where(User.phone == "9000000001"))
    if ramesh is not None:
        ramesh.name = "Ramesh Patil"
        ramesh.employment_type = ramesh.employment_type or "company"
        for k, val in _licence(rnd, today, "MH20").items():
            if getattr(ramesh, k) is None:
                setattr(ramesh, k, val)
        ramesh.assigned_vehicle_id = ramesh.assigned_vehicle_id or (await session.scalar(select(Vehicle.id).where(Vehicle.reg_no == "MH20 EL 4521")))

    new_own: list[Vehicle] = []
    for i in range(max(0, OWN - existing_own)):
        reg = _reg(rnd, "MH20", taken)
        new_own.append(Vehicle(reg_no=reg, is_hired=False, **_papers(rnd, today, reg, "Company A")))
    new_hired: list[Vehicle] = []
    for i in range(max(0, HIRED - existing_hired)):
        reg = _reg(rnd, rnd.choice(HIRED_STATES), taken)
        vendor = vendors[min(int(rnd.random() ** 1.6 * len(vendors)), len(vendors) - 1)]  # a few transporters supply most of the trucks
        new_hired.append(Vehicle(reg_no=reg, is_hired=True, vendor_id=vendor.id, **_papers(rnd, today, reg, vendor.contact_name or vendor.name)))
    made["own"], made["hired"] = len(new_own), len(new_hired)
    session.add_all([*new_own, *new_hired])
    await session.flush()

    phones = {p for p in (await session.scalars(select(User.phone).where(User.phone.is_not(None)))).all()}
    n = 0

    def next_phone(base: int) -> str:
        nonlocal n
        while True:
            n += 1
            p = str(base + n)
            if p not in phones:
                phones.add(p)
                return p

    own_without_driver = list((await session.scalars(select(Vehicle).where(Vehicle.is_hired.is_(False), Vehicle.id.not_in(select(User.assigned_vehicle_id).where(User.assigned_vehicle_id.is_not(None)))))).all())
    for v in own_without_driver:  # every own truck has its regular driver, on the company payroll
        b = rnd.choices(order, weights=[5, 3, 2])[0]
        session.add(User(name=_name(rnd), phone=next_phone(9000100000), role=Role.driver, password_hash=pin, language=rnd.choices(["mr", "hi", "en"], [55, 40, 5])[0],
                         branch_id=b.id, employment_type="company", assigned_vehicle_id=v.id, **_licence(rnd, today, "MH20")))
        made["drivers"] += 1
    for v in rnd.sample(new_hired, k=max(1, int(len(new_hired) * 0.6))):  # most hired trucks have a driver we know; they sign in by link, so no PIN
        session.add(User(name=_name(rnd), phone=next_phone(9000200000), role=Role.driver, password_hash=None, language=rnd.choices(["mr", "hi"], [50, 50])[0],
                         branch_id=hq.id, employment_type="hired", vendor_id=v.vendor_id, assigned_vehicle_id=v.id, **_licence(rnd, today, rnd.choice(["MH20", "MH17", "MH12", "MP09", "GJ05"]))))
        made["drivers"] += 1
    await session.commit()
    return made


async def wipe(session: AsyncSession) -> dict:
    """Remove everything seed_fleet adds (the people, trucks, transporters and extra clients), keeping the brief's three sample trucks and the demo logins.
    Run after `python -m app.demo_data --remove`, because trips hold on to their trucks and drivers."""
    _guard()
    keep = ("MH20 EL 4521", "MH20 GT 7718", "MH17 BY 3092")
    drivers = (await session.scalars(select(User.id).where(User.role == Role.driver, User.phone != "9000000001"))).all()
    office = (await session.scalars(select(User.id).where(User.email.in_([e for e, *_ in OFFICE])))).all()
    trucks = (await session.scalars(select(Vehicle.id).where(Vehicle.reg_no.not_in(keep)))).all()
    await session.execute(update(User).where(User.assigned_vehicle_id.in_(trucks)).values(assigned_vehicle_id=None))
    await session.execute(delete(User).where(User.id.in_([*drivers, *office])))
    await session.execute(delete(Vehicle).where(Vehicle.id.in_(trucks)))
    await session.execute(update(Vehicle).where(Vehicle.reg_no.in_(keep)).values(vendor_id=None))
    gone = await session.execute(delete(Vendor).where(Vendor.id.not_in(select(Vehicle.vendor_id).where(Vehicle.vendor_id.is_not(None)))))
    extra = await session.execute(delete(Client).where(Client.name.in_([c[0] for c in CLIENTS if c[0] not in ("Company B", "Company C", "Company D")]), Client.id.not_in(select(Trip.client_id))))
    await session.commit()
    return {"drivers": len(drivers), "office": len(office), "trucks": len(trucks), "vendors": gone.rowcount, "clients": extra.rowcount}


async def main() -> None:
    if "--wipe" in sys.argv:
        async with SessionLocal() as session:
            print("Removed:", await wipe(session))
        return
    async with SessionLocal() as session:
        print("Added:", await seed_fleet(session))


if __name__ == "__main__":
    asyncio.run(main())
