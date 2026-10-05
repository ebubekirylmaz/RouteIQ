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


# --- list_requests ---------------------------------------------------------------

def make_store_with_history(tmp_path):
    """Beş istek: kabul, kabul (LLM), insana düşen, çözülmüş insan kararı, çöken katman."""
    store = Store(tmp_path / "a.db")
    ids = {}
    ids["accepted_baseline"] = store.log(
        "my card got declined", RouteResult("card_declined", 0.9, "baseline", "accepted", 0.0, 1.0)
    )
    ids["accepted_llm"] = store.log(
        "I lost my wallet", RouteResult("report_lost_card", 0.95, "llm", "accepted", 0.001, 600.0)
    )
    ids["pending_review"] = store.log(
        "delete my saved card", RouteResult("freeze_account", 0.6, "llm", "human_review", 0.001, 700.0)
    )
    ids["resolved_review"] = store.log(
        "freeze it please", RouteResult("freeze_account", 0.5, "llm", "human_review", 0.001, 650.0)
    )
    store.resolve(ids["resolved_review"], "freeze_account")
    ids["degraded"] = store.log(
        "something odd", RouteResult("a", 0.3, "baseline", "human_review", 0.0, 5.0, error="llm: boom")
    )
    store.mark_delivery(ids["accepted_baseline"], "sent")
    store.mark_delivery(ids["accepted_llm"], "failed", "boom")
    return store, ids


def listed_ids(store, **filters):
    rows, _ = store.list_requests(**filters)
    return [row["id"] for row in rows]


def test_list_requests_without_filters_returns_everything_newest_first(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    rows, total = store.list_requests()
    assert total == 5
    assert [r["id"] for r in rows] == sorted(ids.values(), reverse=True)


def test_list_requests_can_return_the_oldest_first(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    assert listed_ids(store, newest_first=False) == sorted(ids.values())


def test_list_requests_rows_contain_all_columns(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    row = store.list_requests(limit=1, newest_first=False)[0][0]
    for column in ("id", "created_at", "text", "label", "confidence", "tier", "action", "cost_usd",
                   "latency_ms", "error", "review_status", "final_label", "resolved_at",
                   "delivery_status", "delivery_error", "delivered_at"):
        assert column in row


def test_filter_by_action(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    assert set(listed_ids(store, action="accepted")) == {ids["accepted_baseline"], ids["accepted_llm"]}
    assert len(listed_ids(store, action="human_review")) == 3


def test_filter_by_tier(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    assert listed_ids(store, tier="baseline", newest_first=False) == [
        ids["accepted_baseline"], ids["degraded"],
    ]


def test_filter_by_review_status(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    assert set(listed_ids(store, review_status="pending")) == {ids["pending_review"], ids["degraded"]}
    assert listed_ids(store, review_status="resolved") == [ids["resolved_review"]]


def test_filter_by_delivery_status(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    assert listed_ids(store, delivery_status="sent") == [ids["accepted_baseline"]]
    assert listed_ids(store, delivery_status="failed") == [ids["accepted_llm"]]
    assert listed_ids(store, delivery_status="pending") == []


def test_filter_by_degraded(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    assert listed_ids(store, degraded=True) == [ids["degraded"]]
    assert ids["degraded"] not in listed_ids(store, degraded=False)
    assert len(listed_ids(store, degraded=False)) == 4


def test_filters_combine_with_and(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    assert listed_ids(store, action="human_review", tier="llm", review_status="pending") == [
        ids["pending_review"],
    ]
    assert listed_ids(store, action="accepted", review_status="pending") == []


def test_text_search_is_a_case_insensitive_substring_match(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    assert listed_ids(store, q="WALLET") == [ids["accepted_llm"]]
    assert set(listed_ids(store, q="card")) == {ids["accepted_baseline"], ids["pending_review"]}


@pytest.mark.parametrize("wildcard", ["%", "_", "a_b", "50%"])
def test_search_treats_percent_and_underscore_literally(tmp_path, wildcard):
    store, _ = make_store_with_history(tmp_path)
    assert store.list_requests(q=wildcard)[1] == 0
    literal = store.log("100% sure, a_b", accepted())
    assert store.list_requests(q="100%")[0][0]["id"] == literal
    assert store.list_requests(q="a_b")[0][0]["id"] == literal


def test_search_with_a_backslash_and_quote_is_safe(tmp_path):
    store, _ = make_store_with_history(tmp_path)
    store.log("it's a back\\slash", accepted())
    assert store.list_requests(q="back\\slash")[1] == 1
    assert store.list_requests(q="'; DROP TABLE requests; --")[1] == 0
    assert store.list_requests()[1] == 6


def test_pagination_with_limit_and_offset(tmp_path):
    store, ids = make_store_with_history(tmp_path)
    everything = sorted(ids.values())
    assert listed_ids(store, limit=2, newest_first=False) == everything[:2]
    assert listed_ids(store, limit=2, offset=2, newest_first=False) == everything[2:4]
    assert listed_ids(store, limit=2, offset=4, newest_first=False) == everything[4:]
    assert listed_ids(store, limit=2, offset=10) == []


def test_total_ignores_limit_and_offset_but_respects_filters(tmp_path):
    store, _ = make_store_with_history(tmp_path)
    rows, total = store.list_requests(limit=1, offset=1)
    assert len(rows) == 1 and total == 5
    rows, total = store.list_requests(action="accepted", limit=1)
    assert len(rows) == 1 and total == 2


def test_list_requests_on_an_empty_database(tmp_path):
    assert Store(tmp_path / "a.db").list_requests() == ([], 0)
