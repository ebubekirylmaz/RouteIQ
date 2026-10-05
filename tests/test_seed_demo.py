import importlib.util
from datetime import datetime, timedelta, timezone

import pytest

from routeiq.config import ROOT, load_config
from routeiq.store import Store

spec = importlib.util.spec_from_file_location("seed_demo", ROOT / "scripts" / "seed_demo.py")
seed_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed_demo)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def seeded(tmp_path, name="demo.db", **kwargs):
    path = tmp_path / name
    summary = seed_demo.seed(path, now=NOW, **kwargs)
    return Store(path), summary


def all_rows(store):
    return store.list_requests(limit=1000, newest_first=False)[0]


def test_writes_the_requested_number_of_requests(tmp_path):
    store, summary = seeded(tmp_path, count=80)
    assert store.list_requests(limit=1)[1] == 80
    assert summary["requests"] == 80


def test_same_seed_gives_the_same_data(tmp_path):
    first, _ = seeded(tmp_path, "a.db", seed=3)
    second, _ = seeded(tmp_path, "b.db", seed=3)
    assert all_rows(first) == all_rows(second)


def test_a_different_seed_gives_different_data(tmp_path):
    first, _ = seeded(tmp_path, "a.db", seed=3)
    second, _ = seeded(tmp_path, "b.db", seed=4)
    assert [r["text"] for r in all_rows(first)] != [r["text"] for r in all_rows(second)]


def test_times_rise_with_the_ids_and_stay_inside_the_period(tmp_path):
    store, _ = seeded(tmp_path, days=2)
    times = [datetime.fromisoformat(r["created_at"]) for r in all_rows(store)]
    assert times == sorted(times)
    assert NOW - timedelta(days=2) <= times[0] and times[-1] <= NOW


def test_every_label_comes_from_the_config(tmp_path):
    labels = set(load_config(seed_demo.CONFIG)["labels"])
    store, _ = seeded(tmp_path)
    rows = all_rows(store)
    assert {r["label"] for r in rows if r["label"]} <= labels
    assert {r["final_label"] for r in rows if r["final_label"]} <= labels


def test_the_example_texts_cover_every_label_of_the_config():
    assert set(load_config(seed_demo.CONFIG)["labels"]) <= set(seed_demo.TEMPLATES)


def test_has_every_kind_of_request_the_dashboard_shows(tmp_path):
    store, _ = seeded(tmp_path)
    assert store.list_requests(action="accepted", tier="baseline", limit=1)[1] > 0
    assert store.list_requests(action="accepted", tier="llm", limit=1)[1] > 0
    assert store.list_requests(review_status="pending", limit=1)[1] > 0
    assert store.list_requests(review_status="resolved", limit=1)[1] > 0
    assert store.list_requests(delivery_status="failed", limit=1)[1] > 0
    assert store.list_requests(degraded=True, limit=1)[1] > 0


def test_reviews_are_consistent(tmp_path):
    store, summary = seeded(tmp_path)
    rows = all_rows(store)
    person = [r for r in rows if r["action"] == "human_review"]
    assert all(r["review_status"] in ("pending", "resolved") for r in person)
    assert all(r["review_status"] is None for r in rows if r["action"] == "accepted")
    assert all(r["final_label"] and r["resolved_at"] for r in person if r["review_status"] == "resolved")
    assert all(not r["final_label"] for r in person if r["review_status"] == "pending")
    assert summary["pending"] == store.pending_count()


def test_decisions_are_spread_over_the_period_not_piled_up_at_its_start(tmp_path):
    store, _ = seeded(tmp_path)
    last_day = store.stats(since=NOW - timedelta(days=1))
    assert last_day["reviewer_agreement"] is not None
    assert last_day["reviewer_agreement"]["resolved"] > 0


def test_the_last_hour_has_not_been_looked_at_yet(tmp_path):
    store, _ = seeded(tmp_path)
    for r in all_rows(store):
        if r["review_status"] == "resolved":
            assert datetime.fromisoformat(r["created_at"]) <= NOW - seed_demo.QUIET_PERIOD


def test_a_decision_comes_after_the_request(tmp_path):
    store, _ = seeded(tmp_path)
    for r in all_rows(store):
        if r["resolved_at"]:
            assert datetime.fromisoformat(r["resolved_at"]) > datetime.fromisoformat(r["created_at"])


def test_deliveries_follow_the_outcome(tmp_path):
    store, _ = seeded(tmp_path)
    for r in all_rows(store):
        waiting = r["review_status"] == "pending"
        if waiting:
            assert r["delivery_status"] is None
        else:
            assert r["delivery_status"] in ("sent", "failed", "pending")
        assert (r["delivery_status"] == "failed") == bool(r["delivery_error"])


def test_the_stuck_delivery_can_be_resent_and_is_not_from_the_future(tmp_path):
    store, summary = seeded(tmp_path)
    stuck = store.list_requests(delivery_status="pending", limit=10)[0]
    assert len(stuck) == summary["delivery_pending"] == 1
    assert datetime.fromisoformat(stuck[0]["delivery_updated_at"]) >= datetime.fromisoformat(stuck[0]["created_at"])
    assert stuck[0]["id"] in store.retryable_deliveries()


def test_the_first_tier_costs_nothing_and_a_failed_request_has_no_suggestion(tmp_path):
    store, _ = seeded(tmp_path)
    for r in all_rows(store):
        if r["tier"] == "baseline":
            assert r["cost_usd"] == 0
        if r["error"] and r["action"] == "human_review":
            assert r["label"] is None


def test_the_totals_add_up(tmp_path):
    store, summary = seeded(tmp_path, count=100)
    stats = store.stats()
    assert stats["requests"] == 100
    assert sum(stats["accepted_by_tier"].values()) + stats["human_review"] == 100
    assert stats["human_review"] == summary["human_review"]
    assert stats["delivery"]["failed"] == summary["delivery_failed"]


def test_refuses_a_database_that_already_has_requests(tmp_path):
    seeded(tmp_path)
    with pytest.raises(seed_demo.DemoDataError, match="already has 150 requests"):
        seed_demo.seed(tmp_path / "demo.db", now=NOW)


def test_refusing_leaves_the_data_alone(tmp_path):
    store, _ = seeded(tmp_path)
    before = all_rows(store)
    with pytest.raises(seed_demo.DemoDataError):
        seed_demo.seed(tmp_path / "demo.db", now=NOW)
    assert all_rows(store) == before


def test_add_adds_to_existing_requests(tmp_path):
    store, _ = seeded(tmp_path, count=20)
    seed_demo.seed(tmp_path / "demo.db", count=15, now=NOW, add=True, seed=9)
    assert store.list_requests(limit=1)[1] == 35


@pytest.mark.parametrize("kwargs", [{"count": 0}, {"days": 0}, {"count": -1}])
def test_rejects_nonsense_sizes(tmp_path, kwargs):
    with pytest.raises(seed_demo.DemoDataError):
        seed_demo.seed(tmp_path / "x.db", now=NOW, **kwargs)
    assert not (tmp_path / "x.db").exists()


def test_the_command_line_writes_the_database_and_says_it_is_synthetic(tmp_path, capsys):
    path = tmp_path / "cli.db"
    assert seed_demo.main(["--db", str(path), "--count", "30"]) == 0
    out = capsys.readouterr().out
    assert "synthetic" in out and f"ROUTEIQ_DB={path}" in out
    assert Store(path).list_requests(limit=1)[1] == 30


def test_the_command_line_fails_with_a_message_on_a_used_database(tmp_path, capsys):
    path = tmp_path / "cli.db"
    seed_demo.main(["--db", str(path), "--count", "10"])
    capsys.readouterr()
    assert seed_demo.main(["--db", str(path)]) == 1
    assert "already has 10 requests" in capsys.readouterr().err
