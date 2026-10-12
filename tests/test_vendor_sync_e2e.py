"""Prove OpenAI / Anthropic sync write historical buckets + daily costs (not empty snapshots)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import httpx

from tokentab.adapters.anthropic_usage import AnthropicAdapter
from tokentab.adapters.openai_usage import OpenAIAdapter
from tokentab.config import AppConfig
from tokentab.db import list_buckets, list_daily_costs
from tokentab.ledger import current_cycle_report
from tokentab.pricer import apply_pricing
from tokentab.secrets import ANTHROPIC_ADMIN, OPENAI_ADMIN


def _unix(day: date) -> int:
    return int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())


def test_openai_sync_writes_history_and_shows_in_report(conn, monkeypatch):
    monkeypatch.setenv("TOKENTAB_OPENAI_ADMIN_KEY", "sk-test-openai")
    day = date(2026, 10, 10)
    start_ts = _unix(day)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/usage/completions"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "start_time": start_ts,
                            "results": [
                                {
                                    "model": "gpt-4o",
                                    "input_tokens": 1000,
                                    "output_tokens": 200,
                                    "input_cached_tokens": 100,
                                }
                            ],
                        }
                    ],
                    "has_more": False,
                },
            )
        if request.url.path.endswith("/costs"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "start_time": start_ts,
                            "results": [{"amount": {"value": 1.25, "currency": "usd"}}],
                        }
                    ],
                    "has_more": False,
                },
            )
        return httpx.Response(404, json={"error": "unexpected"})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = OpenAIAdapter(client=client, cfg=AppConfig()).sync(
        since=date(2026, 10, 1), today=date(2026, 10, 12)
    )
    assert len(result.buckets) == 1
    assert result.buckets[0].model == "gpt-4o"
    assert result.buckets[0].input_tokens == 1000
    assert len(result.daily_costs) == 1
    assert result.daily_costs[0].vendor_cost_usd == 1.25

    from tokentab.db import upsert_buckets, upsert_daily_costs

    upsert_buckets(conn, result.buckets)
    upsert_daily_costs(conn, result.daily_costs)
    apply_pricing(conn)

    report = current_cycle_report(conn, AppConfig(), today=date(2026, 10, 12))
    assert report["forecast"].metered_mtd == 1.25
    assert report["by_source"]["openai"] == 1.25
    assert report["by_model"][0]["model"] == "gpt-4o"
    assert list_buckets(conn)
    assert list_daily_costs(conn)


def test_anthropic_sync_writes_history_and_shows_in_report(conn, monkeypatch):
    monkeypatch.setenv("TOKENTAB_ANTHROPIC_ADMIN_KEY", "sk-ant-admin01-test")
    day = date(2026, 10, 11)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/usage_report/messages"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "starting_at": f"{day.isoformat()}T00:00:00Z",
                            "ending_at": "2026-10-12T00:00:00Z",
                            "results": [
                                {
                                    "model": "claude-sonnet-4-5",
                                    "uncached_input_tokens": 800,
                                    "cache_read_input_tokens": 200,
                                    "cache_creation": {
                                        "ephemeral_5m_input_tokens": 50,
                                        "ephemeral_1h_input_tokens": 0,
                                    },
                                    "output_tokens": 40,
                                }
                            ],
                        }
                    ],
                    "has_more": False,
                },
            )
        if path.endswith("/cost_report"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "starting_at": f"{day.isoformat()}T00:00:00Z",
                            "results": [{"amount": "250.00"}],  # cents → $2.50
                        }
                    ],
                    "has_more": False,
                },
            )
        return httpx.Response(404, json={"error": path})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    result = AnthropicAdapter(client=client, cfg=AppConfig()).sync(
        since=date(2026, 10, 1), today=date(2026, 10, 12)
    )
    assert len(result.buckets) == 1
    assert result.buckets[0].model == "claude-sonnet-4-5"
    assert result.buckets[0].cache_read_tokens == 200
    assert result.daily_costs[0].vendor_cost_usd == 2.5

    from tokentab.db import upsert_buckets, upsert_daily_costs

    upsert_buckets(conn, result.buckets)
    upsert_daily_costs(conn, result.daily_costs)
    apply_pricing(conn)

    report = current_cycle_report(conn, AppConfig(), today=date(2026, 10, 12))
    assert report["forecast"].metered_mtd == 2.5
    assert report["by_source"]["anthropic"] == 2.5
    assert any(m["model"] == "claude-sonnet-4-5" for m in report["by_model"])


def test_openai_and_anthropic_configured_flags(monkeypatch):
    monkeypatch.delenv("TOKENTAB_OPENAI_ADMIN_KEY", raising=False)
    monkeypatch.delenv("OPENAI_ADMIN_KEY", raising=False)
    monkeypatch.delenv("TOKENTAB_ANTHROPIC_ADMIN_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_ADMIN_KEY", raising=False)
    # Clear keyring lookups by forcing empty env path only; configured() uses get_secret.
    # If keyring has a real key this could still be True — stub get_secret.
    import tokentab.adapters.openai_usage as oi
    import tokentab.adapters.anthropic_usage as an

    monkeypatch.setattr(oi, "get_secret", lambda name: None)
    monkeypatch.setattr(an, "get_secret", lambda name: None)
    assert OpenAIAdapter().configured() is False
    assert AnthropicAdapter().configured() is False

    monkeypatch.setattr(oi, "get_secret", lambda name: "x" if name == OPENAI_ADMIN else None)
    monkeypatch.setattr(an, "get_secret", lambda name: "y" if name == ANTHROPIC_ADMIN else None)
    assert OpenAIAdapter().configured() is True
    assert AnthropicAdapter().configured() is True
