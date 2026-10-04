import sqlite3

from routeiq.cascade import RouteResult
from routeiq.store import NEW_COLUMNS, Store

OLD_SCHEMA = """
CREATE TABLE requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    text TEXT NOT NULL,
    label TEXT,
    confidence REAL,
    tier TEXT,
    action TEXT NOT NULL,
    cost_usd REAL,
    latency_ms REAL,
    error TEXT,
    review_status TEXT,
    final_label TEXT,
    resolved_at TEXT
)
"""


def accepted(label="a"):
    return RouteResult(label, 0.9, "baseline", "accepted", 0.0, 1.0)


def needs_review(label="b"):
    return RouteResult(label, 0.4, "llm", "human_review", 0.001, 500.0)


def column_names(path):
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute("PRAGMA table_info(requests)")}
    finally:
        conn.close()


def test_new_database_has_delivery_columns(tmp_path):
    path = tmp_path / "a.db"
    Store(path)
    assert set(NEW_COLUMNS) <= column_names(path)


def test_migration_adds_columns_to_old_database_and_keeps_rows(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO requests (created_at, text, label, action) VALUES (?,?,?,?)",
        ("2026-01-01T00:00:00", "old request", "a", "accepted"),
    )
    conn.commit()
    conn.close()
    assert not (set(NEW_COLUMNS) & column_names(path))

    store = Store(path)

    assert set(NEW_COLUMNS) <= column_names(path)
    row = store.get(1)
    assert row["text"] == "old request"
    assert row["delivery_status"] is None


def test_migration_can_run_twice(tmp_path):
    path = tmp_path / "a.db"
    Store(path)
    Store(path)
    assert set(NEW_COLUMNS) <= column_names(path)


def test_log_marks_only_human_review_as_pending(tmp_path):
    store = Store(tmp_path / "a.db")
    ok = store.log("fine", accepted())
    review = store.log("unsure", needs_review())
    assert store.get(ok)["review_status"] is None
    assert store.get(review)["review_status"] == "pending"
    assert [item["id"] for item in store.pending()] == [review]


def test_resolve_only_works_on_pending_requests(tmp_path):
    store = Store(tmp_path / "a.db")
    ok = store.log("fine", accepted())
    review = store.log("unsure", needs_review())
    assert store.resolve(ok, "a") is False
    assert store.resolve(review, "a") is True
    assert store.resolve(review, "b") is False
    assert store.get(review)["final_label"] == "a"


def test_mark_delivery_sent(tmp_path):
    store = Store(tmp_path / "a.db")
    rid = store.log("fine", accepted())
    store.mark_delivery(rid, "sent")
    row = store.get(rid)
    assert row["delivery_status"] == "sent"
    assert row["delivered_at"] is not None
    assert row["delivery_error"] is None


def test_mark_delivery_failed_keeps_error_and_no_delivery_time(tmp_path):
    store = Store(tmp_path / "a.db")
    rid = store.log("fine", accepted())
    store.mark_delivery(rid, "failed", "boom")
    row = store.get(rid)
    assert row["delivery_status"] == "failed"
    assert row["delivery_error"] == "boom"
    assert row["delivered_at"] is None


def test_failed_deliveries_lists_only_failed_in_order(tmp_path):
    store = Store(tmp_path / "a.db")
    first = store.log("one", accepted())
    second = store.log("two", accepted())
    third = store.log("three", accepted())
    fourth = store.log("four", accepted())
    store.mark_delivery(first, "failed", "x")
    store.mark_delivery(second, "sent")
    store.mark_delivery(fourth, "failed", "y")
    assert store.failed_deliveries() == [first, fourth]
    assert third not in store.failed_deliveries()


def test_failed_deliveries_respects_limit(tmp_path):
    store = Store(tmp_path / "a.db")
    ids = [store.log(str(i), accepted()) for i in range(3)]
    for rid in ids:
        store.mark_delivery(rid, "failed", "x")
    assert store.failed_deliveries(limit=2) == ids[:2]
