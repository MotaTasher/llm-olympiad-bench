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
By default it reads data paths relative to the repository root. Deployments can
override those paths with `SCORER_LOGS_DIR`, `SCORER_RESULTS_DIR` and
`SCORER_COMPETITIONS_DIR`.
The site is closed by default. Without a successful login, only `/login` and
Flask static resources are public; all current and future scoring routes are
blocked by a centralized `before_request` rule. HTML GET requests redirect to
`/login?next=<internal path>`. Unsafe or external `next` values are ignored.
Unauthenticated POST requests cannot perform actions.

Authentication uses Flask-Login sessions, Flask-WTF CSRF protection and a local
SQLite user database. The default DB path is:

```text
instance/scorer-auth.sqlite3
```

It can be overridden with `SCORER_AUTH_DB`. `SCORER_SECRET_KEY` provides the
stable Flask session key; without it local development gets a temporary
per-process key and a warning. Session cookies are HTTP-only, SameSite=Lax, and
`SESSION_COOKIE_SECURE` is controlled by `SCORER_COOKIE_SECURE`. Session lifetime
defaults to 12 hours and is configurable with `SCORER_SESSION_HOURS`.

Reviewer accounts are managed only from the Flask CLI:

```bash
flask --app scoring.app user create <username>
flask --app scoring.app user reset-password <username>
flask --app scoring.app user disable <username>
flask --app scoring.app user enable <username>
flask --app scoring.app user list
```

Passwords are generated with `secrets.token_urlsafe(32)`, printed once in the
terminal, and stored only as Werkzeug password hashes. Disabled users cannot log
in and existing sessions are rejected on the next request. Password reset and
enable/disable increment a session version to invalidate old cookies without a
separate session store.

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
| `GET /login` | Russian login form; does not display competition/model data; authenticated users redirect to `/` |
| `POST /login` | CSRF-protected login; unknown user, wrong password and disabled user share the same error |
| `POST /logout` | CSRF-protected logout; clears the session and redirects to `/login` |
| `GET /` | Russian competition cards from canonical data plus log/evaluation counts and live cost estimates, grouped by inferred year |
| `GET /competition/<competition_id>` | live cost estimate plus matrix: rows are tasks, columns are models; task title opens anonymous scoring |
| `GET /competition/<competition_id>/stats?model=<model_key>` | aggregate model statistics and model-task table |
| `GET /competition/<competition_id>/problem/<problem_id>?model=<model_key>&attempt=<result_id>` | task statement, selected model attempt, metrics, score form, attempt switcher |
| `GET /competition/<competition_id>/problem/<problem_id>/anonymous?seed=<seed>&n=<number>` | anonymous scoring page: one numbered answer at a time, without model/provider labels |
| `GET /competition/<competition_id>/evaluations.csv?evaluator=<name>` | export evaluation pool for a competition, optionally filtered by reviewer; "my checks" links use `current_user.username` |
| `GET /competition/<competition_id>/problem/<problem_id>/evaluations.csv?evaluator=<name>` | export evaluation pool for one task, optionally filtered by reviewer; "my checks" links use `current_user.username` |
| `POST /competition/<competition_id>/evaluations/import` | import evaluation-pool CSV for the competition |
| `POST /competition/<competition_id>/problem/<problem_id>/evaluations/import` | import evaluation-pool CSV for one task |
| `GET /competition/<competition_id>/problem/<problem_id>/run/<run_id>` | compatibility redirect to the task page with a model and attempt selected |
| `GET /run/<run_id>` | legacy lookup and redirect |
| `POST /score` | validates run/result/score and appends a sidecar evaluation keyed by `result_id` |
| `POST /score/delete` | deletes one evaluation from a result's evaluation pool |

`model_key` is stable and includes provider plus model ID, for example `openai:gpt-5.5`. `attempt` is optional; when omitted the page shows the latest attempt for the selected model. When present it selects the matching `result_id` without leaving the task page. Configured model columns come from provider `versions.py` `VERSIONS` entries only. The scoring UI does not add extra columns for arbitrary weak or retired models found only in historical logs; `LEGACY_VERSIONS` is documentation only and does not seed the matrix. Explicit aliases for the same active model may be canonicalized, for example `yandexgpt:yandexgpt-5.1/latest` is displayed under `yandexgpt:yandexgpt-5.1`.

The anonymous scoring page hides model/provider names, metrics and raw JSON from
the reviewer UI. It displays one answer at a time, followed by a full-width
answer-selection panel with numbered navigation and a "next solution" control.
On first entry the app redirects to the same page with a
random `seed`; answer order is shuffled from that seed and remains stable while
the reviewer moves between answer numbers. The page still submits the underlying
`run_id`, `result_id` and `model_key` as hidden form fields so evaluations are
written to the same sidecar format. This is UI-level anonymity, not a security
boundary against inspecting page source.

## Cost Estimate

Index and competition pages share one compact local cost control in the page
header. It never launches model calls. By default it estimates every active
model from provider `VERSIONS`, matching the set used by `runner.py --models
all`. The same slider/checkbox settings are stored in browser `localStorage`
and apply to every competition card and competition page.

Controls:

- reasoning budget: integer `0..64000`, default `8000`; `0` means no separate reasoning budget is requested;
- final-answer token cap: integer `512..32000`, default `8000`;
- `include_solved` checkbox defaults to off.

Browser range and number inputs are synchronized for both numeric settings.
Changing a slider, manual input or checkbox immediately recalculates displayed
numbers; there is no recalculation button or HTTP request. Different APIs split
hidden reasoning and visible answer tokens differently, so the estimate is best
effort. The calculation uses local price tables, rough token estimates and the
current USD/RUB rate fetched from the Central Bank of Russia XML daily endpoint
with a local fallback. It must not instantiate provider clients, call model
APIs, create background jobs or write run logs.

When `include_solved` is off, skip logic is evaluated independently for every
`problem × model` pair. A pair is already solved only when existing logs contain
at least one successful attempt for that exact model with a non-empty answer.
API errors and empty answers do not count as solved, and answers from other
models do not cause a skip. The index shows total estimated cost in USD and
RUB on each competition card. The competition page also shows per-model costs
in a full-width table with model price per 1K tokens, estimated USD/RUB cost
and a final total row.

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

The normal task page and anonymous page use a one-column review sequence:

1. task statement;
2. closed `<details>` block labeled `Показать эталонное решение`, containing any available `answer` and `solution`;
3. selected LLM answer;
4. score form, evaluation pool/history, telemetry, raw JSON and navigation.

Statement, reference answer/solution and model answer are rendered in reusable
scrollable content containers so wide Markdown tables, code blocks and MathJax
formulas scroll inside the panel instead of widening the page.
Markdown image or file links that use relative `assets/...` paths are served
from the selected competition directory, `data/competitions/<competition_id>/assets/`.

New sidecars use `schema_version: 2` and store an evaluation pool by `result_id`:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Read precedence:

1. sidecar `evaluation_pool` keyed by `result_id`;
2. old sidecar `evaluations` keyed by `result_id`;
3. old sidecar `evaluations` keyed by string result index;
4. legacy score fields embedded in the run-log.

Every browser POST form includes a CSRF token. CSRF failures return HTTP 400
with a short Russian error message. No working `/register` route exists.

`POST /score` validates:

- competition/problem/run IDs;
- `result_id` belongs to the submitted run;
- `0 <= score <= max_score`;
- `max_score` from `problem.metadata.max_score`, then `competition.metadata.max_score`, then `10`.

Each submitted score creates a new evaluation entry with its own
`evaluation_id`. The latest evaluation is also copied to `evaluations[result_id]`
for backward compatibility with older exporters. The reviewer identity for new
evaluations is always `current_user.username`; `/score` does not read or trust
any `evaluator` value submitted by the browser. Old sidecars with arbitrary
`evaluator` values remain readable without migration.

## Competition grouping

The index route passes `competition_groups` to `index.html`:

```text
[
  {"year": 2026, "competitions": [...]},
  {"year": 2025, "competitions": [...]},
  {"year": None, "competitions": [...]},
]
```

Year inference checks `date`, then `competition_id`, then
`competition_title`, accepting years in the `1900..2099` range. Year groups are
sorted descending and the `None` group is always last. Competitions inside each
year group sort chronologically from earlier to later. The order source is:
full date from `competition.json.date`, then date or month parsed from
`competition_id`, then stable title and ID ordering. Competitions without a
determinable date are placed at the end of their year group. `latest_timestamp`
from model runs is displayed but does not affect historical ordering.

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
from pathlib import Path
import tempfile
from scoring.app import app
from scoring.auth import create_user

tmp = tempfile.TemporaryDirectory()
app.config.update(AUTH_DB=Path(tmp.name) / "auth.sqlite3", TESTING=True)
_, password = create_user(app.config["AUTH_DB"], "smoke-user")
client = app.test_client()
login_page = client.get("/login").get_data(as_text=True)
token = login_page.split('name="csrf_token"')[1].split('value="')[1].split('"')[0]
response = client.post("/login", data={"username": "smoke-user", "password": password, "csrf_token": token})
assert response.status_code == 302
response = client.get("/")
assert response.status_code == 200
print("ok")
PY
```

For persistence changes, verify that the run log bytes do not change when saving a score; only the sidecar should be written.
