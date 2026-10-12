from datetime import date

import pytest

from tokentab.models import UsageBucket
from tokentab.pricer import estimate_bucket, price_tokens


def test_price_tokens_gpt4o_mini():
    cost = price_tokens(model="gpt-4o-mini", input_tokens=1_000_000, output_tokens=1_000_000)
    assert cost == pytest.approx(0.75)


def test_estimate_uses_cache_read_rate():
    bucket = UsageBucket(
        source="openai",
        bucket_start=date(2026, 10, 1),
        model="gpt-4o",
        input_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        output_tokens=0,
    )
    assert estimate_bucket(bucket) == pytest.approx(1.25)


def test_unknown_model_falls_back_to_vendor():
    bucket = UsageBucket(
        source="openai",
        bucket_start=date(2026, 10, 1),
        model="mystery-model",
        input_tokens=100,
        vendor_cost_usd=4.2,
    )
    assert estimate_bucket(bucket) == 4.2
