"""The results table in the README comes from `simulate_cascade` in evaluate.py, which replays
saved predictions. The service decides with `route` in cascade.py. They are two separate
implementations of the same rules, so these tests run both on the same scripted answers and
require the same decisions."""
import itertools
from collections import Counter

import pandas as pd
import pytest

from routeiq import evaluate
from routeiq.cascade import route
from routeiq.evaluate import run_tier, simulate_cascade, summarize
from routeiq.models.base import Prediction

LABELS = ["a", "b", "c"]
BASE_GRID = [0.3, 0.5, 0.7, 0.9]      # the grids of the threshold sweep in evaluate.py
LLM_GRID = [0.0, 0.7, 0.9, 0.99]
LLM_COST = 0.00002


class Scripted:
    """Answers every text from a table: a Prediction, or an exception to raise."""

    def __init__(self, answers):
        self.answers = answers
        self.calls = Counter()

    def classify(self, text, labels):
        self.calls[text] += 1
        answer = self.answers[text]
        if isinstance(answer, Exception):
            raise answer
        return answer


def around(threshold):
    """Confidences below, exactly at and above a threshold, then a failing tier (None)."""
    return [max(0.0, threshold - 0.1), threshold, min(1.0, threshold + 0.1), None]


def scenario(base_threshold, llm_threshold):
    """Every combination of what the two tiers can do, with the borders of the thresholds included.

    The two tiers answer with different labels and costs, so the decision shows which of them
    was used and what it cost."""
    texts, true, base, llm = [], [], {}, {}
    for i, (b, l) in enumerate(itertools.product(around(base_threshold), around(llm_threshold))):
        text = f"text {i}"
        texts.append(text)
        true.append("c" if i % 2 else "a")
        base[text] = RuntimeError("baseline down") if b is None else Prediction("a", b, 0.0)
        llm[text] = RuntimeError("llm down") if l is None else Prediction("b", l, LLM_COST)
    return pd.DataFrame({"text": texts, "label": true}), base, llm


def both(base_threshold, llm_threshold):
    """Runs the same scripted answers through the live cascade and through the simulation."""
    df, base_answers, llm_answers = scenario(base_threshold, llm_threshold)

    live_base, live_llm = Scripted(base_answers), Scripted(llm_answers)
    tiers = [
        ({"name": "baseline", "accept_threshold": base_threshold}, live_base),
        ({"name": "llm", "accept_threshold": llm_threshold}, live_llm),
    ]
    live = [route(text, LABELS, tiers) for text in df["text"]]

    # Fresh classifiers for the recorded predictions, so the call counts stay apart.
    tier_preds = [
        ("baseline", run_tier(Scripted(base_answers), df, LABELS)),
        ("llm", run_tier(Scripted(llm_answers), df, LABELS)),
    ]
    sim = simulate_cascade(tier_preds, [base_threshold, llm_threshold])
    calls = [live_base.calls[t] + live_llm.calls[t] for t in df["text"]]
    return df, live, sim, calls


def none_if_missing(value):
    return None if pd.isna(value) else value


@pytest.mark.parametrize("llm_threshold", LLM_GRID)
@pytest.mark.parametrize("base_threshold", BASE_GRID)
def test_same_decision_for_every_combination_around_the_thresholds(base_threshold, llm_threshold):
    df, live, sim, calls = both(base_threshold, llm_threshold)

    assert len(sim) == len(live) == 16
    for i, result in enumerate(live):
        row = sim.iloc[i]
        where = f"text {i} with thresholds {base_threshold}/{llm_threshold}"
        assert none_if_missing(row["label"]) == result.label, where
        assert none_if_missing(row["tier"]) == result.tier, where
        assert row["action"] == result.action, where
        assert row["cost_usd"] == pytest.approx(result.cost_usd), where
        assert none_if_missing(row["error"]) == result.error, where
        assert row["calls"] == calls[i], where
        assert row["true"] == df["label"].iloc[i], where


@pytest.mark.parametrize("llm_threshold", LLM_GRID)
@pytest.mark.parametrize("base_threshold", BASE_GRID)
def test_same_totals_for_the_table_of_results(base_threshold, llm_threshold):
    _, live, sim, _ = both(base_threshold, llm_threshold)
    summary = summarize(sim, LABELS)

    assert summary["human_rate"] == pytest.approx(sum(r.action == "human_review" for r in live) / len(live))
    assert summary["cost_per_1k"] == pytest.approx(sum(r.cost_usd for r in live) / len(live) * 1000)


class TestTheRulesThatMatter:
    """The same few rules, spelled out, so a failure says which one broke."""

    def decide(self, base, llm, base_threshold=0.7, llm_threshold=0.9):
        text = "x"
        df = pd.DataFrame({"text": [text], "label": ["a"]})
        answers = [{text: base}, {text: llm}]
        tiers = [
            ({"name": "baseline", "accept_threshold": base_threshold}, Scripted(answers[0])),
            ({"name": "llm", "accept_threshold": llm_threshold}, Scripted(answers[1])),
        ]
        live = route(text, LABELS, tiers)
        sim = simulate_cascade(
            [("baseline", run_tier(Scripted(answers[0]), df, LABELS)), ("llm", run_tier(Scripted(answers[1]), df, LABELS))],
            [base_threshold, llm_threshold],
        ).iloc[0]
        return live, sim

    def test_a_confidence_exactly_at_the_threshold_is_accepted(self):
        live, sim = self.decide(Prediction("a", 0.7, 0.0), Prediction("b", 0.5, LLM_COST))
        assert (live.action, live.tier) == ("accepted", "baseline")
        assert (sim["action"], sim["tier"]) == ("accepted", "baseline")

    def test_just_below_the_threshold_goes_on_to_the_next_tier(self):
        live, sim = self.decide(Prediction("a", 0.6999, 0.0), Prediction("b", 0.95, LLM_COST))
        assert (live.action, live.tier) == ("accepted", "llm")
        assert (sim["action"], sim["tier"]) == ("accepted", "llm")
        assert live.cost_usd == pytest.approx(sim["cost_usd"]) == pytest.approx(LLM_COST)

    def test_two_unsure_tiers_end_with_a_person_who_gets_the_last_suggestion(self):
        live, sim = self.decide(Prediction("a", 0.4, 0.0), Prediction("b", 0.8, LLM_COST))
        assert (live.action, live.label, live.tier) == ("human_review", "b", "llm")
        assert (sim["action"], sim["label"], sim["tier"]) == ("human_review", "b", "llm")

    def test_a_failing_first_tier_does_not_stop_the_second(self):
        live, sim = self.decide(RuntimeError("down"), Prediction("b", 0.95, LLM_COST))
        assert (live.action, live.tier, live.error) == ("accepted", "llm", "baseline: down")
        assert (sim["action"], sim["tier"], sim["error"]) == ("accepted", "llm", "baseline: down")
        assert sim["calls"] == 2

    def test_a_failing_second_tier_keeps_what_the_first_one_said(self):
        live, sim = self.decide(Prediction("a", 0.4, 0.0), RuntimeError("down"))
        assert (live.action, live.label, live.tier, live.error) == ("human_review", "a", "baseline", "llm: down")
        assert (sim["action"], sim["label"], sim["tier"], sim["error"]) == ("human_review", "a", "baseline", "llm: down")

    def test_when_everything_fails_a_person_gets_it_without_a_suggestion(self):
        live, sim = self.decide(RuntimeError("one"), RuntimeError("two"))
        assert (live.action, live.label, live.tier, live.error) == ("human_review", None, None, "llm: two")
        assert (sim["action"], none_if_missing(sim["label"]), none_if_missing(sim["tier"]), sim["error"]) == (
            "human_review", None, None, "llm: two",
        )
        assert live.cost_usd == sim["cost_usd"] == 0.0

    def test_a_threshold_of_zero_makes_the_last_tier_accept_whatever_it_says(self):
        live, sim = self.decide(Prediction("a", 0.1, 0.0), Prediction("b", 0.01, LLM_COST), llm_threshold=0.0)
        assert live.action == sim["action"] == "accepted"


def test_the_saved_predictions_give_the_same_decisions_after_a_trip_through_the_csv_file(tmp_path, monkeypatch):
    """The evaluation reads its tier predictions back from CSV files. The values at the border of a
    threshold and the failed answers must survive that."""
    monkeypatch.setattr(evaluate, "ROOT", tmp_path)
    df, base_answers, llm_answers = scenario(0.7, 0.9)
    config = {"domain": "test", "labels": LABELS}

    def saved(name, answers):
        evaluate.cached_predictions(config, name, Scripted(answers), "val", df)       # runs the tier, writes the file
        return evaluate.cached_predictions(config, name, Scripted({}), "val", df)     # reads the file; calls nothing

    from_files = simulate_cascade([("baseline", saved("baseline", base_answers)), ("llm", saved("llm", llm_answers))], [0.7, 0.9])
    in_memory = simulate_cascade(
        [("baseline", run_tier(Scripted(base_answers), df, LABELS)), ("llm", run_tier(Scripted(llm_answers), df, LABELS))],
        [0.7, 0.9],
    )

    for column in ("action", "tier", "label", "error", "calls", "true"):
        assert [none_if_missing(v) for v in from_files[column]] == [none_if_missing(v) for v in in_memory[column]], column
    assert list(from_files["cost_usd"]) == pytest.approx(list(in_memory["cost_usd"]))
