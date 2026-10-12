from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from statistics import median

from tokentab.models import Forecast, Seat, UsageBucket
from tokentab.pricer import effective_cost, estimate_bucket


def cycle_bounds(today: date, billing_day: int) -> tuple[date, date]:
    day = max(1, min(billing_day, 28))
    if today.day >= day:
        start = date(today.year, today.month, day)
        if today.month == 12:
            end = date(today.year + 1, 1, day) - timedelta(days=1)
        else:
            end = date(today.year, today.month + 1, day) - timedelta(days=1)
    else:
        if today.month == 1:
            start = date(today.year - 1, 12, day)
        else:
            start = date(today.year, today.month - 1, day)
        end = date(today.year, today.month, day) - timedelta(days=1)
    last = monthrange(end.year, end.month)[1]
    if end.day > last:
        end = date(end.year, end.month, last)
    return start, end


def seat_amortized(seat: Seat, today: date) -> tuple[float, int, int]:
    start, end = cycle_bounds(today, seat.billing_day)
    days_in_cycle = (end - start).days + 1
    elapsed = min(days_in_cycle, max(1, (today - start).days + 1))
    remaining = max(0, (end - today).days)
    amortized = seat.monthly_usd * elapsed / days_in_cycle
    return amortized, remaining, days_in_cycle


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100) * (len(ordered) - 1)))))
    return ordered[idx]


def daily_metered(
    buckets: list[UsageBucket],
    vendor_by_day: dict[tuple[str, date], float],
    billing_sources: set[str],
    today: date,
) -> dict[date, float]:
    days: dict[date, float] = {}
    vendor_keys = {
        (source, day) for (source, day), amount in vendor_by_day.items() if source in billing_sources
    }
    for (source, day), amount in vendor_by_day.items():
        if source in billing_sources:
            days[day] = days.get(day, 0.0) + amount
    for bucket in buckets:
        if bucket.source not in billing_sources:
            continue
        if (bucket.source, bucket.bucket_start) in vendor_keys:
            continue
        days[bucket.bucket_start] = days.get(bucket.bucket_start, 0.0) + effective_cost(bucket)
    return {d: v for d, v in days.items() if d <= today}


def forecast_month(
    *,
    buckets: list[UsageBucket],
    vendor_by_day: dict[tuple[str, date], float],
    billing_sources: set[str],
    seats: list[Seat],
    today: date,
    cycle_day: int,
    window: int = 7,
    what_if_model: str | None = None,
    what_if_tokens_per_day: int | None = None,
) -> Forecast:
    start, end = cycle_bounds(today, cycle_day)
    in_cycle = [b for b in buckets if start <= b.bucket_start <= today]
    daily = daily_metered(in_cycle, vendor_by_day, billing_sources, today)
    metered_mtd = sum(daily.values())

    complete = [v for d, v in sorted(daily.items()) if d < today]
    sample = complete[-window:] if window else complete
    burn = median(sample) if sample else 0.0
    remaining = max(0, (end - today).days)
    forecast_metered = metered_mtd + burn * remaining

    seats_amort = 0.0
    seats_commit = 0.0
    for seat in seats:
        amortized, _, _ = seat_amortized(seat, today)
        seats_amort += amortized
        seats_commit += seat.monthly_usd

    run_rate = forecast_metered + seats_commit

    confidence = "low"
    p25 = p75 = None
    if len(sample) >= 7:
        confidence = "ok"
        p25 = _percentile(sample, 25)
        p75 = _percentile(sample, 75)
        p25 = metered_mtd + p25 * remaining + seats_amort
        p75 = metered_mtd + p75 * remaining + seats_amort

    what_daily = what_month = None
    if what_if_model and what_if_tokens_per_day:
        inp = int(what_if_tokens_per_day * 0.8)
        out = what_if_tokens_per_day - inp
        dummy = UsageBucket(
            source="whatif",
            bucket_start=today,
            model=what_if_model,
            input_tokens=inp,
            output_tokens=out,
        )
        what_daily = estimate_bucket(dummy)
        what_month = what_daily * ((end - start).days + 1)

    return Forecast(
        metered_mtd=metered_mtd,
        seats_amortized_mtd=seats_amort,
        seats_committed=seats_commit,
        daily_burn=float(burn),
        remaining_days=remaining,
        forecast_metered=forecast_metered,
        forecast_run_rate_total=run_rate,
        forecast_with_committed_seats=forecast_metered + seats_commit,
        p25=p25,
        p75=p75,
        confidence=confidence,
        what_if_daily_usd=what_daily,
        what_if_month_usd=what_month,
    )
