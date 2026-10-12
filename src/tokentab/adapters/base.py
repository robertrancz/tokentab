from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Protocol

from tokentab.models import DailyCost, UsageBucket


@dataclass
class SyncResult:
    buckets: list[UsageBucket]
    daily_costs: list[DailyCost]
    replace: bool = False
    watermark: date | None = None


class Adapter(Protocol):
    id: str
    role: str

    def configured(self) -> bool: ...

    def sync(self, since: date | None, today: date | None = None) -> SyncResult: ...


def as_date(value: int | str | datetime | date) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, int):
        return datetime.fromtimestamp(value, tz=timezone.utc).date()
    text = str(value).strip()
    if text.isdigit():
        return datetime.fromtimestamp(int(text), tz=timezone.utc).date()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "T" in text or "+" in text:
        return datetime.fromisoformat(text).date()
    return date.fromisoformat(text[:10])
