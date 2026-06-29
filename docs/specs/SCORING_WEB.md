# Scoring web application

## Runtime

Entry point:

```bash
python scoring/app.py
```

Development URL:

```text
http://127.0.0.1:8000
```

The app is a local Flask/Jinja application. It does not instantiate provider clients and does not require model credentials to browse logs or score answers.

## Data layer

`scoring/repository.py` builds the display catalog from:

```text
data/competitions/
logs/**/*.json
data/results/**/*.json
```

The catalog shape is:

```text
competition
  problems
    model_states
      attempts/results
      evaluation
```

Canonical competitions and problems are loaded first, so a task is visible even when no model has run on it. Logs that cannot be connected to a canonical competition/problem are grouped under `legacy` with title `Старые прогоны`.

Invalid JSON is collected as a diagnostic warning instead of crashing the whole site. The original log objects are not mutated while merging sidecar evaluations.

## Routes

| Method/path | Behavior |
| --- | --- |
| `GET /` | Russian competition cards from canonical data plus log/evaluation counts |
| `GET /competition/<competition_id>` | matrix: rows are tasks, columns are models; task title opens anonymous scoring |
| `GET /competition/<competition_id>/stats?model=<model_key>` | aggregate model statistics and model-task table |
| `GET /competition/<competition_id>/problem/<problem_id>?model=<model_key>&attempt=<result_id>` | task statement, selected model attempt, metrics, score form, attempt switcher |
| `GET /competition/<competition_id>/problem/<problem_id>/anonymous?seed=<seed>&n=<number>` | anonymous scoring page: one numbered answer at a time, without model/provider labels |
| `GET /competition/<competition_id>/evaluations.csv?evaluator=<name>` | export evaluation pool for a competition, optionally filtered by reviewer |
| `GET /competition/<competition_id>/problem/<problem_id>/evaluations.csv?evaluator=<name>` | export evaluation pool for one task, optionally filtered by reviewer |
| `POST /competition/<competition_id>/evaluations/import` | import evaluation-pool CSV for the competition |
| `POST /competition/<competition_id>/problem/<problem_id>/evaluations/import` | import evaluation-pool CSV for one task |
| `GET /competition/<competition_id>/problem/<problem_id>/run/<run_id>` | compatibility redirect to the task page with a model and attempt selected |
| `GET /run/<run_id>` | legacy lookup and redirect |
| `POST /score` | validates run/result/score and appends a sidecar evaluation keyed by `result_id` |
| `POST /score/delete` | deletes one evaluation from a result's evaluation pool |

`model_key` is stable and includes provider plus model ID, for example `openai:gpt-5.5`. `attempt` is optional; when omitted the page shows the latest attempt for the selected model. When present it selects the matching `result_id` without leaving the task page. Configured model columns come from provider `versions.py` `VERSIONS` entries only. Models found in logs are added as historical columns when attempts exist for the current competition/problem; `LEGACY_VERSIONS` does not seed the default matrix.

The anonymous scoring page hides model/provider names, metrics and raw JSON from
the reviewer UI. It displays one answer at a time with numbered navigation and a
"next solution" control. On first entry the app redirects to the same page with a
random `seed`; answer order is shuffled from that seed and remains stable while
the reviewer moves between answer numbers. The page still submits the underlying
`run_id`, `result_id` and `model_key` as hidden form fields so evaluations are
written to the same sidecar format. This is UI-level anonymity, not a security
boundary against inspecting page source.

## Cell status

Model cell status is computed by pure functions in `scoring/repository.py`.

Rules:

- `not_run`: no attempts for the model/problem;
- `error`: latest attempt has no successful non-empty answer;
- `unscored`: latest attempt has a successful non-empty answer and no score;
- `zero`: latest successful answer score is `0`;
- `partial`: `0 < score < max_score`;
- `full`: `score == max_score`.

The primary status is based on the latest attempt timestamp. If the latest attempt is an error but an earlier successful answer was scored, the cell remains `error` while tooltip text reports the earlier scored answer. Tooltips and `aria-label` include model, state, score, latest attempt, attempt count, latency, tokens and error summary where available.

## Score persistence

New sidecars use `schema_version: 2` and store an evaluation pool by `result_id`:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Read precedence:

1. sidecar `evaluation_pool` keyed by `result_id`;
2. old sidecar `evaluations` keyed by `result_id`;
3. old sidecar `evaluations` keyed by string result index;
4. legacy score fields embedded in the run-log.

`POST /score` validates:

- competition/problem/run IDs;
- `result_id` belongs to the submitted run;
- `0 <= score <= max_score`;
- `max_score` from `problem.metadata.max_score`, then `competition.metadata.max_score`, then `10`.

Each submitted score creates a new evaluation entry with its own
`evaluation_id`. The latest evaluation is also copied to `evaluations[result_id]`
for backward compatibility with older exporters. The reviewer name is a global
browser field stored in `localStorage`; score forms send it as a hidden
`evaluator` input.

CSV import/export uses these columns:

```text
competition_id,competition_title,problem_id,problem_title,run_id,result_id,result_index,evaluation_id,evaluator,score,max_score,score_category,feedback,created_at,updated_at,model_key,model
```

## Web-change validation

Compile:

```bash
python -m compileall -q scoring
```

Smoke test:

```bash
python - <<'PY'
from scoring.app import app
client = app.test_client()
response = client.get("/")
assert response.status_code == 200
print("ok")
PY
```

For persistence changes, verify that the run log bytes do not change when saving a score; only the sidecar should be written.
