import hashlib
import hmac
import json

import httpx2
import pytest

from routeiq.cascade import RouteResult
from routeiq.integrations import build_target
from routeiq.integrations.base import make_record
from routeiq.integrations.jsonl import JsonlExport
from routeiq.integrations.webhook import WebhookIntegration


def read_lines(path):
    return path.read_text(encoding="utf-8").splitlines()


def test_jsonl_appends_one_line_per_record(tmp_path):
    path = tmp_path / "out.jsonl"
    export = JsonlExport(path)
    first = {"request_id": 1, "label": "a"}
    second = {"request_id": 2, "label": "b"}
    export.send(first)
    export.send(second)
    lines = read_lines(path)
    assert len(lines) == 2
    assert json.loads(lines[0]) == first
    assert json.loads(lines[1]) == second


def test_jsonl_keeps_non_ascii_characters(tmp_path):
    path = tmp_path / "out.jsonl"
    JsonlExport(path).send({"text": "kartım çalındı"})
    raw = path.read_text(encoding="utf-8")
    assert "çalındı" in raw
    assert "\\u00e7" not in raw


def test_jsonl_creates_missing_directories(tmp_path):
    path = tmp_path / "a" / "b" / "out.jsonl"
    JsonlExport(path).send({"request_id": 1})
    assert path.exists()


def test_jsonl_does_not_overwrite_existing_file(tmp_path):
    path = tmp_path / "out.jsonl"
    JsonlExport(path).send({"request_id": 1})
    JsonlExport(path).send({"request_id": 2})
    assert len(read_lines(path)) == 2


def test_build_target_without_target_returns_none():
    assert build_target({}) is None


def test_build_target_none_type_returns_none():
    assert build_target({"target": {"type": "none"}}) is None


def test_build_target_jsonl(tmp_path):
    config = {"target": {"type": "jsonl", "path": str(tmp_path / "x.jsonl")}}
    assert isinstance(build_target(config), JsonlExport)


def test_build_target_unknown_type_raises():
    with pytest.raises(ValueError):
        build_target({"target": {"type": "zzz"}})


def test_make_record_copies_result_fields():
    result = RouteResult("card_declined", 0.7, "baseline", "accepted", 0.0, 12.0)
    record = make_record(5, "my card got declined", result, "cascade")
    assert record == {
        "request_id": 5,
        "text": "my card got declined",
        "label": "card_declined",
        "confidence": 0.7,
        "tier": "baseline",
        "source": "cascade",
    }


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx2.HTTPStatusError("error", request=None, response=self)


def patch_post(monkeypatch, responses):
    """httpx2.post ve time.sleep'i değiştirir. Yapılan çağrıların listesini döndürür."""
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        r = responses[len(calls) - 1]
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr("routeiq.integrations.webhook.httpx2.post", fake_post)
    monkeypatch.setattr("routeiq.integrations.webhook.time.sleep", lambda s: None)
    return calls


RECORD = {"request_id": 7, "text": "kartım çalındı", "label": "report_lost_card"}


def test_webhook_posts_record_as_json(monkeypatch):
    calls = patch_post(monkeypatch, [FakeResponse(200)])
    WebhookIntegration("http://hook.test/in").send(RECORD)
    assert len(calls) == 1
    assert calls[0]["url"] == "http://hook.test/in"
    assert json.loads(calls[0]["content"].decode("utf-8")) == RECORD
    assert calls[0]["headers"]["Content-Type"] == "application/json"


def test_webhook_signs_the_exact_bytes_it_sends(monkeypatch):
    calls = patch_post(monkeypatch, [FakeResponse(200)])
    WebhookIntegration("http://hook.test/in", secret="s3").send(RECORD)
    body = calls[0]["content"]
    expected = hmac.new(b"s3", body, hashlib.sha256).hexdigest()
    assert calls[0]["headers"]["X-RouteIQ-Signature"] == "sha256=" + expected


def test_webhook_without_secret_sends_no_signature(monkeypatch):
    calls = patch_post(monkeypatch, [FakeResponse(200)])
    WebhookIntegration("http://hook.test/in").send(RECORD)
    assert "X-RouteIQ-Signature" not in calls[0]["headers"]


def test_webhook_retries_on_503_then_succeeds(monkeypatch):
    calls = patch_post(monkeypatch, [FakeResponse(503), FakeResponse(200)])
    WebhookIntegration("http://hook.test/in").send(RECORD)
    assert len(calls) == 2


def test_webhook_retries_on_network_error_then_succeeds(monkeypatch):
    calls = patch_post(monkeypatch, [httpx2.ConnectError("down"), FakeResponse(200)])
    WebhookIntegration("http://hook.test/in").send(RECORD)
    assert len(calls) == 2


def test_webhook_gives_up_after_all_attempts(monkeypatch):
    calls = patch_post(monkeypatch, [FakeResponse(503)] * 3)
    with pytest.raises(RuntimeError):
        WebhookIntegration("http://hook.test/in", max_attempts=3).send(RECORD)
    assert len(calls) == 3


def test_webhook_does_not_retry_client_errors(monkeypatch):
    calls = patch_post(monkeypatch, [FakeResponse(400)])
    with pytest.raises(httpx2.HTTPStatusError):
        WebhookIntegration("http://hook.test/in").send(RECORD)
    assert len(calls) == 1


def test_build_target_webhook_reads_secret_from_environment(monkeypatch):
    monkeypatch.setenv("HOOK_SECRET", "abc")
    config = {"target": {"type": "webhook", "url": "http://x", "secret_env": "HOOK_SECRET"}}
    target = build_target(config)
    assert isinstance(target, WebhookIntegration)
    assert target.secret == "abc"


def test_build_target_webhook_without_secret_env():
    target = build_target({"target": {"type": "webhook", "url": "http://x"}})
    assert isinstance(target, WebhookIntegration)
    assert target.secret is None
