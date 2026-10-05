from datetime import timezone

import pytest

from routeiq.cascade import RouteResult
from routeiq.redact import redact_urls
from routeiq.schemas import RequestItem
from routeiq.store import Store
from routeiq.views import request_item

WEBHOOK = "https://hooks.example.com/in/SECRET-TOKEN-123"


# --- redact_urls ---------------------------------------------------------------

def test_none_stays_none():
    assert redact_urls(None) is None


def test_text_without_a_url_is_unchanged():
    assert redact_urls("connection refused") == "connection refused"


def test_a_url_is_replaced():
    message = f"Server error '503 Service Unavailable' for url '{WEBHOOK}'"
    redacted = redact_urls(message)
    assert "SECRET-TOKEN" not in redacted
    assert "hooks.example.com" not in redacted
    assert "<url>" in redacted
    assert redacted.startswith("Server error '503 Service Unavailable' for url '")


@pytest.mark.parametrize("url", [
    "http://localhost:8000/mock-erp/api/tickets",
    "https://user:pass@example.com/path?token=abc&x=1#frag",
    "HTTPS://example.com/upper",
])
def test_various_url_forms_are_masked(url):
    redacted = redact_urls(f"failed: {url}")
    assert "<url>" in redacted
    assert "example.com" not in redacted and "localhost" not in redacted


def test_every_url_in_a_message_is_masked():
    redacted = redact_urls(f"redirected from {WEBHOOK} to https://other.example.org/x")
    assert redacted.count("<url>") == 2
    assert "SECRET" not in redacted and "other.example.org" not in redacted


# --- request_item --------------------------------------------------------------

def make_store(tmp_path):
    return Store(tmp_path / "a.db")


def item_for(store, request_id):
    return request_item(store.get(request_id))


def test_accepted_request_is_mapped(tmp_path):
    store = make_store(tmp_path)
    rid = store.log("hello", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 12.5))
    item = item_for(store, rid)
    assert isinstance(item, RequestItem)
    assert (item.id, item.text, item.label, item.tier, item.action) == (rid, "hello", "a", "baseline", "accepted")
    assert item.confidence == 0.9 and item.cost_usd == 0.0 and item.latency_ms == 12.5
    assert item.degraded is False
    assert item.review_status is None and item.final_label is None and item.resolved_at is None
    assert item.delivery_status is None and item.delivery_error is None and item.delivered_at is None


def test_created_at_is_a_timezone_aware_datetime(tmp_path):
    store = make_store(tmp_path)
    rid = store.log("hello", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 1.0))
    created = item_for(store, rid).created_at
    assert created.tzinfo is not None
    assert created.utcoffset() == timezone.utc.utcoffset(None)


def test_request_waiting_for_review(tmp_path):
    store = make_store(tmp_path)
    rid = store.log("unsure", RouteResult("b", 0.4, "llm", "human_review", 0.001, 700.0))
    item = item_for(store, rid)
    assert item.action == "human_review"
    assert item.review_status == "pending"
    assert item.final_label is None


def test_resolved_review_carries_the_reviewers_label_and_time(tmp_path):
    store = make_store(tmp_path)
    rid = store.log("unsure", RouteResult("b", 0.4, "llm", "human_review", 0.001, 700.0))
    store.resolve(rid, "a")
    item = item_for(store, rid)
    assert item.review_status == "resolved"
    assert item.final_label == "a"
    assert item.label == "b"
    assert item.resolved_at is not None and item.resolved_at.tzinfo is not None


def test_degraded_flag_is_set_but_the_error_text_is_not_exposed(tmp_path):
    store = make_store(tmp_path)
    result = RouteResult("a", 0.3, "baseline", "human_review", 0.0, 5.0, error=f"llm: boom {WEBHOOK}")
    rid = store.log("odd", result)
    item = item_for(store, rid)
    dumped = item.model_dump_json()
    assert item.degraded is True
    assert "boom" not in dumped and "SECRET" not in dumped
    assert "error" not in item.model_dump() or item.model_dump().get("error") is None
    assert "delivery_error" in item.model_dump()


def test_request_without_any_prediction_is_mapped(tmp_path):
    store = make_store(tmp_path)
    result = RouteResult(None, 0.0, None, "human_review", 0.0, 3.0, error="baseline: x; llm: y")
    item = item_for(store, store.log("nothing worked", result))
    assert item.label is None and item.tier is None
    assert item.degraded is True


def test_delivery_error_is_masked_but_keeps_the_reason(tmp_path):
    store = make_store(tmp_path)
    rid = store.log("hello", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 1.0))
    store.mark_delivery(rid, "failed", f"Server error '503' for url '{WEBHOOK}'")
    item = item_for(store, rid)
    assert item.delivery_status == "failed"
    assert "503" in item.delivery_error
    assert "SECRET-TOKEN" not in item.delivery_error and "hooks.example.com" not in item.delivery_error
    assert "<url>" in item.delivery_error
    assert item.delivered_at is None


def test_sent_delivery_has_a_delivery_time(tmp_path):
    store = make_store(tmp_path)
    rid = store.log("hello", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 1.0))
    store.mark_delivery(rid, "sent")
    item = item_for(store, rid)
    assert item.delivery_status == "sent"
    assert item.delivered_at is not None


def test_the_raw_database_error_never_survives_serialization(tmp_path):
    store = make_store(tmp_path)
    rid = store.log("hello", RouteResult("a", 0.3, "llm", "human_review", 0.0, 1.0, error="llm: SECRET-INTERNAL"))
    store.mark_delivery(rid, "failed", f"boom {WEBHOOK}")
    assert "SECRET" not in item_for(store, rid).model_dump_json()


def test_quotes_around_a_url_stay_balanced():
    assert redact_urls("for url 'https://x.example/y' failed") == "for url '<url>' failed"
    assert redact_urls('see "https://x.example/y".') == 'see "<url>".'
    assert redact_urls("<https://x.example/y>") == "<<url>>"


def test_scheme_is_matched_case_insensitively():
    assert redact_urls("HTTP://A.example/b and Https://c.example/d") == "<url> and <url>"
