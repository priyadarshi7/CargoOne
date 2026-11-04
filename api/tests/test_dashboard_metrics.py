from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.dashboard.metrics import Targets, TripFact, compute

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)
H = lambda n: timedelta(hours=n)
DAYS = lambda n: timedelta(days=n)


_D5, _H3, _D4 = timedelta(days=5), timedelta(hours=3), timedelta(days=4)


def fact(code="T", *, branch="Pune", status="billed", freight=1000, delivered=_D5, pod_after=_H3,
         inv_after=_D4, client="Co B") -> TripFact:
    d = NOW - delivered
    pod = d + pod_after if pod_after is not None else None
    ver = pod + H(1) if pod else None
    inv = ver + inv_after if ver and inv_after is not None else None
    return TripFact(code, client, branch, "MH20 AA 1", status, Decimal(freight), d, pod, ver, inv)


def test_reproduces_the_briefs_working_capital_numbers() -> None:
    # Brief: Rs 84.48 crore/yr, 18 -> 4 days => 14 days earlier => Rs 3.24 crore, Rs 38.9 lakh interest at 12 %.
    f = fact(freight=844_800_000, delivered=DAYS(30), inv_after=DAYS(4))
    wc = compute([f], now=NOW, window_days=365)["working_capital"]
    assert wc["annual_freight"] == pytest.approx(844_800_000)
    assert wc["days_saved"] == pytest.approx(14, abs=0.1)
    assert wc["released"] == pytest.approx(32_400_000, rel=0.01)
    assert wc["interest_saved_per_year"] == pytest.approx(3_890_000, rel=0.01)


def test_within_24h_counts_only_trips_delivered_more_than_a_day_ago() -> None:
    facts = [fact("a", pod_after=H(5)), fact("b", pod_after=H(24)), fact("c", pod_after=H(30)),
             fact("d", status="pending", pod_after=None),
             fact("fresh", delivered=H(3), pod_after=None, status="pending")]  # delivered 3 h ago: too early to judge
    k = compute(facts, now=NOW)["kpis"]
    assert k["eligible_trips"] == 4 and k["within_24h_pct"] == 50.0  # a, b yes; c, d no


def test_pod_to_invoice_days_average_ignores_uninvoiced() -> None:
    facts = [fact("a", inv_after=DAYS(2)), fact("b", inv_after=DAYS(6)), fact("c", status="verified", inv_after=None)]
    assert compute(facts, now=NOW)["kpis"]["pod_to_invoice_days"] == 4.0


def test_lost_rate_is_rejected_over_eligible() -> None:
    facts = [fact(str(i)) for i in range(199)] + [fact("x", status="rejected")]
    assert compute(facts, now=NOW)["kpis"]["lost_pct"] == 0.5


def test_missing_pods_bucketed_by_age_and_branch_with_money_at_risk() -> None:
    facts = [
        fact("m1", branch="Pune", status="pending", pod_after=None, delivered=DAYS(1) + H(2), freight=100),
        fact("m2", branch="Pune", status="pending", pod_after=None, delivered=DAYS(5), freight=200),
        fact("m3", branch="Nagpur", status="retake_requested", pod_after=None, delivered=DAYS(10), freight=300),
        fact("m4", branch="Nagpur", status="pending", pod_after=None, delivered=DAYS(20), freight=400),
        fact("ok", status="needs_review"),  # has a POD: in review, not missing
    ]
    out = compute(facts, now=NOW)["missing"]
    assert out["total"] == 4 and out["amount"] == 1000
    assert {b["label"]: b["count"] for b in out["buckets"]} == {"1–2 days": 1, "3–7 days": 1, "8–14 days": 1, "15+ days": 1}
    assert out["at_risk_amount"] == 700  # only the >= 7-day-old ones (300 + 400)
    nagpur = next(b for b in out["by_branch"] if b["branch"] == "Nagpur")
    assert {b["label"]: b["count"] for b in nagpur["buckets"]}["15+ days"] == 1


def test_oldest_missing_is_sorted_and_capped() -> None:
    facts = [fact(f"m{i}", status="pending", pod_after=None, delivered=DAYS(2 + i)) for i in range(15)]
    old = compute(facts, now=NOW)["oldest_missing"]
    assert len(old) == 10 and old[0]["age_days"] == 16 and old[0]["age_days"] >= old[-1]["age_days"]


def test_branch_league_and_pipeline() -> None:
    facts = [fact("a", branch="Pune", pod_after=H(2)), fact("b", branch="Nagpur", pod_after=H(40)),
             fact("r", status="needs_review"), fact("v", status="verified", inv_after=None, freight=5000)]
    out = compute(facts, now=NOW)
    league = {b["branch"]: b for b in out["branches"]}
    assert league["Nagpur"]["within_24h_pct"] == 0.0
    assert out["pipeline"] == {"awaiting_review": 1, "ready_to_bill": 1, "ready_to_bill_amount": 5000.0}


def test_empty_data_does_not_crash_or_invent_numbers() -> None:
    out = compute([], now=NOW)
    assert out["kpis"]["within_24h_pct"] is None and out["kpis"]["pod_to_invoice_days"] is None
    assert out["working_capital"]["released"] is None and out["missing"]["total"] == 0 and len(out["trend"]) == 8


def test_weekly_trend_covers_the_requested_weeks_in_order() -> None:
    out = compute([fact("a", delivered=DAYS(2))], now=NOW, weeks=4)["trend"]
    assert len(out) == 4 and [t["week"] for t in out] == sorted(t["week"] for t in out)


def test_no_saving_claimed_when_slower_than_baseline() -> None:
    f = fact(inv_after=DAYS(25))
    wc = compute([f], now=NOW, targets=Targets(baseline_days=18))["working_capital"]
    assert wc["days_saved"] == 0 and wc["released"] == 0
