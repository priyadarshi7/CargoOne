"""Dashboard KPIs as a pure function of trip facts (no database), so every formula is unit-testable.

Definitions (agreed with the client brief):
- POD in system within 24 h : first POD upload <= 24 h after delivery, over trips delivered > 24 h ago.   Target 80 %.
- POD-to-invoice days       : verified_at -> invoiced_at, averaged over invoiced trips.                   18 -> 4 days.
- Lost / disputed           : trips whose POD was rejected, over trips delivered > 24 h ago.             1.5 % -> 0.5 %.
- Missing POD               : delivered > 24 h ago and still no usable POD (pending or retake requested).
- Working capital released  : annual freight x (baseline days - actual days) / 365   (the brief's own formula).
"""
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from app.billing.periods import IST, period_of

AGE_BUCKETS = [("1–2 days", 1, 2), ("3–7 days", 3, 7), ("8–14 days", 8, 14), ("15+ days", 15, 10_000)]
MISSING_STATUSES = {"pending", "retake_requested"}
AT_RISK_AFTER_DAYS = 7


@dataclass(frozen=True)
class TripFact:
    trip_code: str
    client: str
    branch: str
    vehicle: str
    status: str
    freight: Decimal
    delivered_at: datetime | None
    first_pod_at: datetime | None
    verified_at: datetime | None
    invoiced_at: datetime | None
    driver: str | None = None


@dataclass(frozen=True)
class Targets:
    baseline_days: float = 18.0
    target_days: float = 4.0
    target_within_24h_pct: float = 80.0
    baseline_lost_pct: float = 1.5
    target_lost_pct: float = 0.5
    interest_rate: float = 0.12


def _pct(num: int, den: int) -> float | None:
    return round(100 * num / den, 1) if den else None


def _within_24h(t: TripFact) -> bool:
    return t.first_pod_at is not None and t.delivered_at is not None and t.first_pod_at - t.delivered_at <= timedelta(hours=24)


def _invoice_days(t: TripFact) -> float | None:
    if t.verified_at is None or t.invoiced_at is None:
        return None
    return max(0.0, (t.invoiced_at - t.verified_at).total_seconds() / 86400)


def _avg(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def _kpis(facts: list[TripFact], now: datetime) -> dict:
    eligible = [t for t in facts if t.delivered_at and t.delivered_at <= now - timedelta(hours=24)]
    days = [d for t in facts if (d := _invoice_days(t)) is not None]
    return {
        "eligible": len(eligible),
        "within_24h_pct": _pct(sum(_within_24h(t) for t in eligible), len(eligible)),
        "pod_to_invoice_days": _avg(days),
        "lost_pct": _pct(sum(t.status == "rejected" for t in eligible), len(eligible)),
    }


def _age_days(t: TripFact, now: datetime) -> int:
    return int((now - t.delivered_at).total_seconds() // 86400)


def compute(facts: list[TripFact], *, now: datetime, window_days: int = 90, targets: Targets | None = None,
            weeks: int = 8, open_facts: list[TripFact] | None = None) -> dict:
    """`facts` are the trips delivered in the window (the rates and the trend). `open_facts` are every trip still waiting on something, whenever it was
    delivered: a POD missing for 45 days must not disappear from a 30-day view, and the counts must agree with the Today tab and the queues."""
    targets = targets or Targets()
    kpi = _kpis(facts, now)
    waiting = facts if open_facts is None else open_facts

    # Missing PODs by age bucket and branch
    missing = [t for t in waiting if t.status in MISSING_STATUSES and t.delivered_at and _age_days(t, now) >= 1]
    by_branch: dict[str, dict[str, int]] = defaultdict(lambda: {b[0]: 0 for b in AGE_BUCKETS})
    for t in missing:
        label = next(b[0] for b in AGE_BUCKETS if b[1] <= _age_days(t, now) <= b[2])
        by_branch[t.branch][label] += 1
    buckets = [{"label": b[0], "count": sum(v[b[0]] for v in by_branch.values())} for b in AGE_BUCKETS]
    oldest = sorted(missing, key=lambda t: t.delivered_at)[:10]

    at_risk = sum((t.freight for t in missing if _age_days(t, now) >= AT_RISK_AFTER_DAYS), Decimal(0))
    at_risk += sum((t.freight for t in facts if t.status == "rejected"), Decimal(0))

    # Branch league
    names = sorted({t.branch for t in facts})
    league = []
    for name in names:
        bf = [t for t in facts if t.branch == name]
        k = _kpis(bf, now)
        bm = [t for t in missing if t.branch == name]
        league.append({
            "branch": name, "trips": len(bf), "within_24h_pct": k["within_24h_pct"],
            "pod_to_invoice_days": k["pod_to_invoice_days"], "lost_pct": k["lost_pct"], "missing": len(bm),
            "missing_amount": float(sum((t.freight for t in bm), Decimal(0))),
        })

    # Working capital (the brief's formula), annualised from the trips in the window
    window_freight = sum((t.freight for t in facts), Decimal(0))
    annual_freight = window_freight * Decimal(365) / Decimal(window_days)
    avg_days = kpi["pod_to_invoice_days"]
    days_saved = max(0.0, targets.baseline_days - avg_days) if avg_days is not None else None
    released = annual_freight * Decimal(str(days_saved)) / Decimal(365) if days_saved is not None else None

    # Weekly trend (Mon-Sun, IST) for the last `weeks` weeks
    week_keys = sorted({period_of("weekly", now - timedelta(weeks=i))[0:2] for i in range(weeks)})
    trend = []
    for key, label in week_keys:
        wk_delivered = [t for t in facts if t.delivered_at and period_of("weekly", t.delivered_at)[0] == key]
        wk_invoiced = [t for t in facts if t.invoiced_at and period_of("weekly", t.invoiced_at)[0] == key]
        eligible = [t for t in wk_delivered if t.delivered_at <= now - timedelta(hours=24)]
        trend.append({
            "week": key, "label": label.split(" – ")[0],
            "within_24h_pct": _pct(sum(_within_24h(t) for t in eligible), len(eligible)),
            "pod_to_invoice_days": _avg([d for t in wk_invoiced if (d := _invoice_days(t)) is not None]),
        })

    ready = [t for t in waiting if t.status == "verified"]
    return {
        "window_days": window_days,
        "as_of": now.astimezone(IST).isoformat(),
        "kpis": {
            "within_24h_pct": kpi["within_24h_pct"], "pod_to_invoice_days": avg_days, "lost_pct": kpi["lost_pct"],
            "trips_in_window": len(facts), "eligible_trips": kpi["eligible"],
        },
        "targets": {
            "within_24h_pct": targets.target_within_24h_pct, "pod_to_invoice_days": targets.target_days,
            "baseline_pod_to_invoice_days": targets.baseline_days, "lost_pct": targets.target_lost_pct,
            "baseline_lost_pct": targets.baseline_lost_pct,
        },
        "working_capital": {
            "annual_freight": float(annual_freight), "days_saved": days_saved,
            "released": float(released) if released is not None else None,
            "interest_saved_per_year": float(released * Decimal(str(targets.interest_rate))) if released is not None else None,
            "interest_rate": targets.interest_rate,
        },
        "missing": {
            "total": len(missing), "amount": float(sum((t.freight for t in missing), Decimal(0))), "at_risk_amount": float(at_risk),
            "buckets": buckets,
            "by_branch": [{"branch": b, "buckets": [{"label": k, "count": v} for k, v in c.items()]} for b, c in sorted(by_branch.items())],
        },
        "pipeline": {
            "awaiting_review": sum(t.status == "needs_review" for t in waiting),
            "ready_to_bill": len(ready), "ready_to_bill_amount": float(sum((t.freight for t in ready), Decimal(0))),
        },
        "branches": league,
        "trend": trend,
        "oldest_missing": [{
            "trip_code": t.trip_code, "client": t.client, "branch": t.branch, "vehicle": t.vehicle, "driver": t.driver,
            "age_days": _age_days(t, now), "freight": float(t.freight), "status": t.status,
        } for t in oldest],
    }
