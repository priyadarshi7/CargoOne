"""Pure rules for fuel economy and anomaly flags.

Drivers fill the tank each time, so the litres bought at a fill cover the distance since the previous fill:
km per litre = (odometer now - odometer at the previous fill) / litres now. A leg is flagged when the odometer goes
backwards, when the figure is physically implausible for a loaded truck, or when it is far below the truck's usual."""
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from statistics import median

LOW_FACTOR = 0.6  # below 60% of the truck's own median km/l = suspicious (fuel pilferage, a leak, a wrong entry)
MIN_PLAUSIBLE_KMPL = 1.5
MAX_PLAUSIBLE_KMPL = 12.0  # loaded goods vehicles do ~2.5-6 km/l; beyond this is almost certainly a wrong odometer or litres
MAX_TANK_LITRES = 700.0


@dataclass(frozen=True)
class Fill:
    at: datetime
    odometer_km: int
    litres: float


@dataclass(frozen=True)
class Leg:
    from_km: int
    to_km: int
    km: int
    litres: float
    kmpl: float | None
    flags: tuple[str, ...]


def leg(prev: Fill, cur: Fill, usual_kmpl: float | None = None) -> Leg:
    km = cur.odometer_km - prev.odometer_km
    flags: list[str] = []
    kmpl: float | None = None
    if cur.litres > MAX_TANK_LITRES:
        flags.append("implausible_litres")
    if km <= 0:
        flags.append("odometer_backwards")
    elif cur.litres > 0:
        kmpl = round(km / cur.litres, 2)
        if kmpl < MIN_PLAUSIBLE_KMPL or kmpl > MAX_PLAUSIBLE_KMPL:
            flags.append("implausible_mileage")
        elif usual_kmpl and kmpl < LOW_FACTOR * usual_kmpl:
            flags.append("low_mileage")
    return Leg(prev.odometer_km, cur.odometer_km, km, cur.litres, kmpl, tuple(flags))


def legs(fills: list[Fill]) -> list[Leg]:
    """All legs of a vehicle in time order. The 'usual' km/l is the median of the plausible legs seen BEFORE each leg
    (needs 3), so one bad fill cannot hide itself by dragging the median down."""
    ordered = sorted(fills, key=lambda f: f.at)
    out: list[Leg] = []
    seen: list[float] = []
    for prev, cur in pairwise(ordered):
        usual = median(seen) if len(seen) >= 3 else None
        lg = leg(prev, cur, usual)
        out.append(lg)
        if lg.kmpl is not None and not lg.flags:
            seen.append(lg.kmpl)
    return out


def usual_kmpl(fills: list[Fill]) -> float | None:
    good = [lg.kmpl for lg in legs(fills) if lg.kmpl is not None and not lg.flags]
    return round(median(good), 2) if len(good) >= 3 else None
