from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from tokentab.adapters.base import SyncResult, as_date
from tokentab.config import AppConfig
from tokentab.http import make_client
from tokentab.models import DailyCost, UsageBucket
from tokentab.secrets import OPENAI_ADMIN, get_secret

USAGE_URL = "https://api.openai.com/v1/organization/usage/completions"
COSTS_URL = "https://api.openai.com/v1/organization/costs"


def parse_usage_page(payload: dict[str, Any], source: str = "openai") -> list[UsageBucket]:
    buckets: list[UsageBucket] = []
    for item in payload.get("data", []):
        start = as_date(item.get("start_time") or item.get("start"))
        for result in item.get("results", []):
            model = result.get("model") or "(unknown)"
            buckets.append(
                UsageBucket(
                    source=source,
                    bucket_start=start,
                    model=model,
                    input_tokens=int(result.get("input_tokens") or 0),
                    output_tokens=int(result.get("output_tokens") or 0),
                    cache_read_tokens=int(result.get("input_cached_tokens") or 0),
                    cache_write_tokens=0,
                    raw=result,
                )
            )
    return _merge(buckets)


def parse_costs_page(payload: dict[str, Any], source: str = "openai") -> list[DailyCost]:
    by_day: dict[date, float] = {}
    for item in payload.get("data", []):
        start = as_date(item.get("start_time") or item.get("start"))
        total = 0.0
        for result in item.get("results", []):
            amount = result.get("amount")
            if isinstance(amount, dict):
                total += float(amount.get("value") or 0)
            elif amount is not None:
                total += float(amount)
        if total:
            by_day[start] = by_day.get(start, 0.0) + total
    return [DailyCost(source=source, bucket_start=day, vendor_cost_usd=usd) for day, usd in by_day.items()]


def _merge(buckets: list[UsageBucket]) -> list[UsageBucket]:
    merged: dict[tuple[str, date, str], UsageBucket] = {}
    for bucket in buckets:
        key = (bucket.source, bucket.bucket_start, bucket.model)
        existing = merged.get(key)
        if existing is None:
            merged[key] = bucket
            continue
        merged[key] = UsageBucket(
            source=bucket.source,
            bucket_start=bucket.bucket_start,
            model=bucket.model,
            input_tokens=existing.input_tokens + bucket.input_tokens,
            output_tokens=existing.output_tokens + bucket.output_tokens,
            cache_read_tokens=existing.cache_read_tokens + bucket.cache_read_tokens,
            cache_write_tokens=existing.cache_write_tokens + bucket.cache_write_tokens,
            raw=bucket.raw,
        )
    return list(merged.values())


class OpenAIAdapter:
    id = "openai"
    role = "billing"

    def __init__(
        self, client: httpx.Client | None = None, cfg: AppConfig | None = None
    ) -> None:
        self._client = client
        self.cfg = cfg

    def configured(self) -> bool:
        return bool(get_secret(OPENAI_ADMIN))

    def sync(self, since: date | None, today: date | None = None) -> SyncResult:
        today = today or date.today()
        start = since or (today - timedelta(days=40))
        start = min(start, today)
        key = get_secret(OPENAI_ADMIN)
        if not key:
            raise RuntimeError("OpenAI admin/usage API key not set")
        client = self._client or make_client(self.cfg)
        owns = self._client is None
        try:
            usage_payload = _paginate(
                client,
                USAGE_URL,
                key,
                {
                    "start_time": _unix(start),
                    "bucket_width": "1d",
                    "group_by": ["model"],
                    "limit": 31,
                },
            )
            cost_payload = _paginate(
                client,
                COSTS_URL,
                key,
                {
                    "start_time": _unix(start),
                    "bucket_width": "1d",
                    "limit": 31,
                },
            )
        finally:
            if owns:
                client.close()
        buckets = parse_usage_page(usage_payload)
        costs = parse_costs_page(cost_payload)
        watermark = today
        return SyncResult(buckets=buckets, daily_costs=costs, watermark=watermark)


def _unix(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def _paginate(
    client: httpx.Client, url: str, key: str, params: dict[str, Any]
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {key}"}
    merged: dict[str, Any] = {"data": []}
    page = None
    query = dict(params)
    while True:
        if page:
            query["page"] = page
        response = client.get(url, headers=headers, params=query)
        response.raise_for_status()
        payload = response.json()
        merged["data"].extend(payload.get("data", []))
        if not payload.get("has_more"):
            break
        page = payload.get("next_page")
        if not page:
            break
    return merged
