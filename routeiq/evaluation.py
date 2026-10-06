"""The offline evaluation shown on the Evaluation screen.

It is computed from recorded predictions (demo/<domain>_<split>_predictions.csv), the same file that
fills the demo database. Every number comes from the functions of evaluate.py that also produce the
results table of the README, so the screen and the README cannot disagree.

This is an offline measurement on labeled examples, not on live traffic, and the screen says so.
"""
import math
from pathlib import Path

import pandas as pd

from routeiq.config import ROOT
from routeiq.evaluate import calibration, compute_metrics, simulate_cascade, with_human

RECORDED_DIR = ROOT / "demo"
SPLIT = "test"
Z_95 = 1.96
TIER_COLUMNS = ("label", "confidence", "cost_usd", "latency_ms")


class EvaluationUnavailable(Exception):
    """There is nothing to show for this configuration. The message is meant to be shown."""


def predictions_path(domain, split=SPLIT):
    return Path(RECORDED_DIR) / f"{domain}_{split}_predictions.csv"


def wilson_interval(correct, n, z=Z_95):
    """A 95% interval for a share, from `correct` out of `n`. It stays inside 0 to 1 and is
    honest for shares close to 1, where the usual plus-or-minus rule is not."""
    if n <= 0:
        return 0.0, 1.0
    p = correct / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def _tier_frame(df, name):
    return pd.DataFrame({
        "label": df[f"{name}_label"],
        "confidence": df[f"{name}_confidence"],
        "cost_usd": df[f"{name}_cost_usd"],
        "latency_ms": df[f"{name}_latency_ms"],
        "error": None,
        "text": df["text"],
        "true": df["true"],
    })


def _setup(name, description, frame, labels, assumes_reviewer_always_right=False):
    metrics = compute_metrics(frame, labels)
    correct = int((frame["label"] == frame["true"]).sum())
    low, high = wilson_interval(correct, len(frame))
    return {
        "name": name,
        "description": description,
        "accuracy": float(metrics["accuracy"]),
        "accuracy_low": low,
        "accuracy_high": high,
        "macro_f1": float(metrics["macro_f1"]),
        "cost_per_1k_usd": float(metrics["cost_per_1k"]),
        "p50_ms": float(metrics["p50_ms"]),
        "p95_ms": float(metrics["p95_ms"]),
        "assumes_reviewer_always_right": assumes_reviewer_always_right,
    }


def _calibration(name, frame):
    table, ece = calibration(frame)
    bins = [
        {
            "lower": float(interval.left),
            "upper": min(float(interval.right), 1.0),
            "n": int(row["n"]),
            "mean_confidence": float(row["confidence"]),
            "accuracy": float(row["accuracy"]),
        }
        for interval, row in table.iterrows()
    ]
    return {"tier": name, "ece": float(ece), "bins": bins}


def build_report(config, split=SPLIT):
    """The numbers of the Evaluation screen for a config. Raises EvaluationUnavailable when there are none."""
    names = [tier["name"] for tier in config["tiers"]]
    if names != ["baseline", "llm"]:
        raise EvaluationUnavailable("the evaluation covers a configuration with a baseline tier followed by an llm tier")

    path = predictions_path(config["domain"], split)
    if not path.exists():
        raise EvaluationUnavailable(f"no recorded predictions for the domain '{config['domain']}'")
    df = pd.read_csv(path)
    needed = ["text", "true"] + [f"{name}_{column}" for name in names for column in TIER_COLUMNS]
    if df.empty or any(column not in df.columns for column in needed):
        raise EvaluationUnavailable(f"the recorded predictions of the domain '{config['domain']}' are not usable")

    labels = config["labels"]
    t_base, t_llm = (tier["accept_threshold"] for tier in config["tiers"])
    frames = {name: _tier_frame(df, name) for name in names}
    tier_preds = [(name, frames[name]) for name in names]

    # The four setups of the results table in the README, computed by the same functions.
    cascade = simulate_cascade(tier_preds, [t_base, 0.0])
    decided = simulate_cascade(tier_preds, [t_base, t_llm])
    with_person = with_human(decided)
    setups = [
        _setup("Baseline only", "Every example is answered by the baseline.", frames["baseline"], labels),
        _setup("LLM only", "Every example is answered by the LLM.", frames["llm"], labels),
        _setup(
            "Cascade (baseline then LLM)",
            f"The baseline answers when it is at least {t_base:g} sure; otherwise the LLM answers.",
            cascade, labels,
        ),
        _setup(
            "Cascade + human review",
            f"As the cascade, but when the LLM is not at least {t_llm:g} sure either, a person answers. "
            "This assumes the person is always right.",
            with_person, labels, assumes_reviewer_always_right=True,
        ),
    ]

    # How the cascade, with its real thresholds, handled the examples, and how often it was right.
    right = decided["label"] == decided["true"]
    groups = [
        {"kind": "accepted", "tier": name, "count": int(mask.sum()), "correct": int((right & mask).sum())}
        for name in names
        for mask in [(decided["action"] == "accepted") & (decided["tier"] == name)]
    ]
    person = decided["action"] == "human_review"
    groups.append({"kind": "human_review", "tier": None, "count": int(person.sum()), "correct": int((right & person).sum())})

    return {
        "domain": config["domain"],
        "split": split,
        "n": len(df),
        "data_source": config.get("data_source"),
        "tiers": [{"name": tier["name"], "accept_threshold": float(tier["accept_threshold"])} for tier in config["tiers"]],
        "setups": setups,
        "cascade": {"groups": groups, "escalated": int((decided["calls"] > 1).sum())},
        "calibration": [_calibration(name, frames[name]) for name in names],
    }
