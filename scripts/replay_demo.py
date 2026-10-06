"""Fills a database with REAL decisions of the cascade, replayed from saved model answers.

Every text is a real test example, and every tier's answer (label, confidence, cost, latency) was
recorded when the model was evaluated. The cascade itself (`route`) runs on those answers, so the
decisions are what the live service would decide. No model is called and nothing costs money.

    python scripts/replay_demo.py                    # writes demo.db from demo/clinc150_test_predictions.csv
    ROUTEIQ_DB=demo.db uvicorn routeiq.api:app       # then look at it in the dashboard

What is NOT real: the times (spread over the last days) and the decisions of the reviewers. A
reviewer is simulated as always choosing the true label, the same assumption as the "cascade +
human review" row of the README.

It refuses to write into a database that already has requests, unless --add is given.
"""
import argparse
import random
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from routeiq.cascade import route
from routeiq.config import ROOT, load_config
from routeiq.models.base import Prediction
from routeiq.store import Store

DEFAULT_DB = ROOT / "demo.db"
DEFAULT_CONFIG = ROOT / "configs" / "clinc150.yaml"
DEFAULT_PREDICTIONS = ROOT / "demo" / "clinc150_test_predictions.csv"

WAITING = 3                          # the newest requests sent to a person still wait, so the queue is never empty
QUIET_PERIOD = timedelta(hours=1)    # nobody has looked at the last hour's requests yet


class ReplayError(ValueError):
    """The replay cannot be carried out; the message says why and is meant to be shown."""


class Recorded:
    """A tier that answers with what was recorded for one text, and remembers that it was asked."""

    def __init__(self, row, name, called):
        self.row, self.name, self.called = row, name, called

    def classify(self, text, labels):
        self.called.append(self.name)
        return Prediction(
            label=self.row[f"{self.name}_label"],
            confidence=float(self.row[f"{self.name}_confidence"]),
            cost_usd=float(self.row[f"{self.name}_cost_usd"]),
        )


def _set_times(conn, request_id, **columns):
    sets = ", ".join(f"{name} = ?" for name in columns)
    conn.execute(f"UPDATE requests SET {sets} WHERE id = ?", [*columns.values(), request_id])


def _check_columns(df, tiers):
    needed = ["text", "true"] + [f"{t['name']}_{c}" for t in tiers for c in ("label", "confidence", "cost_usd", "latency_ms")]
    missing = [column for column in needed if column not in df.columns]
    if missing:
        raise ReplayError(
            f"the predictions file lacks the columns {', '.join(missing)}. "
            "Make it with `python scripts/export_predictions.py` for the same config."
        )


def replay(db_path, predictions_path=DEFAULT_PREDICTIONS, config_path=DEFAULT_CONFIG,
           days=1, seed=7, now=None, add=False):
    """Writes every recorded example as a request. Returns a summary."""
    if days < 1:
        raise ReplayError("days must be at least 1")
    config = load_config(config_path)
    tiers = config["tiers"]
    predictions_path = Path(predictions_path)
    if not predictions_path.exists():
        raise ReplayError(f"{predictions_path} does not exist. Make it with `python scripts/export_predictions.py`.")
    df = pd.read_csv(predictions_path)
    if df.empty:
        raise ReplayError(f"{predictions_path} has no rows")
    _check_columns(df, tiers)

    store = Store(db_path)
    existing = store.list_requests(limit=1)[1]
    if existing and not add:
        raise ReplayError(f"{db_path} already has {existing} requests. Use another file, or --add to add to it.")

    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    order = rng.sample(range(len(df)), len(df))       # the file is grouped by label; the history should not be
    moments = sorted(now - timedelta(seconds=rng.uniform(0, days * 86400)) for _ in order)
    has_target = config.get("target") is not None

    # First what the cascade decides for every example, in the order of time; then who has looked at it.
    decisions = []
    for moment, i in zip(moments, order):
        row = df.iloc[i]
        called = []
        result = route(row["text"], config["labels"], [(tier, Recorded(row, tier["name"], called)) for tier in tiers])
        # The cascade measured no time (nothing was run), so use the recorded time of the tiers it asked.
        result.latency_ms = float(sum(row[f"{name}_latency_ms"] for name in called))
        decisions.append((moment, row, result))

    to_person = [k for k, (_, _, result) in enumerate(decisions) if result.action == "human_review"]
    waiting = set(to_person[-WAITING:])
    summary = {"requests": len(df), "accepted": {}, "human_review": len(to_person), "resolved": 0, "pending": 0, "correct": 0}

    with closing(sqlite3.connect(str(db_path), isolation_level=None)) as conn:
        for k, (moment, row, result) in enumerate(decisions):
            request_id = store.log(row["text"], result)
            _set_times(conn, request_id, created_at=moment.isoformat())
            summary["correct"] += result.label == row["true"]

            deliver = result.action == "accepted"
            if deliver:
                summary["accepted"][result.tier] = summary["accepted"].get(result.tier, 0) + 1
            elif k not in waiting and moment <= now - QUIET_PERIOD:
                store.resolve(request_id, row["true"])
                _set_times(conn, request_id, resolved_at=(moment + timedelta(minutes=rng.randint(2, 90))).isoformat())
                summary["resolved"] += 1
                deliver = True
            else:
                summary["pending"] += 1
            if deliver and has_target:
                store.mark_delivery(request_id, "sent")
                stamp = (moment + timedelta(seconds=2)).isoformat()
                _set_times(conn, request_id, delivered_at=stamp, delivery_updated_at=stamp)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fill a database with real decisions replayed from saved model answers.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="database file (default: demo.db)")
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--days", type=int, default=1, help="spread the times over this many days (default: 1, so the 24-hour views show everything)")
    parser.add_argument("--seed", type=int, default=7, help="same seed, same order and times (default: 7)")
    parser.add_argument("--add", action="store_true", help="add to a database that already has requests")
    args = parser.parse_args(argv)

    try:
        summary = replay(args.db, args.predictions, args.config, days=args.days, seed=args.seed, add=args.add)
    except ReplayError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Replayed {summary['requests']} recorded examples through the cascade into {args.db}.")
    for tier, count in summary["accepted"].items():
        print(f"  accepted by {tier}: {count}")
    print(f"  sent to a person: {summary['human_review']} ({summary['resolved']} decided, {summary['pending']} waiting)")
    print(f"  the cascade's label was right for {summary['correct']} of {summary['requests']}")
    print("No model was called. The times and the reviewers' decisions are simulated; the rest was recorded.")
    print()
    print("Look at it in the dashboard:")
    print(f"  ROUTEIQ_DB={args.db} uvicorn routeiq.api:app")
    print("  then open http://localhost:8000/dashboard/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
