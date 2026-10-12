from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date

from tokentab.config import AppConfig
from tokentab.db import list_buckets, list_daily_costs, list_seats, list_sources
from tokentab.forecast import cycle_bounds, daily_metered, forecast_month, seat_amortized
from tokentab.models import Forecast, UsageBucket
from tokentab.pricer import effective_cost


def billing_source_ids(conn: sqlite3.Connection, cfg: AppConfig) -> set[str]:
    ids: set[str] = set()
    vendor_on = False
    for source in list_sources(conn):
        if not source.enabled:
            continue
        if source.id == "aider":
            continue
        if source.role == "billing":
            ids.add(source.id)
            if source.id in {"openai", "anthropic", "openrouter"}:
                vendor_on = True
    if cfg.aider.counts_as_billing:
        aider = next((s for s in list_sources(conn) if s.id == "aider"), None)
        if aider and aider.enabled:
            ids.add("aider")
    elif not vendor_on:
        aider = next((s for s in list_sources(conn) if s.id == "aider"), None)
        if aider and aider.enabled:
            ids.add("aider")
    return ids


def activity_source_ids(conn: sqlite3.Connection, cfg: AppConfig) -> set[str]:
    ids = set()
    for source in list_sources(conn):
        if source.enabled and source.role == "activity":
            ids.add(source.id)
    if not cfg.aider.counts_as_billing:
        ids.add("aider")
    return ids


def current_cycle_report(
    conn: sqlite3.Connection,
    cfg: AppConfig,
    today: date | None = None,
    *,
    what_if_model: str | None = None,
    what_if_tokens_per_day: int | None = None,
) -> dict:
    today = today or date.today()
    start, end = cycle_bounds(today, cfg.billing_cycle_day)
    billing = billing_source_ids(conn, cfg)
    buckets = list_buckets(conn, start=start, end=today)
    costs = list_daily_costs(conn, start=start, end=today)
    vendor_by_day = {(c.source, c.bucket_start): c.vendor_cost_usd for c in costs}
    seats = list_seats(conn)
    fc = forecast_month(
        buckets=buckets,
        vendor_by_day=vendor_by_day,
        billing_sources=billing,
        seats=seats,
        today=today,
        cycle_day=cfg.billing_cycle_day,
        window=cfg.forecast_days,
        what_if_model=what_if_model,
        what_if_tokens_per_day=what_if_tokens_per_day,
    )
    daily = daily_metered(buckets, vendor_by_day, billing, today)
    by_source = _by_source(buckets, vendor_by_day, billing)
    by_model = _by_model(buckets, billing)
    activity = _by_source(
        buckets, vendor_by_day, activity_source_ids(conn, cfg) | ({"aider"} if not cfg.aider.counts_as_billing else set())
    )
    return {
        "today": today.isoformat(),
        "cycle_start": start.isoformat(),
        "cycle_end": end.isoformat(),
        "billing_sources": sorted(billing),
        "forecast": fc,
        "daily": {d.isoformat(): v for d, v in sorted(daily.items())},
        "by_source": by_source,
        "by_model": by_model,
        "activity_by_source": activity,
        "seats": [
            {
                "id": s.id,
                "name": s.name,
                "monthly_usd": s.monthly_usd,
                "billing_day": s.billing_day,
                "notes": s.notes,
                "amortized_mtd": seat_amortized(s, today)[0],
            }
            for s in seats
        ],
        "tokens": _token_totals(buckets, billing),
        "estimated_vs_vendor": _estimated_vs_vendor(buckets, vendor_by_day, billing),
    }


def _token_totals(buckets: list[UsageBucket], sources: set[str]) -> dict[str, int]:
    inp = out = cache_r = cache_w = 0
    for b in buckets:
        if b.source not in sources:
            continue
        inp += b.input_tokens
        out += b.output_tokens
        cache_r += b.cache_read_tokens
        cache_w += b.cache_write_tokens
    return {
        "input": inp,
        "output": out,
        "cache_read": cache_r,
        "cache_write": cache_w,
        "total": inp + out + cache_r + cache_w,
    }


def _by_source(
    buckets: list[UsageBucket],
    vendor_by_day: dict[tuple[str, date], float],
    sources: set[str],
) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    vendor_sources = {s for s, _ in vendor_by_day if s in sources}
    for (source, _day), amount in vendor_by_day.items():
        if source in sources:
            totals[source] += amount
    for bucket in buckets:
        if bucket.source not in sources or bucket.source in vendor_sources:
            continue
        totals[bucket.source] += effective_cost(bucket)
    return dict(totals)


def _by_model(buckets: list[UsageBucket], sources: set[str]) -> list[dict]:
    agg: dict[str, dict] = {}
    for bucket in buckets:
        if bucket.source not in sources:
            continue
        row = agg.setdefault(
            bucket.model,
            {
                "model": bucket.model,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "cost": 0.0,
            },
        )
        row["input_tokens"] += bucket.input_tokens
        row["output_tokens"] += bucket.output_tokens
        row["cache_read_tokens"] += bucket.cache_read_tokens
        row["cache_write_tokens"] += bucket.cache_write_tokens
        row["cost"] += effective_cost(bucket)
    rows = list(agg.values())
    for row in rows:
        total = (
            row["input_tokens"]
            + row["output_tokens"]
            + row["cache_read_tokens"]
            + row["cache_write_tokens"]
        )
        row["total_tokens"] = total
        row["usd_per_m"] = (row["cost"] / total * 1_000_000) if total else 0.0
    rows.sort(key=lambda r: r["cost"], reverse=True)
    return rows


def _estimated_vs_vendor(
    buckets: list[UsageBucket],
    vendor_by_day: dict[tuple[str, date], float],
    sources: set[str],
) -> dict[str, float]:
    vendor = sum(v for (s, _), v in vendor_by_day.items() if s in sources)
    estimated = 0.0
    for bucket in buckets:
        if bucket.source in sources:
            from tokentab.pricer import estimate_bucket

            estimated += estimate_bucket(bucket)
    return {"vendor": vendor, "estimated": estimated}


def forecast_to_dict(fc: Forecast) -> dict:
    return {
        "metered_mtd": fc.metered_mtd,
        "seats_amortized_mtd": fc.seats_amortized_mtd,
        "seats_committed": fc.seats_committed,
        "daily_burn": fc.daily_burn,
        "remaining_days": fc.remaining_days,
        "forecast_metered": fc.forecast_metered,
        "forecast_run_rate_total": fc.forecast_run_rate_total,
        "forecast_with_committed_seats": fc.forecast_with_committed_seats,
        "p25": fc.p25,
        "p75": fc.p75,
        "confidence": fc.confidence,
        "what_if_daily_usd": fc.what_if_daily_usd,
        "what_if_month_usd": fc.what_if_month_usd,
    }
