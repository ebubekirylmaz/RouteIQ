"""Puts the saved predictions of every tier on one split into a single file.

`python -m routeiq.evaluate` saves what each tier answered under reports/ (which is not committed).
This combines those files into one small file that can be committed, so the dashboard can be
filled with real decisions without calling any model again:

    python scripts/export_predictions.py                      # CLINC150, test split
    python scripts/replay_demo.py                             # then fill a demo database from it

The columns are the text, the true label, and for each tier its label, confidence, cost and
latency. No model is called.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

from routeiq.config import ROOT, load_config

DEFAULT_CONFIG = ROOT / "configs" / "clinc150.yaml"
TIER_COLUMNS = ("label", "confidence", "cost_usd", "latency_ms")


class ExportError(ValueError):
    """The saved predictions cannot be combined. The message says why and is meant to be shown."""


def export(config_path=DEFAULT_CONFIG, split="test", out=None, reports_dir=None):
    config = load_config(config_path)
    reports_dir = Path(reports_dir or ROOT / "reports")
    out = Path(out or ROOT / "demo" / f"{config['domain']}_{split}_predictions.csv")

    frames = {}
    for tier in config["tiers"]:
        path = reports_dir / f"{config['domain']}_{split}_{tier['name']}.csv"
        if not path.exists():
            raise ExportError(
                f"{path} does not exist. Run `python -m routeiq.evaluate --config <config> --split {split}` first."
            )
        frames[tier["name"]] = pd.read_csv(path)

    first_name, first = next(iter(frames.items()))
    for name, frame in frames.items():
        if len(frame) != len(first) or not (frame["text"].tolist() == first["text"].tolist()):
            raise ExportError(f"the texts of tier '{name}' are not the same, in the same order, as those of '{first_name}'")
        if not (frame["true"].tolist() == first["true"].tolist()):
            raise ExportError(f"the true labels of tier '{name}' differ from those of '{first_name}'")
        if frame["error"].notna().any():
            raise ExportError(f"tier '{name}' has {int(frame['error'].notna().sum())} failed predictions; refresh them first")
        if not frame["confidence"].between(0, 1).all():
            raise ExportError(f"tier '{name}' has a confidence outside 0 to 1")
        if not frame["label"].isin(config["labels"]).all():
            raise ExportError(f"tier '{name}' predicted a label that is not in the config")

    combined = pd.DataFrame({"text": first["text"], "true": first["true"]})
    for name, frame in frames.items():
        for column in TIER_COLUMNS:
            combined[f"{name}_{column}"] = frame[column]

    out.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(out, index=False)
    return out, len(combined)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Combine the saved predictions of all tiers into one file.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--split", default="test")
    parser.add_argument("--out", type=Path, help="default: demo/<domain>_<split>_predictions.csv")
    args = parser.parse_args(argv)
    try:
        out, count = export(args.config, args.split, args.out)
    except ExportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {count} predictions to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
