"""Pure scheduling rules for the planning board: when is a vehicle or driver already taken?

A trip occupies its vehicle and driver from its start (planned start, or the moment it actually started) until its
planned end - or, if no end was given, one day after the start. Trips with no start at all occupy nothing, so legacy
data never blocks a new booking."""
from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_LENGTH = timedelta(days=1)


@dataclass(frozen=True)
class Slot:
    start: datetime | None
    end: datetime | None


def window(start: datetime | None, end: datetime | None) -> tuple[datetime, datetime] | None:
    if start is None:
        return None
    return start, end if end is not None and end > start else start + DEFAULT_LENGTH


def overlaps(a: tuple[datetime, datetime] | None, b: tuple[datetime, datetime] | None) -> bool:
    """Back-to-back is fine: a trip that ends at 10:00 does not clash with one starting at 10:00."""
    return a is not None and b is not None and a[0] < b[1] and b[0] < a[1]
