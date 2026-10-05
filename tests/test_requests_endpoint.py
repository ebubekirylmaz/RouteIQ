from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from fakes import Boom, Fake, Recorder
from routeiq.api import create_app

LABELS = ["a", "b"]
WEBHOOK = "https://hooks.example.com/in/SECRET-TOKEN-123"


class FailingTarget:
    def send(self, record):
        raise RuntimeError(f"Server error '503' for url '{WEBHOOK}'")


def make_app(tmp_path, baseline=0.9, llm=None, target=None):
    llm = llm if llm is not None else Fake("b", 0.4)
    tiers = [
        ({"name": "baseline", "accept_threshold": 0.5}, Fake("a", baseline)),
        ({"name": "llm", "accept_threshold": 0.7}, llm),
    ]
    return create_app(tiers=tiers, labels=LABELS, db_path=tmp_path / "t.db", target=target)


def post_route(client, text):
    return client.post("/route", json={"text": text}).json()["request_id"]


def ids(response):
    return [item["id"] for item in response.json()]


def total(response):
    return int(response.headers["X-Total-Count"])


# --- basics --------------------------------------------------------------------

def test_empty_history(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        response = client.get("/requests")
    assert response.status_code == 200
    assert response.json() == []
    assert total(response) == 0


def test_lists_requests_newest_first_by_default(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        first, second, third = (post_route(client, t) for t in ("one", "two", "three"))
        response = client.get("/requests")
    assert ids(response) == [third, second, first]
    assert total(response) == 3


def test_order_oldest(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        first, second = post_route(client, "one"), post_route(client, "two")
        assert ids(client.get("/requests", params={"order": "oldest"})) == [first, second]


def test_item_shape(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        rid = post_route(client, "hello")
        item = client.get("/requests").json()[0]
    assert set(item) == {
        "id", "created_at", "text", "label", "confidence", "tier", "action", "cost_usd",
        "latency_ms", "degraded", "review_status", "final_label", "resolved_at",
        "delivery_status", "delivery_error", "delivered_at",
    }
    assert item["id"] == rid and item["text"] == "hello"
    assert item["action"] == "accepted" and item["tier"] == "baseline" and item["label"] == "a"
    assert item["degraded"] is False
    assert datetime.fromisoformat(item["created_at"].replace("Z", "+00:00")).tzinfo is not None


# --- filters -------------------------------------------------------------------

def test_filter_by_action(tmp_path):
    with TestClient(make_app(tmp_path, baseline=0.3)) as client:
        rid = post_route(client, "unsure")
        assert ids(client.get("/requests", params={"action": "human_review"})) == [rid]
        assert ids(client.get("/requests", params={"action": "accepted"})) == []


def test_filter_by_tier_and_review_status(tmp_path):
    with TestClient(make_app(tmp_path, baseline=0.3)) as client:
        rid = post_route(client, "unsure")
        assert ids(client.get("/requests", params={"tier": "llm"})) == [rid]
        assert ids(client.get("/requests", params={"tier": "baseline"})) == []
        assert ids(client.get("/requests", params={"review_status": "pending"})) == [rid]
        client.post(f"/review/{rid}", json={"label": "a"})
        assert ids(client.get("/requests", params={"review_status": "pending"})) == []
        resolved = client.get("/requests", params={"review_status": "resolved"}).json()
        assert [i["id"] for i in resolved] == [rid]
        assert resolved[0]["final_label"] == "a"
        assert resolved[0]["resolved_at"] is not None


def test_filter_by_delivery_status(tmp_path):
    with TestClient(make_app(tmp_path, target=Recorder())) as client:
        rid = post_route(client, "hello")
        assert ids(client.get("/requests", params={"delivery_status": "sent"})) == [rid]
        assert ids(client.get("/requests", params={"delivery_status": "failed"})) == []


def test_filter_by_degraded(tmp_path):
    with TestClient(make_app(tmp_path, baseline=0.3, llm=Boom())) as client:
        broken = post_route(client, "llm is down")
    with TestClient(make_app(tmp_path)) as client:
        healthy = post_route(client, "fine")
        assert ids(client.get("/requests", params={"degraded": "true"})) == [broken]
        assert ids(client.get("/requests", params={"degraded": "false"})) == [healthy]


def test_text_search(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        wallet = post_route(client, "I lost my WALLET")
        post_route(client, "card declined")
        assert ids(client.get("/requests", params={"q": "wallet"})) == [wallet]
        assert total(client.get("/requests", params={"q": "nothing like this"})) == 0


def test_search_treats_percent_literally(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        post_route(client, "plain text")
        assert total(client.get("/requests", params={"q": "%"})) == 0


def test_empty_search_string_is_no_filter(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        post_route(client, "one")
        assert total(client.get("/requests", params={"q": ""})) == 1


def test_filters_combine(tmp_path):
    with TestClient(make_app(tmp_path, baseline=0.3)) as client:
        post_route(client, "alpha")
        beta = post_route(client, "beta")
        response = client.get("/requests", params={"action": "human_review", "q": "bet"})
        assert ids(response) == [beta]


# --- pagination ----------------------------------------------------------------

def test_pagination_and_total(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        created = [post_route(client, str(i)) for i in range(5)]
        page = client.get("/requests", params={"limit": 2, "offset": 2, "order": "oldest"})
    assert ids(page) == created[2:4]
    assert total(page) == 5


def test_offset_beyond_the_end_returns_an_empty_page_with_the_real_total(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        post_route(client, "one")
        page = client.get("/requests", params={"offset": 10})
    assert page.json() == [] and total(page) == 1


def test_total_follows_the_filter_not_the_page(tmp_path):
    with TestClient(make_app(tmp_path, baseline=0.3)) as client:
        for i in range(3):
            post_route(client, str(i))
        page = client.get("/requests", params={"action": "human_review", "limit": 1})
    assert len(page.json()) == 1 and total(page) == 3


# --- validation ----------------------------------------------------------------

@pytest.mark.parametrize("params", [
    {"action": "maybe"},
    {"review_status": "done"},
    {"delivery_status": "lost"},
    {"order": "random"},
    {"degraded": "perhaps"},
    {"limit": 0},
    {"limit": 201},
    {"offset": -1},
    {"q": "x" * 201},
    {"tier": "x" * 51},
])
def test_invalid_parameters_are_rejected(tmp_path, params):
    with TestClient(make_app(tmp_path)) as client:
        assert client.get("/requests", params=params).status_code == 422


def test_maximum_page_size_is_allowed(tmp_path):
    with TestClient(make_app(tmp_path)) as client:
        assert client.get("/requests", params={"limit": 200}).status_code == 200


# --- no leaks ------------------------------------------------------------------

def test_failed_delivery_shows_the_reason_without_the_url(tmp_path):
    with TestClient(make_app(tmp_path, target=FailingTarget())) as client:
        post_route(client, "hello")
        response = client.get("/requests", params={"delivery_status": "failed"})
    item = response.json()[0]
    assert "503" in item["delivery_error"]
    assert "<url>" in item["delivery_error"]
    assert "SECRET" not in response.text and "hooks.example.com" not in response.text


def test_internal_error_text_is_never_returned(tmp_path):
    with TestClient(make_app(tmp_path, baseline=0.3, llm=Boom())) as client:
        post_route(client, "llm is down")
        response = client.get("/requests")
    item = response.json()[0]
    assert item["degraded"] is True
    assert "boom" not in response.text
    assert "error" not in item
