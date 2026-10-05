"""The API contract the dashboard (and its generated TypeScript types) depends on."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from fakes import Fake
from routeiq.api import create_app

LABELS = ["a", "b"]

OPERATIONS = {
    "health": ("get", "/health", "HealthResponse"),
    "get_config": ("get", "/config", "ConfigResponse"),
    "route_request": ("post", "/route", "RouteResponse"),
    "list_review": ("get", "/review", "ReviewItem"),
    "resolve_review": ("post", "/review/{request_id}", "ReviewResolved"),
    "retry_deliveries": ("post", "/deliveries/retry", "RetryResult"),
    "stats": ("get", "/stats", "StatsResponse"),
}


def tiers(baseline_confidence=0.9):
    return [
        ({"name": "baseline", "accept_threshold": 0.5}, Fake("a", baseline_confidence)),
        ({"name": "llm", "accept_threshold": 0.7}, Fake("b", 0.4)),
    ]


@pytest.fixture
def spec():
    return create_app(tiers=tiers(), labels=LABELS).openapi()


def make_client(tmp_path, baseline_confidence=0.9):
    app = create_app(
        tiers=tiers(baseline_confidence), labels=LABELS, db_path=tmp_path / "t.db", target=None
    )
    return TestClient(app)


def schema(spec, name):
    return spec["components"]["schemas"][name]


def response_schema_ref(operation):
    content = operation["responses"]["200"]["content"]["application/json"]["schema"]
    return (content.get("items") or content)["$ref"].rsplit("/", 1)[-1]


# --- operations ---------------------------------------------------------------

def test_operation_ids_are_the_function_names(spec):
    found = {
        op["operationId"]: (method, path)
        for path, ops in spec["paths"].items()
        for method, op in ops.items()
    }
    for operation_id, (method, path, _) in OPERATIONS.items():
        assert found[operation_id] == (method, path)


@pytest.mark.parametrize("operation_id", sorted(OPERATIONS))
def test_every_endpoint_declares_its_response_schema(spec, operation_id):
    method, path, schema_name = OPERATIONS[operation_id]
    operation = spec["paths"][path][method]
    assert response_schema_ref(operation) == schema_name


def test_review_list_is_an_array_of_review_items(spec):
    content = spec["paths"]["/review"]["get"]["responses"]["200"]["content"]["application/json"]
    assert content["schema"]["type"] == "array"


def test_error_responses_are_documented(spec):
    resolve = spec["paths"]["/review/{request_id}"]["post"]["responses"]
    retry = spec["paths"]["/deliveries/retry"]["post"]["responses"]
    for status in ("404", "409"):
        assert resolve[status]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
    assert retry["409"]["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")


def test_operation_ids_stay_unique_with_the_mock_erp_mounted():
    spec = create_app(tiers=tiers(), labels=LABELS, mock_erp=True).openapi()
    ids = [op["operationId"] for ops in spec["paths"].values() for op in ops.values()]
    assert len(ids) == len(set(ids))


# --- schemas ------------------------------------------------------------------

def test_route_response_fields(spec):
    route = schema(spec, "RouteResponse")
    assert set(route["properties"]) == {
        "label", "confidence", "tier", "action", "cost_usd", "latency_ms", "degraded", "request_id",
    }
    assert set(route["required"]) == set(route["properties"])


def test_action_is_a_closed_set_of_values(spec):
    assert schema(spec, "RouteResponse")["properties"]["action"]["enum"] == [
        "accepted", "human_review",
    ]


def test_label_and_tier_are_nullable(spec):
    props = schema(spec, "RouteResponse")["properties"]
    for field in ("label", "tier"):
        types = {option.get("type") for option in props[field]["anyOf"]}
        assert types == {"string", "null"}


def test_review_item_fields_and_timestamp_format(spec):
    item = schema(spec, "ReviewItem")
    assert set(item["properties"]) == {
        "id", "created_at", "text", "suggested_label", "confidence", "tier",
    }
    assert item["properties"]["created_at"]["format"] == "date-time"


def test_stats_fields(spec):
    stats = schema(spec, "StatsResponse")
    assert set(stats["properties"]) == {
        "requests", "accepted_by_tier", "human_review", "review", "reviewer_agreement",
        "degraded", "cost_usd", "latency_ms", "delivery",
    }
    assert set(schema(spec, "DeliveryCounts")["properties"]) == {
        "pending", "sent", "failed", "retryable",
    }
    assert set(schema(spec, "ReviewCounts")["properties"]) == {"pending", "resolved"}
    assert set(schema(spec, "LatencyStats")["properties"]) == {"avg", "p95"}


def test_request_bodies_are_documented(spec):
    route_body = spec["paths"]["/route"]["post"]["requestBody"]["content"]["application/json"]
    review_body = spec["paths"]["/review/{request_id}"]["post"]["requestBody"]["content"]["application/json"]
    assert route_body["schema"]["$ref"].endswith("/RouteRequest")
    assert review_body["schema"]["$ref"].endswith("/ReviewDecision")
    assert schema(spec, "RouteRequest")["properties"]["text"]["maxLength"] == 5000


# --- real responses match the declared shape ----------------------------------

def test_route_response_has_exactly_the_declared_fields(tmp_path, spec):
    with make_client(tmp_path) as client:
        body = client.post("/route", json={"text": "hello"}).json()
    assert set(body) == set(schema(spec, "RouteResponse")["properties"])


def test_internal_error_text_never_reaches_the_response(tmp_path):
    from fakes import Boom

    failing = [
        ({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.3)),
        ({"name": "llm", "accept_threshold": 0.7}, Boom()),
    ]
    app = create_app(tiers=failing, labels=LABELS, db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        body = client.post("/route", json={"text": "hello"}).json()
    assert "error" not in body
    assert "boom" not in str(body)
    assert body["degraded"] is True


def test_review_items_carry_an_iso_timestamp(tmp_path):
    with make_client(tmp_path, baseline_confidence=0.3) as client:
        client.post("/route", json={"text": "unsure"})
        item = client.get("/review").json()[0]
    parsed = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
    assert parsed.tzinfo is not None
    assert item["text"] == "unsure"
    assert item["suggested_label"] == "b"


def test_stats_response_matches_the_declared_shape(tmp_path, spec):
    with make_client(tmp_path) as client:
        client.post("/route", json={"text": "hello"})
        body = client.get("/stats").json()
    declared = schema(spec, "StatsResponse")["properties"]
    assert set(body) == set(declared)
    assert set(body["delivery"]) == set(schema(spec, "DeliveryCounts")["properties"])
    assert body["requests"] == 1


def test_config_response_fields(spec):
    assert set(schema(spec, "ConfigResponse")["properties"]) == {
        "domain", "task", "labels", "tiers", "target_type",
    }
    assert set(schema(spec, "LabelInfo")["properties"]) == {"name", "description"}
    assert set(schema(spec, "TierInfo")["properties"]) == {
        "name", "model", "model_id", "accept_threshold",
    }


def test_config_response_never_declares_a_url_or_path_field(spec):
    declared = set()
    for name in ("ConfigResponse", "LabelInfo", "TierInfo"):
        declared |= set(schema(spec, name)["properties"])
    assert not {"url", "path", "secret", "secret_env", "price_in_per_m"} & declared


def test_requests_endpoint_contract(spec):
    operation = spec["paths"]["/requests"]["get"]
    assert operation["operationId"] == "list_requests"
    assert response_schema_ref(operation) == "RequestItem"
    assert operation["responses"]["200"]["headers"]["X-Total-Count"]["schema"]["type"] == "integer"
    params = {p["name"]: p["schema"] for p in operation["parameters"]}
    assert set(params) == {
        "action", "tier", "review_status", "delivery_status", "degraded", "q", "limit", "offset", "order",
    }
    assert params["order"]["enum"] == ["newest", "oldest"]
    assert params["limit"]["maximum"] == 200 and params["limit"]["minimum"] == 1


def test_request_item_fields(spec):
    item = schema(spec, "RequestItem")
    assert set(item["properties"]) == {
        "id", "created_at", "text", "label", "confidence", "tier", "action", "cost_usd",
        "latency_ms", "degraded", "review_status", "final_label", "resolved_at",
        "delivery_status", "delivery_error", "delivered_at",
    }
    assert "error" not in item["properties"]
    assert item["properties"]["action"]["enum"] == ["accepted", "human_review"]


def test_review_endpoint_supports_offset_and_declares_the_total_header(spec):
    operation = spec["paths"]["/review"]["get"]
    params = {p["name"]: p["schema"] for p in operation["parameters"]}
    assert set(params) == {"limit", "offset"}
    assert params["offset"]["minimum"] == 0
    assert operation["responses"]["200"]["headers"]["X-Total-Count"]["schema"]["type"] == "integer"


def test_reviewer_agreement_is_documented_as_not_being_accuracy(spec):
    agreement = schema(spec, "ReviewerAgreement")
    assert set(agreement["properties"]) == {"resolved", "agreed", "rate"}
    description = agreement["properties"]["rate"]["description"]
    assert "NOT the model's overall accuracy" in description
    assert {option.get("type") for option in agreement["properties"]["rate"]["anyOf"]} == {"number", "null"}


def test_stats_accepts_an_optional_since_window(spec):
    params = {p["name"]: p for p in spec["paths"]["/stats"]["get"]["parameters"]}
    assert set(params) == {"since"}
    assert params["since"]["required"] is False
    formats = {option.get("format") for option in params["since"]["schema"]["anyOf"]}
    assert "date-time" in formats
