from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from tokentab.db import add_seat, upsert_buckets, upsert_daily_costs
from tokentab.models import DailyCost, Seat, UsageBucket
from tokentab.pricer import apply_pricing


def seed_demo(conn: sqlite3.Connection, today: date | None = None) -> None:
    today = today or date.today()
    if conn.execute("SELECT COUNT(*) AS n FROM usage_buckets").fetchone()["n"]:
        return
    models = [
        ("openai", "gpt-4o", 120_000, 18_000, 2.8),
        ("openai", "gpt-4o-mini", 400_000, 40_000, 0.12),
        ("anthropic", "claude-sonnet-4-5", 90_000, 22_000, 3.1),
        ("openrouter", "anthropic/claude-3.7-sonnet", 40_000, 8_000, 1.4),
        ("aider", "gpt-4o-mini", 30_000, 4_000, 0.05),
    ]
    for offset in range(14, -1, -1):
        day = today - timedelta(days=offset)
        scale = 0.6 + (offset % 5) * 0.15
        day_costs: dict[str, float] = {}
        for source, model, inp, out, cost in models:
            upsert_buckets(
                conn,
                [
                    UsageBucket(
                        source=source,
                        bucket_start=day,
                        model=model,
                        input_tokens=int(inp * scale),
                        output_tokens=int(out * scale),
                    )
                ],
            )
            if source != "aider":
                day_costs[source] = day_costs.get(source, 0.0) + cost * scale
        upsert_daily_costs(
            conn,
            [
                DailyCost(source=source, bucket_start=day, vendor_cost_usd=round(usd, 4))
                for source, usd in day_costs.items()
            ],
        )
    add_seat(
        conn,
        Seat(name="Cursor Pro", monthly_usd=20.0, notes="Seat only — included quota unknown"),
    )
    add_seat(conn, Seat(name="GitHub Copilot", monthly_usd=19.0, notes="Seat only"))
    apply_pricing(conn)
