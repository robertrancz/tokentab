from tokentab.adapters.aider import parse_analytics_jsonl, parse_chat_history
import pytest


def test_parse_analytics_jsonl():
    text = """
{"event": "message_send", "properties": {"main_model": "gpt-4o-mini", "prompt_tokens": 1000, "completion_tokens": 50, "cost": 0.01}, "time": 1759689600}
{"event": "session_start", "properties": {}}
{"event": "message_send", "properties": {"main_model": "gpt-4o-mini", "prompt_tokens": 2000, "completion_tokens": 80, "cost": 0.02}, "time": 1759689700}
""".strip()
    buckets = parse_analytics_jsonl(text)
    assert len(buckets) == 1
    bucket = buckets[0]
    assert bucket.model == "gpt-4o-mini"
    assert bucket.input_tokens == 3000
    assert bucket.output_tokens == 130
    assert bucket.vendor_cost_usd == pytest.approx(0.03)


def test_parse_chat_history():
    text = """
# aider chat started at 2026-10-05 09:00:00
#### hello
> Tokens: 12k sent, 133 received. Cost: $0.04 message, $0.10 session.
> Tokens: 2k sent, 10 received. Cost: $0.01 message, $0.11 session.
"""
    buckets = parse_chat_history(text)
    assert len(buckets) == 1
    bucket = buckets[0]
    assert bucket.bucket_start.isoformat() == "2026-10-05"
    assert bucket.input_tokens == 14000
    assert bucket.output_tokens == 143
    assert bucket.vendor_cost_usd == pytest.approx(0.05)
