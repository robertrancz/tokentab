from datetime import date

from tokentab.adapters.openrouter import (
    delta_cost,
    parse_activity,
    parse_credits_payload,
    parse_key_payload,
)


def test_parse_key_usage():
    assert parse_key_payload({"data": {"usage": 12.5, "limit_remaining": 10}}) == 12.5


def test_parse_credits():
    credits, usage = parse_credits_payload(
        {"data": {"total_credits": 100.5, "total_usage": 25.75}}
    )
    assert credits == 100.5
    assert usage == 25.75


def test_snapshot_delta_positive_only():
    costs = delta_cost(10.0, 15.5, date(2026, 10, 6))
    assert costs[0].vendor_cost_usd == 5.5
    assert delta_cost(None, 15.5, date(2026, 10, 6)) == []
    assert delta_cost(20.0, 15.0, date(2026, 10, 6)) == []


def test_parse_activity_aggregates_by_day_and_model():
    payload = {
        "data": [
            {
                "date": "2026-10-05",
                "model": "openai/gpt-4.1",
                "prompt_tokens": 50,
                "completion_tokens": 125,
                "cached_tokens": 10,
                "usage": 0.015,
                "byok_usage_inference": 0.0,
            },
            {
                "date": "2026-10-05",
                "model": "openai/gpt-4.1",
                "prompt_tokens": 50,
                "completion_tokens": 75,
                "cached_tokens": 0,
                "usage": 0.010,
                "byok_usage_inference": 0.002,
            },
            {
                "date": "2026-10-06",
                "model": "anthropic/claude-sonnet-4",
                "prompt_tokens": 1000,
                "completion_tokens": 200,
                "cached_tokens": 0,
                "usage": 1.25,
                "byok_usage_inference": 0,
            },
        ]
    }
    buckets, costs = parse_activity(payload)
    assert len(buckets) == 2
    gpt = next(b for b in buckets if b.model == "openai/gpt-4.1")
    assert gpt.bucket_start == date(2026, 10, 5)
    assert gpt.input_tokens == 100
    assert gpt.output_tokens == 200
    assert gpt.cache_read_tokens == 10
    assert gpt.vendor_cost_usd == 0.027
    by_day = {c.bucket_start: c.vendor_cost_usd for c in costs}
    assert by_day[date(2026, 10, 5)] == 0.027
    assert by_day[date(2026, 10, 6)] == 1.25
