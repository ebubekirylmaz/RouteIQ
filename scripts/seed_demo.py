"""Fills a database with SYNTHETIC requests, so the dashboard has something to show.

Nothing here is real data or a measured result: the texts come from a few templates, and the
outcomes (confidence, cost, latency, who got reviewed, which deliveries failed) are drawn at
random with a fixed seed, so the same command always gives the same history. It writes the
database directly and calls no model.

    python scripts/seed_demo.py                  # writes demo.db in the repository root
    ROUTEIQ_DB=demo.db uvicorn routeiq.api:app   # then look at it in the dashboard

It refuses to write into a database that already has requests, unless --add is given, so it
cannot bury real data under made-up data.
"""
import argparse
import random
import sqlite3
import sys
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from routeiq.cascade import RouteResult
from routeiq.config import ROOT, load_config
from routeiq.store import Store

DEFAULT_DB = ROOT / "demo.db"
CONFIG = ROOT / "configs" / "clinc150.yaml"

# Share of each outcome, in order: cheap tier accepts, expensive tier accepts, sent to a person.
CHEAP, EXPENSIVE, PERSON = 0.52, 0.38, 0.10
DEGRADED_SHARE = 0.04
DELIVERY_FAILS = 0.06
DECIDED_SHARE = 0.75        # of the requests sent to a person that are old enough, the share already decided
QUIET_PERIOD = timedelta(hours=1)   # nobody has looked at the last hour's requests yet
REVIEWER_KEEPS = 0.7        # how often a reviewer keeps the model's suggestion

SYNTHETIC_NOTE = "synthetic demo data"

TEMPLATES = {
    "report_lost_card": [
        "I can't find my debit card anywhere",
        "I think I left my card at the {place}",
        "my wallet is gone and my card was inside",
        "I lost my credit card on the way to {place}",
        "please help, I have no idea where my card is",
        "my card went missing after I left the {place}",
    ],
    "damaged_card": [
        "the chip on my card is scratched and will not read",
        "my card snapped in half in my wallet",
        "the magnetic stripe on my card is worn out",
        "my debit card got bent and the terminal rejects it",
        "I washed my jeans with the card inside and it is damaged",
        "the card is cracked at the corner, can I get a new one",
    ],
    "card_declined": [
        "my card got declined at the {place}",
        "the payment of ${amount} was refused even though I have money",
        "the terminal says my card is not accepted",
        "why was my card rejected at the {place} today",
        "my card does not work for online payments anymore",
        "the transaction at the {place} failed with my card",
    ],
    "report_fraud": [
        "there is a charge of ${amount} I did not make",
        "someone used my card at the {place} and it was not me",
        "I see a suspicious payment on my account",
        "I did not authorize the ${amount} transaction from yesterday",
        "my statement has purchases I do not recognize",
        "I think my card details were stolen, there are strange charges",
    ],
    "freeze_account": [
        "please block my account until I sort this out",
        "I want my card frozen right now",
        "can you lock my account temporarily",
        "freeze everything on my profile please",
        "suspend my account, I will tell you when to reopen it",
        "I need to put a hold on all my cards",
    ],
    "out_of_scope": [
        "what is the weather like in Berlin",
        "can you recommend a good Italian restaurant",
        "how tall is the Eiffel tower",
        "tell me a joke about cats",
        "who won the football game last night",
        "what time does the sun set today",
    ],
}
PLACES = ["supermarket", "gas station", "airport", "pharmacy", "train station", "bookshop", "cinema"]


class DemoDataError(ValueError):
    """The request cannot be carried out; the message says why and is meant to be shown."""


def _text(rng, label):
    template = rng.choice(TEMPLATES[label])
    return template.format(place=rng.choice(PLACES), amount=rng.choice([19, 42, 87, 120, 349, 560]))


def _outcome(rng, label, labels, cheap, expensive):
    """One routed request: what the cascade would have answered, as a RouteResult."""
    other = rng.choice([name for name in labels if name != label])
    kind = rng.random()
    failed = rng.random() < DEGRADED_SHARE
    if kind < CHEAP:
        return RouteResult(label, round(rng.uniform(0.72, 0.99), 4), cheap, "accepted", 0.0,
                           round(rng.uniform(1, 30), 1), None)
    if kind < CHEAP + EXPENSIVE:
        # When the cheap tier failed, the expensive one still answered: accepted, but degraded.
        error = f"tier {cheap} failed" if failed else None
        return RouteResult(label, round(rng.uniform(0.9, 0.995), 4), expensive, "accepted",
                           round(rng.uniform(0.00001, 0.00003), 6), round(rng.uniform(450, 1800), 1), error)
    if failed:
        # The expensive tier failed, so there is no suggestion and the request goes to a person.
        return RouteResult(None, 0.0, None, "human_review", 0.0, round(rng.uniform(900, 4000), 1),
                           f"tier {expensive} failed")
    return RouteResult(rng.choice([label, other]), round(rng.uniform(0.55, 0.89), 4), expensive,
                       "human_review", round(rng.uniform(0.00001, 0.00003), 6),
                       round(rng.uniform(450, 1800), 1), None)


def _set_times(conn, request_id, **columns):
    sets = ", ".join(f"{name} = ?" for name in columns)
    conn.execute(f"UPDATE requests SET {sets} WHERE id = ?", [*columns.values(), request_id])


def seed(db_path, count=150, days=3, seed=7, now=None, add=False, config_path=CONFIG):
    """Writes `count` synthetic requests spread over the last `days` days. Returns a summary."""
    if count < 1 or days < 1:
        raise DemoDataError("count and days must be at least 1")

    config = load_config(config_path)
    labels = config["labels"]
    tiers = [tier["name"] for tier in config["tiers"]]
    missing = [name for name in labels if name not in TEMPLATES]
    if len(tiers) < 2 or missing:
        raise DemoDataError(
            "this script has example texts for the clinc150 config only"
            + (f" (no texts for: {', '.join(missing)})" if missing else " (it needs two tiers)")
        )
    cheap, expensive = tiers[0], tiers[1]

    store = Store(db_path)
    existing = store.list_requests(limit=1)[1]
    if existing and not add:
        raise DemoDataError(
            f"{db_path} already has {existing} requests. Use another file, or --add to add to it."
        )

    rng = random.Random(seed)
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    moments = sorted(start + timedelta(seconds=rng.uniform(0, days * 86400)) for _ in range(count))

    rows = []
    for moment in moments:
        label = rng.choice(labels)
        rows.append((moment, label, _text(rng, label), _outcome(rng, label, labels, cheap, expensive)))

    to_person = [i for i, row in enumerate(rows) if row[3].action == "human_review"]
    # People get to the requests within hours, so decisions are spread over the whole period
    # instead of piling up at its start.
    decided = {i for i in to_person if rows[i][0] <= now - QUIET_PERIOD and rng.random() < DECIDED_SHARE}

    summary = {"requests": count, "accepted": 0, "human_review": len(to_person), "resolved": len(decided),
               "pending": len(to_person) - len(decided), "delivery_failed": 0, "delivery_pending": 0}
    # The delivery that never finished must be old enough (5 minutes) to count as stuck.
    old_enough = now - timedelta(minutes=10)
    stuck = max((i for i, row in enumerate(rows) if row[3].action == "accepted" and row[0] <= old_enough), default=None)

    # Autocommit: the store writes through its own connections, and an open transaction here
    # would lock them out.
    with closing(sqlite3.connect(str(db_path), isolation_level=None)) as conn:
        for index, (moment, true_label, text, result) in enumerate(rows):
            request_id = store.log(text, result)
            _set_times(conn, request_id, created_at=moment.isoformat())
            deliver = result.action == "accepted"

            if result.action == "human_review" and index in decided:
                suggestion = result.label
                final = suggestion if suggestion and rng.random() < REVIEWER_KEEPS else true_label
                store.resolve(request_id, final)
                _set_times(conn, request_id, resolved_at=(moment + timedelta(minutes=rng.randint(2, 90))).isoformat())
                deliver = True
            summary["accepted"] += result.action == "accepted"

            if not deliver:
                continue
            if index == stuck:
                store.mark_delivery(request_id, "pending")
                _set_times(conn, request_id, delivery_updated_at=(moment + timedelta(seconds=2)).isoformat())
                summary["delivery_pending"] += 1
            elif rng.random() < DELIVERY_FAILS:
                store.mark_delivery(request_id, "failed", "the target answered 503 Service Unavailable")
                _set_times(conn, request_id, delivery_updated_at=(moment + timedelta(seconds=2)).isoformat())
                summary["delivery_failed"] += 1
            else:
                store.mark_delivery(request_id, "sent")
                stamp = (moment + timedelta(seconds=2)).isoformat()
                _set_times(conn, request_id, delivered_at=stamp, delivery_updated_at=stamp)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Fill a database with synthetic requests for the dashboard.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="database file (default: demo.db)")
    parser.add_argument("--count", type=int, default=150, help="number of requests (default: 150)")
    parser.add_argument("--days", type=int, default=3, help="spread over this many days (default: 3)")
    parser.add_argument("--seed", type=int, default=7, help="same seed, same data (default: 7)")
    parser.add_argument("--add", action="store_true", help="add to a database that already has requests")
    args = parser.parse_args(argv)

    try:
        summary = seed(args.db, count=args.count, days=args.days, seed=args.seed, add=args.add)
    except DemoDataError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"Wrote {summary['requests']} requests ({SYNTHETIC_NOTE}) to {args.db}:")
    print(f"  accepted by the cascade: {summary['accepted']}")
    print(f"  sent to a person: {summary['human_review']} ({summary['resolved']} decided, {summary['pending']} waiting)")
    print(f"  deliveries: {summary['delivery_failed']} failed, {summary['delivery_pending']} stuck in pending")
    print()
    print("Look at it in the dashboard:")
    print(f"  ROUTEIQ_DB={args.db} uvicorn routeiq.api:app")
    print("  then open http://localhost:8000/dashboard/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
