from datetime import date

from tokentab.adapters.anthropic_usage import parse_cost_report, parse_usage_report


def test_parse_anthropic_usage():
    payload = {
        "data": [
            {
                "starting_at": "2026-10-05T00:00:00Z",
                "ending_at": "2026-10-06T00:00:00Z",
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
        ]
    }
    buckets = parse_usage_report(payload)
    assert buckets[0].bucket_start == date(2026, 10, 5)
    assert buckets[0].cache_read_tokens == 200
    assert buckets[0].cache_write_tokens == 50
    assert buckets[0].output_tokens == 40
    assert buckets[0].input_tokens == 1050


def test_parse_anthropic_cost_cents():
    payload = {
        "data": [
            {
                "starting_at": "2026-10-05T00:00:00Z",
                "results": [{"amount": "123.45"}],
            }
        ]
    }
    costs = parse_cost_report(payload)
    assert costs[0].vendor_cost_usd == 1.2345
