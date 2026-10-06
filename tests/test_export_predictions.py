import importlib.util

import pandas as pd
import pytest

from routeiq.config import ROOT

spec = importlib.util.spec_from_file_location("export_predictions", ROOT / "scripts" / "export_predictions.py")
export_predictions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_predictions)

CONFIG = ROOT / "configs" / "clinc150.yaml"
TEXTS = ["freeze it", "my card broke", "what is the weather"]
TRUE = ["freeze_account", "damaged_card", "out_of_scope"]


def report(label, confidence=0.9, cost=0.0, latency=3.0, **overrides):
    frame = pd.DataFrame({
        "label": label, "confidence": confidence, "cost_usd": cost, "error": None,
        "text": TEXTS, "true": TRUE, "latency_ms": latency,
    })
    for column, value in overrides.items():
        frame[column] = value
    return frame


def save(tmp_path, baseline=None, llm=None):
    reports = tmp_path / "reports"
    reports.mkdir(exist_ok=True)
    (baseline if baseline is not None else report(TRUE)).to_csv(reports / "clinc150_test_baseline.csv", index=False)
    if llm is not False:
        (llm if llm is not None else report(TRUE, cost=0.00002, latency=800.0)).to_csv(reports / "clinc150_test_llm.csv", index=False)
    return reports


def run(tmp_path, **kwargs):
    reports = save(tmp_path, **kwargs)
    return export_predictions.export(CONFIG, "test", tmp_path / "out.csv", reports)


def test_both_tiers_end_up_side_by_side(tmp_path):
    out, count = run(tmp_path)
    df = pd.read_csv(out)
    assert count == 3
    assert list(df.columns) == [
        "text", "true",
        "baseline_label", "baseline_confidence", "baseline_cost_usd", "baseline_latency_ms",
        "llm_label", "llm_confidence", "llm_cost_usd", "llm_latency_ms",
    ]
    assert df["text"].tolist() == TEXTS and df["true"].tolist() == TRUE
    assert df["llm_cost_usd"].tolist() == [0.00002] * 3 and df["llm_latency_ms"].tolist() == [800.0] * 3


def test_values_keep_their_full_precision_because_a_threshold_can_sit_on_them(tmp_path):
    exact = 0.7000000000000001
    out, _ = run(tmp_path, baseline=report(TRUE, confidence=exact))
    assert pd.read_csv(out)["baseline_confidence"].tolist() == [exact] * 3


def test_a_missing_report_says_how_to_make_it(tmp_path):
    reports = save(tmp_path, llm=False)
    with pytest.raises(export_predictions.ExportError, match=r"routeiq.evaluate .* --split test"):
        export_predictions.export(CONFIG, "test", tmp_path / "out.csv", reports)


@pytest.mark.parametrize(
    "llm, message",
    [
        (report(TRUE, text=["a", "b", "c"]), "texts of tier 'llm'"),
        (report(TRUE).iloc[:2], "texts of tier 'llm'"),
        (report(TRUE, true=["freeze_account", "damaged_card", "card_declined"]), "true labels of tier 'llm'"),
        (report(TRUE, error=["boom", None, None]), "1 failed predictions"),
        (report(TRUE, confidence=1.5), "confidence outside 0 to 1"),
        (report(["freeze_account", "damaged_card", "made_up"]), "label that is not in the config"),
    ],
)
def test_reports_that_do_not_fit_together_are_refused_with_the_reason(tmp_path, llm, message):
    with pytest.raises(export_predictions.ExportError, match=message):
        run(tmp_path, llm=llm)
    assert not (tmp_path / "out.csv").exists()


def test_the_command_reports_success_and_failure(tmp_path, capsys, monkeypatch):
    save(tmp_path)
    out = tmp_path / "cli.csv"
    monkeypatch.setattr(export_predictions, "ROOT", tmp_path)
    assert export_predictions.main(["--config", str(CONFIG), "--out", str(out)]) == 0
    assert "Wrote 3 predictions" in capsys.readouterr().out

    (tmp_path / "reports" / "clinc150_test_llm.csv").unlink()
    assert export_predictions.main(["--config", str(CONFIG), "--out", str(out)]) == 1
    assert "does not exist" in capsys.readouterr().err
