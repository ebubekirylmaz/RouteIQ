import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fakes import Fake
from routeiq import evaluation
from routeiq.api import create_app
from routeiq.config import ROOT, load_config
from routeiq.evaluate import report_rows, simulate_cascade
from routeiq.evaluation import EvaluationUnavailable, build_report, wilson_interval

LLM_COST = 0.00002
BASE_MS, LLM_MS = 2.0, 1000.0


def config_for(domain="mini", **extra):
    config = {
        "domain": domain,
        "labels": ["a", "b"],
        "tiers": [
            {"name": "baseline", "model": "sklearn_tfidf_logreg", "accept_threshold": 0.7},
            {"name": "llm", "model": "openrouter", "model_id": "v/m", "price_in_per_m": 0.1,
             "price_out_per_m": 0.3, "accept_threshold": 0.9},
        ],
    }
    config.update(extra)
    return config


# Ten examples whose true label is always "a". What each tier says (label, confidence):
#   1-4  baseline right and sure                       -> accepted by the baseline, correct
#   5    baseline wrong but sure                       -> accepted by the baseline, wrong
#   6-7  baseline unsure, llm right and sure           -> accepted by the llm, correct
#   8    baseline unsure, llm wrong and sure           -> accepted by the llm, wrong
#   9    baseline unsure, llm right but unsure         -> sent to a person, suggestion right
#   10   baseline unsure, llm wrong and unsure         -> sent to a person, suggestion wrong
ROWS = (
    [("a", 0.95, "a", 0.99)] * 4
    + [("b", 0.8, "a", 0.99)]
    + [("b", 0.4, "a", 0.95)] * 2
    + [("b", 0.4, "b", 0.95)]
    + [("b", 0.4, "a", 0.6), ("b", 0.4, "b", 0.6)]
)


def crafted():
    return pd.DataFrame([
        {
            "text": f"text {i}", "true": "a",
            "baseline_label": bl, "baseline_confidence": bc, "baseline_cost_usd": 0.0, "baseline_latency_ms": BASE_MS,
            "llm_label": ll, "llm_confidence": lc, "llm_cost_usd": LLM_COST, "llm_latency_ms": LLM_MS,
        }
        for i, (bl, bc, ll, lc) in enumerate(ROWS)
    ])


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, "RECORDED_DIR", tmp_path)

    def put(df=None, domain="mini"):
        (crafted() if df is None else df).to_csv(tmp_path / f"{domain}_test_predictions.csv", index=False)

    put()
    return put


def setups(report):
    return {s["name"]: s for s in report["setups"]}


# --- the interval ----------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "correct, n, low, high",
    [
        (8, 10, 0.4902, 0.9433),
        (0, 10, 0.0, 0.2775),
        (10, 10, 0.7225, 1.0),
        (50, 100, 0.4038, 0.5962),
    ],
)
def test_the_wilson_interval_matches_known_values(correct, n, low, high):
    got_low, got_high = wilson_interval(correct, n)
    assert got_low == pytest.approx(low, abs=1e-4)
    assert got_high == pytest.approx(high, abs=1e-4)


def test_the_interval_stays_inside_zero_and_one_and_around_the_share():
    for correct in range(0, 31):
        low, high = wilson_interval(correct, 30)
        assert 0.0 <= low <= correct / 30 <= high <= 1.0


def test_a_larger_sample_gives_a_narrower_interval():
    small = wilson_interval(9, 10)
    large = wilson_interval(900, 1000)
    assert (large[1] - large[0]) < (small[1] - small[0])


def test_no_examples_means_nothing_is_known():
    assert wilson_interval(0, 0) == (0.0, 1.0)


# --- the four setups, worked out by hand ------------------------------------------------------------------

def test_the_accuracy_of_every_setup(recorded):
    report = build_report(config_for())
    found = setups(report)
    assert report["n"] == 10
    assert found["Baseline only"]["accuracy"] == pytest.approx(0.4)
    assert found["LLM only"]["accuracy"] == pytest.approx(0.8)
    assert found["Cascade (baseline then LLM)"]["accuracy"] == pytest.approx(0.7)
    assert found["Cascade + human review"]["accuracy"] == pytest.approx(0.8)


def test_the_setups_come_in_the_order_of_the_readme_table(recorded):
    assert [s["name"] for s in build_report(config_for())["setups"]] == [
        "Baseline only", "LLM only", "Cascade (baseline then LLM)", "Cascade + human review",
    ]


def test_cost_and_latency_follow_the_tiers_that_were_asked(recorded):
    found = setups(build_report(config_for()))
    assert found["Baseline only"]["cost_per_1k_usd"] == 0.0
    assert found["LLM only"]["cost_per_1k_usd"] == pytest.approx(LLM_COST * 1000)
    assert found["Cascade (baseline then LLM)"]["cost_per_1k_usd"] == pytest.approx(LLM_COST * 1000 / 2)   # 5 of 10 asked the llm
    assert found["Baseline only"]["p50_ms"] == pytest.approx(BASE_MS)
    assert found["LLM only"]["p50_ms"] == pytest.approx(LLM_MS)


def test_the_median_of_the_cascade_is_between_the_two_kinds_of_requests(recorded):
    # Five requests took 2 ms (baseline only), five took 1,002 ms (both tiers): the median is their middle.
    assert setups(build_report(config_for()))["Cascade (baseline then LLM)"]["p50_ms"] == pytest.approx((2.0 + 1002.0) / 2)


def test_every_accuracy_has_an_interval_around_it(recorded):
    for setup in build_report(config_for())["setups"]:
        assert 0 <= setup["accuracy_low"] < setup["accuracy"] < setup["accuracy_high"] <= 1


def test_only_the_human_review_setup_says_it_assumes_a_perfect_reviewer(recorded):
    flags = {s["name"]: s["assumes_reviewer_always_right"] for s in build_report(config_for())["setups"]}
    assert flags == {
        "Baseline only": False, "LLM only": False, "Cascade (baseline then LLM)": False, "Cascade + human review": True,
    }
    human = setups(build_report(config_for()))["Cascade + human review"]
    assert "always right" in human["description"]


def test_the_descriptions_name_the_thresholds_of_the_config(recorded):
    found = setups(build_report(config_for()))
    assert "0.7" in found["Cascade (baseline then LLM)"]["description"]
    assert "0.9" in found["Cascade + human review"]["description"]


# --- what the cascade did ------------------------------------------------------------------------------------

def test_how_the_cascade_handled_the_examples_and_how_often_it_was_right(recorded):
    cascade = build_report(config_for())["cascade"]
    assert cascade["groups"] == [
        {"kind": "accepted", "tier": "baseline", "count": 5, "correct": 4},
        {"kind": "accepted", "tier": "llm", "count": 3, "correct": 2},
        {"kind": "human_review", "tier": None, "count": 2, "correct": 1},
    ]
    assert cascade["escalated"] == 5


def test_the_groups_cover_every_example_exactly_once(recorded):
    report = build_report(config_for())
    assert sum(g["count"] for g in report["cascade"]["groups"]) == report["n"]


def test_the_thresholds_of_the_config_decide(recorded):
    config = config_for()
    config["tiers"][0]["accept_threshold"] = 0.3     # the baseline is now sure about everything
    cascade = build_report(config)["cascade"]
    assert [(g["tier"], g["count"]) for g in cascade["groups"]] == [("baseline", 10), ("llm", 0), (None, 0)]
    assert cascade["escalated"] == 0


# --- calibration, worked out by hand --------------------------------------------------------------------------

def test_the_calibration_of_the_baseline(recorded):
    baseline = build_report(config_for())["calibration"][0]
    assert baseline["tier"] == "baseline"
    assert [(b["lower"], b["upper"], b["n"]) for b in baseline["bins"]] == [(0.0, 0.5, 5), (0.7, 0.9, 1), (0.9, 0.99, 4)]
    assert [b["accuracy"] for b in baseline["bins"]] == [0.0, 0.0, 1.0]
    assert [round(b["mean_confidence"], 2) for b in baseline["bins"]] == [0.4, 0.8, 0.95]
    # 5/10 * |0 - 0.4| + 1/10 * |0 - 0.8| + 4/10 * |1 - 0.95|
    assert baseline["ece"] == pytest.approx(0.2 + 0.08 + 0.02)


def test_the_last_bin_ends_at_one_not_just_above(recorded):
    df = crafted()
    df["llm_confidence"] = 1.0
    recorded(df)
    bins = build_report(config_for())["calibration"][1]["bins"]
    assert bins[-1]["upper"] == 1.0


def test_both_tiers_have_a_calibration(recorded):
    assert [c["tier"] for c in build_report(config_for())["calibration"]] == ["baseline", "llm"]


# --- the rest of the report -----------------------------------------------------------------------------------

def test_the_report_names_its_domain_split_and_tiers(recorded):
    report = build_report(config_for(data_source="synthetic"))
    assert (report["domain"], report["split"], report["data_source"]) == ("mini", "test", "synthetic")
    assert report["tiers"] == [{"name": "baseline", "accept_threshold": 0.7}, {"name": "llm", "accept_threshold": 0.9}]


def test_without_data_source_it_is_none(recorded):
    assert build_report(config_for())["data_source"] is None


# --- when there is nothing to show -------------------------------------------------------------------------------

def test_a_domain_without_recorded_predictions_is_unavailable_and_the_message_has_no_path(recorded):
    with pytest.raises(EvaluationUnavailable) as info:
        build_report(config_for(domain="other"))
    assert "'other'" in str(info.value)
    assert "/" not in str(info.value)


def test_a_config_with_other_tiers_is_unavailable(recorded):
    config = config_for()
    config["tiers"][1]["name"] = "big_model"
    with pytest.raises(EvaluationUnavailable, match="baseline tier followed by an llm tier"):
        build_report(config)


def test_missing_columns_or_no_rows_are_unavailable(recorded):
    recorded(crafted().drop(columns=["llm_confidence"]))
    with pytest.raises(EvaluationUnavailable, match="not usable"):
        build_report(config_for())
    recorded(crafted().iloc[:0])
    with pytest.raises(EvaluationUnavailable, match="not usable"):
        build_report(config_for())


# --- the committed file and the README --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def clinc():
    return build_report(load_config(ROOT / "configs" / "clinc150.yaml"))


def test_the_report_of_clinc150_is_the_results_table_of_the_readme(clinc):
    found = setups(clinc)
    expected = {
        "Baseline only": (0.917, 0.899, 0.0),
        "LLM only": (0.983, 0.976, 0.0118),
        "Cascade (baseline then LLM)": (0.983, 0.976, 0.0064),
        "Cascade + human review": (0.993, 0.989, 0.0064),
    }
    for name, (accuracy, f1, cost) in expected.items():
        assert round(found[name]["accuracy"], 3) == accuracy, name
        assert round(found[name]["macro_f1"], 3) == f1, name
        assert round(found[name]["cost_per_1k_usd"], 4) == cost, name
    assert clinc["n"] == 300
    assert round(found["LLM only"]["p50_ms"]) == 600 and round(found["LLM only"]["p95_ms"] / 1000, 2) == 2.17
    assert round(found["Cascade (baseline then LLM)"]["p50_ms"]) == 559


def test_the_cascade_numbers_of_clinc150_are_the_ones_the_readme_gives(clinc):
    """README: 139 requests (46%) accepted by the baseline, all correct; 161 escalated to the LLM, 6 of
    them sent to a person; human review removed 3 of the cascade's 5 errors."""
    groups = {(g["kind"], g["tier"]): g for g in clinc["cascade"]["groups"]}
    assert groups[("accepted", "baseline")]["count"] == groups[("accepted", "baseline")]["correct"] == 139
    assert groups[("human_review", None)]["count"] == 6
    assert clinc["cascade"]["escalated"] == 161
    errors = sum(g["count"] - g["correct"] for g in clinc["cascade"]["groups"])
    person = groups[("human_review", None)]
    removed_by_people = person["count"] - person["correct"]      # wrong suggestions that a person replaces
    left_over = round((1 - setups(clinc)["Cascade + human review"]["accuracy"]) * clinc["n"])
    assert errors == 5
    assert removed_by_people == 3
    assert left_over == errors - removed_by_people == 2


def test_the_calibration_of_clinc150_is_the_one_the_readme_gives(clinc):
    ece = {c["tier"]: c["ece"] for c in clinc["calibration"]}
    assert round(ece["baseline"], 2) == 0.27
    assert round(ece["llm"], 3) == 0.012


def test_the_screen_and_the_evaluation_script_use_the_same_numbers(clinc):
    df = pd.read_csv(evaluation.predictions_path("clinc150"))
    frames = {name: evaluation._tier_frame(df, name) for name in ("baseline", "llm")}
    table = report_rows(list(frames.items()), load_config(ROOT / "configs" / "clinc150.yaml")["labels"], 0.7, 0.9)
    for setup in clinc["setups"]:
        assert setup["accuracy"] == pytest.approx(table.loc[setup["name"], "accuracy"])
        assert setup["macro_f1"] == pytest.approx(table.loc[setup["name"], "macro_f1"])
        assert setup["cost_per_1k_usd"] == pytest.approx(table.loc[setup["name"], "cost_per_1k"])


# --- GET /evaluation ---------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch, recorded):
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(
        "domain: mini\ndata_source: synthetic\nlabels: [a, b]\n"
        "tiers:\n  - name: baseline\n    model: sklearn_tfidf_logreg\n    accept_threshold: 0.7\n"
        "  - name: llm\n    model: openrouter\n    model_id: v/m\n    price_in_per_m: 0.1\n"
        "    price_out_per_m: 0.3\n    accept_threshold: 0.9\n",
        encoding="utf-8",
    )
    tiers = [({"name": "baseline", "accept_threshold": 0.7}, Fake("a", 0.9)), ({"name": "llm", "accept_threshold": 0.9}, Fake("a", 0.9))]
    monkeypatch.setenv("ROUTEIQ_CONFIG", str(config_file))
    monkeypatch.setenv("ROUTEIQ_DB", str(tmp_path / "t.db"))
    monkeypatch.setattr("routeiq.api.build_tiers", lambda config: tiers)
    with TestClient(create_app()) as client:
        yield client


def test_the_endpoint_returns_the_report(client):
    response = client.get("/evaluation")
    assert response.status_code == 200
    body = response.json()
    assert (body["domain"], body["split"], body["n"], body["data_source"]) == ("mini", "test", 10, "synthetic")
    assert [s["name"] for s in body["setups"]][0] == "Baseline only"
    assert body["cascade"]["escalated"] == 5


def test_the_endpoint_says_404_when_there_are_no_recorded_predictions(client, tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, "RECORDED_DIR", tmp_path / "empty")
    response = client.get("/evaluation")
    assert response.status_code == 404
    assert response.json() == {"detail": "no recorded predictions for the domain 'mini'"}
    assert str(tmp_path) not in response.text


def test_an_app_without_a_config_file_has_no_evaluation(tmp_path):
    tiers = [({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9))]
    with TestClient(create_app(tiers=tiers, labels=["a"], db_path=tmp_path / "t.db")) as client:
        response = client.get("/evaluation")
    assert response.status_code == 404
    assert "no evaluation is available" in response.json()["detail"]
