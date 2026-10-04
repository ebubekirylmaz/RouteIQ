import pytest

from routeiq.cascade import route
from routeiq.models.base import Prediction


class Fake:
    def __init__(self, label, confidence, cost=0.0):
        self.label = label
        self.confidence = confidence
        self.cost = cost
        self.calls = 0

    def classify(self, text, labels):
        self.calls += 1
        return Prediction(self.label, self.confidence, self.cost)


class Boom:
    def __init__(self):
        self.calls = 0

    def classify(self, text, labels):
        self.calls += 1
        raise RuntimeError("boom")


LABELS = ["a", "b"]


def make_tiers(baseline, llm):
    return [
        ({"name": "baseline", "accept_threshold": 0.5}, baseline),
        ({"name": "llm", "accept_threshold": 0.7}, llm),
    ]


def test_baseline_confident_skips_llm():
    baseline = Fake("a", 0.9)
    llm = Fake("b", 0.95, cost=0.001)
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.action == "accepted"
    assert result.tier == "baseline"
    assert result.label == "a"
    assert llm.calls == 0
    assert result.cost_usd == 0.0
    assert result.error is None


def test_baseline_unsure_escalates_to_llm():
    baseline = Fake("a", 0.3)
    llm = Fake("b", 0.9, cost=0.001)
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.action == "accepted"
    assert result.tier == "llm"
    assert result.label == "b"
    assert llm.calls == 1
    assert result.cost_usd == pytest.approx(0.001)

def test_both_unsure_goes_to_human_review():
    baseline = Fake("a", 0.3)
    llm = Fake("b", 0.4, cost=0.001)
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.action == "human_review"
    assert result.tier == "llm"
    assert result.label == "b"
    assert result.confidence == 0.4
    assert llm.calls == 1
    assert result.cost_usd == pytest.approx(0.001)


def test_confidence_equal_to_threshold_is_accepted():
    baseline = Fake("a", 0.5)
    llm = Fake("b", 0.95, cost=0.001)
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.action == "accepted"
    assert result.tier == "baseline"
    assert llm.calls == 0


def test_confidence_just_below_threshold_escalates():
    baseline = Fake("a", 0.49)
    llm = Fake("b", 0.95, cost=0.001)
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.tier == "llm"
    assert llm.calls == 1


def test_cost_is_summed_across_tiers():
    baseline = Fake("a", 0.3, cost=0.002)
    llm = Fake("b", 0.4, cost=0.001)
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.cost_usd == pytest.approx(0.003)


def test_empty_tiers_raises():
    with pytest.raises(ValueError):
        route("x", LABELS, [])


def test_llm_failure_falls_back_to_human_review_with_baseline_suggestion():
    baseline = Fake("a", 0.3)
    llm = Boom()
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.action == "human_review"
    assert result.label == "a"
    assert result.tier == "baseline"
    assert "llm" in result.error
    assert llm.calls == 1


def test_baseline_failure_still_accepted_by_llm():
    baseline = Boom()
    llm = Fake("b", 0.95, cost=0.001)
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.action == "accepted"
    assert result.tier == "llm"
    assert result.label == "b"
    assert "baseline" in result.error
    assert result.cost_usd == pytest.approx(0.001)


def test_all_tiers_failing_goes_to_human_review_without_suggestion():
    result = route("x", LABELS, make_tiers(Boom(), Boom()))
    assert result.action == "human_review"
    assert result.label is None
    assert result.tier is None
    assert result.confidence == 0.0
    assert result.error is not None
    assert result.cost_usd == 0.0


def test_llm_failure_falls_back_to_human_review_with_baseline_suggestion():
    baseline = Fake("a", 0.3)
    llm = Boom()
    result = route("x", LABELS, make_tiers(baseline, llm))
    assert result.action == "human_review"
    assert result.label == "a"
    assert result.tier == "baseline"
    assert "llm" in result.error
    assert llm.calls == 1