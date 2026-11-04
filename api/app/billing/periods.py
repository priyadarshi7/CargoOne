"""Billing-cycle buckets. A client on a weekly/fortnightly/monthly cycle is invoiced once per bucket,
so the billing queue groups verified trips by (client, bucket). Dates are taken in IST (no DST)."""
import calendar
from datetime import UTC, datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def period_of(cycle: str, when: datetime) -> tuple[str, str, datetime]:
    """Returns (sort key, human label, bucket start) for the cycle bucket containing `when`."""
    d = (when if when.tzinfo else when.replace(tzinfo=UTC)).astimezone(IST).date()
    if cycle == "weekly":
        start = d - timedelta(days=d.weekday())  # Monday
        end = start + timedelta(days=6)
        label = f"{start:%d %b} – {end:%d %b %Y}"
    elif cycle == "fortnightly":
        last = calendar.monthrange(d.year, d.month)[1]
        start, end = (d.replace(day=1), d.replace(day=15)) if d.day <= 15 else (d.replace(day=16), d.replace(day=last))
        label = f"{start.day}–{end.day} {end:%b %Y}"
    else:  # monthly (and any unknown value)
        start = d.replace(day=1)
        label = f"{start:%B %Y}"
    return start.isoformat(), label, datetime(start.year, start.month, start.day, tzinfo=IST)


def financial_year(when: datetime) -> str:
    """Indian FY label, e.g. 2026-11-05 -> '26-27'."""
    d = when.astimezone(IST)
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y % 100:02d}-{(y + 1) % 100:02d}"
