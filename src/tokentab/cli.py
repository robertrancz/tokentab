from __future__ import annotations

import argparse
import json
from getpass import getpass
from pathlib import Path

from tokentab.config import load_config
from tokentab.db import connect
from tokentab.demo import seed_demo
from tokentab.ledger import current_cycle_report, forecast_to_dict
from tokentab.paths import config_path, db_path
from tokentab.secrets import (
    ANTHROPIC_ADMIN,
    OPENAI_ADMIN,
    OPENROUTER,
    OPENROUTER_MGMT,
    set_secret,
)
from tokentab.sync import sync_all, sync_message


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="tokentab",
        description="Local dashboard for API token usage, seat costs, and month-end forecast.",
    )
    parser.add_argument("--db", type=Path, default=None, help="SQLite path (defaults to user data dir)")
    parser.add_argument("--config", type=Path, default=None, help="config.toml path")
    parser.add_argument("--demo", action="store_true", help="Launch with seeded demo data (no vendor APIs)")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("sync", help="Fetch usage from configured sources")
    report = sub.add_parser("report", help="Print this cycle's totals")
    report.add_argument("--json", action="store_true")

    sub.add_parser("config-path", help="Print config and database paths")
    keys = sub.add_parser("set-key", help="Store a vendor key in the OS keyring")
    keys.add_argument(
        "name",
        choices=["openai", "anthropic", "openrouter", "openrouter-mgmt"],
    )
    keys.add_argument("--value", default=None, help="Key value (otherwise prompted)")

    args = parser.parse_args(argv)
    if args.cmd == "config-path":
        print(f"config: {args.config or config_path()}")
        print(f"db:     {args.db or db_path()}")
        return
    if args.cmd == "set-key":
        value = args.value or getpass("API key: ")
        mapping = {
            "openai": OPENAI_ADMIN,
            "anthropic": ANTHROPIC_ADMIN,
            "openrouter": OPENROUTER,
            "openrouter-mgmt": OPENROUTER_MGMT,
        }
        set_secret(mapping[args.name], value)
        print(f"Saved {args.name} to keyring service 'tokentab'.")
        return

    database = args.db
    if args.demo and database is None:
        from tokentab.paths import data_dir

        database = data_dir() / "demo.db"
    conn = connect(database)
    cfg = load_config(args.config)
    if args.demo:
        seed_demo(conn)

    if args.cmd == "sync":
        if args.demo:
            print("demo: skipped vendor APIs (seeded local data)")
            return
        print(sync_message(sync_all(conn, cfg)))
        return
    if args.cmd == "report":
        data = current_cycle_report(conn, cfg)
        data = dict(data)
        data["forecast"] = forecast_to_dict(data["forecast"])
        if args.json:
            print(json.dumps(data, indent=2))
            return
        fc = data["forecast"]
        print(f"Cycle {data['cycle_start']} -> {data['cycle_end']}")
        print(f"Metered MTD     ${fc['metered_mtd']:.2f}")
        print(f"Seats amortized ${fc['seats_amortized_mtd']:.2f}")
        print(f"Seats committed ${fc['seats_committed']:.2f}")
        print(f"Burn / day      ${fc['daily_burn']:.2f} ({fc['confidence']})")
        print(f"Forecast + seats ${fc['forecast_with_committed_seats']:.2f}")
        print(f"Billing sources: {', '.join(data['billing_sources']) or 'none'}")
        return

    from tokentab.app import TokenTabApp

    TokenTabApp(db_path=database, config_path=args.config, demo=args.demo).run()


if __name__ == "__main__":
    main()
