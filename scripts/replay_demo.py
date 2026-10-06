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
import sys
from pathlib import Path

from routeiq.config import ROOT, load_config
from routeiq.replay import (  # noqa: F401  (re-exported: the tests and other scripts use these names)
    QUIET_PERIOD, WAITING, ReplayError, Recorded, _check_columns, _set_times,
)
from routeiq.replay import replay as _replay

DEFAULT_DB = ROOT / "demo.db"
DEFAULT_CONFIG = ROOT / "configs" / "clinc150.yaml"
DEFAULT_PREDICTIONS = ROOT / "demo" / "clinc150_test_predictions.csv"


def replay(db_path, predictions_path=DEFAULT_PREDICTIONS, config_path=DEFAULT_CONFIG, **options):
    """Writes every recorded example as a request. Takes the path of the config. Returns a summary."""
    return _replay(db_path, predictions_path, load_config(config_path), **options)


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
