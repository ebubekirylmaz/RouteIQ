import importlib.util
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
import yaml

from routeiq.config import ROOT, load_config
from routeiq.store import Store

spec = importlib.util.spec_from_file_location("replay_demo", ROOT / "scripts" / "replay_demo.py")
replay_demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay_demo)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
CONFIG = ROOT / "configs" / "clinc150.yaml"
LLM_COST = 0.00002
BASE_MS, LLM_MS = 2.0, 900.0

# (kind, baseline confidence, llm confidence): what a text needs to be decided in that way (0.7 / 0.9)
KINDS = {
    "base": (0.95, 0.99),          # the baseline is sure; the LLM must not even be asked
    "base_edge": (0.7, 0.99),      # exactly at the baseline's threshold: accepted
    "llm": (0.4, 0.95),            # the baseline is unsure, the LLM is sure
    "llm_edge": (0.4, 0.9),        # exactly at the LLM's threshold: accepted
    "person": (0.4, 0.6),          # nobody is sure
}


def make_predictions(per_kind=6):
    rows = []
    for kind, (base, llm) in KINDS.items():
        for n in range(per_kind):
            rows.append({
                "text": f"{kind} text {n}", "true": "card_declined", "kind": kind,
                "baseline_label": "report_fraud", "baseline_confidence": base,
                "baseline_cost_usd": 0.0, "baseline_latency_ms": BASE_MS,
                # Where nobody is sure the model is also wrong, so a reviewer's label differs from its suggestion.
                "llm_label": "freeze_account" if kind == "person" else "card_declined", "llm_confidence": llm,
                "llm_cost_usd": LLM_COST, "llm_latency_ms": LLM_MS,
            })
    return pd.DataFrame(rows)


def write(tmp_path, df=None, name="predictions.csv"):
    path = tmp_path / name
    (make_predictions() if df is None else df).drop(columns=["kind"], errors="ignore").to_csv(path, index=False)
    return path


def run(tmp_path, df=None, **kwargs):
    path = write(tmp_path, df)
    db = tmp_path / kwargs.pop("db_name", "demo.db")
    summary = replay_demo.replay(db, path, CONFIG, now=NOW, **kwargs)
    store = Store(db)
    rows = store.list_requests(limit=1000, newest_first=False)[0]
    return store, rows, summary


def kind_of(row):
    return row["text"].split(" text ")[0]


# --- what the cascade decides ----------------------------------------------------------------

def test_every_example_becomes_a_request(tmp_path):
    store, rows, summary = run(tmp_path)
    assert len(rows) == summary["requests"] == 30
    assert {kind_of(r) for r in rows} == set(KINDS)


def test_the_cascade_decides_with_its_own_thresholds(tmp_path):
    _, rows, _ = run(tmp_path)
    for row in rows:
        kind = kind_of(row)
        if kind in ("base", "base_edge"):
            assert (row["action"], row["tier"], row["label"]) == ("accepted", "baseline", "report_fraud"), kind
        elif kind in ("llm", "llm_edge"):
            assert (row["action"], row["tier"], row["label"]) == ("accepted", "llm", "card_declined"), kind
        else:
            assert (row["action"], row["tier"], row["label"]) == ("human_review", "llm", "freeze_account"), kind


def test_cost_latency_and_confidence_are_the_recorded_ones_of_the_tiers_that_were_asked(tmp_path):
    _, rows, _ = run(tmp_path)
    for row in rows:
        kind = kind_of(row)
        if kind in ("base", "base_edge"):
            assert row["cost_usd"] == 0.0
            assert row["latency_ms"] == pytest.approx(BASE_MS)
            assert row["confidence"] == KINDS[kind][0]
        else:
            assert row["cost_usd"] == pytest.approx(LLM_COST)
            assert row["latency_ms"] == pytest.approx(BASE_MS + LLM_MS)
            assert row["confidence"] == KINDS[kind][1]


def test_another_threshold_in_the_config_gives_other_decisions(tmp_path):
    config = yaml.safe_load(CONFIG.read_text())
    config["tiers"][0]["accept_threshold"] = 0.3        # now the baseline is sure enough about everything
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(config))
    db = tmp_path / "demo.db"
    replay_demo.replay(db, write(tmp_path), path, now=NOW)
    rows = Store(db).list_requests(limit=1000)[0]
    assert {r["tier"] for r in rows} == {"baseline"}
    assert {r["action"] for r in rows} == {"accepted"}


def test_the_stats_of_the_store_agree(tmp_path):
    store, _, summary = run(tmp_path)
    stats = store.stats()
    assert stats["accepted_by_tier"] == summary["accepted"] == {"baseline": 12, "llm": 12}
    assert stats["human_review"] == summary["human_review"] == 6


# --- time and order ---------------------------------------------------------------------------------

def test_the_history_is_not_in_the_order_of_the_file(tmp_path):
    _, rows, _ = run(tmp_path)
    in_file = [r["text"] for r in make_predictions().to_dict("records")]
    assert [r["text"] for r in rows] != in_file
    assert sorted(r["text"] for r in rows) == sorted(in_file)


def test_times_rise_with_the_ids_and_stay_inside_the_period(tmp_path):
    _, rows, _ = run(tmp_path, days=2)
    times = [datetime.fromisoformat(r["created_at"]) for r in rows]
    assert times == sorted(times)
    assert NOW - timedelta(days=2) <= times[0] and times[-1] <= NOW


def test_the_same_seed_gives_the_same_history_and_another_seed_another_order(tmp_path):
    _, first, _ = run(tmp_path, db_name="a.db", seed=1)
    _, same, _ = run(tmp_path, db_name="b.db", seed=1)
    _, other, _ = run(tmp_path, db_name="c.db", seed=2)
    assert first == same
    assert [r["text"] for r in first] != [r["text"] for r in other]


# --- the reviewers -----------------------------------------------------------------------------------

def test_the_newest_requests_for_a_person_still_wait(tmp_path):
    store, rows, summary = run(tmp_path)
    person = [r for r in rows if r["action"] == "human_review"]
    assert [r["review_status"] for r in person[-replay_demo.WAITING:]] == ["pending"] * replay_demo.WAITING
    assert summary["pending"] == store.pending_count() >= replay_demo.WAITING


def test_the_older_ones_are_decided_with_the_true_label_not_the_models_suggestion(tmp_path):
    _, rows, summary = run(tmp_path)
    decided = [r for r in rows if r["review_status"] == "resolved"]
    assert len(decided) == summary["resolved"] > 0
    for row in decided:
        assert row["label"] == "freeze_account"          # what the model suggested
        assert row["final_label"] == "card_declined"     # what the simulated reviewer chose: the true label
        assert datetime.fromisoformat(row["resolved_at"]) > datetime.fromisoformat(row["created_at"])


def test_nothing_from_the_last_hour_has_been_decided(tmp_path):
    _, rows, _ = run(tmp_path)
    for row in rows:
        if row["review_status"] == "resolved":
            assert datetime.fromisoformat(row["created_at"]) <= NOW - replay_demo.QUIET_PERIOD


def test_accepted_requests_have_no_review(tmp_path):
    _, rows, _ = run(tmp_path)
    assert all(r["review_status"] is None for r in rows if r["action"] == "accepted")


# --- deliveries ---------------------------------------------------------------------------------------

def test_what_was_decided_is_delivered_and_what_waits_is_not(tmp_path):
    _, rows, _ = run(tmp_path)
    for row in rows:
        waiting = row["review_status"] == "pending"
        assert row["delivery_status"] == (None if waiting else "sent")
        assert (row["delivered_at"] is None) == waiting


def test_without_a_target_nothing_is_delivered(tmp_path):
    config = yaml.safe_load(CONFIG.read_text())
    del config["target"]
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(config))
    db = tmp_path / "demo.db"
    replay_demo.replay(db, write(tmp_path), path, now=NOW)
    assert all(r["delivery_status"] is None for r in Store(db).list_requests(limit=1000)[0])


# --- refusing and failing ------------------------------------------------------------------------------

def test_a_database_with_requests_is_refused_and_left_alone(tmp_path):
    store, before, _ = run(tmp_path)
    with pytest.raises(replay_demo.ReplayError, match="already has 30 requests"):
        replay_demo.replay(tmp_path / "demo.db", write(tmp_path), CONFIG, now=NOW)
    assert store.list_requests(limit=1000, newest_first=False)[0] == before


def test_add_adds_to_the_requests_that_are_there(tmp_path):
    store, _, _ = run(tmp_path)
    replay_demo.replay(tmp_path / "demo.db", write(tmp_path), CONFIG, now=NOW, add=True, seed=9)
    assert store.list_requests(limit=1)[1] == 60


def test_a_missing_predictions_file_says_how_to_make_it(tmp_path):
    with pytest.raises(replay_demo.ReplayError, match="export_predictions.py"):
        replay_demo.replay(tmp_path / "x.db", tmp_path / "nope.csv", CONFIG, now=NOW)


def test_missing_columns_are_named(tmp_path):
    df = make_predictions().drop(columns=["llm_confidence", "baseline_latency_ms"])
    with pytest.raises(replay_demo.ReplayError) as info:
        replay_demo.replay(tmp_path / "x.db", write(tmp_path, df), CONFIG, now=NOW)
    assert "llm_confidence" in str(info.value) and "baseline_latency_ms" in str(info.value)
    assert not (tmp_path / "x.db").exists()


def test_an_empty_file_and_zero_days_are_refused(tmp_path):
    with pytest.raises(replay_demo.ReplayError, match="no rows"):
        replay_demo.replay(tmp_path / "x.db", write(tmp_path, make_predictions().iloc[:0]), CONFIG, now=NOW)
    with pytest.raises(replay_demo.ReplayError, match="days"):
        replay_demo.replay(tmp_path / "x.db", write(tmp_path), CONFIG, now=NOW, days=0)


def test_the_command_says_what_is_real_and_what_is_not(tmp_path, capsys):
    path = write(tmp_path)
    db = tmp_path / "cli.db"
    assert replay_demo.main(["--db", str(db), "--predictions", str(path), "--config", str(CONFIG)]) == 0
    out = capsys.readouterr().out
    assert "No model was called" in out and "simulated" in out and f"ROUTEIQ_DB={db}" in out
    assert Store(db).list_requests(limit=1)[1] == 30


def test_the_command_fails_with_a_message_on_a_used_database(tmp_path, capsys):
    path = write(tmp_path)
    db = tmp_path / "cli.db"
    args = ["--db", str(db), "--predictions", str(path), "--config", str(CONFIG)]
    replay_demo.main(args)
    capsys.readouterr()
    assert replay_demo.main(args) == 1
    assert "already has 30 requests" in capsys.readouterr().err


# --- the committed file and the numbers of the README --------------------------------------------------

def test_the_committed_predictions_replay_into_the_numbers_of_the_readme(tmp_path):
    """README: 139 requests accepted by the baseline, 161 sent on to the LLM, 6 of those to a person,
    accuracy 0.983 and $0.0064 per 1,000 requests for the cascade."""
    db = tmp_path / "demo.db"
    summary = replay_demo.replay(db, replay_demo.DEFAULT_PREDICTIONS, CONFIG, now=NOW)
    store = Store(db)
    stats = store.stats()

    assert summary["requests"] == 300
    assert stats["accepted_by_tier"] == {"baseline": 139, "llm": 155}
    assert stats["human_review"] == 6
    assert round(summary["correct"] / 300, 3) == 0.983
    assert round(stats["cost_usd"] / 300 * 1000, 4) == 0.0064


def test_the_committed_predictions_match_the_config():
    config = load_config(CONFIG)
    df = pd.read_csv(replay_demo.DEFAULT_PREDICTIONS)
    replay_demo._check_columns(df, config["tiers"])
    assert len(df) == 300 and not df["text"].duplicated().any()
    assert set(df["true"]) <= set(config["labels"])
    for tier in config["tiers"]:
        assert set(df[f"{tier['name']}_label"]) <= set(config["labels"])
