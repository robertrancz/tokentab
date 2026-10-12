from __future__ import annotations

import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from tokentab.adapters.base import SyncResult
from tokentab.config import AppConfig
from tokentab.models import UsageBucket

TOKEN_LINE = re.compile(
    r">\s*Tokens:\s*([0-9]+(?:\.[0-9]+)?k?)\s+sent,\s*([0-9]+(?:\.[0-9]+)?k?)\s+received"
    r"(?:\.\s*Cost:\s*\$([0-9]+\.[0-9]+)\s+message)?",
    re.IGNORECASE,
)
STARTED = re.compile(r"#\s*aider chat started at\s+(.+)", re.IGNORECASE)


def _parse_count(text: str) -> int:
    text = text.strip().lower()
    if text.endswith("k"):
        return int(float(text[:-1]) * 1000)
    return int(float(text))


def parse_analytics_jsonl(text: str, source: str = "aider") -> list[UsageBucket]:
    by_key: dict[tuple[date, str], dict[str, Any]] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event") != "message_send":
            continue
        props = event.get("properties") or {}
        ts = event.get("time")
        if ts is None:
            continue
        day = datetime.fromtimestamp(int(ts)).date()
        model = props.get("main_model") or "(unknown)"
        key = (day, str(model))
        row = by_key.setdefault(
            key,
            {
                "input": 0,
                "output": 0,
                "cost": 0.0,
                "has_cost": False,
            },
        )
        row["input"] += int(props.get("prompt_tokens") or 0)
        row["output"] += int(props.get("completion_tokens") or 0)
        if props.get("cost") is not None:
            row["cost"] += float(props["cost"])
            row["has_cost"] = True
    buckets = []
    for (day, model), row in by_key.items():
        buckets.append(
            UsageBucket(
                source=source,
                bucket_start=day,
                model=model,
                input_tokens=row["input"],
                output_tokens=row["output"],
                vendor_cost_usd=row["cost"] if row["has_cost"] else None,
                cost_basis="vendor" if row["has_cost"] else "estimated",
            )
        )
    return buckets


def parse_chat_history(text: str, source: str = "aider") -> list[UsageBucket]:
    current_day = date.today()
    by_key: dict[tuple[date, str], dict[str, Any]] = {}
    model = "(aider)"
    for line in text.splitlines():
        started = STARTED.search(line)
        if started:
            stamp = started.group(1).strip()
            try:
                current_day = datetime.fromisoformat(stamp.replace("Z", "")).date()
            except ValueError:
                try:
                    current_day = datetime.strptime(stamp[:19], "%Y-%m-%d %H:%M:%S").date()
                except ValueError:
                    pass
            continue
        match = TOKEN_LINE.search(line)
        if not match:
            continue
        sent = _parse_count(match.group(1))
        received = _parse_count(match.group(2))
        cost = float(match.group(3)) if match.group(3) else None
        key = (current_day, model)
        row = by_key.setdefault(key, {"input": 0, "output": 0, "cost": 0.0, "has_cost": False})
        row["input"] += sent
        row["output"] += received
        if cost is not None:
            row["cost"] += cost
            row["has_cost"] = True
    return [
        UsageBucket(
            source=source,
            bucket_start=day,
            model=model,
            input_tokens=row["input"],
            output_tokens=row["output"],
            vendor_cost_usd=row["cost"] if row["has_cost"] else None,
            cost_basis="vendor" if row["has_cost"] else "estimated",
        )
        for (day, model), row in by_key.items()
    ]


def default_analytics_path() -> Path:
    return Path.home() / ".aider" / "analytics.jsonl"


class AiderAdapter:
    id = "aider"
    role = "activity"

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        if cfg.aider.counts_as_billing:
            self.role = "billing"

    def configured(self) -> bool:
        path = self._analytics_path()
        if path.exists():
            return True
        return any(Path(p).exists() for p in self.cfg.aider.history_dirs)

    def _analytics_path(self) -> Path:
        if self.cfg.aider.analytics_log:
            return Path(self.cfg.aider.analytics_log).expanduser()
        return default_analytics_path()

    def sync(self, since: date | None, today: date | None = None) -> SyncResult:
        buckets: list[UsageBucket] = []
        path = self._analytics_path()
        if path.exists():
            buckets.extend(parse_analytics_jsonl(path.read_text(encoding="utf-8", errors="replace")))
        for directory in self.cfg.aider.history_dirs:
            hist = Path(directory).expanduser()
            if hist.is_file() and hist.name.endswith(".md"):
                buckets.extend(parse_chat_history(hist.read_text(encoding="utf-8", errors="replace")))
                continue
            if hist.is_dir():
                for file in hist.glob("**/.aider.chat.history.md"):
                    buckets.extend(
                        parse_chat_history(file.read_text(encoding="utf-8", errors="replace"))
                    )
        merged: dict[tuple[date, str], UsageBucket] = {}
        for bucket in buckets:
            if since and bucket.bucket_start < since:
                continue
            key = (bucket.bucket_start, bucket.model)
            existing = merged.get(key)
            if existing is None:
                merged[key] = bucket
                continue
            cost = None
            if existing.vendor_cost_usd is not None or bucket.vendor_cost_usd is not None:
                cost = (existing.vendor_cost_usd or 0) + (bucket.vendor_cost_usd or 0)
            merged[key] = UsageBucket(
                source="aider",
                bucket_start=bucket.bucket_start,
                model=bucket.model,
                input_tokens=existing.input_tokens + bucket.input_tokens,
                output_tokens=existing.output_tokens + bucket.output_tokens,
                vendor_cost_usd=cost,
                cost_basis="vendor" if cost is not None else "estimated",
            )
        today = today or date.today()
        return SyncResult(
            buckets=list(merged.values()),
            daily_costs=[],
            replace=True,
            watermark=today,
        )
