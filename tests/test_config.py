import copy

import pytest
import yaml

from routeiq.config import ROOT, ConfigError, load_config, validate_config

VALID = {
    "domain": "demo",
    "labels": ["a", "b"],
    "tiers": [
        {"name": "baseline", "model": "sklearn_tfidf_logreg", "accept_threshold": 0.7},
        {
            "name": "llm", "model": "openrouter", "model_id": "vendor/model",
            "price_in_per_m": 0.1, "price_out_per_m": 0.3, "accept_threshold": 0.9,
            "timeout": 10, "max_attempts": 2,
        },
    ],
    "target": {"type": "mock_erp", "url": "http://localhost:8000/mock-erp/api/tickets"},
}


def config(**changes):
    result = copy.deepcopy(VALID)
    result.update(changes)
    return result


def errors_of(cfg):
    with pytest.raises(ConfigError) as info:
        validate_config(cfg)
    return str(info.value)


def test_valid_config_passes():
    validate_config(copy.deepcopy(VALID))


def test_the_shipped_config_is_valid():
    load_config(ROOT / "configs" / "clinc150.yaml")


def test_target_section_is_optional():
    cfg = copy.deepcopy(VALID)
    del cfg["target"]
    validate_config(cfg)


def test_empty_target_section_is_accepted():
    validate_config(config(target=None))


def test_empty_file_is_rejected():
    assert "mapping" in errors_of(None)


def test_unknown_top_level_key_is_reported():
    assert "unknown top-level key 'tagret'" in errors_of(config(tagret={}))


def test_missing_domain_is_reported():
    cfg = copy.deepcopy(VALID)
    del cfg["domain"]
    assert "'domain'" in errors_of(cfg)


@pytest.mark.parametrize("labels", [[], "a", None, ["a", ""], ["a", 3]])
def test_invalid_labels_are_reported(labels):
    assert "'labels'" in errors_of(config(labels=labels))


def test_duplicate_labels_are_reported():
    assert "duplicates" in errors_of(config(labels=["a", "a"]))


@pytest.mark.parametrize("tiers", [[], None, "baseline"])
def test_invalid_tiers_are_reported(tiers):
    assert "'tiers'" in errors_of(config(tiers=tiers))


def test_duplicate_tier_names_are_reported():
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][1]["name"] = "baseline"
    assert "unique" in errors_of(cfg)


def test_unknown_model_is_reported():
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][0]["model"] = "magic"
    assert "unknown model 'magic'" in errors_of(cfg)


def test_target_nested_inside_a_tier_is_reported_with_its_location():
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][1]["target"] = cfg.pop("target")
    message = errors_of(cfg)
    assert "tiers[1] (llm)" in message
    assert "unknown key 'target'" in message


@pytest.mark.parametrize("value", [0, -0.1, 1.5, "0.7", True, None])
def test_invalid_accept_threshold_is_reported(value):
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][0]["accept_threshold"] = value
    assert "accept_threshold" in errors_of(cfg)


def test_threshold_of_exactly_one_is_allowed():
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][0]["accept_threshold"] = 1
    validate_config(cfg)


def test_openrouter_tier_requires_model_id_and_prices():
    cfg = copy.deepcopy(VALID)
    for key in ("model_id", "price_in_per_m", "price_out_per_m"):
        del cfg["tiers"][1][key]
    message = errors_of(cfg)
    assert "'model_id'" in message
    assert "'price_in_per_m'" in message
    assert "'price_out_per_m'" in message


def test_negative_price_is_reported():
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][1]["price_in_per_m"] = -1
    assert "price_in_per_m" in errors_of(cfg)


@pytest.mark.parametrize("value", [0, -5, "10"])
def test_invalid_timeout_is_reported(value):
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][1]["timeout"] = value
    assert "timeout" in errors_of(cfg)


@pytest.mark.parametrize("value", [0, 1.5, "2", True])
def test_invalid_max_attempts_is_reported(value):
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][1]["max_attempts"] = value
    assert "max_attempts" in errors_of(cfg)


def test_baseline_tier_rejects_openrouter_only_keys():
    cfg = copy.deepcopy(VALID)
    cfg["tiers"][0]["timeout"] = 5
    assert "tiers[0] (baseline): unknown key 'timeout'" in errors_of(cfg)


@pytest.mark.parametrize("target", [
    {"type": "zzz"},
    {"url": "http://x"},
    {"type": "webhook"},
    {"type": "mock_erp"},
    {"type": "jsonl"},
    {"type": "jsonl", "path": "x.jsonl", "url": "http://x"},
    "mock_erp",
])
def test_invalid_target_is_reported(target):
    assert "target" in errors_of(config(target=target))


@pytest.mark.parametrize("target", [
    {"type": "none"},
    {"type": "jsonl", "path": "out.jsonl"},
    {"type": "webhook", "url": "http://x"},
    {"type": "webhook", "url": "http://x", "secret_env": "SECRET"},
    {"type": "mock_erp", "url": "http://x"},
])
def test_valid_targets_are_accepted(target):
    validate_config(config(target=target))


def test_all_problems_are_reported_together():
    cfg = copy.deepcopy(VALID)
    cfg["labels"] = []
    cfg["tiers"][0]["accept_threshold"] = 5
    cfg["target"] = {"type": "zzz"}
    message = errors_of(cfg)
    assert "'labels'" in message
    assert "accept_threshold" in message
    assert "target" in message


def test_load_config_validates(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump({"domain": "x"}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)


# --- task and label_descriptions -----------------------------------------------

def test_complete_label_descriptions_are_accepted():
    validate_config(config(task="tickets", label_descriptions={"a": "first.", "b": "second."}))


def test_label_descriptions_and_task_are_optional():
    cfg = copy.deepcopy(VALID)
    assert "label_descriptions" not in cfg and "task" not in cfg
    validate_config(cfg)


def test_missing_label_description_is_reported():
    message = errors_of(config(label_descriptions={"a": "first."}))
    assert "missing a description for 'b'" in message


def test_description_for_an_unknown_label_is_reported():
    message = errors_of(config(label_descriptions={"a": "x.", "b": "y.", "zzz": "z."}))
    assert "unknown label 'zzz'" in message


@pytest.mark.parametrize("text", ["", None, 5, ["list"]])
def test_empty_or_non_text_description_is_reported(text):
    message = errors_of(config(label_descriptions={"a": text, "b": "second."}))
    assert "label_descriptions.a" in message


@pytest.mark.parametrize("value", ["a description", ["a", "b"], 3])
def test_label_descriptions_must_be_a_mapping(value):
    assert "must be a mapping" in errors_of(config(label_descriptions=value))


@pytest.mark.parametrize("task", ["", 3, ["x"]])
def test_invalid_task_is_reported(task):
    assert "'task'" in errors_of(config(task=task))
