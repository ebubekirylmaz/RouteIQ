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

- **Config-driven.** Categories, thresholds, models and targets live in YAML. A new use case needs labeled data and a config, including a one-line description of each label for the LLM prompt.
- **Pluggable models.** Every model implements one interface, so swapping providers is a config change.
- **Confidence-based cascade.** Two thresholds decide between accept, escalate and human review.
- **Human-in-the-loop queue.** Low-confidence items are stored with the model's suggestion for a person to confirm or correct.
- **Integration adapters.** Webhook, mock ERP (OData-style REST) and JSON Lines export out of the box. Delivery runs after the response, and its status is tracked per request.
- **Dashboard.** A React UI served by the API under `/dashboard/`: a review queue for a person to confirm or correct the model's suggestion, an overview with cost, latency and delivery status, charts over time, a searchable request history, and a form to try a text.
- **Built-in evaluation.** Accuracy, macro-F1, cost per 1,000 requests, p50/p95 latency, calibration and escalation rate, all from one command.
- **One worked example.** Ships with a bank-support scenario built on the public CLINC150 dataset. More example domains are planned (see [Roadmap](#roadmap)).

## Quick start

```bash
git clone https://github.com/ebubekirylmaz/routeiq.git
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
  -d '{"text": "my card got declined at the store"}'
```

Example response:

```json
{
  "label": "card_declined",
  "confidence": 0.7005,
  "tier": "baseline",
  "action": "accepted",
  "cost_usd": 0.0,
  "latency_ms": 26.8,
  "degraded": false,
  "request_id": 1
}
```

Or run it with Docker, without a local Python setup:

```bash
cp .env.example .env             # add OPENROUTER_API_KEY
docker compose up --build
```

The first build takes a few minutes: it installs the dependencies, downloads CLINC150, and trains the baseline inside the image. The API is then available at `http://localhost:8000`. It is published on localhost only, because it has no authentication. The API key is read from `.env` when the container starts and is not stored in the image. The SQLite database lives in the `routeiq-data` volume and survives restarts; `docker compose down -v` deletes it. The mock ERP keeps its tickets in memory, so they reset on restart. The image also contains the built dashboard: open `http://localhost:8000/dashboard/`.

## API

| Endpoint | Purpose |
|---|---|
| `GET /health` | Liveness check |
| `GET /config` | The task, the labels with their descriptions, the tiers with their thresholds, and the type of the delivery target. Target URLs, file paths, secret names and prices are never returned |
| `POST /route` | Body `{"text": "..."}` (1 to 5,000 characters). Runs the cascade and stores the request |
| `GET /requests` | Request history with filters, paging and a total count (see below) |
| `GET /review?limit=50&offset=0` | Requests waiting for a person, oldest first, with the model's suggestion. The header `X-Total-Count` holds the number waiting |
| `POST /review/{id}` | Body `{"label": "..."}`. Records the person's decision |
| `POST /deliveries/retry?limit=100` | Resends deliveries that failed, or that have been pending for more than 5 minutes (for example after a restart), oldest first |
| `GET /stats?since=...` | Totals for everything or for a window: requests, accepted per tier, human-review, delivery and reviewer-agreement counts, cost, average and p95 latency |
| `GET /stats/timeseries` | The same kind of numbers per hour or per day, for charts (see below) |

`action` is `accepted` or `human_review`. `tier` names the tier that produced the label (or the last suggestion). `degraded` is `true` when a tier failed and the cascade fell back to what it had; the error details are logged and stored, not returned.

Resolving a review item returns `404` for an unknown id, `409` if it is already resolved or never needed review, and `422` for a label that is not in the config.

```bash
curl http://localhost:8000/review
curl -X POST http://localhost:8000/review/1 \
  -H "Content-Type: application/json" \
  -d '{"label": "out_of_scope"}'
```

### Request history

`GET /requests` filters by `action`, `tier`, `review_status`, `delivery_status`, `degraded` and `q` (a case-insensitive substring of the text; `%` and `_` are matched literally). `limit` (1 to 200, default 50) and `offset` page through the result, newest first unless `order=oldest`. The number of requests matching the filters, ignoring paging, is in the `X-Total-Count` header.

Internal error text is never returned: each item only says whether it was `degraded`. A failed delivery shows its reason with any URL replaced by `<url>`, because such messages can contain the target's address and tokens.

### Statistics

`GET /stats?since=2026-10-05T00:00:00Z` limits every counter to requests created at or after that time. A time without a zone is read as UTC.

`reviewer_agreement` is the share of human-reviewed requests where the reviewer kept the model's suggestion. It is not the model's accuracy: only the requests the model was unsure about are sent to a person, so the sample is biased towards hard cases. It is `null` until the first review is resolved.

`GET /stats/timeseries?bucket=hour|day&since=...&until=...` returns one point per bucket with the request count (split into accepted and human review), cost and average latency. Buckets are aligned to the hour or day in UTC, so the first one starts at the beginning of the bucket that contains `since`. `since` is included and `until` is excluded. Buckets without requests are returned with zeros, so a chart gets a continuous axis. The defaults are the last 24 hours (hourly) and the last 30 days (daily); a range of more than 1,000 buckets is rejected with `422`.

### Typed schema

Every endpoint declares its response model, and the operation ids are the function names (`route_request`, `list_requests`, ...). The OpenAPI schema at `/openapi.json` can be fed to a code generator to get typed clients; tests pin the field names and types so a change to them is noticed.

Every request is stored in a SQLite file (text, result, cost, latency, and the reviewer's decision). Settings are read from the environment: `ROUTEIQ_CONFIG` (default `configs/clinc150.yaml`) and `ROUTEIQ_DB` (default `routeiq.db` in the repository root). Interactive documentation is served at `/docs`.

## Dashboard

The dashboard is a single-page app in [`dashboard/`](dashboard/) (React, TypeScript, Vite). The API serves the built files under `/dashboard/`, and `/` redirects there. The Docker image builds it in a Node stage, so `docker compose up --build` is enough. Without Docker, build it once and start the API:

```bash
cd dashboard && npm install && npm run build && cd ..
uvicorn routeiq.api:app
```

Open `http://localhost:8000/dashboard/`. Node 20.19 or later is needed to build. `ROUTEIQ_DASHBOARD_DIR` points the API at another folder of built files.

| Screen | What it shows |
|---|---|
| Review queue | Requests waiting for a person, oldest first, with one button per label. The model's suggestion is marked but not preselected. The list refreshes every 10 seconds. If somebody else already decided a request, you get a notice instead of an overwritten decision |
| Overview | Totals for the last 24 hours, 7 days or all time: requests, cost, p95 latency, requests where a tier failed, how requests ended, and the delivery status with a button to resend failed deliveries |
| Charts | Requests (accepted or sent to a person), cumulative cost and average latency per hour or day, and a table of the same numbers below the charts |
| History | Every request, newest first, with filters (outcome, review, delivery, tier, tier failure), text search and paging. Filters and page are kept in the address, so a view can be bookmarked. A row opens to show the full text and the delivery problem |
| Try it | Send a text through the cascade and see its label, confidence, tier, cost and latency. The text is stored like any other request and may call the paid model. Ctrl or Cmd + Enter sends |

Times are shown in UTC. The overview shows reviewer agreement next to a note that it is not the model's accuracy (see [Statistics](#statistics)).

The dashboard has no login, like the API. Publish it on localhost only, or put both behind a gateway.

### Demo data

A new installation has no requests, so every screen is empty. To see the dashboard filled without real traffic, write synthetic requests into a separate database and start the API on it:

```bash
python scripts/seed_demo.py                    # writes demo.db
ROUTEIQ_DB=demo.db uvicorn routeiq.api:app
```

The texts come from a few templates, and the outcomes (confidence, cost, latency, which requests were reviewed, which deliveries failed) are drawn at random with a fixed seed, so the same command gives the same history. They are not results of the models. The script calls no model, and it refuses to write into a database that already has requests unless `--add` is given. The API itself still needs `OPENROUTER_API_KEY` to start, as with the real configuration.

For development, run the API and `npm run dev` in `dashboard/` (http://localhost:5173/dashboard/); the dev server forwards the API paths, so no CORS setup is needed. After an API change, regenerate the schema and the types:

```bash
python scripts/export_openapi.py
cd dashboard && npm run api:types
```

A Python test fails when the committed `dashboard/openapi.json` is out of date. More in [`dashboard/README.md`](dashboard/README.md).

## Integrations

Final decisions are sent to a target system: requests the cascade accepted are sent right away, and requests that went to human review are sent once a person resolves them (with the person's label). Delivery happens in the background after the API responds, so a slow or unavailable target never delays the caller. Each request records its delivery status (`pending`, `sent` or `failed`, with the error) in the database, and `POST /deliveries/retry` resends the failed ones.

Delivery is at-least-once: a record can occasionally arrive twice, so the receiving side should deduplicate on `request_id`.

The target is chosen in the config:

```yaml
target:
  type: mock_erp          # webhook | mock_erp | jsonl | none (or omit the section)
  url: http://localhost:8000/mock-erp/api/tickets
```

| Type | Settings | What it does |
|---|---|---|
| `jsonl` | `path` | Appends one JSON object per line to a file |
| `webhook` | `url`, optional `secret_env` | POSTs the record as JSON. With a secret, the body is signed: header `X-RouteIQ-Signature: sha256=<HMAC-SHA256 of the body>`. Retries network errors, `429` and `5xx` |
| `mock_erp` | `url` | Sends the record as a ticket to the built-in mock ERP |

The record sent to `webhook` and `jsonl` looks like this:

```json
{"request_id": 3, "text": "...", "label": "report_lost_card", "confidence": 0.79,
 "tier": "baseline", "source": "cascade"}
```

For human-resolved requests `label` is the reviewer's choice, `tier` is `human` and `source` is `human_review`.

The mock ERP runs inside the same application (only when the config targets it) under `/mock-erp/api/tickets`. It accepts `POST`, lists with `$top` and `$skip`, and returns `@odata.count`. Posting the same `ExternalID` twice returns the existing ticket instead of creating a second one, so redeliveries are harmless. It keeps its data in memory. It imitates the shape of an enterprise API and does not connect to any real ERP product.

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

task: bank customer support messages    # what is being classified, used in the LLM prompt

label_descriptions:                     # one line per label, used in the LLM prompt
  report_lost_card: the customer lost their card or cannot find it.
  damaged_card: the card is physically damaged (cracked, burned, bent).
  card_declined: a payment was refused or the card was not accepted.
  report_fraud: unauthorized or suspicious charges on the account.
  freeze_account: the customer wants the account blocked or locked.
  out_of_scope: anything else, including messages unrelated to banking.

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

## Datasets

| Domain | Source | Notes |
|---|---|---|
| `clinc150` | CLINC150 (`clinc_oos` on Hugging Face), public intent-classification dataset | Main benchmark, real human-written text, includes out-of-scope queries |

No real company data is included.

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

CLINC150 is released under CC BY 3.0 (see the dataset card on Hugging Face). If you use it, cite: Larson et al., "An Evaluation Dataset for Intent Classification and Out-of-Scope Prediction", EMNLP-IJCNLP 2019 (<https://aclanthology.org/D19-1131>).

## Adding a domain

The cascade, the evaluation and the integrations do not depend on the CLINC150 data. The bank-support scenario is the one worked example; a new domain takes these steps:

1. Prepare labeled `train.csv`, `val.csv` and `test.csv` files (columns `text,label`) under `data/`. `data/prepare_clinc.py` shows how it is done for CLINC150.
2. Create a config under `configs/` with the labels, thresholds and a target. The config is validated at startup and mistakes are reported with their location.
3. Describe what is being classified (`task`) and each label (`label_descriptions`) in the config. They are placed in the system prompt of the LLM tier. Every label needs a description, and the descriptions matter: they decide how the LLM treats the confusable labels and the out-of-scope class, so check them on the validation split, not the test split.
4. Run `python -m routeiq.train` and `python -m routeiq.evaluate` with the new config.

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

Measured on the held-out test split (300 examples: 30 per intent plus 150 out-of-scope). The thresholds (baseline 0.7, LLM 0.9) were chosen on the validation split and not changed after seeing the test results. The LLM tier is `mistralai/mistral-small-3.2-24b-instruct` via OpenRouter.

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
├── dashboard/               # React UI (see dashboard/README.md)
├── data/
│   └── prepare_clinc.py     # builds the train, validation and test files
├── routeiq/
│   ├── api.py               # FastAPI app and its endpoints
│   ├── cascade.py           # threshold-based routing logic
│   ├── config.py            # config loading and validation
│   ├── dashboard.py         # serves the built UI under /dashboard/
│   ├── delivery.py          # sends decisions to the target and tracks the status
│   ├── evaluate.py          # metrics, calibration and threshold sweep
│   ├── redact.py            # masks URLs in error messages before they are shown
│   ├── schemas.py           # request and response models of the API
│   ├── store.py             # SQLite store: requests, review queue, deliveries
│   ├── timeutil.py          # UTC and time bucket helpers
│   ├── train.py             # baseline training
│   ├── views.py             # builds the public views (config, request items)
│   ├── models/              # classifier adapters and registry
│   └── integrations/        # JSONL export, webhook, mock ERP
├── scripts/                 # export_openapi.py (schema for the UI types), seed_demo.py (synthetic demo data)
├── tests/
├── Dockerfile
├── docker-compose.yml
├── LICENSE
├── pyproject.toml
└── README.md
```

## Testing

```bash
pytest
```

Tests cover the cascade decisions at threshold boundaries (and that the threshold simulation in `evaluate.py`, which produces the results table, makes the same decisions as the live cascade), the OpenRouter adapter (response parsing, retries), the API routes and their OpenAPI contract, the review queue, request history and statistics, delivery tracking, the integrations, the SQLite store with its schema migration and indexes, and config validation. LLM and network calls are mocked in tests.

The dashboard has its own tests and type check (`cd dashboard && npm test && npm run typecheck`). They run in Vitest with a mocked API, so no server is needed.

## Limitations

- Confidence scores from different model types are not directly comparable. Calibration is evaluated, and thresholds should be tuned per domain.
- Benchmarks on public data do not guarantee the same results on a real company's data.
- The prompt wording was written once and not tuned. Different label descriptions can change the LLM's accuracy, especially on the out-of-scope class, and `data/prepare_clinc.py` is specific to CLINC150.
- The mock ERP only imitates the shape of an enterprise API. A production integration needs authentication, retries and error handling for the real system.
- LLM cost figures depend on current provider pricing and should be rechecked.
- The CLINC150 setup uses a subset of intents plus out-of-scope. Results do not transfer to the full 150-intent task.
- CLINC150 queries are short, single-turn utterances. Real business emails are longer and messier.
- Many `card_declined` examples are one template sentence with small variations, so this intent is easy to learn and can make results look better than they would on varied text.
- The validation set has only 20 examples per intent, so one mistake moves a class's recall by 5 points. Small differences between classes may be noise.
- The API has no authentication. Anyone who can reach `/review`, `/requests` or `/stats` can read the stored texts, and anyone who can reach `/review` can resolve items. Put it behind a gateway or add authentication before exposing it.
- `GET /requests` pages with `offset`, so while a client pages through the newest-first list, new requests shift the pages and a row can show up twice or be skipped. The text search scans the table; it has no full-text index.
- Reviewer agreement measures how often a person keeps the model's suggestion on requests the model was unsure about. It says little about accuracy on the requests the cascade accepted.
- Request texts are stored unencrypted in a local SQLite file, with no retention limit or anonymization. A real deployment needs a retention policy and access control.
- Requests that reach the LLM wait for it. With the configured budget (10 s timeout, 2 attempts) a request can take about 21 s before it falls back to human review.
- `POST /deliveries/retry` takes the oldest failed deliveries first, so a record that keeps failing can hold back newer ones when the limit is smaller than the backlog.
- The mock ERP keeps its tickets in memory and the application is designed for a single process; neither is meant for production use.
- The dashboard does not record who made a decision: a review is stored with the label and the time only, so there is no audit trail per person.
- The history screen does not refresh by itself, because new requests would move the rows while somebody reads. It has a Refresh button; the review queue and the overview poll.

## Roadmap

- [x] Baseline training and evaluation
- [x] OpenRouter adapter with structured output
- [x] Cascade routing and threshold sweep
- [x] FastAPI service and human-review queue
- [x] Mock ERP integration
- [x] Docker setup
- [x] Automated test that the threshold simulation in `evaluate.py` matches the live cascade
- [ ] Example domains with synthetic data, labeled as synthetic (electric-vehicle after-sales, supplier communication, internal requests)
- [x] Dashboard (React + TypeScript): review queue, overview, charts, request history and a form to try a text
- [ ] Dashboard: accuracy charts (these need labeled ground truth, which production requests do not have)
- [ ] Threshold auto-tuning from review feedback
- [ ] Drift monitoring

## License

MIT, see [LICENSE](LICENSE). The CLINC150 data keeps its own license (CC BY 3.0).
