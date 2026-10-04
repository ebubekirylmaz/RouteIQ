import pytest

from routeiq.config import ROOT, load_config
from routeiq.models.openrouter import OpenRouterClassifier
from routeiq.models.registry import build_classifier


@pytest.fixture(autouse=True)
def no_real_key_or_dotenv(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr("routeiq.models.openrouter.load_dotenv", lambda: None)


def llm_tier(config):
    return next(t for t in config["tiers"] if t["model"] == "openrouter")


def test_llm_classifier_gets_the_task_and_descriptions_from_the_config():
    config = load_config(ROOT / "configs" / "clinc150.yaml")
    classifier = build_classifier(config, llm_tier(config))
    assert isinstance(classifier, OpenRouterClassifier)
    assert classifier.task == config["task"]
    assert classifier.label_descriptions == config["label_descriptions"]


def test_llm_classifier_gets_its_model_prices_and_retry_budget_from_the_tier():
    config = load_config(ROOT / "configs" / "clinc150.yaml")
    tier = llm_tier(config)
    classifier = build_classifier(config, tier)
    assert classifier.model_id == tier["model_id"]
    assert classifier.price_in == tier["price_in_per_m"]
    assert classifier.price_out == tier["price_out_per_m"]
    assert classifier.timeout == tier["timeout"]
    assert classifier.max_attempts == tier["max_attempts"]


def test_config_without_task_and_descriptions_falls_back_to_defaults():
    config = load_config(ROOT / "configs" / "clinc150.yaml")
    del config["task"]
    del config["label_descriptions"]
    classifier = build_classifier(config, llm_tier(config))
    assert classifier.task == "messages"
    assert classifier.label_descriptions is None


def test_unknown_model_type_is_rejected():
    config = load_config(ROOT / "configs" / "clinc150.yaml")
    with pytest.raises(ValueError):
        build_classifier(config, {"name": "x", "model": "magic"})
