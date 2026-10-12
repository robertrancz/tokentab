from datetime import date

import pytest

from tokentab.config import AppConfig, AiderConfig
from tokentab.db import add_seat, set_source_enabled, upsert_buckets, upsert_daily_costs
from tokentab.ledger import billing_source_ids, current_cycle_report
from tokentab.models import DailyCost, Seat, UsageBucket
from tokentab.pricer import apply_pricing


def test_aider_excluded_when_vendor_billing_enabled(conn):
    upsert_daily_costs(
        conn,
        [DailyCost(source="openai", bucket_start=date(2026, 10, 5), vendor_cost_usd=10.0)],
    )
    upsert_buckets(
        conn,
        [
            UsageBucket(
                source="aider",
                bucket_start=date(2026, 10, 5),
                model="gpt-4o",
                input_tokens=1000,
                vendor_cost_usd=10.0,
            )
        ],
    )
    cfg = AppConfig()
    assert "aider" not in billing_source_ids(conn, cfg)
    report = current_cycle_report(conn, cfg, today=date(2026, 10, 6))
    assert report["forecast"].metered_mtd == 10.0


def test_aider_counts_when_flag_set(conn):
    upsert_daily_costs(
        conn,
        [DailyCost(source="openai", bucket_start=date(2026, 10, 5), vendor_cost_usd=10.0)],
    )
    upsert_buckets(
        conn,
        [
            UsageBucket(
                source="aider",
                bucket_start=date(2026, 10, 5),
                model="gpt-4o",
                input_tokens=1000,
                vendor_cost_usd=3.0,
            )
        ],
    )
    cfg = AppConfig(aider=AiderConfig(counts_as_billing=True))
    assert "aider" in billing_source_ids(conn, cfg)
    report = current_cycle_report(conn, cfg, today=date(2026, 10, 6))
    assert report["forecast"].metered_mtd == 13.0


def test_aider_is_billing_if_no_vendor_sources(conn):
    set_source_enabled(conn, "openai", False)
    set_source_enabled(conn, "anthropic", False)
    set_source_enabled(conn, "openrouter", False)
    upsert_buckets(
        conn,
        [
            UsageBucket(
                source="aider",
                bucket_start=date(2026, 10, 5),
                model="gpt-4o-mini",
                input_tokens=1_000_000,
                output_tokens=0,
            )
        ],
    )
    apply_pricing(conn)
    cfg = AppConfig()
    cfg.sources.openai = False
    cfg.sources.anthropic = False
    cfg.sources.openrouter = False
    assert "aider" in billing_source_ids(conn, cfg)
    report = current_cycle_report(conn, cfg, today=date(2026, 10, 6))
    assert report["forecast"].metered_mtd > 0


def test_seats_show_up_as_amortized_not_metered(conn):
    add_seat(conn, Seat(name="Cursor Pro", monthly_usd=31.0, billing_day=1))
    cfg = AppConfig()
    report = current_cycle_report(conn, cfg, today=date(2026, 10, 6))
    assert report["forecast"].metered_mtd == 0
    assert report["forecast"].seats_amortized_mtd == pytest.approx(6.0)
    assert report["forecast"].seats_committed == 31.0
