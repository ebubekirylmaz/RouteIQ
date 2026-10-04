import argparse
import time

import pandas as pd
import numpy as np

from sklearn.metrics import f1_score
from routeiq.config import ROOT, load_config
from routeiq.models.registry import build_tiers


def run_tier(clf, df, labels):
    rows = []
    for text, true in zip(df["text"], df["label"]):
        t0 = time.perf_counter()
        try:
            pred = clf.classify(text, labels)
            row = {"label": pred.label, "confidence": pred.confidence,
                   "cost_usd": pred.cost_usd, "error": None}
        except Exception as e:
            row = {"label": None, "confidence": 0.0, "cost_usd": 0.0, "error": str(e)}
        row["text"] = text
        row["true"] = true
        row["latency_ms"] = (time.perf_counter() - t0) * 1000
        rows.append(row)
    return pd.DataFrame(rows)


def cached_predictions(config, tier_name, clf, split, df, refresh=False):
    path = ROOT / "reports" / f"{config['domain']}_{split}_{tier_name}.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path)
    labels = config["labels"]
    preds = run_tier(clf, df, labels)
    path.parent.mkdir(exist_ok=True)
    preds.to_csv(path, index=False)
    return preds


def compute_metrics(df, labels):
    ok = df["label"] == df["true"]
    return {
        "n": len(df),
        "accuracy": ok.mean(),
        "macro_f1": f1_score(
            df["true"], df["label"].fillna("none"),
            labels=labels, average="macro", zero_division=0,
        ),
        "cost_per_1k": df["cost_usd"].mean() * 1000,
        "p50_ms": np.percentile(df["latency_ms"], 50),
        "p95_ms": np.percentile(df["latency_ms"], 95),
        "errors": int(df["error"].notna().sum()),
    }


def with_human(sim):
    out = sim.copy()
    human = out["action"] == "human_review"
    out.loc[human, "label"] = out.loc[human, "true"]
    return out


def report_rows(tier_preds, labels, t_base, t_llm):
    base = dict(tier_preds)["baseline"]
    llm = dict(tier_preds)["llm"]
    cascade = simulate_cascade(tier_preds, [t_base, 0.0])
    cascade_h = with_human(simulate_cascade(tier_preds, [t_base, t_llm]))
    rows = {
        "Baseline only": compute_metrics(base, labels),
        "LLM only": compute_metrics(llm, labels),
        "Cascade (baseline then LLM)": compute_metrics(cascade, labels),
        "Cascade + human review": compute_metrics(cascade_h, labels),
    }
    return pd.DataFrame(rows).T[["accuracy", "macro_f1", "cost_per_1k", "p50_ms", "p95_ms"]]


def calibration(preds, edges=(0.0, 0.5, 0.7, 0.9, 0.99, 1.0001)):
    d = preds.dropna(subset=["label"]).copy()
    d["correct"] = d["label"] == d["true"]
    d["bin"] = pd.cut(d["confidence"], bins=list(edges), right=False)
    g = d.groupby("bin", observed=True).agg(
        n=("correct", "size"),
        confidence=("confidence", "mean"),
        accuracy=("correct", "mean")
    )
    ece = (g["n"] / g["n"].sum() * (g["accuracy"] - g["confidence"]).abs()).sum()
    return g, ece


def simulate_cascade(tier_preds, thresholds):
    """tier_preds: [(ad, DataFrame), ...] cascade sırasıyla; thresholds: aynı sırada eşikler."""
    n = len(tier_preds[0][1])
    rows = []
    for i in range(n):
        label, used, cost, latency, error, calls = None, None, 0.0, 0.0, None, 0
        for (name, preds), thr in zip(tier_preds, thresholds):
            r = preds.iloc[i]
            calls += 1
            latency += r["latency_ms"]
            if pd.notna(r["error"]):
                error = f"{name}: {r['error']}"
                continue
            label, used = r["label"], name
            cost += r["cost_usd"]
            if r["confidence"] >= thr:
                action = "accepted"
                break
        else:
            action = "human_review"
        rows.append({
            "true": tier_preds[0][1].iloc[i]["true"],
            "label": label, "tier": used, "action": action,
            "cost_usd": cost, "latency_ms": latency, "error": error,
            "calls": calls
        })
    return pd.DataFrame(rows)


def summarize(sim, labels):
    accepted = sim["action"] == "accepted"
    human = ~accepted
    correct = sim["label"] == sim["true"]
    m = compute_metrics(sim, labels)
    return {
        "accuracy_raw": m["accuracy"],
        "auto_accuracy": (correct[accepted].mean()),
        "accuracy_with_human": (correct[accepted].sum() + human.sum()) / len(sim),
        "human_rate": human.mean(),
        "escalation_rate": (sim["calls"] > 1).mean(),
        "cost_per_1k": m["cost_per_1k"],
        "p95_ms": m["p95_ms"],
    }


def sweep(tier_preds, labels, base_grid, llm_grid):
    rows = []
    for tb in base_grid:
        for tl in llm_grid:
            sim = simulate_cascade(tier_preds, [tb, tl])
            row = {"t_base": tb, "t_llm": tl}
            row.update(summarize(sim, labels))
            rows.append(row)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--split", default="val")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    labels = config["labels"]
    df = pd.read_csv(ROOT / "data" / f"{args.split}.csv")

    tiers = build_tiers(config)
    tier_preds = [
        (t["name"], cached_predictions(config, t["name"], clf, args.split, df, args.refresh))
        for t, clf in tiers
    ]
    thresholds = [t["accept_threshold"] for t, _ in tiers]

    results = {name: compute_metrics(preds, labels) for name, preds in tier_preds}
    print(pd.DataFrame(results).T.round(4).to_string())

    for name, preds in tier_preds:
        g, ece = calibration(preds)
        print(f"\n{name} calibration (ECE={ece:.3f})")
        print(g.round(3).to_string())

    print(f"\nThresholds: baseline={thresholds[0]}, llm={thresholds[1]}")
    print(report_rows(tier_preds, labels, thresholds[0], thresholds[1]).round(4).to_string())

    if args.sweep:
        grid = sweep(
            tier_preds, labels,
            base_grid=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
            llm_grid=[0.0, 0.7, 0.9, 0.99],
        )
        print(grid.round(4).to_string(index=False))


if __name__ == "__main__":
    main()