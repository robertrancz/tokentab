from __future__ import annotations

import sqlite3
from datetime import date

from tokentab.catalog import lookup_rate
from tokentab.db import list_buckets, list_daily_costs, update_bucket_pricing
from tokentab.models import UsageBucket


def estimate_bucket(bucket: UsageBucket) -> float:
    rate = lookup_rate(bucket.model)
    if rate is None:
        if bucket.vendor_cost_usd is not None:
            return float(bucket.vendor_cost_usd)
        return 0.0
    uncached = max(bucket.input_tokens - bucket.cache_read_tokens, 0)
    usd = (
        uncached * rate.input_per_m
        + bucket.output_tokens * rate.output_per_m
        + bucket.cache_read_tokens * rate.cache_read_per_m
        + bucket.cache_write_tokens * rate.cache_write_per_m
    ) / 1_000_000
    return usd


def effective_cost(bucket: UsageBucket) -> float:
    if bucket.vendor_cost_usd is not None:
        return float(bucket.vendor_cost_usd)
    if bucket.estimated_cost_usd is not None:
        return float(bucket.estimated_cost_usd)
    return estimate_bucket(bucket)


def price_tokens(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    return estimate_bucket(
        UsageBucket(
            source="whatif",
            bucket_start=date.today(),
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
        )
    )


def apply_pricing(conn: sqlite3.Connection) -> None:
    buckets = list_buckets(conn)
    daily = {(c.source, c.bucket_start): c.vendor_cost_usd for c in list_daily_costs(conn)}
    by_key: dict[tuple[str, object], list[UsageBucket]] = {}
    for bucket in buckets:
        by_key.setdefault((bucket.source, bucket.bucket_start), []).append(bucket)

    for (source, day), group in by_key.items():
        estimates = [estimate_bucket(b) for b in group]
        vendor_total = daily.get((source, day))
        est_sum = sum(estimates)
        for bucket, estimated in zip(group, estimates):
            allocated = None
            basis = "estimated"
            if bucket.vendor_cost_usd is not None:
                allocated = float(bucket.vendor_cost_usd)
                basis = "vendor"
            elif vendor_total is not None and est_sum > 0:
                allocated = vendor_total * (estimated / est_sum)
                basis = "vendor"
            elif vendor_total is not None and len(group) == 1:
                allocated = vendor_total
                basis = "vendor"
            update_bucket_pricing(
                conn,
                bucket.source,
                bucket.bucket_start,
                bucket.model,
                estimated,
                allocated if allocated is not None else bucket.vendor_cost_usd,
                basis,
            )
    conn.commit()
