from fastapi.testclient import TestClient

from fakes import Fake
from routeiq.api import create_app
from routeiq.integrations import build_target
from routeiq.integrations.mock_erp_adapter import MAX_DESCRIPTION, MockErpIntegration, to_ticket

ERP_URL = "http://testserver/mock-erp/api/tickets"

RECORD = {
    "request_id": 5,
    "text": "my card got declined at the store",
    "label": "card_declined",
    "confidence": 0.7,
    "tier": "baseline",
    "source": "cascade",
}


def make_erp_client(tmp_path):
    tiers = [
        ({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9)),
        ({"name": "llm", "accept_threshold": 0.7}, Fake("b", 0.9)),
    ]
    app = create_app(tiers=tiers, labels=["a", "b"], db_path=tmp_path / "t.db", mock_erp=True)
    return TestClient(app)


def route_http_to(client, monkeypatch):
    """Webhook'un HTTP çağrısını gerçek ağ yerine TestClient'a yönlendirir."""

    def fake_post(url, content, headers, timeout):
        return client.post(url, content=content, headers=headers)

    monkeypatch.setattr("routeiq.integrations.webhook.httpx2.post", fake_post)


def test_to_ticket_maps_fields():
    assert to_ticket(RECORD) == {
        "ExternalID": "5",
        "Category": "card_declined",
        "Description": "my card got declined at the store",
        "Confidence": 0.7,
        "Source": "cascade",
    }


def test_to_ticket_external_id_is_a_string():
    assert isinstance(to_ticket(RECORD)["ExternalID"], str)


def test_to_ticket_truncates_long_description():
    record = {**RECORD, "text": "x" * (MAX_DESCRIPTION + 1000)}
    assert len(to_ticket(record)["Description"]) == MAX_DESCRIPTION


def test_build_target_mock_erp():
    target = build_target({"target": {"type": "mock_erp", "url": "http://x"}})
    assert isinstance(target, MockErpIntegration)


def test_record_reaches_the_mock_erp(tmp_path, monkeypatch):
    with make_erp_client(tmp_path) as client:
        route_http_to(client, monkeypatch)
        MockErpIntegration(ERP_URL).send(RECORD)
        body = client.get("/mock-erp/api/tickets").json()
        assert body["@odata.count"] == 1
        ticket = body["value"][0]
        assert ticket["ExternalID"] == "5"
        assert ticket["Category"] == "card_declined"
        assert ticket["Description"] == "my card got declined at the store"
        assert ticket["Status"] == "Open"


def test_sending_the_same_record_twice_creates_one_ticket(tmp_path, monkeypatch):
    with make_erp_client(tmp_path) as client:
        route_http_to(client, monkeypatch)
        erp = MockErpIntegration(ERP_URL)
        erp.send(RECORD)
        erp.send(RECORD)
        assert client.get("/mock-erp/api/tickets").json()["@odata.count"] == 1


def test_different_records_create_different_tickets(tmp_path, monkeypatch):
    with make_erp_client(tmp_path) as client:
        route_http_to(client, monkeypatch)
        erp = MockErpIntegration(ERP_URL)
        erp.send(RECORD)
        erp.send({**RECORD, "request_id": 6, "label": "report_fraud"})
        body = client.get("/mock-erp/api/tickets").json()
        assert body["@odata.count"] == 2
        assert [t["Category"] for t in body["value"]] == ["card_declined", "report_fraud"]
