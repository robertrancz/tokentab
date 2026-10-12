from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Literal

Role = Literal["billing", "activity", "seat"]
CostBasis = Literal["vendor", "estimated", "seat"]


@dataclass(frozen=True)
class UsageBucket:
    source: str
    bucket_start: date
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    vendor_cost_usd: float | None = None
    estimated_cost_usd: float | None = None
    cost_basis: CostBasis = "estimated"
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return (
            self.input_tokens
            + self.output_tokens
            + self.cache_read_tokens
            + self.cache_write_tokens
        )


@dataclass(frozen=True)
class DailyCost:
    source: str
    bucket_start: date
    vendor_cost_usd: float


@dataclass
class Seat:
    name: str
    monthly_usd: float
    billing_day: int = 1
    notes: str = ""
    id: int | None = None


@dataclass
class SourceState:
    id: str
    enabled: bool
    role: Role
    last_sync: datetime | None = None
    last_error: str | None = None


@dataclass(frozen=True)
class PriceRate:
    input_per_m: float
    output_per_m: float
    cache_read_per_m: float = 0.0
    cache_write_per_m: float = 0.0
    origin: str = "catalog"


@dataclass(frozen=True)
class Forecast:
    metered_mtd: float
    seats_amortized_mtd: float
    seats_committed: float
    daily_burn: float
    remaining_days: int
    forecast_metered: float
    forecast_run_rate_total: float
    forecast_with_committed_seats: float
    p25: float | None
    p75: float | None
    confidence: str
    what_if_daily_usd: float | None = None
    what_if_month_usd: float | None = None
