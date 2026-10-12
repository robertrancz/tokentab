from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any

import httpx

from tokentab.adapters.base import SyncResult, as_date
from tokentab.config import AppConfig
from tokentab.db import add_snapshot, last_snapshot
from tokentab.http import make_client
from tokentab.models import DailyCost, UsageBucket
from tokentab.secrets import OPENROUTER, OPENROUTER_MGMT, get_secret

KEY_URL = "https://openrouter.ai/api/v1/key"
CREDITS_URL = "https://openrouter.ai/api/v1/credits"
ACTIVITY_URL = "https://openrouter.ai/api/v1/activity"


def parse_key_payload(payload: dict[str, Any]) -> float:
    data = payload.get("data", payload)
    usage = data.get("usage")
    if usage is None:
        usage = data.get("total_usage")
    return float(usage or 0)


def parse_credits_payload(payload: dict[str, Any]) -> tuple[float, float]:
    data = payload.get("data", payload)
    return float(data.get("total_credits") or 0), float(data.get("total_usage") or 0)


def parse_activity(
    payload: dict[str, Any], source: str = "openrouter"
) -> tuple[list[UsageBucket], list[DailyCost]]:
    """Parse GET /api/v1/activity into model buckets + daily vendor costs."""
    by_model: dict[tuple[date, str], dict[str, float]] = defaultdict(
        lambda: {
            "input": 0.0,
            "output": 0.0,
            "cache_read": 0.0,
            "cost": 0.0,
        }
    )
    by_day: dict[date, float] = defaultdict(float)

    rows = payload.get("data", payload)
    if isinstance(rows, dict):
        rows = rows.get("data", [])
    if not isinstance(rows, list):
        return [], []

    for item in rows:
        if not isinstance(item, dict):
            continue
        day = as_date(item["date"])
        model = str(item.get("model") or item.get("model_permaslug") or "(unknown)")
        prompt = float(item.get("prompt_tokens") or 0)
        completion = float(item.get("completion_tokens") or 0)
        cached = float(item.get("cached_tokens") or 0)
        # OpenRouter "usage" is OpenRouter credits spent; include BYOK inference too.
        cost = float(item.get("usage") or 0) + float(item.get("byok_usage_inference") or 0)

        key = (day, model)
        by_model[key]["input"] += prompt
        by_model[key]["output"] += completion
        by_model[key]["cache_read"] += cached
        by_model[key]["cost"] += cost
        by_day[day] += cost

    buckets = [
        UsageBucket(
            source=source,
            bucket_start=day,
            model=model,
            input_tokens=int(vals["input"]),
            output_tokens=int(vals["output"]),
            cache_read_tokens=int(vals["cache_read"]),
            vendor_cost_usd=vals["cost"],
            cost_basis="vendor",
            raw={"aggregated": True},
        )
        for (day, model), vals in sorted(by_model.items())
    ]
    costs = [
        DailyCost(source=source, bucket_start=day, vendor_cost_usd=usd)
        for day, usd in sorted(by_day.items())
        if usd
    ]
    return buckets, costs


def delta_cost(
    previous: float | None, current: float, day: date, source: str = "openrouter"
) -> list[DailyCost]:
    if previous is None:
        return []
    delta = current - previous
    if delta <= 0:
        return []
    return [DailyCost(source=source, bucket_start=day, vendor_cost_usd=delta)]


class OpenRouterAdapter:
    id = "openrouter"
    role = "billing"

    def __init__(
        self,
        conn=None,
        client: httpx.Client | None = None,
        cfg: AppConfig | None = None,
    ) -> None:
        self.conn = conn
        self._client = client
        self.cfg = cfg

    def configured(self) -> bool:
        return bool(get_secret(OPENROUTER) or get_secret(OPENROUTER_MGMT))

    def sync(self, since: date | None, today: date | None = None) -> SyncResult:
        today = today or date.today()
        if self.conn is None:
            raise RuntimeError("OpenRouter adapter needs a database connection for snapshots")
        client = self._client or make_client(self.cfg)
        owns = self._client is None
        usage = 0.0
        extra: dict[str, Any] = {}
        buckets: list[UsageBucket] = []
        costs: list[DailyCost] = []
        try:
            key = get_secret(OPENROUTER)
            mgmt = get_secret(OPENROUTER_MGMT)
            auth = mgmt or key
            if not auth:
                raise RuntimeError("OpenRouter API key not set")

            if key:
                response = client.get(
                    KEY_URL, headers={"Authorization": f"Bearer {key}"}
                )
                response.raise_for_status()
                payload = response.json()
                extra["key"] = payload
                usage = parse_key_payload(payload)

            if mgmt:
                response = client.get(
                    CREDITS_URL, headers={"Authorization": f"Bearer {mgmt}"}
                )
                response.raise_for_status()
                payload = response.json()
                extra["credits"] = payload
                _credits, total_usage = parse_credits_payload(payload)
                usage = total_usage

                # Daily history (last ~30 UTC days). Management key required.
                activity_resp = client.get(
                    ACTIVITY_URL, headers={"Authorization": f"Bearer {mgmt}"}
                )
                activity_resp.raise_for_status()
                activity_payload = activity_resp.json()
                extra["activity_rows"] = len(activity_payload.get("data") or [])
                buckets, costs = parse_activity(activity_payload)

            if not costs:
                # Fallback: only useful after a prior snapshot when activity is unavailable.
                previous = last_snapshot(self.conn, self.id)
                prev_usage = previous[1] if previous else None
                costs = delta_cost(prev_usage, usage, today)
        finally:
            if owns:
                client.close()

        add_snapshot(self.conn, self.id, usage, extra)
        return SyncResult(
            buckets=buckets,
            daily_costs=costs,
            replace=bool(buckets),
            watermark=today,
        )
