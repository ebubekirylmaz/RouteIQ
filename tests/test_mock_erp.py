from fastapi.testclient import TestClient

from fakes import Fake
from routeiq.api import create_app

LABELS = ["a", "b"]
URL = "/mock-erp/api/tickets"


def make_client(tmp_path, mock_erp=True):
    tiers = [
        ({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9)),
        ({"name": "llm", "accept_threshold": 0.7}, Fake("b", 0.9)),
    ]
    app = create_app(tiers=tiers, labels=LABELS, db_path=tmp_path / "test.db", mock_erp=mock_erp)
    return TestClient(app)


def ticket(external_id="1", category="card_declined"):
    return {
        "ExternalID": external_id,
        "Category": category,
        "Description": "my card got declined",
        "Confidence": 0.7,
        "Source": "cascade",
    }


def test_ticket_is_created(tmp_path):
    with make_client(tmp_path) as client:
        response = client.post(URL, json=ticket())
        assert response.status_code == 201
        body = response.json()
        assert body["TicketID"] == 1
        assert body["Status"] == "Open"
        assert body["Category"] == "card_declined"
        assert body["CreatedAt"]


def test_same_external_id_returns_existing_ticket(tmp_path):
    with make_client(tmp_path) as client:
        first = client.post(URL, json=ticket("42"))
        second = client.post(URL, json=ticket("42"))
        assert first.status_code == 201
        assert second.status_code == 200
        assert second.json()["TicketID"] == first.json()["TicketID"]
        assert client.get(URL).json()["@odata.count"] == 1


def test_different_external_ids_get_different_ticket_ids(tmp_path):
    with make_client(tmp_path) as client:
        one = client.post(URL, json=ticket("1")).json()
        two = client.post(URL, json=ticket("2")).json()
        assert (one["TicketID"], two["TicketID"]) == (1, 2)


def test_collection_has_odata_shape(tmp_path):
    with make_client(tmp_path) as client:
        for i in range(3):
            client.post(URL, json=ticket(str(i)))
        body = client.get(URL).json()
        assert body["@odata.count"] == 3
        assert len(body["value"]) == 3
        assert "@odata.context" in body


def test_top_and_skip(tmp_path):
    with make_client(tmp_path) as client:
        for i in range(3):
            client.post(URL, json=ticket(str(i)))
        body = client.get(URL, params={"$top": 1, "$skip": 1}).json()
        assert [t["TicketID"] for t in body["value"]] == [2]
        assert body["@odata.count"] == 3


def test_get_single_ticket(tmp_path):
    with make_client(tmp_path) as client:
        client.post(URL, json=ticket("7", category="report_fraud"))
        response = client.get(f"{URL}/1")
        assert response.status_code == 200
        assert response.json()["ExternalID"] == "7"
        assert response.json()["Category"] == "report_fraud"


def test_unknown_ticket_returns_404(tmp_path):
    with make_client(tmp_path) as client:
        assert client.get(f"{URL}/99").status_code == 404


def test_missing_required_field_returns_422(tmp_path):
    with make_client(tmp_path) as client:
        body = ticket()
        del body["Category"]
        assert client.post(URL, json=body).status_code == 422


def test_mock_erp_is_not_mounted_by_default(tmp_path):
    with make_client(tmp_path, mock_erp=False) as client:
        assert client.get(URL).status_code == 404
