"""Synthetic labeled text for example domains.

A domain is described by a spec file (data/synthetic/<domain>.yaml): templates per label, values
for the {slots} in them, and how messy the texts should be. Nothing here is real data, and the
accuracy a model reaches on it says nothing about real text.

    python -m routeiq.synthetic --config configs/ev_after_sales.yaml

The output is deterministic: the same spec always gives the same files.

Two rules keep the numbers from looking better than they are:
- The templates of each label are divided between train, validation and test, so a sentence
  pattern used for testing was never seen in training. Only the filled-in slot values overlap.
- A text is never produced twice, not within a split, across splits or across labels.
"""
import argparse
import random
import string
from pathlib import Path

import pandas as pd
import yaml

from routeiq.config import DATA_DIR, ROOT, load_config

SPLITS = ("train", "val", "test")
SPEC_KEYS = {"domain", "seed", "per_label", "noise", "slots", "labels"}
NOISE_KEYS = ("lowercase", "typo", "filler")
MIN_TEMPLATES = 6          # enough to give every split at least one template of its own
HELD_OUT_SHARE = 0.2       # of the templates of a label, for validation and the same for test
MAX_ATTEMPTS_PER_TEXT = 200

PREFIXES = ["hi, ", "hello, ", "hey, ", "good morning, ", "please help: "]
SUFFIXES = [" thanks", " thank you", " asap", " please advise"]


class SpecError(ValueError):
    """The spec cannot be used. The message lists every problem, with its place."""


def _is_text(value):
    return isinstance(value, str) and value.strip() != ""


def _is_slot_value(value):
    """A slot value is a text or a number (YAML reads 180 as a number). It is used as text."""
    if isinstance(value, bool):
        return False
    return _is_text(value) or isinstance(value, (int, float))


def _fields(template):
    """The names inside the {braces} of a template."""
    return [name for _, name, _, _ in string.Formatter().parse(template) if name is not None]


def validate_spec(spec):
    if not isinstance(spec, dict):
        raise SpecError("invalid spec:\n  - the file must contain a mapping at the top level")

    errors = [f"unknown top-level key '{key}'" for key in sorted(set(spec) - SPEC_KEYS)]

    if not _is_text(spec.get("domain")):
        errors.append("'domain' must be a non-empty string")
    if "seed" in spec and (not isinstance(spec["seed"], int) or isinstance(spec["seed"], bool)):
        errors.append("'seed' must be a whole number")

    per_label = spec.get("per_label")
    if not isinstance(per_label, dict) or set(per_label) != set(SPLITS):
        errors.append(f"'per_label' must give a number for each of: {', '.join(SPLITS)}")
    else:
        for split in SPLITS:
            count = per_label[split]
            if not isinstance(count, int) or isinstance(count, bool) or count < 1:
                errors.append(f"'per_label.{split}' must be a whole number, 1 or more")

    noise = spec.get("noise", {})
    if not isinstance(noise, dict):
        errors.append("'noise' must be a mapping")
    else:
        for key in sorted(set(noise) - set(NOISE_KEYS)):
            errors.append(f"unknown noise key '{key}' (expected: {', '.join(NOISE_KEYS)})")
        for key in NOISE_KEYS:
            value = noise.get(key, 0)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 1:
                errors.append(f"'noise.{key}' must be a number from 0 to 1")

    slots = spec.get("slots", {})
    slot_names = set()
    if not isinstance(slots, dict):
        errors.append("'slots' must be a mapping")
    else:
        slot_names = set(slots)
        for name, values in slots.items():
            if not isinstance(values, list) or not values or not all(_is_slot_value(v) for v in values):
                errors.append(f"slot '{name}' must be a non-empty list of texts or numbers")

    labels = spec.get("labels")
    if not isinstance(labels, dict) or not labels:
        errors.append("'labels' must be a mapping with at least one label")
    else:
        seen = {}
        for label, templates in labels.items():
            where = f"label '{label}'"
            if not isinstance(templates, list) or not all(_is_text(t) for t in templates):
                errors.append(f"{where}: templates must be a list of non-empty texts")
                continue
            if len(templates) < MIN_TEMPLATES:
                errors.append(f"{where}: needs at least {MIN_TEMPLATES} templates, has {len(templates)}")
            if len(set(templates)) != len(templates):
                errors.append(f"{where}: has the same template twice")
            for template in templates:
                try:
                    fields = _fields(template)
                except ValueError as error:
                    errors.append(f"{where}: bad braces in '{template}' ({error})")
                    continue
                for field in fields:
                    if field not in slot_names:
                        errors.append(f"{where}: '{template}' uses {{{field}}}, which is not a slot")
                if template in seen and seen[template] != label:
                    errors.append(f"'{template}' is a template of both '{seen[template]}' and '{label}'")
                seen.setdefault(template, label)

    if errors:
        raise SpecError("invalid spec:\n" + "\n".join(f"  - {e}" for e in errors))


def split_templates(templates, rng):
    """Shares out the templates of one label: a few for test, a few for validation, the rest for train."""
    shuffled = list(templates)
    rng.shuffle(shuffled)
    held = max(1, round(len(shuffled) * HELD_OUT_SHARE))
    return {"test": shuffled[:held], "val": shuffled[held:2 * held], "train": shuffled[2 * held:]}


def _fill(template, slots, rng):
    values = {name: str(rng.choice(slots[name])) for name in _fields(template)}
    return template.format(**values)


def _typo(text, rng):
    words = text.split(" ")
    candidates = [i for i, word in enumerate(words) if len(word) >= 5 and word.isalpha()]
    if not candidates:
        return text
    i = rng.choice(candidates)
    word = words[i]
    position = rng.randrange(1, len(word) - 2)
    kind = rng.choice(["swap", "drop", "double"])
    if kind == "swap":
        word = word[:position] + word[position + 1] + word[position] + word[position + 2:]
    elif kind == "drop":
        word = word[:position] + word[position + 1:]
    else:
        word = word[:position] + word[position] + word[position:]
    words[i] = word
    return " ".join(words)


def make_noisy(text, noise, rng):
    """Makes a clean text look more like something a person typed. Each step happens by chance."""
    if rng.random() < noise.get("typo", 0):
        text = _typo(text, rng)
    if rng.random() < noise.get("filler", 0):
        text = rng.choice(PREFIXES) + text if rng.random() < 0.5 else text + rng.choice(SUFFIXES)
    if rng.random() < noise.get("lowercase", 0):
        text = text.lower()
    return text


def _texts(templates, slots, count, noise, rng, taken, where):
    texts = []
    for _ in range(count * MAX_ATTEMPTS_PER_TEXT):
        if len(texts) == count:
            break
        text = make_noisy(_fill(rng.choice(templates), slots, rng), noise, rng)
        if text.lower() in taken:
            continue
        taken.add(text.lower())
        texts.append(text)
    if len(texts) < count:
        raise SpecError(
            f"{where}: only {len(texts)} distinct texts could be made, {count} are needed. "
            "Add templates or slot values, or lower 'per_label'."
        )
    return texts


def generate(spec):
    """Returns {"train": DataFrame, "val": ..., "test": ...} with the columns text and label."""
    validate_spec(spec)
    seed = spec.get("seed", 0)
    noise = spec.get("noise", {})
    taken = set()
    rows = {split: [] for split in SPLITS}

    for split in SPLITS:
        for label, templates in spec["labels"].items():
            portion = split_templates(templates, random.Random(f"{seed}:{label}:partition"))[split]
            rng = random.Random(f"{seed}:{label}:{split}")
            texts = _texts(portion, spec["slots"], spec["per_label"][split], noise, rng, taken,
                           f"label '{label}', split '{split}'")
            rows[split].extend({"text": text, "label": label} for text in texts)

    return {
        split: pd.DataFrame(rows[split]).sample(frac=1, random_state=seed).reset_index(drop=True)
        for split in SPLITS
    }


def write_splits(spec, out_dir):
    frames = generate(spec)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for split, frame in frames.items():
        frame.to_csv(out_dir / f"{split}.csv", index=False)
    return {split: len(frame) for split, frame in frames.items()}


def load_spec(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def check_against_config(spec, config):
    """The spec and the config of a domain must agree, and the config must say the data is synthetic."""
    errors = []
    if spec.get("domain") != config["domain"]:
        errors.append(f"the spec is for '{spec.get('domain')}' but the config is for '{config['domain']}'")
    if set(spec.get("labels", {})) != set(config["labels"]):
        errors.append("the labels of the spec and of the config are not the same")
    if config.get("data_source") != "synthetic":
        errors.append("the config must say 'data_source: synthetic' for generated data")
    if errors:
        raise SpecError("spec and config do not match:\n" + "\n".join(f"  - {e}" for e in errors))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate synthetic train, validation and test files.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--spec", help="default: data/synthetic/<domain>.yaml")
    parser.add_argument("--out-dir", help="default: data/<domain>")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    spec_path = args.spec or ROOT / "data" / "synthetic" / f"{config['domain']}.yaml"
    out_dir = args.out_dir or DATA_DIR / config["domain"]

    try:
        spec = load_spec(spec_path)
        validate_spec(spec)
        check_against_config(spec, config)
        counts = write_splits(spec, out_dir)
    except SpecError as error:
        print(f"error: {error}")
        return 1

    print(f"Wrote SYNTHETIC data for '{config['domain']}' to {out_dir}:")
    for split, count in counts.items():
        print(f"  {split}: {count} texts")
    print("This text was generated from templates. Accuracy on it says nothing about real data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
