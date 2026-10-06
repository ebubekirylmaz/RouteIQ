import pytest
from fastapi.testclient import TestClient

from fakes import Fake
from routeiq.api import create_app
from routeiq.config import ROOT, load_config
from routeiq.views import describe_config

SECRET_URL = "https://hooks.example.com/in/SECRET-TOKEN-123"


def config_with(**changes):
    config = {
        "domain": "demo",
        "task": "support tickets",
        "labels": ["a", "b"],
        "label_descriptions": {"a": "first one.", "b": "second one."},
        "tiers": [
            {"name": "baseline", "model": "sklearn_tfidf_logreg", "accept_threshold": 0.7},
            {
                "name": "llm", "model": "openrouter", "model_id": "vendor/model",
                "price_in_per_m": 0.1, "price_out_per_m": 0.3, "accept_threshold": 0.9,
            },
        ],
        "target": {"type": "webhook", "url": SECRET_URL, "secret_env": "HOOK_SECRET_NAME"},
    }
    config.update(changes)
    return config


# --- describe_config ----------------------------------------------------------

def test_shipped_config_is_described():
    config = load_config(ROOT / "configs" / "clinc150.yaml")
    view = describe_config(config=config)
    assert view.domain == "clinc150"
    assert view.task == config["task"]
    assert [label.name for label in view.labels] == config["labels"]
    assert view.labels[0].description == config["label_descriptions"][config["labels"][0]]
    assert [(t.name, t.accept_threshold) for t in view.tiers] == [("baseline", 0.7), ("llm", 0.9)]
    assert view.tiers[1].model_id == config["tiers"][1]["model_id"]
    assert view.target_type == "mock_erp"


def test_labels_keep_the_order_of_the_config():
    view = describe_config(config=config_with(labels=["b", "a"]))
    assert [label.name for label in view.labels] == ["b", "a"]


def test_secrets_and_locations_never_appear_in_the_view():
    raw = describe_config(config=config_with()).model_dump_json()
    for forbidden in (SECRET_URL, "SECRET-TOKEN", "hooks.example.com", "HOOK_SECRET_NAME",
                      "price_in", "price_out", "0.3"):
        assert forbidden not in raw
    assert '"target_type":"webhook"' in raw


def test_file_target_path_is_not_exposed():
    config = config_with(target={"type": "jsonl", "path": "/var/data/private/out.jsonl"})
    raw = describe_config(config=config).model_dump_json()
    assert "/var/data" not in raw
    assert '"target_type":"jsonl"' in raw


def test_missing_optional_parts_become_null():
    config = config_with()
    for key in ("task", "label_descriptions", "target"):
        del config[key]
    view = describe_config(config=config)
    assert view.task is None
    assert view.target_type is None
    assert all(label.description is None for label in view.labels)


def test_baseline_tier_has_no_model_id():
    view = describe_config(config=config_with())
    assert view.tiers[0].model_id is None
    assert view.tiers[0].model == "sklearn_tfidf_logreg"


def test_view_from_injected_labels_and_tiers():
    tiers = [({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9))]
    view = describe_config(labels=["a", "b"], tiers=tiers)
    assert view.domain is None
    assert [label.name for label in view.labels] == ["a", "b"]
    assert [(t.name, t.model, t.accept_threshold) for t in view.tiers] == [("baseline", None, 0.5)]
    assert view.target_type is None


# --- GET /config --------------------------------------------------------------

def test_endpoint_returns_the_injected_labels_and_thresholds(tmp_path):
    tiers = [
        ({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9)),
        ({"name": "llm", "accept_threshold": 0.7}, Fake("b", 0.9)),
    ]
    app = create_app(tiers=tiers, labels=["a", "b"], db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        response = client.get("/config")
    assert response.status_code == 200
    body = response.json()
    assert [label["name"] for label in body["labels"]] == ["a", "b"]
    assert [(t["name"], t["accept_threshold"]) for t in body["tiers"]] == [
        ("baseline", 0.5), ("llm", 0.7),
    ]


def test_endpoint_reads_the_real_config_and_hides_the_target_location(tmp_path, monkeypatch):
    out = tmp_path / "private" / "out.jsonl"
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        "domain: demo\ntask: tickets\nlabels: [a, b]\n"
        "label_descriptions:\n  a: first one.\n  b: second one.\n"
        "tiers:\n  - name: baseline\n    model: sklearn_tfidf_logreg\n    accept_threshold: 0.5\n"
        f'target:\n  type: jsonl\n  path: "{out}"\n',
        encoding="utf-8",
    )
    tiers = [({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9))]
    monkeypatch.setenv("ROUTEIQ_CONFIG", str(config_file))
    monkeypatch.setenv("ROUTEIQ_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr("routeiq.api.build_tiers", lambda config: tiers)

    with TestClient(create_app()) as client:
        response = client.get("/config")

    body = response.json()
    assert body["domain"] == "demo"
    assert body["task"] == "tickets"
    assert body["labels"][1] == {"name": "b", "description": "second one."}
    assert body["target_type"] == "jsonl"
    assert "private" not in response.text
    assert "out.jsonl" not in response.text


# --- data_source ---------------------------------------------------------------------------------

def test_the_view_says_where_the_data_comes_from():
    assert describe_config(config=config_with(data_source="synthetic")).data_source == "synthetic"
    assert describe_config(config=config_with(data_source="public")).data_source == "public"


def test_a_config_without_data_source_has_none_in_the_view():
    assert describe_config(config=config_with()).data_source is None
    assert describe_config(labels=["a"], tiers=[]).data_source is None


def test_the_shipped_configs_say_where_their_data_comes_from():
    sources = {
        path.stem: describe_config(config=load_config(path)).data_source
        for path in (ROOT / "configs").glob("*.yaml")
    }
    assert sources == {"clinc150": "public", "ev_after_sales": "synthetic"}


@pytest.mark.parametrize("line, expected", [("data_source: synthetic\n", "synthetic"), ("", None)])
def test_the_endpoint_returns_it(tmp_path, monkeypatch, line, expected):
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        f"domain: demo\n{line}labels: [a, b]\n"
        "tiers:\n  - name: baseline\n    model: sklearn_tfidf_logreg\n    accept_threshold: 0.5\n",
        encoding="utf-8",
    )
    tiers = [({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9))]
    monkeypatch.setenv("ROUTEIQ_CONFIG", str(config_file))
    monkeypatch.setenv("ROUTEIQ_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr("routeiq.api.build_tiers", lambda config: tiers)

    with TestClient(create_app()) as client:
        assert client.get("/config").json()["data_source"] == expected
