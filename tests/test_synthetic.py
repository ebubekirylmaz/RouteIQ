import copy
import random

import pandas as pd
import pytest
import yaml

from routeiq import config as config_module
from routeiq import synthetic, train
from routeiq.config import ROOT, data_path, load_config
from routeiq.synthetic import SpecError, check_against_config, generate, load_spec, split_templates, validate_spec

SPEC_PATH = ROOT / "data" / "synthetic" / "ev_after_sales.yaml"
CONFIG_PATH = ROOT / "configs" / "ev_after_sales.yaml"


def mini_spec(**changes):
    """A small valid spec. Every template has a marker word of its own (t0, t1, ...) so that a test
    can tell which template a text came from."""
    spec = {
        "domain": "mini",
        "seed": 3,
        "per_label": {"train": 10, "val": 4, "test": 4},
        "noise": {"lowercase": 0, "typo": 0, "filler": 0},
        "slots": {"n": [str(i) for i in range(1, 31)]},
        "labels": {
            "first": [f"t{i} first thing number {{n}}" for i in range(0, 10)],
            "second": [f"t{i} second thing number {{n}}" for i in range(10, 20)],
        },
    }
    spec.update(changes)
    return spec


def errors_of(spec):
    with pytest.raises(SpecError) as info:
        validate_spec(spec)
    return str(info.value)


# --- the shipped example --------------------------------------------------------

def test_the_shipped_spec_is_valid_and_matches_its_config():
    spec = load_spec(SPEC_PATH)
    validate_spec(spec)
    check_against_config(spec, load_config(CONFIG_PATH))


def test_the_shipped_config_says_the_data_is_synthetic():
    assert load_config(CONFIG_PATH)["data_source"] == "synthetic"


def test_the_shipped_spec_gives_the_sizes_it_asks_for_and_balanced_classes():
    spec = load_spec(SPEC_PATH)
    frames = generate(spec)
    labels = len(spec["labels"])
    for split, frame in frames.items():
        assert len(frame) == spec["per_label"][split] * labels
        assert set(frame["label"].value_counts()) == {spec["per_label"][split]}
        assert list(frame.columns) == ["text", "label"]


def test_the_shipped_spec_never_repeats_a_text():
    frames = generate(load_spec(SPEC_PATH))
    texts = pd.concat(frames.values())["text"].str.lower()
    assert not texts.duplicated().any()


def test_every_shipped_label_has_a_description_and_texts():
    config = load_config(CONFIG_PATH)
    assert set(config["label_descriptions"]) == set(config["labels"])
    assert set(generate(load_spec(SPEC_PATH))["test"]["label"]) == set(config["labels"])


# --- the rules that keep the numbers honest ----------------------------------------

def test_a_template_used_for_testing_is_never_used_for_training_or_validation():
    frames = generate(mini_spec())
    markers = {
        split: {text.split()[0] for text in frame["text"]}
        for split, frame in frames.items()
    }
    assert markers["train"].isdisjoint(markers["val"])
    assert markers["train"].isdisjoint(markers["test"])
    assert markers["val"].isdisjoint(markers["test"])
    assert markers["test"] and markers["val"] and markers["train"]


def test_the_templates_are_shared_out_completely_and_without_overlap():
    templates = [f"template {i} {{n}}" for i in range(10)]
    parts = split_templates(templates, random.Random(1))
    joined = parts["train"] + parts["val"] + parts["test"]
    assert sorted(joined) == sorted(templates)
    assert len(parts["test"]) == len(parts["val"]) == 2 and len(parts["train"]) == 6


def test_every_split_gets_at_least_one_template_even_with_the_minimum():
    parts = split_templates([f"t{i}" for i in range(synthetic.MIN_TEMPLATES)], random.Random(1))
    assert all(len(parts[split]) >= 1 for split in synthetic.SPLITS)


def test_no_text_appears_in_two_splits_or_under_two_labels():
    frames = generate(mini_spec())
    everything = pd.concat(frames.values())
    assert not everything["text"].str.lower().duplicated().any()


# --- determinism and noise ----------------------------------------------------------

def test_the_same_spec_gives_the_same_data():
    first, second = generate(mini_spec()), generate(mini_spec())
    for split in synthetic.SPLITS:
        pd.testing.assert_frame_equal(first[split], second[split])


def test_another_seed_gives_other_data():
    first, second = generate(mini_spec(seed=1)), generate(mini_spec(seed=2))
    assert list(first["train"]["text"]) != list(second["train"]["text"])


def test_without_noise_texts_are_exactly_the_templates_filled_in():
    frame = generate(mini_spec())["train"]
    assert all(text[0] == "t" and "thing number" in text for text in frame["text"])
    assert all(text == text.lower() for text in frame["text"])  # the templates themselves are lower case


def test_lowercase_noise_removes_every_capital():
    spec = mini_spec(noise={"lowercase": 1})
    spec["labels"]["first"] = [f"T{i} First thing number {{n}}" for i in range(0, 10)]
    spec["labels"]["second"] = [f"T{i} Second thing number {{n}}" for i in range(10, 20)]
    assert all(text == text.lower() for frame in generate(spec).values() for text in frame["text"])


def test_a_typo_changes_one_word_by_at_most_one_letter():
    rng = random.Random(5)
    for _ in range(200):
        text = "please replace the charging cable quickly"
        changed = synthetic._typo(text, rng)
        old, new = text.split(), changed.split()
        assert len(old) == len(new)
        different = [(a, b) for a, b in zip(old, new) if a != b]
        assert len(different) <= 1
        assert all(abs(len(a) - len(b)) <= 1 for a, b in different)


def test_a_text_without_a_long_word_survives_a_typo_unchanged():
    assert synthetic._typo("is it ok", random.Random(1)) == "is it ok"


def test_filler_adds_a_greeting_or_a_thank_you():
    frame = generate(mini_spec(noise={"filler": 1}))["train"]
    assert all(
        text.startswith(tuple(synthetic.PREFIXES)) or text.endswith(tuple(synthetic.SUFFIXES))
        for text in frame["text"]
    )


# --- spec validation ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "spec, message",
    [
        ("not a mapping", "mapping at the top level"),
        (mini_spec(extra=1), "unknown top-level key 'extra'"),
        (mini_spec(domain=""), "'domain' must be a non-empty string"),
        (mini_spec(seed="x"), "'seed' must be a whole number"),
        (mini_spec(seed=True), "'seed' must be a whole number"),
        (mini_spec(per_label={"train": 5}), "'per_label' must give a number for each of"),
        (mini_spec(per_label={"train": 0, "val": 1, "test": 1}), "'per_label.train'"),
        (mini_spec(per_label={"train": 1.5, "val": 1, "test": 1}), "'per_label.train'"),
        (mini_spec(noise={"typo": 2}), "'noise.typo' must be a number from 0 to 1"),
        (mini_spec(noise={"typo": -0.1}), "'noise.typo'"),
        (mini_spec(noise={"shouting": 1}), "unknown noise key 'shouting'"),
        (mini_spec(slots={"n": []}), "slot 'n' must be a non-empty list"),
        (mini_spec(slots={"n": [True]}), "slot 'n'"),
        (mini_spec(labels={}), "'labels' must be a mapping with at least one label"),
    ],
)
def test_bad_specs_are_refused_with_the_reason(spec, message):
    assert message in errors_of(spec)


def test_a_label_needs_enough_templates_to_give_each_split_its_own():
    spec = mini_spec()
    spec["labels"]["first"] = ["a {n}", "b {n}"]
    assert "label 'first': needs at least 6 templates, has 2" in errors_of(spec)


def test_a_template_may_only_use_slots_that_exist():
    spec = mini_spec()
    spec["labels"]["first"][0] = "t0 uses {nothing}"
    assert "'t0 uses {nothing}' uses {nothing}, which is not a slot" in errors_of(spec)


@pytest.mark.parametrize("template", ["t0 {}", "t0 {0}", "t0 {n", "t0 n}"])
def test_positional_or_broken_braces_are_refused(template):
    spec = mini_spec()
    spec["labels"]["first"][0] = template
    assert "label 'first'" in errors_of(spec)


def test_the_same_template_twice_in_a_label_is_refused():
    spec = mini_spec()
    spec["labels"]["first"][1] = spec["labels"]["first"][0]
    assert "has the same template twice" in errors_of(spec)


def test_a_template_under_two_labels_is_refused():
    spec = mini_spec()
    spec["labels"]["second"][0] = spec["labels"]["first"][0]
    assert "is a template of both 'first' and 'second'" in errors_of(spec)


def test_every_problem_is_reported_at_once():
    message = errors_of(mini_spec(seed="x", domain="", noise={"typo": 5}))
    assert message.count("\n  - ") == 3


def test_asking_for_more_distinct_texts_than_a_label_can_give_is_an_error_that_says_so():
    spec = mini_spec(slots={"n": ["1", "2"]}, per_label={"train": 40, "val": 4, "test": 4})
    with pytest.raises(SpecError, match="distinct texts could be made"):
        generate(spec)


# --- spec and config must agree ----------------------------------------------------------------

def test_a_spec_for_another_domain_does_not_match_the_config():
    spec = load_spec(SPEC_PATH)
    spec["domain"] = "other"
    with pytest.raises(SpecError, match="the spec is for 'other'"):
        check_against_config(spec, load_config(CONFIG_PATH))


def test_labels_that_differ_do_not_match():
    spec = load_spec(SPEC_PATH)
    del spec["labels"]["parts_order"]
    with pytest.raises(SpecError, match="labels of the spec and of the config"):
        check_against_config(spec, load_config(CONFIG_PATH))


def test_generated_data_needs_a_config_that_says_so():
    config = load_config(CONFIG_PATH)
    config["data_source"] = "public"
    with pytest.raises(SpecError, match="data_source: synthetic"):
        check_against_config(load_spec(SPEC_PATH), config)


# --- the command line -------------------------------------------------------------------------------

def test_the_command_writes_three_files_and_says_the_data_is_synthetic(tmp_path, capsys):
    assert synthetic.main(["--config", str(CONFIG_PATH), "--out-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "SYNTHETIC" in out and "says nothing about real data" in out
    for split in synthetic.SPLITS:
        frame = pd.read_csv(tmp_path / f"{split}.csv")
        assert list(frame.columns) == ["text", "label"]
        assert len(frame) > 0


def test_the_command_refuses_a_config_that_is_not_synthetic(tmp_path, capsys):
    config = yaml.safe_load(CONFIG_PATH.read_text())
    config["data_source"] = "public"
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(config))
    assert synthetic.main(["--config", str(path), "--out-dir", str(tmp_path / "out")]) == 1
    assert "data_source: synthetic" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


# --- a new domain needs no code ------------------------------------------------------------------------

def test_a_baseline_can_be_trained_on_a_generated_domain_without_changing_any_code(tmp_path, monkeypatch):
    """The whole path of a new domain: spec -> files -> data_path -> training. Only a config and
    a spec exist for it; no Python was written."""
    monkeypatch.setattr(config_module, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config_module, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(train, "MODELS_DIR", tmp_path / "models")
    config = load_config(CONFIG_PATH)

    synthetic.write_splits(load_spec(SPEC_PATH), data_path(config, "train").parent)
    result = train.train_baseline(config)

    assert result["path"].exists() and result["path"].parent == tmp_path / "models"
    assert result["accuracy"] > 2 / len(config["labels"])   # far better than guessing


def test_the_files_of_a_domain_live_in_a_folder_of_that_domain():
    config = load_config(CONFIG_PATH)
    assert data_path(config, "val") == config_module.DATA_DIR / "ev_after_sales" / "val.csv"
    assert data_path(load_config(ROOT / "configs" / "clinc150.yaml"), "test").parent.name == "clinc150"
