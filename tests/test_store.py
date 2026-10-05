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


# --- pending pagination ------------------------------------------------------------

def test_pending_pagination_and_count(tmp_path):
    store = Store(tmp_path / "a.db")
    review = [store.log(str(i), needs_review()) for i in range(5)]
    store.log("fine", accepted())
    assert store.pending_count() == 5
    assert [r["id"] for r in store.pending(limit=2)] == review[:2]
    assert [r["id"] for r in store.pending(limit=2, offset=2)] == review[2:4]
    assert [r["id"] for r in store.pending(limit=2, offset=4)] == review[4:]
    assert store.pending(limit=2, offset=9) == []


def test_pending_count_drops_when_a_request_is_resolved(tmp_path):
    store = Store(tmp_path / "a.db")
    first = store.log("one", needs_review())
    store.log("two", needs_review())
    store.resolve(first, "a")
    assert store.pending_count() == 1
    assert [r["text"] for r in store.pending()] == ["two"]


def test_pending_count_on_an_empty_database(tmp_path):
    assert Store(tmp_path / "a.db").pending_count() == 0


# --- indexes ---------------------------------------------------------------------

def index_names(path):
    conn = sqlite3.connect(path)
    try:
        return {row[1] for row in conn.execute("PRAGMA index_list(requests)")}
    finally:
        conn.close()


def test_new_database_has_the_filter_indexes(tmp_path):
    from routeiq.store import INDEXES

    path = tmp_path / "a.db"
    Store(path)
    assert set(INDEXES) <= index_names(path)


def test_migration_adds_indexes_to_an_old_database(tmp_path):
    from routeiq.store import INDEXES

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.execute(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO requests (created_at, text, label, action) VALUES (?,?,?,?)",
        ("2026-01-01T00:00:00", "old request", "a", "accepted"),
    )
    conn.commit()
    conn.close()
    assert not (set(INDEXES) & index_names(path))

    store = Store(path)

    assert set(INDEXES) <= index_names(path)
    assert set(NEW_COLUMNS) <= column_names(path)
    assert store.get(1)["text"] == "old request"


def test_index_migration_can_run_repeatedly(tmp_path):
    from routeiq.store import INDEXES

    path = tmp_path / "a.db"
    for _ in range(3):
        Store(path)
    names = index_names(path)
    assert set(INDEXES) <= names


def test_indexes_cover_exactly_existing_columns(tmp_path):
    from routeiq.store import INDEXES

    path = tmp_path / "a.db"
    Store(path)
    assert set(INDEXES.values()) <= column_names(path)


def query_plan(path, sql, params=()):
    conn = sqlite3.connect(path)
    try:
        return " ".join(str(row[3]) for row in conn.execute("EXPLAIN QUERY PLAN " + sql, params))
    finally:
        conn.close()


@pytest.mark.parametrize("column, index", [
    ("review_status", "idx_requests_review_status"),
    ("delivery_status", "idx_requests_delivery_status"),
    ("action", "idx_requests_action"),
    ("tier", "idx_requests_tier"),
])
def test_filter_queries_use_the_index(tmp_path, column, index):
    path = tmp_path / "a.db"
    store = Store(path)
    for i in range(50):
        store.log(str(i), accepted())
    plan = query_plan(path, f"SELECT * FROM requests WHERE {column} = ?", ("x",))
    assert index in plan


def test_the_review_queue_query_uses_its_index(tmp_path):
    path = tmp_path / "a.db"
    Store(path)
    plan = query_plan(
        path,
        "SELECT id FROM requests WHERE review_status = 'pending' ORDER BY id LIMIT 50",
    )
    assert "idx_requests_review_status" in plan


# --- stats window and reviewer agreement -------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402


def iso(moment):
    return moment.astimezone(timezone.utc).isoformat()


def age(path, request_id, moment):
    set_raw(path, request_id, created_at=iso(moment))


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def test_reviewer_agreement_on_an_empty_database(tmp_path):
    assert Store(tmp_path / "a.db").stats()["reviewer_agreement"] == {
        "resolved": 0, "agreed": 0, "rate": None,
    }


def test_reviewer_agreement_counts_only_resolved_reviews(tmp_path):
    store = Store(tmp_path / "a.db")
    agree = store.log("1", needs_review("b"))
    disagree = store.log("2", needs_review("b"))
    store.log("3", needs_review("b"))  # still pending
    store.log("4", accepted("b"))  # never reviewed
    store.resolve(agree, "b")
    store.resolve(disagree, "a")
    assert store.stats()["reviewer_agreement"] == {"resolved": 2, "agreed": 1, "rate": 0.5}


def test_a_review_without_a_model_suggestion_never_counts_as_agreement(tmp_path):
    store = Store(tmp_path / "a.db")
    rid = store.log("x", RouteResult(None, 0.0, None, "human_review", 0.0, 1.0, error="all failed"))
    store.resolve(rid, "a")
    assert store.stats()["reviewer_agreement"] == {"resolved": 1, "agreed": 0, "rate": 0.0}


def test_full_agreement_and_full_disagreement(tmp_path):
    store = Store(tmp_path / "a.db")
    for i in range(3):
        store.resolve(store.log(str(i), needs_review("b")), "b")
    assert store.stats()["reviewer_agreement"]["rate"] == 1.0


def build_history(tmp_path):
    """İki eski istek (3 gün önce) ve üç yeni istek (1 saat önce)."""
    path = tmp_path / "a.db"
    store = Store(path)
    old_accepted = store.log("old fine", RouteResult("a", 0.9, "baseline", "accepted", 0.5, 100.0))
    old_review = store.log("old unsure", needs_review("b"))
    store.resolve(old_review, "a")
    new_accepted = store.log("new fine", RouteResult("a", 0.9, "baseline", "accepted", 0.25, 10.0))
    new_review = store.log("new unsure", needs_review("b"))
    store.resolve(new_review, "b")
    new_failed = store.log("new broken", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 20.0))
    store.mark_delivery(old_accepted, "failed", "x")
    store.mark_delivery(new_failed, "failed", "y")
    store.mark_delivery(new_accepted, "sent")
    for rid in (old_accepted, old_review):
        age(path, rid, NOW - timedelta(days=3))
    for rid in (new_accepted, new_review, new_failed):
        age(path, rid, NOW - timedelta(hours=1))
    return store


def test_stats_without_a_window_counts_everything(tmp_path):
    stats = build_history(tmp_path).stats()
    assert stats["requests"] == 5
    assert stats["review"] == {"pending": 0, "resolved": 2}
    assert stats["delivery"]["failed"] == 2
    assert stats["delivery"]["retryable"] == 2


def test_stats_window_limits_every_counter(tmp_path):
    stats = build_history(tmp_path).stats(since=NOW - timedelta(days=1))
    assert stats["requests"] == 3
    assert stats["accepted_by_tier"] == {"baseline": 2}
    assert stats["human_review"] == 1
    assert stats["review"] == {"pending": 0, "resolved": 1}
    assert stats["reviewer_agreement"] == {"resolved": 1, "agreed": 1, "rate": 1.0}
    assert stats["cost_usd"] == pytest.approx(0.251)
    assert stats["latency_ms"]["avg"] == pytest.approx((10.0 + 500.0 + 20.0) / 3)
    assert stats["latency_ms"]["p95"] == 500.0
    assert stats["delivery"] == {"pending": 0, "sent": 1, "failed": 1, "retryable": 1}


def test_stats_window_starting_in_the_future_is_empty(tmp_path):
    stats = build_history(tmp_path).stats(since=NOW + timedelta(days=1))
    assert stats["requests"] == 0
    assert stats["reviewer_agreement"] == {"resolved": 0, "agreed": 0, "rate": None}
    assert stats["delivery"]["retryable"] == 0


def test_window_start_is_inclusive(tmp_path):
    store = build_history(tmp_path)
    boundary = NOW - timedelta(hours=1)
    assert store.stats(since=boundary)["requests"] == 3
    assert store.stats(since=boundary + timedelta(seconds=1))["requests"] == 0


def test_a_naive_since_is_treated_as_utc(tmp_path):
    store = build_history(tmp_path)
    naive = (NOW - timedelta(days=1)).replace(tzinfo=None)
    aware = NOW - timedelta(days=1)
    assert store.stats(since=naive) == store.stats(since=aware)


def test_since_in_another_timezone_is_converted(tmp_path):
    store = build_history(tmp_path)
    plus_three = timezone(timedelta(hours=3))
    # new requests are at 11:00 UTC. 13:30+03:00 is 10:30 UTC (includes them),
    # 15:00+03:00 is 12:00 UTC (excludes them).
    assert store.stats(since=datetime(2026, 10, 5, 13, 30, tzinfo=plus_three))["requests"] == 3
    assert store.stats(since=datetime(2026, 10, 5, 15, 0, tzinfo=plus_three))["requests"] == 0


def test_retryable_deliveries_respects_the_window(tmp_path):
    store = build_history(tmp_path)
    assert len(store.retryable_deliveries()) == 2
    recent = store.retryable_deliveries(since=NOW - timedelta(days=1))
    assert len(recent) == 1
    assert store.get(recent[0])["text"] == "new broken"


def test_window_and_stale_pending_rule_combine_with_the_right_precedence(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    old = store.log("old", accepted())
    new = store.log("new", accepted())
    store.mark_delivery(old, "failed", "x")
    store.mark_delivery(new, "sent")
    age(path, old, NOW - timedelta(days=5))
    age(path, new, NOW - timedelta(hours=1))
    # a 'sent' request inside the window must not be picked up because of the OR
    assert store.retryable_deliveries(since=NOW - timedelta(days=1)) == []
