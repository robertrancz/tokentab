from datetime import date

import pytest

from tokentab.forecast import cycle_bounds, forecast_month, seat_amortized
from tokentab.models import Seat, UsageBucket


def test_cycle_bounds_mid_month():
    start, end = cycle_bounds(date(2026, 10, 6), 1)
    assert start == date(2026, 10, 1)
    assert end == date(2026, 10, 31)


def test_seat_amortized_sixth_of_month():
    seat = Seat(name="Cursor Pro", monthly_usd=31.0, billing_day=1)
    amortized, remaining, days = seat_amortized(seat, date(2026, 10, 6))
    assert days == 31
    assert remaining == 25
    assert amortized == pytest.approx(6.0)


def test_forecast_ignores_today_in_burn_and_projects():
    today = date(2026, 10, 8)
    buckets = []
    vendor = {}
    for day in range(1, 9):
        d = date(2026, 10, day)
        vendor[("openai", d)] = 2.0 if day < 8 else 9.0
        buckets.append(
            UsageBucket(source="openai", bucket_start=d, model="gpt-4o", input_tokens=1)
        )
    fc = forecast_month(
        buckets=buckets,
        vendor_by_day=vendor,
        billing_sources={"openai"},
        seats=[Seat(name="Copilot", monthly_usd=19.0)],
        today=today,
        cycle_day=1,
        window=7,
    )
    assert fc.metered_mtd == pytest.approx(23.0)
    assert fc.daily_burn == pytest.approx(2.0)
    assert fc.remaining_days == 23
    assert fc.forecast_metered == pytest.approx(23 + 2.0 * 23)
    assert fc.confidence == "ok"
    assert fc.forecast_with_committed_seats == pytest.approx(fc.forecast_metered + 19.0)


def test_what_if_tokens():
    fc = forecast_month(
        buckets=[],
        vendor_by_day={},
        billing_sources=set(),
        seats=[],
        today=date(2026, 10, 1),
        cycle_day=1,
        what_if_model="gpt-4o-mini",
        what_if_tokens_per_day=1_000_000,
    )
    assert fc.what_if_daily_usd == pytest.approx(0.8 * 0.15 + 0.2 * 0.6)
    assert fc.what_if_month_usd == pytest.approx(fc.what_if_daily_usd * 31)
