from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from pathlib import Path

from tokentab.models import DailyCost, Seat, SourceState, UsageBucket
from tokentab.paths import db_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    role TEXT NOT NULL,
    last_sync TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS usage_buckets (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    vendor_cost_usd REAL,
    estimated_cost_usd REAL,
    cost_basis TEXT NOT NULL DEFAULT 'estimated',
    raw_json TEXT,
    UNIQUE(source, bucket_start, model)
);

CREATE TABLE IF NOT EXISTS daily_costs (
    source TEXT NOT NULL,
    bucket_start TEXT NOT NULL,
    vendor_cost_usd REAL NOT NULL,
    PRIMARY KEY (source, bucket_start)
);

CREATE TABLE IF NOT EXISTS seats (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    monthly_usd REAL NOT NULL,
    billing_day INTEGER NOT NULL DEFAULT 1,
    notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS sync_cursors (
    source TEXT PRIMARY KEY,
    watermark TEXT
);

CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    usage_usd REAL,
    extra_json TEXT
);
"""

DEFAULT_SOURCES: list[tuple[str, str]] = [
    ("openai", "billing"),
    ("anthropic", "billing"),
    ("openrouter", "billing"),
    ("aider", "activity"),
    ("seats", "seat"),
]


def connect(path: Path | None = None) -> sqlite3.Connection:
    target = path or db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: UI + sync worker may open separate connections
    # to the same file; each connection is still only used from its own thread.
    conn = sqlite3.connect(str(target), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    for source_id, role in DEFAULT_SOURCES:
        conn.execute(
            "INSERT OR IGNORE INTO sources (id, enabled, role) VALUES (?, 1, ?)",
            (source_id, role),
        )
    conn.commit()


def _date_str(value: date) -> str:
    return value.isoformat()


def _parse_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def upsert_buckets(conn: sqlite3.Connection, buckets: list[UsageBucket]) -> None:
    for bucket in buckets:
        conn.execute(
            """
            INSERT INTO usage_buckets (
                source, bucket_start, model, input_tokens, output_tokens,
                cache_read_tokens, cache_write_tokens, vendor_cost_usd,
                estimated_cost_usd, cost_basis, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, bucket_start, model) DO UPDATE SET
                input_tokens = excluded.input_tokens,
                output_tokens = excluded.output_tokens,
                cache_read_tokens = excluded.cache_read_tokens,
                cache_write_tokens = excluded.cache_write_tokens,
                vendor_cost_usd = excluded.vendor_cost_usd,
                estimated_cost_usd = COALESCE(excluded.estimated_cost_usd, usage_buckets.estimated_cost_usd),
                cost_basis = excluded.cost_basis,
                raw_json = excluded.raw_json
            """,
            (
                bucket.source,
                _date_str(bucket.bucket_start),
                bucket.model,
                bucket.input_tokens,
                bucket.output_tokens,
                bucket.cache_read_tokens,
                bucket.cache_write_tokens,
                bucket.vendor_cost_usd,
                bucket.estimated_cost_usd,
                bucket.cost_basis,
                json.dumps(bucket.raw) if bucket.raw else None,
            ),
        )
    conn.commit()


def replace_source_buckets(
    conn: sqlite3.Connection, source: str, buckets: list[UsageBucket]
) -> None:
    conn.execute("DELETE FROM usage_buckets WHERE source = ?", (source,))
    conn.commit()
    upsert_buckets(conn, buckets)


def upsert_daily_costs(conn: sqlite3.Connection, costs: list[DailyCost]) -> None:
    for cost in costs:
        conn.execute(
            """
            INSERT INTO daily_costs (source, bucket_start, vendor_cost_usd)
            VALUES (?, ?, ?)
            ON CONFLICT(source, bucket_start) DO UPDATE SET
                vendor_cost_usd = excluded.vendor_cost_usd
            """,
            (cost.source, _date_str(cost.bucket_start), cost.vendor_cost_usd),
        )
    conn.commit()


def list_buckets(
    conn: sqlite3.Connection,
    *,
    start: date | None = None,
    end: date | None = None,
    sources: list[str] | None = None,
) -> list[UsageBucket]:
    sql = "SELECT * FROM usage_buckets WHERE 1=1"
    params: list[object] = []
    if start:
        sql += " AND bucket_start >= ?"
        params.append(_date_str(start))
    if end:
        sql += " AND bucket_start <= ?"
        params.append(_date_str(end))
    if sources:
        sql += f" AND source IN ({','.join('?' for _ in sources)})"
        params.extend(sources)
    sql += " ORDER BY bucket_start, source, model"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_bucket(row) for row in rows]


def list_daily_costs(
    conn: sqlite3.Connection,
    *,
    start: date | None = None,
    end: date | None = None,
    sources: list[str] | None = None,
) -> list[DailyCost]:
    sql = "SELECT * FROM daily_costs WHERE 1=1"
    params: list[object] = []
    if start:
        sql += " AND bucket_start >= ?"
        params.append(_date_str(start))
    if end:
        sql += " AND bucket_start <= ?"
        params.append(_date_str(end))
    if sources:
        sql += f" AND source IN ({','.join('?' for _ in sources)})"
        params.extend(sources)
    rows = conn.execute(sql, params).fetchall()
    return [
        DailyCost(
            source=row["source"],
            bucket_start=_parse_date(row["bucket_start"]),
            vendor_cost_usd=float(row["vendor_cost_usd"]),
        )
        for row in rows
    ]


def _row_to_bucket(row: sqlite3.Row) -> UsageBucket:
    raw = json.loads(row["raw_json"]) if row["raw_json"] else {}
    return UsageBucket(
        source=row["source"],
        bucket_start=_parse_date(row["bucket_start"]),
        model=row["model"],
        input_tokens=int(row["input_tokens"]),
        output_tokens=int(row["output_tokens"]),
        cache_read_tokens=int(row["cache_read_tokens"]),
        cache_write_tokens=int(row["cache_write_tokens"]),
        vendor_cost_usd=row["vendor_cost_usd"],
        estimated_cost_usd=row["estimated_cost_usd"],
        cost_basis=row["cost_basis"],
        raw=raw,
    )


def list_seats(conn: sqlite3.Connection) -> list[Seat]:
    rows = conn.execute(
        "SELECT * FROM seats ORDER BY name COLLATE NOCASE"
    ).fetchall()
    return [
        Seat(
            id=row["id"],
            name=row["name"],
            monthly_usd=float(row["monthly_usd"]),
            billing_day=int(row["billing_day"]),
            notes=row["notes"] or "",
        )
        for row in rows
    ]


def add_seat(conn: sqlite3.Connection, seat: Seat) -> int:
    cur = conn.execute(
        "INSERT INTO seats (name, monthly_usd, billing_day, notes) VALUES (?, ?, ?, ?)",
        (seat.name, seat.monthly_usd, seat.billing_day, seat.notes),
    )
    conn.commit()
    return int(cur.lastrowid)


def update_seat(conn: sqlite3.Connection, seat: Seat) -> None:
    if seat.id is None:
        raise ValueError("seat id required")
    conn.execute(
        """
        UPDATE seats SET name = ?, monthly_usd = ?, billing_day = ?, notes = ?
        WHERE id = ?
        """,
        (seat.name, seat.monthly_usd, seat.billing_day, seat.notes, seat.id),
    )
    conn.commit()


def delete_seat(conn: sqlite3.Connection, seat_id: int) -> None:
    conn.execute("DELETE FROM seats WHERE id = ?", (seat_id,))
    conn.commit()


def list_sources(conn: sqlite3.Connection) -> list[SourceState]:
    rows = conn.execute("SELECT * FROM sources ORDER BY id").fetchall()
    result: list[SourceState] = []
    for row in rows:
        last_sync = None
        if row["last_sync"]:
            last_sync = datetime.fromisoformat(row["last_sync"])
        result.append(
            SourceState(
                id=row["id"],
                enabled=bool(row["enabled"]),
                role=row["role"],
                last_sync=last_sync,
                last_error=row["last_error"],
            )
        )
    return result


def set_source_enabled(conn: sqlite3.Connection, source_id: str, enabled: bool) -> None:
    conn.execute(
        "UPDATE sources SET enabled = ? WHERE id = ?",
        (1 if enabled else 0, source_id),
    )
    conn.commit()


def set_source_role(conn: sqlite3.Connection, source_id: str, role: str) -> None:
    conn.execute("UPDATE sources SET role = ? WHERE id = ?", (role, source_id))
    conn.commit()


def mark_source_sync(
    conn: sqlite3.Connection,
    source_id: str,
    *,
    error: str | None = None,
    when: datetime | None = None,
) -> None:
    conn.execute(
        "UPDATE sources SET last_sync = ?, last_error = ? WHERE id = ?",
        ((when or datetime.now()).isoformat(timespec="seconds"), error, source_id),
    )
    conn.commit()


def get_cursor(conn: sqlite3.Connection, source: str) -> date | None:
    row = conn.execute(
        "SELECT watermark FROM sync_cursors WHERE source = ?", (source,)
    ).fetchone()
    if not row or not row["watermark"]:
        return None
    return _parse_date(row["watermark"])


def set_cursor(conn: sqlite3.Connection, source: str, watermark: date) -> None:
    conn.execute(
        """
        INSERT INTO sync_cursors (source, watermark) VALUES (?, ?)
        ON CONFLICT(source) DO UPDATE SET watermark = excluded.watermark
        """,
        (source, _date_str(watermark)),
    )
    conn.commit()


def add_snapshot(
    conn: sqlite3.Connection, source: str, usage_usd: float, extra: dict | None = None
) -> None:
    conn.execute(
        "INSERT INTO snapshots (source, captured_at, usage_usd, extra_json) VALUES (?, ?, ?, ?)",
        (
            source,
            datetime.now().isoformat(timespec="seconds"),
            usage_usd,
            json.dumps(extra) if extra else None,
        ),
    )
    conn.commit()


def last_snapshot(conn: sqlite3.Connection, source: str) -> tuple[datetime, float] | None:
    row = conn.execute(
        """
        SELECT captured_at, usage_usd FROM snapshots
        WHERE source = ? ORDER BY id DESC LIMIT 1
        """,
        (source,),
    ).fetchone()
    if not row:
        return None
    return datetime.fromisoformat(row["captured_at"]), float(row["usage_usd"] or 0)


def update_bucket_pricing(
    conn: sqlite3.Connection,
    source: str,
    bucket_start: date,
    model: str,
    estimated: float,
    vendor: float | None,
    basis: str,
) -> None:
    conn.execute(
        """
        UPDATE usage_buckets
        SET estimated_cost_usd = ?, vendor_cost_usd = ?, cost_basis = ?
        WHERE source = ? AND bucket_start = ? AND model = ?
        """,
        (estimated, vendor, basis, source, _date_str(bucket_start), model),
    )
