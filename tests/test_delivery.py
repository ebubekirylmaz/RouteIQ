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
