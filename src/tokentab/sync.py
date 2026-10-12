from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from tokentab.adapters.aider import AiderAdapter
from tokentab.adapters.anthropic_usage import AnthropicAdapter
from tokentab.adapters.openai_usage import OpenAIAdapter
from tokentab.adapters.openrouter import OpenRouterAdapter
from tokentab.config import AppConfig
from tokentab.db import (
    get_cursor,
    list_sources,
    mark_source_sync,
    replace_source_buckets,
    set_cursor,
    set_source_role,
    upsert_buckets,
    upsert_daily_costs,
)
from tokentab.pricer import apply_pricing


def sync_all(conn: sqlite3.Connection, cfg: AppConfig, today: date | None = None) -> dict[str, str]:
    today = today or date.today()
    aider_role = "billing" if cfg.aider.counts_as_billing else "activity"
    set_source_role(conn, "aider", aider_role)

    adapters = {
        "openai": OpenAIAdapter(cfg=cfg),
        "anthropic": AnthropicAdapter(cfg=cfg),
        "openrouter": OpenRouterAdapter(conn, cfg=cfg),
        "aider": AiderAdapter(cfg),
    }
    enabled = {s.id: s.enabled for s in list_sources(conn)}
    results: dict[str, str] = {}
    for source_id, adapter in adapters.items():
        if not enabled.get(source_id, True):
            results[source_id] = "disabled"
            continue
        if not adapter.configured():
            mark_source_sync(conn, source_id, error="not configured")
            results[source_id] = "not configured"
            continue
        since = get_cursor(conn, source_id)
        if since:
            since = since - timedelta(days=2)
        try:
            result = adapter.sync(since, today=today)
            if result.replace:
                replace_source_buckets(conn, source_id, result.buckets)
            else:
                upsert_buckets(conn, result.buckets)
            if result.daily_costs:
                upsert_daily_costs(conn, result.daily_costs)
            if result.watermark:
                set_cursor(conn, source_id, result.watermark)
            mark_source_sync(conn, source_id, error=None)
            results[source_id] = f"ok ({len(result.buckets)} buckets, {len(result.daily_costs)} cost days)"
        except Exception as exc:
            mark_source_sync(conn, source_id, error=str(exc))
            results[source_id] = f"error: {exc}"
    apply_pricing(conn)
    return results


def sync_message(results: dict[str, str]) -> str:
    parts = [f"{k}: {v}" for k, v in results.items()]
    return " | ".join(parts)
