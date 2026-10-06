from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"


class ConfigError(ValueError):
    pass


TIER_KEYS = {
    "sklearn_tfidf_logreg": {"name", "model", "accept_threshold"},
    "openrouter": {
        "name", "model", "accept_threshold", "model_id",
        "price_in_per_m", "price_out_per_m", "timeout", "max_attempts",
    },
}
TARGET_KEYS = {
    "none": {"type"},
    "jsonl": {"type", "path"},
    "webhook": {"type", "url", "secret_env"},
    "mock_erp": {"type", "url"},
}
TARGET_REQUIRED = {"jsonl": "path", "webhook": "url", "mock_erp": "url"}
MAX_EXAMPLES = 12
MAX_EXAMPLE_LENGTH = 200
DATA_SOURCES = ("public", "synthetic", "private")
TOP_KEYS = {"domain", "data_source", "labels", "task", "label_descriptions", "examples", "tiers", "target"}


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_text(value):
    return isinstance(value, str) and value != ""


def _check_tier(index, tier):
    if not isinstance(tier, dict):
        return [f"tiers[{index}] must be a mapping"]

    name = tier.get("name")
    where = f"tiers[{index}] ({name})" if _is_text(name) else f"tiers[{index}]"
    errors = []

    if not _is_text(name):
        errors.append(f"{where}: 'name' must be a non-empty string")

    kind = tier.get("model")
    if not isinstance(kind, str) or kind not in TIER_KEYS:
        known = ", ".join(sorted(TIER_KEYS))
        errors.append(f"{where}: unknown model '{kind}' (expected one of: {known})")
        return errors

    for key in sorted(set(tier) - TIER_KEYS[kind]):
        errors.append(f"{where}: unknown key '{key}'")

    threshold = tier.get("accept_threshold")
    if not _is_number(threshold) or not 0 < threshold <= 1:
        errors.append(f"{where}: 'accept_threshold' must be a number above 0 and at most 1")

    if kind == "openrouter":
        if not _is_text(tier.get("model_id")):
            errors.append(f"{where}: 'model_id' must be a non-empty string")
        for key in ("price_in_per_m", "price_out_per_m"):
            value = tier.get(key)
            if not _is_number(value) or value < 0:
                errors.append(f"{where}: '{key}' must be a number, zero or more")
        if "timeout" in tier and (not _is_number(tier["timeout"]) or tier["timeout"] <= 0):
            errors.append(f"{where}: 'timeout' must be a number above 0")
        if "max_attempts" in tier:
            attempts = tier["max_attempts"]
            if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
                errors.append(f"{where}: 'max_attempts' must be a whole number, 1 or more")

    return errors


def _check_target(target):
    if not isinstance(target, dict):
        return ["'target' must be a mapping"]

    kind = target.get("type")
    if not isinstance(kind, str) or kind not in TARGET_KEYS:
        known = ", ".join(sorted(TARGET_KEYS))
        return [f"target: unknown type '{kind}' (expected one of: {known})"]

    errors = []
    for key in sorted(set(target) - TARGET_KEYS[kind]):
        errors.append(f"target: unknown key '{key}' for type '{kind}'")

    needed = TARGET_REQUIRED.get(kind)
    if needed and not _is_text(target.get(needed)):
        errors.append(f"target: type '{kind}' needs '{needed}'")

    return errors


def validate_config(config):
    if not isinstance(config, dict):
        raise ConfigError("invalid config:\n  - the file must contain a mapping at the top level")

    errors = []

    for key in sorted(set(config) - TOP_KEYS):
        errors.append(f"unknown top-level key '{key}'")

    if not _is_text(config.get("domain")):
        errors.append("'domain' must be a non-empty string")

    labels = config.get("labels")
    if not isinstance(labels, list) or not labels:
        errors.append("'labels' must be a non-empty list")
    elif not all(_is_text(label) for label in labels):
        errors.append("'labels' must contain only non-empty strings")
    elif len(set(labels)) != len(labels):
        errors.append("'labels' contains duplicates")

    if "data_source" in config and config["data_source"] not in DATA_SOURCES:
        errors.append(f"'data_source' must be one of: {', '.join(DATA_SOURCES)}")

    if "examples" in config:
        examples = config["examples"]
        if not isinstance(examples, list) or not examples or not all(_is_text(e) for e in examples):
            errors.append("'examples' must be a non-empty list of non-empty strings")
        else:
            if len(examples) > MAX_EXAMPLES:
                errors.append(f"'examples' has {len(examples)} entries, at most {MAX_EXAMPLES} are allowed")
            if any(len(e) > MAX_EXAMPLE_LENGTH for e in examples):
                errors.append(f"every entry of 'examples' must have at most {MAX_EXAMPLE_LENGTH} characters")
            if len(set(examples)) != len(examples):
                errors.append("'examples' contains duplicates")

    if "task" in config and not _is_text(config["task"]):
        errors.append("'task' must be a non-empty string")

    descriptions = config.get("label_descriptions")
    if descriptions is not None:
        if not isinstance(descriptions, dict):
            errors.append("'label_descriptions' must be a mapping")
        else:
            known = set(labels) if isinstance(labels, list) else set()
            for label in sorted(str(k) for k in set(descriptions) - known):
                errors.append(f"'label_descriptions' has an unknown label '{label}'")
            for label in sorted(known - set(descriptions)):
                errors.append(f"'label_descriptions' is missing a description for '{label}'")
            for label, text in descriptions.items():
                if not _is_text(text):
                    errors.append(f"'label_descriptions.{label}' must be a non-empty string")

    tiers = config.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        errors.append("'tiers' must be a non-empty list")
    else:
        names = []
        for index, tier in enumerate(tiers):
            errors.extend(_check_tier(index, tier))
            if isinstance(tier, dict) and _is_text(tier.get("name")):
                names.append(tier["name"])
        if len(set(names)) != len(names):
            errors.append("tier names must be unique")

    if config.get("target") is not None:
        errors.extend(_check_target(config["target"]))

    if errors:
        raise ConfigError("invalid config:\n" + "\n".join(f"  - {e}" for e in errors))


def load_config(path):
    with open(path, "r") as f:
        config = yaml.safe_load(f)
    validate_config(config)
    return config


def model_path(config, tier_name):
    return MODELS_DIR / f"{config['domain']}_{tier_name}.joblib"


def data_path(config, split):
    """Where the labeled file of a split lives: data/<domain>/<split>.csv."""
    return DATA_DIR / config["domain"] / f"{split}.csv"
