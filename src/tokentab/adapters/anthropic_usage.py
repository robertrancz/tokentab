from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from tokentab.adapters.base import SyncResult, as_date
from tokentab.config import AppConfig
from tokentab.http import make_client
from tokentab.models import DailyCost, UsageBucket
from tokentab.secrets import ANTHROPIC_ADMIN, get_secret

USAGE_URL = "https://api.anthropic.com/v1/organizations/usage_report/messages"
COST_URL = "https://api.anthropic.com/v1/organizations/cost_report"


def parse_usage_report(payload: dict[str, Any], source: str = "anthropic") -> list[UsageBucket]:
    buckets: list[UsageBucket] = []
    for item in payload.get("data", []):
        start = as_date(item.get("starting_at") or item.get("start_time") or item.get("ending_at"))
        if item.get("ending_at") and not item.get("starting_at"):
            end = as_date(item["ending_at"])
            start = date.fromordinal(end.toordinal() - 1)
        for result in item.get("results", []):
            cache = result.get("cache_creation") or {}
            cache_write = int(cache.get("ephemeral_1h_input_tokens") or 0) + int(
                cache.get("ephemeral_5m_input_tokens") or 0
            )
            uncached = int(
                result.get("uncached_input_tokens")
                or result.get("input_tokens")
                or 0
            )
            cache_read = int(result.get("cache_read_input_tokens") or 0)
            buckets.append(
                UsageBucket(
                    source=source,
                    bucket_start=start,
                    model=result.get("model") or "(unknown)",
                    input_tokens=uncached + cache_read + cache_write,
                    output_tokens=int(result.get("output_tokens") or 0),
                    cache_read_tokens=cache_read,
                    cache_write_tokens=cache_write,
                    raw=result,
                )
            )
    return buckets


def parse_cost_report(payload: dict[str, Any], source: str = "anthropic") -> list[DailyCost]:
    by_day: dict[date, float] = {}
    for item in payload.get("data", []):
        start = as_date(item.get("starting_at") or item.get("start_time") or item.get("ending_at"))
        if item.get("ending_at") and not item.get("starting_at"):
            end = as_date(item["ending_at"])
            start = date.fromordinal(end.toordinal() - 1)
        total = 0.0
        for result in item.get("results", []):
            amount = result.get("amount")
            if amount is None:
                continue
            cents = float(amount)
            total += cents / 100.0
        if total:
            by_day[start] = by_day.get(start, 0.0) + total
    return [DailyCost(source=source, bucket_start=day, vendor_cost_usd=usd) for day, usd in by_day.items()]


class AnthropicAdapter:
    id = "anthropic"
    role = "billing"

    def __init__(
        self, client: httpx.Client | None = None, cfg: AppConfig | None = None
    ) -> None:
        self._client = client
        self.cfg = cfg

    def configured(self) -> bool:
        return bool(get_secret(ANTHROPIC_ADMIN))

    def sync(self, since: date | None, today: date | None = None) -> SyncResult:
        today = today or date.today()
        start = since or (today - timedelta(days=40))
        key = get_secret(ANTHROPIC_ADMIN)
        if not key:
            raise RuntimeError("Anthropic Admin API key not set (sk-ant-admin01-…)")
        client = self._client or make_client(self.cfg)
        owns = self._client is None
        try:
            usage = _paginate(
                client,
                USAGE_URL,
                key,
                {
                    "starting_at": _rfc3339(start),
                    "ending_at": _rfc3339(today + timedelta(days=1)),
                    "bucket_width": "1d",
                    "group_by[]": "model",
                    "limit": 31,
                },
            )
            costs = _paginate(
                client,
                COST_URL,
                key,
                {
                    "starting_at": _rfc3339(start),
                    "ending_at": _rfc3339(today + timedelta(days=1)),
                    "bucket_width": "1d",
                    "limit": 31,
                },
            )
        finally:
            if owns:
                client.close()
        return SyncResult(
            buckets=parse_usage_report(usage),
            daily_costs=parse_cost_report(costs),
            watermark=today,
        )


def _rfc3339(day: date) -> str:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _paginate(
    client: httpx.Client, url: str, key: str, params: dict[str, Any]
) -> dict[str, Any]:
    headers = {
        "x-api-key": key,
        "anthropic-version": "2023-06-01",
        "Authorization": f"Bearer {key}",
    }
    merged: dict[str, Any] = {"data": []}
    query = dict(params)
    while True:
        response = client.get(url, headers=headers, params=query)
        response.raise_for_status()
        payload = response.json()
        merged["data"].extend(payload.get("data", []))
        page = payload.get("has_more") and payload.get("next_page")
        if not page:
            break
        query["page"] = page
    return merged
