from datetime import date

from tokentab.adapters.openai_usage import parse_costs_page, parse_usage_page


def test_parse_openai_usage():
    payload = {
        "data": [
            {
                "start_time": 1759622400,
                "results": [
                    {
                        "model": "gpt-4o",
                        "input_tokens": 1000,
                        "output_tokens": 20,
                        "input_cached_tokens": 100,
                    },
                    {
                        "model": "gpt-4o",
                        "input_tokens": 500,
                        "output_tokens": 10,
                        "input_cached_tokens": 0,
                    },
                ],
            }
        ]
    }
    buckets = parse_usage_page(payload)
    assert len(buckets) == 1
    bucket = buckets[0]
    assert bucket.model == "gpt-4o"
    assert bucket.input_tokens == 1500
    assert bucket.output_tokens == 30
    assert bucket.cache_read_tokens == 100


def test_parse_openai_costs():
    payload = {
        "data": [
            {
                "start_time": "2026-10-05",
                "results": [
                    {"amount": {"value": 1.25, "currency": "usd"}},
                    {"amount": {"value": 0.25, "currency": "usd"}},
                ],
            }
        ]
    }
    costs = parse_costs_page(payload)
    assert costs[0].bucket_start == date(2026, 10, 5)
    assert costs[0].vendor_cost_usd == 1.5
