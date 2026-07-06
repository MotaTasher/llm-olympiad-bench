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
  model_columns
  model_groups
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
| `GET /` | Russian competition cards for competitions with an inferred year, grouped by year |
| `GET /competition/<competition_id>` | matrix: rows are tasks, columns are models; task title opens anonymous scoring |
| `GET /competition/<competition_id>/stats?model=<model_key>` | aggregate model statistics across all reviewers, with optional model detail |
| `GET /competition/<competition_id>/checks` | separate all-checks statistics page; shows all reviewers, aggregate model-task scores and the raw evaluation table |
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

The competition overview, model statistics and all-checks pages share a single
competition shell. The shell renders the competition title and the three
server-side navigation links: `Меню соревнования`, `Статистика моделей` and
`Все проверки`. The active link is marked with `aria-current="page"`. The
navigation is a normal `<nav class="competition-tabs">`; it is not a JavaScript
tablist, because each section is a separate HTTP page. The same Jinja component
is reused by `competition.html`, `stats.html` and `checks.html`.

The competition matrix presents active model columns in fixed provider groups:
`anthropic`, `deepseek`, `google`, `gigachat`, `xai`, `zai`, `openai`,
`yandexgpt`. Unknown future providers sort after these groups. The
`model_columns` order follows this provider order, and the order inside each
provider follows the provider `VERSIONS` list instead of alphabetic model IDs.
Every problem's `model_states` list is built in the same order as
`model_columns`.

Each model column carries display metadata in addition to stable identifiers:
`provider_label`, `provider_order`, `model_order`, `short_label` and `label`.
`label` remains the full technical model ID. Known short labels are used in the
matrix header, while the full model ID remains available through the link
`title`, `aria-label` and a hover/focus tooltip. The grouped header data is also
available as:

```text
competition["model_groups"] = [
  {"provider": "anthropic", "label": "Claude", "models": [...]},
  {"provider": "deepseek", "label": "DeepSeek", "models": [...]},
  {"provider": "google", "label": "Gemini", "models": [...]},
  {"provider": "gigachat", "label": "GigaChat", "models": [...]},
  {"provider": "xai", "label": "Grok", "models": [...]},
  {"provider": "zai", "label": "GLM", "models": [...]},
  {"provider": "openai", "label": "OpenAI", "models": [...]},
  {"provider": "yandexgpt", "label": "Яндекс", "models": [...]},
]
```

On `/competition/<competition_id>`, the matrix wrapper uses scoped
`competition-matrix-wrap` / `competition-matrix` classes. It does not impose a
fixed or viewport-derived vertical height; the page scrolls vertically, while
the wrapper keeps horizontal scrolling for narrow screens and for the current
16 active columns. The table uses compact fixed model columns and must not
expand from full model IDs in tooltips. The first column is scoped for long
wrapping task titles and shows only the problem title as the anonymous-scoring
link, prefixed by the problem number when one exists. It does not render problem
ID, `анонимная проверка`, or maximum-score metadata.

The anonymous scoring page hides model/provider names, metrics and raw JSON from
the reviewer UI. It displays one answer at a time, followed by a full-width
answer-selection panel with numbered navigation and a "next solution" control.
On first entry the app redirects to the same page with a
random `seed`; answer order is shuffled from that seed and remains stable while
the reviewer moves between answer numbers. Initial anonymous entry selects the
first unreviewed successful answer in that deterministic order. Reviewed answers
are skipped while unreviewed answers for the task still exist, and models that
have not produced a successful answer are not included. The page still submits
the underlying `run_id`, `result_id` and `model_key` as hidden form fields so
evaluations are written to the same sidecar format. This is UI-level anonymity,
not a security boundary against inspecting page source.

On the non-anonymous problem page, model selector buttons are grouped
stably relative to the configured model order: run but unreviewed, then
reviewed, then not run. The visible button text is only the model short label;
status remains encoded by the existing cell color and by the `title`/ARIA text.
After a successful `/score` save, the app redirects to the next existing
successful unreviewed answer from a different model for the same task. Search
starts after the current model in the configured model order and wraps to the
start. If no other unreviewed answer exists, the existing post-save redirect is
used.

## Statistics

`GET /competition/<competition_id>/stats` uses the full catalog, not
`catalog_for_reviewer()`. It is global analytics for the competition and
includes evaluations from every reviewer, including legacy evaluations that the
repository normalizes into the evaluation pool. Task pages, anonymous scoring,
competition matrix statuses, delete permissions and "my checks" CSV links remain
reviewer-scoped.

Statistics are aggregated in two levels. First, every successful model solution
is identified by stable `result_id`; all valid evaluations for that solution are
converted to normalized percentages with `score / max_score * 100`, then averaged
into one solution percentage. An unreviewed solution contributes to
`solution_count`, but not to model averages. Second, each model averages these
per-solution percentages, so a solution with ten human evaluations has the same
weight as a solution with one evaluation.

The main model table shows solution count, problem count, reviewed solution
count, raw evaluation count, average percent and full-solution count. It does
not show a cross-task average absolute score, because task maximums can differ.
The old "Модель-задача" matrix was removed from `/stats`; the separate
`/checks` page remains the place for raw evaluation records, reviewers,
comments, CSV actions and model-task aggregates. The optional
`?model=<model_key>` detail section remains and shows per-task solution counts,
reviewed solution counts, evaluation counts, average absolute score, task
maximum, average percent and latest solution time. Unknown `model` query values
must not fail the page; the main table still renders.

## All-checks matrix

`GET /competition/<competition_id>/checks` builds aggregate cells from all
evaluation records by every reviewer. For each `problem_id × model_key` pair it
precomputes four values in Python:

- median;
- average;
- maximum;
- minimum.

Median is the default visible mode. The page renders a compact radio-based
segmented control in this order: `Медиана`, `Среднее`, `Максимум`, `Минимум`.
Changing the radio selection updates already-rendered `data-*` values in the
browser; it does not navigate, reload, send HTTP requests, alter browser
history or use `?mode=` links. The legacy `mode` query parameter is not required
for rendering and is ignored by the UI.

The aggregate table reuses the same matrix presentation as the overview matrix:
two-level provider/model headers, provider grouping, short model labels,
model-ID tooltips, first task column, score-cell base markup and cell color
classes. The first task column shows only the problem title as a link to
anonymous scoring; it does not show problem IDs, problem numbers, maximum
scores or metadata. Compact aggregate cells show only the selected score text.
They do not show `/ max_score`, evaluation counts, percentages or aggregate
mode labels. The raw evaluation log remains a separate table below the matrix
and keeps task, model, reviewer, score, comment, time, links and CSV actions.

## Index page

The index is a simple competition gallery. It passes only visible
`competition_groups` to `index.html`; groups with `year is None` are hidden on
`/` without mutating the catalog returned by `build_catalog()`. Those
competitions remain in `competition_map`, remain on disk and continue to open
through direct `/competition/<competition_id>` URLs. The index never renders a
`Без года` heading. If no visible competitions remain after filtering, it shows:

```text
Соревнования не найдены.
```

Each card is one real `<a class="card competition-card">` link, with no nested
links and no JavaScript navigation. Standard keyboard focus and browser link
actions, including opening in a new tab, must keep working.

Card content is intentionally compact:

- competition title;
- competition date formatted as day plus Russian month name, without the year;
- optional description;
- problem count;
- reviewer-scoped progress.

If a description starts with `Полное название:`, that leading full-name sentence
is not rendered on the index card. The card may still render the remaining
description text after that sentence.

The date formatter uses fixed Russian month names and does not depend on the
system locale. Empty dates render as an empty string. Invalid non-empty date
strings are allowed to render as the original value instead of breaking the
page.

Progress is based only on existing attempts visible to the current reviewer:
`answer_count`, `scored_count` and `progress_percent`. It does not use the
theoretical `problem × model` matrix size as the denominator. When there are no
attempts, the progress bar is gray and labeled `Запусков пока нет`. When
attempts exist, the unreviewed portion is red and the reviewed portion is green.
The active bar exposes `role="progressbar"`, `aria-valuemin="0"`,
`aria-valuemax="<answer_count>"`, `aria-valuenow="<scored_count>"` and
`aria-valuetext="Проверено X из N"`.

## Cell status

Model cell status is computed by pure functions in `scoring/repository.py`.

Rules:

- `not_run`: no attempts for the model/problem;
- `error`: latest attempt has no successful non-empty answer;
- `unscored`: latest attempt has a successful non-empty answer and no score;
- `zero`: latest successful answer score is `0`;
- `partial`: `0 < score < max_score`;
- `full`: score is equal to `max_score` within float tolerance.

The primary status is based on the latest attempt timestamp. If the latest attempt is an error but an earlier successful answer was scored, the cell remains `error` while tooltip text reports the earlier scored answer. Tooltips and `aria-label` include model, state, score, latest attempt, attempt count, latency, tokens and error summary where available.
Overview and all-checks matrices share one compact color contract:

- gray: the model was not run;
- gray dashed/error: the latest attempt has no successful answer;
- white: a successful answer exists and is waiting for a visible evaluation;
- red: score is zero;
- yellow: score is between zero and the maximum;
- green: score equals the maximum within tolerance.

Compact cells show only `?`, an empty string or the formatted numeric score.
White unscored cells use `?`; gray error and not-run cells are empty. Textual
status names remain in `title`, tooltips and `aria-label` metadata, not as
visible cell text.

## Score persistence

The normal task page and anonymous page use a one-column review sequence:

1. task statement;
2. closed `<details>` block labeled `Показать эталонное решение`, containing any available `answer` and `solution`;
3. selected LLM answer;
4. score form, evaluation pool/history, telemetry, raw JSON and navigation.

Authenticated reviewers see only their own evaluation entries, score summaries,
cell statuses and evaluation counts on task pages, anonymous scoring pages and
competition matrices. Evaluation entries from other reviewers are intentionally
hidden there to avoid bias during review. `/stats` is the exception: it is
competition-level analytics across all reviewers. Full cross-reviewer row data
also remains available through CSV export/import routes and the separate
all-checks page, which can aggregate every reviewer score per model-task cell as
median, average, maximum or minimum.

Statement, reference answer/solution and model answer are rendered in reusable
scrollable content containers so wide Markdown tables, code blocks and MathJax
formulas scroll inside the panel instead of widening the page.
Markdown image or file links that use relative `assets/...` paths are served
from the selected competition directory, `data/competitions/<competition_id>/assets/`.
Rendered Markdown/LaTeX blocks expose copy buttons that copy the original source
text captured before browser-side Markdown and MathJax rendering. The normal
task page also exposes a copy button for the cleaned JSON result shown in the
raw-result details block. Copy controls are browser-only and do not write logs
or sidecars.

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
- score is a finite number and `0 <= score <= max_score`;
- `max_score` from `problem.metadata.max_score`, then `competition.metadata.max_score`, then `10`.

The score form shows both an official-scale range input and a manual number
input. The range uses `score_step` from problem metadata, then competition
metadata, then fallback `1`; the same arithmetic progression from `0` to
`max_score` is rendered as visible tick labels under the slider. The slider/tick
row width scales from the number of intervals, with bounded per-interval sizing,
so a binary scale such as `0..2` does not stretch across the full form. The range
also drives the quick buttons `0`, conditional `Половина` and `Максимум`. The
manual number input uses `step="any"` and can submit a non-grid fractional score
such as `12.5`; `score_step` is a UI scale, not a server-side divisibility
constraint. The `Половина` button is rendered only when `max_score / 2` lies on
the official range grid.

Each submitted score creates a new evaluation entry with its own
`evaluation_id`. The latest evaluation is also copied to `evaluations[result_id]`
for backward compatibility with older exporters. The reviewer identity for new
evaluations is always `current_user.username`; `/score` does not read or trust
any `evaluator` value submitted by the browser. Old sidecars with arbitrary
`evaluator` values remain readable without migration. `/score/delete` only
deletes evaluations owned by the authenticated reviewer.

## Competition grouping

`build_catalog()` returns `competition_groups` with this shape:

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
from model runs does not affect historical ordering.

The index route filters this list before rendering and passes only groups whose
`year` is not `None`. The unfiltered catalog contract remains available to
other routes and callers.

CSV import/export uses these columns:

```text
competition_id,competition_title,problem_id,problem_title,run_id,result_id,result_index,evaluation_id,evaluator,score,max_score,score_category,feedback,created_at,updated_at,model_key,model
```

Visible timestamps in active scoring templates are formatted with fixed Russian
month names to day and minute precision, for example `29 июня 2026` and `13:24`
on separate lines in main UI blocks. Raw timestamp strings remain unchanged in
logs, sidecars, CSV, hidden fields and machine-readable `datetime`/`title`
attributes.

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
