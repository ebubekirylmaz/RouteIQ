import pytest
from fastapi.testclient import TestClient

from fakes import Fake
from routeiq.api import create_app

LABELS = ["a", "b"]


def make_client(tmp_path, baseline, llm):
    tiers = [
        ({"name": "baseline", "accept_threshold": 0.5}, baseline),
        ({"name": "llm", "accept_threshold": 0.7}, llm),
    ]
    app = create_app(tiers=tiers, labels=LABELS, db_path=tmp_path / "test.db")
    return TestClient(app)


def unsure_client(tmp_path):
    """Her iki katman da emin değil: her istek insana düşer, öneri 'b'."""
    return make_client(tmp_path, Fake("a", 0.3), Fake("b", 0.4, cost=0.001))


def route_to_review(client, text="x"):
    response = client.post("/route", json={"text": text})
    assert response.json()["action"] == "human_review"
    return response.json()["request_id"]


def test_health(tmp_path):
    with make_client(tmp_path, Fake("a", 0.9), Fake("b", 0.9)) as client:
        assert client.get("/health").json() == {"status": "ok"}


def test_confident_request_is_accepted_and_not_queued(tmp_path):
    with make_client(tmp_path, Fake("a", 0.9), Fake("b", 0.9)) as client:
        response = client.post("/route", json={"text": "hello"})
        assert response.status_code == 200
        body = response.json()
        assert body["action"] == "accepted"
        assert body["tier"] == "baseline"
        assert body["label"] == "a"
        assert "request_id" in body
        assert client.get("/review").json() == []


def test_unsure_request_goes_to_review_queue_with_suggestion(tmp_path):
    with unsure_client(tmp_path) as client:
        request_id = route_to_review(client, "some text")
        items = client.get("/review").json()
        assert len(items) == 1
        assert items[0]["id"] == request_id
        assert items[0]["suggested_label"] == "b"
        assert items[0]["text"] == "some text"


def test_resolving_a_review_item_removes_it_from_the_queue(tmp_path):
    with unsure_client(tmp_path) as client:
        request_id = route_to_review(client)
        response = client.post(f"/review/{request_id}", json={"label": "a"})
        assert response.status_code == 200
        assert response.json()["final_label"] == "a"
        assert client.get("/review").json() == []


def test_resolving_twice_returns_409(tmp_path):
    with unsure_client(tmp_path) as client:
        request_id = route_to_review(client)
        client.post(f"/review/{request_id}", json={"label": "a"})
        response = client.post(f"/review/{request_id}", json={"label": "b"})
        assert response.status_code == 409


def test_resolving_unknown_request_returns_404(tmp_path):
    with unsure_client(tmp_path) as client:
        response = client.post("/review/9999", json={"label": "a"})
        assert response.status_code == 404


def test_resolving_with_unknown_label_returns_422(tmp_path):
    with unsure_client(tmp_path) as client:
        request_id = route_to_review(client)
        response = client.post(f"/review/{request_id}", json={"label": "zzz"})
        assert response.status_code == 422
        assert len(client.get("/review").json()) == 1


def test_resolving_an_accepted_request_returns_409(tmp_path):
    with make_client(tmp_path, Fake("a", 0.9), Fake("b", 0.9)) as client:
        request_id = client.post("/route", json={"text": "hello"}).json()["request_id"]
        response = client.post(f"/review/{request_id}", json={"label": "a"})
        assert response.status_code == 409


def test_empty_text_is_rejected(tmp_path):
    with make_client(tmp_path, Fake("a", 0.9), Fake("b", 0.9)) as client:
        assert client.post("/route", json={"text": ""}).status_code == 422


def test_too_long_text_is_rejected(tmp_path):
    with make_client(tmp_path, Fake("a", 0.9), Fake("b", 0.9)) as client:
        assert client.post("/route", json={"text": "x" * 5001}).status_code == 422


def test_review_limit_out_of_range_is_rejected(tmp_path):
    with unsure_client(tmp_path) as client:
        assert client.get("/review?limit=0").status_code == 422