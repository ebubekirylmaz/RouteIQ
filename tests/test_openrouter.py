import math

import httpx
import pytest

from routeiq.models.openrouter import OpenRouterClassifier

LABELS = ["report_lost_card", "damaged_card", "card_declined",
          "report_fraud", "freeze_account", "out_of_scope"]

TOKENS = [
    ("{", -0.3386), (' "', -0.00005), ("label", 0.0), ('":', -0.0044),
    (' "', -0.00002), ("card", -0.00027736), ("_de", 0.0), ("cl", 0.0),
    ("ined", 0.0), ('"', -0.0068), (" }", -0.00056),
]


def good_payload(usage=None):
    return {
        "choices": [{
            "message": {"content": '{ "label": "card_declined" }'},
            "logprobs": {"content": [{"token": t, "logprob": lp} for t, lp in TOKENS]},
        }],
        "usage": usage or {"prompt_tokens": 149, "completion_tokens": 12, "cost": 1.701e-05},
    }


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=self)


def make_classifier(monkeypatch, responses):
    """responses: sırayla dönecek FakeResponse listesi. (clf, calls) döndürür."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("routeiq.models.openrouter.load_dotenv", lambda: None)
    monkeypatch.setattr("routeiq.models.openrouter.time.sleep", lambda s: None)
    calls = []

    def fake_post(*args, **kwargs):
        calls.append(kwargs)
        r = responses[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr("routeiq.models.openrouter.httpx.post", fake_post)
    return OpenRouterClassifier("test-model", 0.09, 0.30), calls


def test_classify_parses_label_confidence_and_cost(monkeypatch):
    clf, calls = make_classifier(monkeypatch, [FakeResponse(payload=good_payload())])
    pred = clf.classify("my card got declined", LABELS)
    assert pred.label == "card_declined"
    assert pred.confidence == pytest.approx(math.exp(-0.00027736))
    assert pred.cost_usd == pytest.approx(1.701e-05)
    assert len(calls) == 1


def test_cost_falls_back_to_token_prices_when_response_has_no_cost(monkeypatch):
    usage = {"prompt_tokens": 149, "completion_tokens": 12}
    clf, _ = make_classifier(monkeypatch, [FakeResponse(payload=good_payload(usage))])
    pred = clf.classify("x", LABELS)
    assert pred.cost_usd == pytest.approx((149 * 0.09 + 12 * 0.30) / 1_000_000)


def test_retries_after_429_then_succeeds(monkeypatch):
    responses = [FakeResponse(429), FakeResponse(payload=good_payload())]
    clf, calls = make_classifier(monkeypatch, responses)
    pred = clf.classify("x", LABELS)
    assert pred.label == "card_declined"
    assert len(calls) == 2


def test_retry_after_header_is_respected(monkeypatch):
    responses = [
        FakeResponse(429, headers={"retry-after": "3"}),
        FakeResponse(payload=good_payload()),
    ]
    clf, _ = make_classifier(monkeypatch, responses)
    slept = []
    monkeypatch.setattr("routeiq.models.openrouter.time.sleep", slept.append)
    clf.classify("x", LABELS)
    assert slept == [3.0]


def test_network_error_is_retried(monkeypatch):
    responses = [httpx.ConnectError("down"), FakeResponse(payload=good_payload())]
    clf, calls = make_classifier(monkeypatch, responses)
    pred = clf.classify("x", LABELS)
    assert pred.label == "card_declined"
    assert len(calls) == 2


def test_gives_up_after_all_retries(monkeypatch):
    clf, calls = make_classifier(monkeypatch, [FakeResponse(429) for _ in range(6)])
    with pytest.raises(RuntimeError):
        clf.classify("x", LABELS)
    assert len(calls) == 6


def test_client_error_is_not_retried(monkeypatch):
    clf, calls = make_classifier(monkeypatch, [FakeResponse(401)])
    with pytest.raises(httpx.HTTPStatusError):
        clf.classify("x", LABELS)
    assert len(calls) == 1


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr("routeiq.models.openrouter.load_dotenv", lambda: None)
    with pytest.raises(RuntimeError):
        OpenRouterClassifier("m", 0.09, 0.30)


def test_max_attempts_is_configurable(monkeypatch):
    clf, calls = make_classifier(monkeypatch, [FakeResponse(429), FakeResponse(429)])
    clf.max_attempts = 2
    with pytest.raises(RuntimeError):
        clf.classify("x", LABELS)
    assert len(calls) == 2