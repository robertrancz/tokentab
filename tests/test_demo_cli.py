from tokentab.cli import main
from tokentab.demo import seed_demo
from tokentab.db import connect, list_seats, list_buckets


def test_seed_demo_is_idempotent(tmp_path):
    conn = connect(tmp_path / "demo.db")
    seed_demo(conn)
    n = len(list_buckets(conn))
    seed_demo(conn)
    assert len(list_buckets(conn)) == n
    assert len(list_seats(conn)) == 2
    assert n > 10


def test_report_json(tmp_path, capsys):
    db = tmp_path / "demo.db"
    cfg = tmp_path / "config.toml"
    conn = connect(db)
    seed_demo(conn)
    main(["--db", str(db), "--config", str(cfg), "report", "--json"])
    out = capsys.readouterr().out
    assert "forecast" in out
    assert "metered_mtd" in out
