import sqlite3

import pytest

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


# --- delivery_updated_at, retryable deliveries and stats -----------------------

def set_raw(path, request_id, **columns):
    """Veritabanını Store'u atlayarak değiştirir (zamanı eskitmek için)."""
    assignments = ", ".join(f"{name} = ?" for name in columns)
    conn = sqlite3.connect(path)
    conn.execute(f"UPDATE requests SET {assignments} WHERE id = ?", (*columns.values(), request_id))
    conn.commit()
    conn.close()


LONG_AGO = "2000-01-01T00:00:00+00:00"


def test_mark_delivery_records_when_the_status_changed(tmp_path):
    store = Store(tmp_path / "a.db")
    rid = store.log("x", accepted())
    assert store.get(rid)["delivery_updated_at"] is None
    for status in ("pending", "failed", "sent"):
        store.mark_delivery(rid, status)
        assert store.get(rid)["delivery_updated_at"] is not None


def test_sent_delivery_has_matching_timestamps(tmp_path):
    store = Store(tmp_path / "a.db")
    rid = store.log("x", accepted())
    store.mark_delivery(rid, "sent")
    row = store.get(rid)
    assert row["delivered_at"] == row["delivery_updated_at"]


def test_retryable_includes_failed_deliveries(tmp_path):
    store = Store(tmp_path / "a.db")
    rid = store.log("x", accepted())
    store.mark_delivery(rid, "failed", "boom")
    assert store.retryable_deliveries() == [rid]


def test_retryable_skips_a_fresh_pending_delivery(tmp_path):
    store = Store(tmp_path / "a.db")
    rid = store.log("x", accepted())
    store.mark_delivery(rid, "pending")
    assert store.retryable_deliveries() == []


def test_retryable_includes_a_stale_pending_delivery(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    rid = store.log("x", accepted())
    store.mark_delivery(rid, "pending")
    set_raw(path, rid, delivery_updated_at=LONG_AGO)
    assert store.retryable_deliveries() == [rid]


def test_retryable_treats_pending_without_a_timestamp_as_stale(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    rid = store.log("x", accepted())
    store.mark_delivery(rid, "pending")
    set_raw(path, rid, delivery_updated_at=None)
    assert store.retryable_deliveries() == [rid]


def test_retryable_skips_sent_and_untouched_requests(tmp_path):
    store = Store(tmp_path / "a.db")
    sent = store.log("one", accepted())
    store.log("two", accepted())
    store.mark_delivery(sent, "sent")
    assert store.retryable_deliveries() == []


def test_retryable_is_ordered_and_respects_limit(tmp_path):
    store = Store(tmp_path / "a.db")
    ids = [store.log(str(i), accepted()) for i in range(3)]
    for rid in reversed(ids):
        store.mark_delivery(rid, "failed", "x")
    assert store.retryable_deliveries() == ids
    assert store.retryable_deliveries(limit=2) == ids[:2]


def test_stats_on_an_empty_database(tmp_path):
    stats = Store(tmp_path / "a.db").stats()
    assert stats["requests"] == 0
    assert stats["accepted_by_tier"] == {}
    assert stats["human_review"] == 0
    assert stats["review"] == {"pending": 0, "resolved": 0}
    assert stats["degraded"] == 0
    assert stats["cost_usd"] == 0
    assert stats["latency_ms"] == {"avg": 0, "p95": 0.0}
    assert stats["delivery"] == {"pending": 0, "sent": 0, "failed": 0, "retryable": 0}


def test_stats_counts_requests_by_outcome(tmp_path):
    store = Store(tmp_path / "a.db")
    store.log("1", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 10.0))
    second = store.log("2", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 20.0))
    third = store.log("3", RouteResult("b", 0.9, "llm", "accepted", 0.002, 600.0))
    review = store.log(
        "4", RouteResult("b", 0.3, "llm", "human_review", 0.001, 700.0, error="llm: x")
    )
    store.mark_delivery(second, "failed", "x")
    store.mark_delivery(third, "pending")

    stats = store.stats()

    assert stats["requests"] == 4
    assert stats["accepted_by_tier"] == {"baseline": 2, "llm": 1}
    assert stats["human_review"] == 1
    assert stats["review"] == {"pending": 1, "resolved": 0}
    assert stats["degraded"] == 1
    assert stats["cost_usd"] == pytest.approx(0.003)
    assert stats["latency_ms"]["avg"] == pytest.approx(332.5)
    assert stats["latency_ms"]["p95"] == 700.0
    assert stats["delivery"] == {"pending": 1, "sent": 0, "failed": 1, "retryable": 1}

    store.resolve(review, "b")
    assert store.stats()["review"] == {"pending": 0, "resolved": 1}
