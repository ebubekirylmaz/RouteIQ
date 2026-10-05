import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from fakes import Fake
from routeiq.api import create_app
from routeiq.cascade import RouteResult
from routeiq.store import Store

UTC = timezone.utc
T0 = datetime(2026, 10, 5, 10, 0, tzinfo=UTC)


def accepted(cost=0.0, latency=10.0):
    return RouteResult("a", 0.9, "baseline", "accepted", cost, latency)


def review(cost=0.0, latency=500.0):
    return RouteResult("b", 0.4, "llm", "human_review", cost, latency)


def set_created(path, request_id, moment):
    conn = sqlite3.connect(path)
    conn.execute("UPDATE requests SET created_at = ? WHERE id = ?", (moment.isoformat(), request_id))
    conn.commit()
    conn.close()


def add(store, path, moment, result):
    rid = store.log("x", result)
    set_created(path, rid, moment)
    return rid


def starts(points):
    return [p["start"] for p in points]


# --- store: buckets ------------------------------------------------------------------

def test_hour_buckets_count_and_split_requests(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    add(store, path, T0 + timedelta(minutes=5), accepted(cost=0.25, latency=10.0))
    add(store, path, T0 + timedelta(minutes=50), review(cost=0.5, latency=30.0))
    add(store, path, T0 + timedelta(hours=1, minutes=1), accepted())

    points = store.timeseries("hour", T0, T0 + timedelta(hours=2))

    assert starts(points) == [T0, T0 + timedelta(hours=1)]
    first, second = points
    assert (first["requests"], first["accepted"], first["human_review"]) == (2, 1, 1)
    assert first["cost_usd"] == pytest.approx(0.75)
    assert first["avg_latency_ms"] == pytest.approx(20.0)
    assert (second["requests"], second["accepted"], second["human_review"]) == (1, 1, 0)


def test_empty_buckets_are_filled_with_zeros(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    add(store, path, T0 + timedelta(hours=3, minutes=10), accepted())

    points = store.timeseries("hour", T0, T0 + timedelta(hours=5))

    assert [p["requests"] for p in points] == [0, 0, 0, 1, 0]
    assert all(p["cost_usd"] == 0 and p["avg_latency_ms"] == 0 for p in points if p["requests"] == 0)


def test_an_empty_database_still_returns_every_bucket(tmp_path):
    points = Store(tmp_path / "a.db").timeseries("hour", T0, T0 + timedelta(hours=3))
    assert len(points) == 3 and all(p["requests"] == 0 for p in points)


def test_since_is_inclusive_and_until_is_exclusive(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    add(store, path, T0, accepted())
    add(store, path, T0 + timedelta(hours=1), accepted())

    points = store.timeseries("hour", T0, T0 + timedelta(hours=1))

    assert starts(points) == [T0]
    assert points[0]["requests"] == 1


def test_the_first_bucket_starts_at_the_beginning_of_the_hour_and_counts_all_of_it(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    add(store, path, T0 + timedelta(minutes=5), accepted())   # before the 10:37 start

    points = store.timeseries("hour", T0 + timedelta(minutes=37), T0 + timedelta(hours=2))

    assert starts(points)[0] == T0
    assert points[0]["requests"] == 1


def test_the_last_bucket_is_partial_but_included(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    add(store, path, T0 + timedelta(hours=1, minutes=10), accepted())
    points = store.timeseries("hour", T0, T0 + timedelta(hours=1, minutes=30))
    assert starts(points) == [T0, T0 + timedelta(hours=1)]
    assert points[1]["requests"] == 1


def test_day_buckets(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    day = datetime(2026, 10, 5, tzinfo=UTC)
    add(store, path, day + timedelta(hours=1), accepted())
    add(store, path, day + timedelta(hours=23, minutes=59), accepted())
    add(store, path, day + timedelta(days=2, hours=5), review())

    points = store.timeseries("day", day, day + timedelta(days=3))

    assert starts(points) == [day, day + timedelta(days=1), day + timedelta(days=2)]
    assert [p["requests"] for p in points] == [2, 0, 1]
    assert [p["human_review"] for p in points] == [0, 0, 1]


def test_day_buckets_start_at_midnight_utc(tmp_path):
    points = Store(tmp_path / "a.db").timeseries(
        "day", datetime(2026, 10, 5, 15, 30, tzinfo=UTC), datetime(2026, 10, 7, 1, 0, tzinfo=UTC)
    )
    assert starts(points)[0] == datetime(2026, 10, 5, tzinfo=UTC)


def test_other_time_zones_are_converted_to_utc(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    add(store, path, T0 + timedelta(minutes=30), accepted())
    plus_three = timezone(timedelta(hours=3))
    since = datetime(2026, 10, 5, 13, 0, tzinfo=plus_three)   # 10:00 UTC
    until = datetime(2026, 10, 5, 15, 0, tzinfo=plus_three)   # 12:00 UTC
    points = store.timeseries("hour", since, until)
    assert starts(points) == [T0, T0 + timedelta(hours=1)]
    assert points[0]["requests"] == 1


def test_naive_datetimes_are_treated_as_utc(tmp_path):
    store = Store(tmp_path / "a.db")
    points = store.timeseries("hour", T0.replace(tzinfo=None), (T0 + timedelta(hours=2)).replace(tzinfo=None))
    assert starts(points) == [T0, T0 + timedelta(hours=1)]


def test_bucket_totals_match_the_stats_for_the_same_window(tmp_path):
    path = tmp_path / "a.db"
    store = Store(path)
    for minutes in (5, 65, 125, 130):
        add(store, path, T0 + timedelta(minutes=minutes), accepted(cost=0.1, latency=10.0))
    add(store, path, T0 + timedelta(minutes=70), review(cost=0.2, latency=20.0))
    since, until = T0, T0 + timedelta(hours=3)

    points = store.timeseries("hour", since, until)
    stats = store.stats(since=since)

    assert sum(p["requests"] for p in points) == stats["requests"] == 5
    assert sum(p["cost_usd"] for p in points) == pytest.approx(stats["cost_usd"])
    assert sum(p["human_review"] for p in points) == stats["human_review"]


# --- API -------------------------------------------------------------------------------

def make_client(tmp_path):
    tiers = [
        ({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9)),
        ({"name": "llm", "accept_threshold": 0.7}, Fake("b", 0.9)),
    ]
    return TestClient(create_app(tiers=tiers, labels=["a", "b"], db_path=tmp_path / "t.db"))


def get(client, **params):
    return client.get("/stats/timeseries", params=params)


def test_default_window_is_the_last_24_hours(tmp_path):
    with make_client(tmp_path) as client:
        client.post("/route", json={"text": "now"})
        body = get(client).json()
    assert body["bucket"] == "hour"
    assert 24 <= len(body["points"]) <= 25
    assert body["points"][-1]["requests"] == 1
    assert sum(p["requests"] for p in body["points"]) == 1


def test_default_day_window_is_the_last_30_days(tmp_path):
    with make_client(tmp_path) as client:
        body = get(client, bucket="day").json()
    assert body["bucket"] == "day"
    assert 30 <= len(body["points"]) <= 31


def test_response_shape(tmp_path):
    with make_client(tmp_path) as client:
        body = get(client, since="2026-10-05T10:00:00Z", until="2026-10-05T12:00:00Z").json()
    assert set(body) == {"bucket", "since", "until", "points"}
    assert set(body["points"][0]) == {
        "start", "requests", "accepted", "human_review", "cost_usd", "avg_latency_ms",
    }
    assert len(body["points"]) == 2


def test_explicit_window(tmp_path):
    with make_client(tmp_path) as client:
        body = get(client, since="2026-10-05T10:00:00Z", until="2026-10-05T13:00:00Z").json()
    assert [p["start"][:13] for p in body["points"]] == [
        "2026-10-05T10", "2026-10-05T11", "2026-10-05T12",
    ]


@pytest.mark.parametrize("params", [
    {"bucket": "week"},
    {"since": "yesterday"},
    {"until": "tomorrow"},
])
def test_invalid_parameters_are_rejected(tmp_path, params):
    with make_client(tmp_path) as client:
        assert get(client, **params).status_code == 422


def test_since_must_be_earlier_than_until(tmp_path):
    with make_client(tmp_path) as client:
        assert get(client, since="2026-10-05T12:00:00Z", until="2026-10-05T10:00:00Z").status_code == 422
        assert get(client, since="2026-10-05T12:00:00Z", until="2026-10-05T12:00:00Z").status_code == 422


def test_a_naive_since_with_the_default_until_does_not_crash(tmp_path):
    with make_client(tmp_path) as client:
        since = (datetime.now(UTC) - timedelta(hours=3)).replace(tzinfo=None).isoformat()
        response = get(client, since=since)
    assert response.status_code == 200
    assert 3 <= len(response.json()["points"]) <= 5


def test_naive_and_aware_bounds_can_be_mixed(tmp_path):
    with make_client(tmp_path) as client:
        response = get(client, since="2026-10-05T10:00:00", until="2026-10-05T12:00:00Z")
    assert response.status_code == 200 and len(response.json()["points"]) == 2


def test_a_range_of_more_than_1000_buckets_is_rejected(tmp_path):
    with make_client(tmp_path) as client:
        too_long = get(client, since="2000-01-01T00:00:00Z", until="2026-01-01T00:00:00Z")
        assert too_long.status_code == 422
        assert "1000" in too_long.text


def test_exactly_1000_buckets_is_allowed_and_1001_is_not(tmp_path):
    until = datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
    with make_client(tmp_path) as client:
        ok = get(client, since=(until - timedelta(hours=1000)).isoformat(), until=until.isoformat())
        over = get(client, since=(until - timedelta(hours=1001)).isoformat(), until=until.isoformat())
    assert ok.status_code == 200 and len(ok.json()["points"]) == 1000
    assert over.status_code == 422


def test_the_limit_applies_to_day_buckets_too(tmp_path):
    with make_client(tmp_path) as client:
        assert get(client, bucket="day", since="2020-01-01T00:00:00Z", until="2026-10-05T00:00:00Z").status_code == 422
        assert get(client, bucket="day", since="2025-01-01T00:00:00Z", until="2026-10-05T00:00:00Z").status_code == 200
