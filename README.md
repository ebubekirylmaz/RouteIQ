# RouteIQ

**A cost-aware decision layer for routing text requests.** RouteIQ classifies incoming requests (emails, support tickets, purchase requests, form submissions), decides with a cheap and fast model first, escalates to a stronger LLM only when confidence is low, falls back to a human when even that is unsure, and writes the outcome to a target system over REST. Every step is measured for accuracy, cost and latency.

> Status: MVP in active development. Numbers in the results section are filled in only from real runs. See [Roadmap](#roadmap).

---

## Why this exists

Many business processes start with someone reading a message and deciding where it goes: which team, which category, which priority. Sending every one of those decisions to a large LLM works, but it is slow and expensive, and most requests are easy.

RouteIQ explores a simple idea: **use the cheapest model that is confident enough, and spend LLM budget only where it changes the outcome.** It also makes that trade-off measurable instead of guessed.

## How it works

```
                 incoming request
                        |
                        v
             +---------------------+
             |  Tier 1: fast model |   sklearn baseline / small decision model
             |  label + confidence |
             +----------+----------+
                        |
          confidence >= t1 ?
             yes /            \ no
                /              \
               v                v
        +-----------+   +---------------------+
        |   accept  |   |  Tier 2: LLM        |
        +-----------+   |  via OpenRouter     |
               |        +----------+----------+
               |                   |
               |        confidence >= t2 ?
               |           yes /        \ no
               |              /          \
               |             v            v
               |        +---------+  +--------------+
               |        | accept  |  | human review |
               |        +---------+  |    queue     |
               |             |       +------+-------+
               +------+------+--------------+
                      v
          +------------------------+
          |  Integration adapter   |   webhook / mock ERP (OData-style REST) / JSON
          +------------------------+
                      |
                      v
          metrics store (SQLite): label, confidence, tier, cost, latency
```

## Features

- **Config-driven.** Categories, thresholds, models and targets live in YAML. A new use case needs a new config, not new code.
- **Pluggable models.** Every model implements one interface, so swapping providers is a config change.
- **Confidence-based cascade.** Two thresholds decide between accept, escalate and human review.
- **Human-in-the-loop queue.** Low-confidence items are stored with the model's suggestion for a person to confirm or correct.
- **Integration adapters.** Webhook, mock ERP (OData-style REST) and JSON/CSV export out of the box.
- **Built-in evaluation.** Accuracy, macro-F1, cost per 1,000 requests, p50/p95 latency, calibration and escalation rate, all from one command.
- **Domain-agnostic.** Ships with two example domains to show it is not tied to one dataset.

## Quick start

```bash
git clone https://github.com/<your-username>/routeiq.git
cd routeiq

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

cp .env.example .env             # add OPENROUTER_API_KEY
```

Prepare the benchmark data, train the baseline and run an evaluation:

```bash
python data/prepare_clinc.py
python -m routeiq.train --config configs/clinc150.yaml
python -m routeiq.evaluate --config configs/clinc150.yaml
```

Start the API:

```bash
uvicorn routeiq.api:app --reload
```

Route a request:

```bash
curl -X POST http://localhost:8000/route \
  -H "Content-Type: application/json" \
  -d '{"text": "<an example request>"}'
```

Example response:

```json
{
  "label": "<predicted_intent>",
  "confidence": 0.94,
  "tier": "baseline",
  "action": "accepted",
  "latency_ms": 12,
  "cost_usd": 0.0
}
```

Or run everything with Docker:

```bash
docker compose up --build
```

## Configuration

```yaml
# configs/clinc150.yaml
domain: clinc150
data_source: public   # CLINC150 (clinc_oos): subset of intents + out-of-scope

labels:               # intents chosen from the dataset, plus the out-of-scope class
  - report_lost_card
  - damaged_card
  - card_declined
  - report_fraud
  - freeze_account
  - out_of_scope

tiers:
  - name: baseline
    model: sklearn_tfidf_logreg
    accept_threshold: 0.7   # chosen on the validation set; the baseline's scores are
                            # underconfident, so thresholds are rank cut-offs, not probabilities

  - name: llm
    model: openrouter
    model_id: mistralai/mistral-small-3.2-24b-instruct
    price_in_per_m: 0.09    # USD per 1M input tokens, fallback only: the real cost
    price_out_per_m: 0.30   # USD per 1M output tokens, is read from the API response
    accept_threshold: 0.90

target:
  type: mock_erp
  url: http://localhost:8000/mock-erp/api/tickets
```

## Adding a model

Implement the interface and register it:

```python
# routeiq/models/base.py
from dataclasses import dataclass
from typing import Protocol

@dataclass
class Prediction:
    label: str
    confidence: float
    cost_usd: float = 0.0

class Classifier(Protocol):
    def classify(self, text: str, labels: list[str]) -> Prediction: ...
```

Included adapters:

| Adapter | Purpose | Notes |
|---|---|---|
| `sklearn_tfidf_logreg` | Cheap, fast baseline | Trained locally |
| `openrouter` | LLM tier with structured output, any model available on OpenRouter | Needs `OPENROUTER_API_KEY` |
| `jev` | Direct decision model | Optional, depends on access |

## Datasets

| Domain | Source | Notes |
|---|---|---|
| `clinc150` | CLINC150 (`clinc_oos` on Hugging Face), public intent-classification dataset | Main benchmark, real human-written text, includes out-of-scope queries |
| `ev_after_sales` | Synthetic, generated with an LLM and reviewed by hand | Example domain: electric vehicle after-sales |
| `ev_supplier_comms` | Synthetic, generated with an LLM and reviewed by hand | Example domain: supplier communication |
| `ev_internal_requests` | Synthetic, generated with an LLM and reviewed by hand | Example domain: internal requests |

Synthetic data is labeled as synthetic everywhere it is used. No real company data is included. Results on synthetic data are reported separately from the public benchmark, because synthetic text tends to be easier to classify and says less about real-world performance.

## Main benchmark: CLINC150

CLINC150 contains user queries covering 150 intents across 10 domains, plus an out-of-scope label for queries that match none of them. RouteIQ uses a subset: a handful of intents chosen from the dataset (listed in `configs/clinc150.yaml`) plus the out-of-scope class.

The out-of-scope class is the reason for choosing this dataset. A routing system must also recognise requests it should not route automatically, so these examples exercise the escalation and human-review path directly instead of only measuring easy, in-scope cases.

`data/prepare_clinc.py` downloads the dataset, keeps the chosen intents, maps the out-of-scope examples to `out_of_scope`, and writes train, validation and test files under `data/`.

**Chosen scenario: bank support requests.** The five intents are `report_lost_card`, `damaged_card`, `card_declined`, `report_fraud` and `freeze_account`. They are semantically close (for example lost vs. damaged card), so the baseline makes real mistakes and the cascade has something to fix. The other 145 CLINC150 intents are dropped; only the original `oos` examples become `out_of_scope`.

| Split | Per intent | `out_of_scope` | Total |
|---|---|---|---|
| train | 100 | 250 | 750 |
| validation | 20 | 100 | 200 |
| test | 30 | 150 | 300 |

The raw test split has 1,000 out-of-scope examples against 30 per intent, which would make accuracy mostly a measure of the out-of-scope class. The script therefore samples 150 of them (`random_state=42`). Train and validation are left as they are.

**Baseline (validation only).** TF-IDF (unigrams and bigrams) with logistic regression reaches accuracy 0.94 and macro-F1 0.915. The weakest classes are `damaged_card` and `report_fraud`. Its confidence is lower than its accuracy suggests: the mean confidence is 0.68 on correct predictions and 0.39 on wrong ones. Test results are reported only in the evaluation section below.

<!-- TODO: confirm the dataset license in its source repository and state it here. The Hugging Face dataset card did not specify one. -->

## Example domains

The core of RouteIQ knows nothing about any industry. To show how a new use case is added, the repository includes three example domains inspired by typical processes of an electric vehicle manufacturer. They are illustrations built from assumptions, not descriptions of any real company's processes.

| Config | Incoming text | Example labels | Target record (mock ERP) |
|---|---|---|---|
| `ev_after_sales.yaml` | Customer and dealer messages | `warranty_claim`, `spare_part_request`, `battery_or_charging_issue`, `delivery_delay`, `complaint`, `other` | Service notification |
| `ev_supplier_comms.yaml` | Supplier emails | `delivery_delay`, `quality_issue`, `invoice_question`, `price_update`, `other` | Supplier case |
| `ev_internal_requests.yaml` | Employee forms | `purchase_request`, `it_support`, `maintenance_request`, `other` | Purchase requisition or ticket |

Adding a domain takes three steps:

1. Create a config under `configs/` with labels, thresholds and a target.
2. Provide labeled data, or generate synthetic data with `data/prompts/` and review it by hand.
3. Run `train` and `evaluate`. No code changes are needed.

The mock ERP exposes OData-style REST endpoints with entity names modeled on common enterprise systems. It imitates the shape of such an API and does not connect to any real ERP product.

## Evaluation

```bash
python -m routeiq.evaluate --config configs/clinc150.yaml --split test
```

Tier predictions are cached under `reports/`, so repeated runs do not call the LLM again. Useful flags: `--split val|test` (default `val`), `--refresh` to recompute the cached predictions, and `--sweep` to also print the full threshold grid.

The report covers:

- **Accuracy and macro-F1** per tier and for the full cascade
- **Cost per 1,000 requests**
- **Latency** (p50, p95)
- **Escalation rate** and **human-review rate**
- **Accuracy vs. cost** across threshold settings (`--sweep` prints the grid)
- **Calibration**: when the system says 90% confident, is it right about 90% of the time?

### Results: CLINC150

Measured on the held-out test split (300 examples: 30 per intent plus 150 out-of-scope). The thresholds (baseline 0.7, LLM 0.9) were chosen on the validation split and not changed after seeing the test results. The LLM tier is `mistralai/mistral-small-3.2-24b-instruct` via OpenRouter. Synthetic example domains get their own table, reported separately.

| Setup | Accuracy | Macro-F1 | Cost / 1k req | p50 latency | p95 latency |
|---|---|---|---|---|---|
| Baseline only | 0.917 | 0.899 | $0 | 0.2 ms | 0.2 ms |
| LLM only | 0.983 | 0.976 | $0.0118 | 600 ms | 2.17 s |
| Cascade (baseline then LLM) | 0.983 | 0.976 | $0.0064 | 559 ms | 1.93 s |
| Cascade + human review | 0.993 | 0.989 | $0.0064 | 559 ms | 1.93 s |

In the cascade, 139 requests (46%) were accepted by the baseline (all correct), 161 (54%) were escalated to the LLM, and 6 (2%) went to human review. The "+ human review" row assumes the reviewer is always right and does not count human time in cost or latency. With 300 examples, a 95% confidence interval on accuracy is roughly ±1.5 points, so the difference between "LLM only" and "Cascade" is not meaningful.

Key findings:

- The LLM is clearly more accurate than the baseline (0.983 vs 0.917 accuracy, 0.976 vs 0.899 macro-F1).
- The cascade matches the LLM's accuracy at about 54% of its cost. Because only 46% of requests skip the LLM, the median latency barely improves (559 ms vs 600 ms). A lower baseline threshold cuts cost and latency further, at the price of accuracy on the validation set.
- The baseline's confidence is poorly calibrated (ECE 0.27, it underestimates itself) but ranks well: every request it accepted above 0.7 was correct. The LLM's confidence is well calibrated overall (ECE 0.012).
- Human review on 2% of requests removed 3 of the cascade's 5 errors. The remaining 2 are lost-or-stolen-card messages that the LLM labeled `report_fraud` with confidence above 0.99, a genuinely ambiguous boundary that a confidence threshold cannot catch.
- With this inexpensive LLM the absolute saving is small (about $5 per million requests). The cascade pays off more with a pricier LLM tier or when most requests can be answered without waiting for one.

## Project structure

```
routeiq/
├── configs/                 # YAML use-case definitions (one per domain)
├── data/
│   ├── prompts/             # prompts used to generate synthetic data
│   └── ...                  # datasets and generation scripts
├── routeiq/
│   ├── api.py               # FastAPI app
│   ├── cascade.py           # threshold-based routing logic
│   ├── evaluate.py          # metrics and reports
│   ├── train.py             # baseline training
│   ├── models/              # classifier adapters
│   └── integrations/        # webhook, mock ERP, export
├── tests/
├── docker-compose.yml
├── pyproject.toml
└── README.md
```

## Testing

```bash
pytest
```

Tests cover the cascade decisions at threshold boundaries, adapter contracts and the API routes. LLM calls are mocked in tests.

## Limitations

- Confidence scores from different model types are not directly comparable. Calibration is evaluated, and thresholds should be tuned per domain.
- Benchmarks on public or synthetic data do not guarantee the same results on a real company's data.
- The mock ERP only imitates the shape of an enterprise API. A production integration needs authentication, retries and error handling for the real system.
- LLM cost figures depend on current provider pricing and should be rechecked.
- The CLINC150 setup uses a subset of intents plus out-of-scope. Results do not transfer to the full 150-intent task.
- CLINC150 queries are short, single-turn utterances. Real business emails are longer and messier.
- Many `card_declined` examples are one template sentence with small variations, so this intent is easy to learn and can make results look better than they would on varied text.
- The validation set has only 20 examples per intent, so one mistake moves a class's recall by 5 points. Small differences between classes may be noise.

## Roadmap

- [x] Baseline training and evaluation
- [x] OpenRouter adapter with structured output
- [x] Cascade routing and threshold sweep
- [ ] FastAPI service and human-review queue
- [ ] Mock ERP integration
- [ ] Docker setup
- [ ] Jev adapter (if access is available)
- [ ] Dashboard (React + TypeScript): live routing, cost and accuracy charts
- [ ] Threshold auto-tuning from review feedback
- [ ] Drift monitoring

## License

MIT
