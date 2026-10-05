from fastapi.testclient import TestClient

from fakes import Fake, Recorder
from routeiq.api import create_app
from routeiq.cascade import RouteResult
from routeiq.delivery import deliver
from routeiq.integrations.base import record_from_row
from routeiq.store import Store

LABELS = ["a", "b"]


def make_client(tmp_path, baseline, llm, target):
    tiers = [
        ({"name": "baseline", "accept_threshold": 0.5}, baseline),
        ({"name": "llm", "accept_threshold": 0.7}, llm),
    ]
    app = create_app(tiers=tiers, labels=LABELS, db_path=tmp_path / "t.db", target=target)
    return TestClient(app)


def confident_client(tmp_path, target):
    return make_client(tmp_path, Fake("a", 0.9), Fake("b", 0.9), target)


def unsure_client(tmp_path, target):
    return make_client(tmp_path, Fake("a", 0.3), Fake("b", 0.4), target)


def stored(client, request_id):
    return client.app.state.store.get(request_id)


# --- record_from_row ---------------------------------------------------------

CASCADE_ROW = {
    "id": 3, "text": "hello", "label": "a", "confidence": 0.9, "tier": "baseline",
    "final_label": None,
}


def test_record_from_cascade_row():
    assert record_from_row(CASCADE_ROW) == {
        "request_id": 3, "text": "hello", "label": "a", "confidence": 0.9,
        "tier": "baseline", "source": "cascade",
    }


def test_record_from_human_resolved_row_uses_the_human_label():
    row = {**CASCADE_ROW, "label": "a", "tier": "llm", "final_label": "b"}
    record = record_from_row(row)
    assert record["label"] == "b"
    assert record["tier"] == "human"
    assert record["source"] == "human_review"
    assert record["confidence"] == 0.9


# --- deliver -----------------------------------------------------------------

def logged_request(tmp_path):
    store = Store(tmp_path / "a.db")
    rid = store.log("hello", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 1.0))
    return store, rid


def test_deliver_sends_the_record_and_marks_it_sent(tmp_path):
    store, rid = logged_request(tmp_path)
    target = Recorder()
    deliver(store, target, rid)
    assert [r["request_id"] for r in target.records] == [rid]
    assert store.get(rid)["delivery_status"] == "sent"


def test_deliver_does_not_raise_when_the_target_fails(tmp_path):
    store, rid = logged_request(tmp_path)
    deliver(store, Recorder(fail=True), rid)
    row = store.get(rid)
    assert row["delivery_status"] == "failed"
    assert "target down" in row["delivery_error"]


# --- API integration ---------------------------------------------------------

def test_accepted_request_is_delivered_to_the_target(tmp_path):
    target = Recorder()
    with confident_client(tmp_path, target) as client:
        body = client.post("/route", json={"text": "hello"}).json()
        assert target.records == [{
            "request_id": body["request_id"], "text": "hello", "label": "a",
            "confidence": 0.9, "tier": "baseline", "source": "cascade",
        }]
        assert stored(client, body["request_id"])["delivery_status"] == "sent"


def test_request_needing_review_is_not_delivered_yet(tmp_path):
    target = Recorder()
    with unsure_client(tmp_path, target) as client:
        body = client.post("/route", json={"text": "hello"}).json()
        assert body["action"] == "human_review"
        assert target.records == []
        assert stored(client, body["request_id"])["delivery_status"] is None


def test_resolved_review_is_delivered_with_the_human_label(tmp_path):
    target = Recorder()
    with unsure_client(tmp_path, target) as client:
        rid = client.post("/route", json={"text": "hello"}).json()["request_id"]
        response = client.post(f"/review/{rid}", json={"label": "a"})
        assert response.status_code == 200
        assert len(target.records) == 1
        record = target.records[0]
        assert record["label"] == "a"
        assert record["source"] == "human_review"
        assert record["tier"] == "human"
        assert stored(client, rid)["delivery_status"] == "sent"


def test_rejected_review_does_not_deliver(tmp_path):
    target = Recorder()
    with unsure_client(tmp_path, target) as client:
        rid = client.post("/route", json={"text": "hello"}).json()["request_id"]
        assert client.post(f"/review/{rid}", json={"label": "zzz"}).status_code == 422
        assert target.records == []


def test_target_failure_does_not_break_the_response(tmp_path):
    with confident_client(tmp_path, Recorder(fail=True)) as client:
        response = client.post("/route", json={"text": "hello"})
        assert response.status_code == 200
        assert response.json()["action"] == "accepted"
        row = stored(client, response.json()["request_id"])
        assert row["delivery_status"] == "failed"
        assert "target down" in row["delivery_error"]


def test_without_a_target_nothing_is_delivered(tmp_path):
    with confident_client(tmp_path, None) as client:
        response = client.post("/route", json={"text": "hello"})
        assert response.status_code == 200
        assert stored(client, response.json()["request_id"])["delivery_status"] is None


# --- retry -------------------------------------------------------------------

def test_retry_resends_failed_deliveries_once_the_target_recovers(tmp_path):
    target = Recorder(fail=True)
    with confident_client(tmp_path, target) as client:
        rid = client.post("/route", json={"text": "hello"}).json()["request_id"]
        assert stored(client, rid)["delivery_status"] == "failed"

        target.fail = False
        response = client.post("/deliveries/retry")

        assert response.status_code == 200
        assert response.json() == {"retried": 1, "sent": 1, "failed": 0}
        assert [r["request_id"] for r in target.records] == [rid]
        assert stored(client, rid)["delivery_status"] == "sent"


def test_retry_keeps_failed_status_while_the_target_is_still_down(tmp_path):
    target = Recorder(fail=True)
    with confident_client(tmp_path, target) as client:
        rid = client.post("/route", json={"text": "hello"}).json()["request_id"]
        response = client.post("/deliveries/retry")
        assert response.json() == {"retried": 1, "sent": 0, "failed": 1}
        assert stored(client, rid)["delivery_status"] == "failed"


def test_retry_does_not_resend_delivered_records(tmp_path):
    target = Recorder()
    with confident_client(tmp_path, target) as client:
        client.post("/route", json={"text": "hello"})
        response = client.post("/deliveries/retry")
        assert response.json() == {"retried": 0, "sent": 0, "failed": 0}
        assert len(target.records) == 1


def test_retry_with_nothing_to_do(tmp_path):
    with confident_client(tmp_path, Recorder()) as client:
        response = client.post("/deliveries/retry")
        assert response.status_code == 200
        assert response.json() == {"retried": 0, "sent": 0, "failed": 0}


def test_retry_without_a_target_returns_409(tmp_path):
    with confident_client(tmp_path, None) as client:
        assert client.post("/deliveries/retry").status_code == 409


def test_retry_limit_out_of_range_is_rejected(tmp_path):
    with confident_client(tmp_path, Recorder()) as client:
        assert client.post("/deliveries/retry?limit=0").status_code == 422


def test_retry_resends_a_human_decision_with_the_human_label(tmp_path):
    target = Recorder(fail=True)
    with unsure_client(tmp_path, target) as client:
        rid = client.post("/route", json={"text": "hello"}).json()["request_id"]
        client.post(f"/review/{rid}", json={"label": "a"})
        assert stored(client, rid)["delivery_status"] == "failed"

        target.fail = False
        client.post("/deliveries/retry")

        assert len(target.records) == 1
        assert target.records[0]["label"] == "a"
        assert target.records[0]["source"] == "human_review"
        assert stored(client, rid)["delivery_status"] == "sent"


# --- stale pending deliveries and /stats ----------------------------------------

def age_delivery(client, request_id):
    """Teslimatın 'pending' yazıldığı zamanı eskitir: sunucu görev bitmeden kapanmış gibi."""
    import sqlite3

    conn = sqlite3.connect(client.app.state.store.path)
    conn.execute(
        "UPDATE requests SET delivery_updated_at = ? WHERE id = ?",
        ("2000-01-01T00:00:00+00:00", request_id),
    )
    conn.commit()
    conn.close()


def test_retry_picks_up_a_delivery_stuck_in_pending(tmp_path):
    target = Recorder()
    with confident_client(tmp_path, target) as client:
        rid = client.post("/route", json={"text": "hello"}).json()["request_id"]
        target.records.clear()
        client.app.state.store.mark_delivery(rid, "pending")
        age_delivery(client, rid)

        response = client.post("/deliveries/retry")

        assert response.json() == {"retried": 1, "sent": 1, "failed": 0}
        assert len(target.records) == 1
        assert stored(client, rid)["delivery_status"] == "sent"


def test_retry_leaves_a_fresh_pending_delivery_alone(tmp_path):
    target = Recorder()
    with confident_client(tmp_path, target) as client:
        rid = client.post("/route", json={"text": "hello"}).json()["request_id"]
        target.records.clear()
        client.app.state.store.mark_delivery(rid, "pending")

        response = client.post("/deliveries/retry")

        assert response.json() == {"retried": 0, "sent": 0, "failed": 0}
        assert target.records == []
        assert stored(client, rid)["delivery_status"] == "pending"


def test_stats_reflects_routed_requests(tmp_path):
    with confident_client(tmp_path, Recorder()) as client:
        client.post("/route", json={"text": "one"})
        client.post("/route", json={"text": "two"})
        response = client.get("/stats")
        assert response.status_code == 200
        stats = response.json()
        assert stats["requests"] == 2
        assert stats["accepted_by_tier"] == {"baseline": 2}
        assert stats["human_review"] == 0
        assert stats["delivery"]["sent"] == 2
        assert stats["delivery"]["retryable"] == 0


def test_stats_shows_review_and_failed_deliveries(tmp_path):
    with unsure_client(tmp_path, Recorder(fail=True)) as client:
        rid = client.post("/route", json={"text": "hello"}).json()["request_id"]
        stats = client.get("/stats").json()
        assert stats["human_review"] == 1
        assert stats["review"] == {"pending": 1, "resolved": 0}

        client.post(f"/review/{rid}", json={"label": "a"})
        stats = client.get("/stats").json()
        assert stats["review"] == {"pending": 0, "resolved": 1}
        assert stats["delivery"]["failed"] == 1
        assert stats["delivery"]["retryable"] == 1


def test_stats_on_an_empty_database(tmp_path):
    with confident_client(tmp_path, None) as client:
        stats = client.get("/stats").json()
        assert stats["requests"] == 0
        assert stats["delivery"]["retryable"] == 0


# --- /stats window and reviewer agreement through the API ----------------------------

def test_stats_exposes_reviewer_agreement_after_a_review(tmp_path):
    with unsure_client(tmp_path, None) as client:
        agree = client.post("/route", json={"text": "one"}).json()["request_id"]
        disagree = client.post("/route", json={"text": "two"}).json()["request_id"]
        client.post(f"/review/{agree}", json={"label": "a"})
        client.post(f"/review/{disagree}", json={"label": "b"})
        agreement = client.get("/stats").json()["reviewer_agreement"]
    assert agreement == {"resolved": 2, "agreed": 1, "rate": 0.5}


def test_stats_since_filters_by_creation_time(tmp_path):
    with confident_client(tmp_path, None) as client:
        client.post("/route", json={"text": "now"})
        assert client.get("/stats", params={"since": "2000-01-01T00:00:00Z"}).json()["requests"] == 1
        assert client.get("/stats", params={"since": "2100-01-01T00:00:00Z"}).json()["requests"] == 0
        assert client.get("/stats", params={"since": "2100-01-01T00:00:00"}).json()["requests"] == 0
        assert client.get("/stats", params={"since": "2100-01-01T00:00:00+03:00"}).json()["requests"] == 0


def test_stats_rejects_an_invalid_since(tmp_path):
    with confident_client(tmp_path, None) as client:
        assert client.get("/stats", params={"since": "yesterday"}).status_code == 422
