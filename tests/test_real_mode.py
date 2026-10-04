"""create_app() gerçek modda: her şey config'ten ve ortam değişkenlerinden kurulur.

Yalnızca modeller (build_tiers) sahte, hedef ve mock ERP kurulumu gerçek koddan geçer.
"""
import json

from fastapi.testclient import TestClient

from fakes import Fake
from routeiq.api import create_app


def configure(tmp_path, monkeypatch, target_yaml):
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        "domain: test\nlabels: [a, b]\n"
        "tiers:\n  - name: baseline\n    model: sklearn_tfidf_logreg\n    accept_threshold: 0.5\n"
        + target_yaml,
        encoding="utf-8",
    )
    tiers = [({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9))]
    monkeypatch.setenv("ROUTEIQ_CONFIG", str(config_file))
    monkeypatch.setenv("ROUTEIQ_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr("routeiq.api.build_tiers", lambda config: tiers)


def test_target_is_built_from_the_config(tmp_path, monkeypatch):
    out = tmp_path / "out.jsonl"
    configure(tmp_path, monkeypatch, f'target:\n  type: jsonl\n  path: "{out}"\n')
    with TestClient(create_app()) as client:
        body = client.post("/route", json={"text": "hello"}).json()
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["request_id"] == body["request_id"]
        assert record["label"] == "a"
        assert record["source"] == "cascade"


def test_without_a_target_section_nothing_is_delivered(tmp_path, monkeypatch):
    configure(tmp_path, monkeypatch, "")
    with TestClient(create_app()) as client:
        response = client.post("/route", json={"text": "hello"})
        assert response.status_code == 200
        row = client.app.state.store.get(response.json()["request_id"])
        assert row["delivery_status"] is None


def test_mock_erp_is_mounted_when_the_config_targets_it(tmp_path, monkeypatch):
    url = "http://testserver/mock-erp/api/tickets"
    configure(tmp_path, monkeypatch, f"target:\n  type: mock_erp\n  url: {url}\n")
    with TestClient(create_app()) as client:
        assert client.get("/mock-erp/api/tickets").status_code == 200


def test_mock_erp_is_not_mounted_for_other_targets(tmp_path, monkeypatch):
    out = tmp_path / "out.jsonl"
    configure(tmp_path, monkeypatch, f'target:\n  type: jsonl\n  path: "{out}"\n')
    with TestClient(create_app()) as client:
        assert client.get("/mock-erp/api/tickets").status_code == 404


def test_request_flows_through_the_config_into_the_mock_erp(tmp_path, monkeypatch):
    url = "http://testserver/mock-erp/api/tickets"
    configure(tmp_path, monkeypatch, f"target:\n  type: mock_erp\n  url: {url}\n")
    with TestClient(create_app()) as client:

        def forward(target_url, content, headers, timeout):
            return client.post(target_url, content=content, headers=headers)

        monkeypatch.setattr("routeiq.integrations.webhook.httpx.post", forward)

        body = client.post("/route", json={"text": "my card got declined"}).json()

        tickets = client.get("/mock-erp/api/tickets").json()
        assert tickets["@odata.count"] == 1
        ticket = tickets["value"][0]
        assert ticket["ExternalID"] == str(body["request_id"])
        assert ticket["Category"] == "a"
        assert ticket["Description"] == "my card got declined"
        row = client.app.state.store.get(body["request_id"])
        assert row["delivery_status"] == "sent"
