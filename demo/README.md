# Recorded predictions for the demo

`clinc150_test_predictions.csv` holds the 300 examples of the CLINC150 test split that the README
evaluates (30 for each of the five intents and 150 out-of-scope), with what each tier of the cascade
answered for them: label, confidence, cost and latency.

- **The texts and their true labels** come from CLINC150 (`clinc_oos`, "An Evaluation Dataset for
  Intent Classification and Out-of-Scope Prediction", Larson et al., 2019), which is licensed under
  CC BY 3.0. The data keeps its own license.
- **The answers** are real: they were recorded when `python -m routeiq.evaluate` ran the baseline and
  the LLM tier (`mistralai/mistral-small-3.2-24b-instruct` through OpenRouter) on this split. The file
  was made from them with `python scripts/export_predictions.py`. It is not changed by hand.
- **What it is for:** `python scripts/replay_demo.py` runs the cascade on these recorded answers and
  fills a database, so the dashboard shows real decisions without calling any model. A test checks
  that the replay gives the numbers of the README (139 accepted by the baseline, 155 by the LLM, 6
  sent to a person).
- **What is not real** in a replayed database: the times and the reviewers' decisions.
