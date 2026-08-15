# Operational scripts

## Secret preflight

```bash
python scripts/check_secrets.py --models gpt,claude,deepseek,gemini,gigachat,grok,glm,yandexgpt
```

The command checks required variable presence and must never print values or
make network calls. New aliases accepted by the preflight are
`gemini`/`google`, `grok`/`xai` and `glm`/`zai`/`zhipu`.

## Problem-data validation

```bash
python scripts/validate_problem_data.py data/competitions --all --strict
```

The validator checks the canonical direct-child layout. `--strict` is accepted for command compatibility; validation is canonical either way.

## Dataset export

Only scored answers:

```bash
python scripts/export_scoring.py
```

All answers:

```bash
python scripts/export_scoring.py --all
```

JSONL:

```bash
python scripts/export_scoring.py --format jsonl
```

The exporter joins run logs and sidecars using competition/problem/run/index. It also supports some legacy single-answer log shapes.

## Public-results export

Generate the read-only public projection locally:

```bash
python scripts/export_public_results.py
```

The default output is the ignored `public_results/generated/` directory. The
export contains both Math Cup 2026 stages as independent competition records,
all 10 configured model rows, and one JSON document for every selected
successful answer. The public UI selects exactly one record at a time through
benchmark, year and stage buttons. For each model/problem cell the selection
policy is:

1. newest successful attempt with an effective finalization;
2. otherwise, newest successful attempt that has at least one evaluation;
3. otherwise, newest successful attempt without a public score;
4. otherwise, no link for the cell.

The public score is the effective shared finalization: a persisted organizer
decision or the derived unanimous two-review extreme. Individual checks and
their median are never published as the result. Cells without an effective
finalization are explicitly shown as `На проверке`.
Math Cup 2026 qualifying uses the integer `0..4` scale and half-up rounding;
the final keeps its existing `0..2` scale. Run logs and sidecars remain
unchanged during export. A solution document may include the optional shared
comment from its effective finalization as `review.final.feedback`. This is the
single collegially approved public comment. The documents omit individual
reviewer scores and comments, all reviewer/organizer identities, raw provider
responses, request payloads, errors and internal paths. They never contain a
`review.experts` collection.
Final comments carrying `feedback_review_required: true` are editorial drafts,
not approved comments, and the exporter suppresses their text until the flag is
cleared in the scoring UI.

The exporter also copies selected competition assets into
`generated/assets/<competition_id>/` and rewrites local `assets/...` references
in statements and official solutions to those public files. Plain HTTP(S) links
in published Markdown are normalized to clickable links. The public HTML pages
use the local CS Space SVG as their favicon. Public solution rendering keeps
model logs immutable, works around a missing KaTeX private-use negation glyph
in the browser, and centers long prose in a wider reading column. Leaderboard
participant and member names wrap without truncation.
After a successful projection build, the exporter removes generated solution
JSON documents that are no longer referenced by the new `generated/data.js`;
this prevents obsolete schemas or retired attempts from remaining addressable.
The problem statement is collapsed by default. When the optional shared
finalization comment is non-empty, one final-comment block appears inside the
result section. Final comments use the same sanitized Markdown and KaTeX
pipeline as solutions, so mathematical notation must be stored as LaTeX inside
`$...$` or `$$...$$`. On a single-model solution page the reading order is
result and optional comment, statement, model solution, then official solution.
The result is therefore the first content card and its optional shared comment
appears in the same score-colored card. The statement and official
solution keep neutral card outlines that do not change with the score; only the
model solution and result use the score-colored outline. The result section
contains the verdict, score, metrics and optional shared comment.
Solution cards use a solid dark surface and a score-colored outline matching
the leaderboard cell. The dark-theme status palette uses muted sage for a full
score, ochre for a partial score and terracotta for zero; result gradients are
not used. Their independent
open/closed states are saved in browser local storage and restored across task
navigation and later visits; storage failure falls back to the collapsed HTML
defaults without blocking the page. Clicking an empty background area inside
an expanded reading card collapses it, while text, formulas, links and controls
keep their normal interaction. Task headers in the leaderboard are links,
not sort controls. `/problems/<competition-id>/<task-slug>` opens the task
statement, official solution and every model answer in leaderboard model order,
with all sections initially collapsed and each model card carrying its verdict.
Inside an expanded model card, the result and optional shared comment precede
the answer and use the same score color as the card outline. Model names in the
leaderboard link to `/problems/<competition-id>/<model-page-slug>`, which lists
that model's result, optional shared comment and full answer for every task in
the stage. Claude model-page slugs omit the redundant `claude-` prefix, for
example `fable-5`.
The fallback public metadata also supplies team member names and stage-specific
competition rules. The leaderboard switches that rules block together with the
selected release; generated model data continues to overlay only the result
matrix.

Each exported model row also contains `points`, the sum of all non-null
absolute task scores for that stage. The public table uses this field for its
default descending order; it is distinct from `solved`, which remains the count
of perfect-score cells for compatibility.

The standalone Object Storage deployment uses `/` for the leaderboard,
`/problems` for the catalog, and
`/problems/<competition-id>` for all statements and official solutions in a
stage,
`/problems/<competition-id>/<task-slug>` for all answers to one task,
`/problems/<competition-id>/<model-page-slug>` for all answers from one model,
and
`/problems/<competition-id>/<task-slug>/<model-slug>` for model answers. Because
Object Storage has no application router, deployment uploads the catalog HTML
under the exact extensionless `problems` key, the problem-set shell under each
competition key, the task shell under every concrete task key, the model shell
under every model-page key and the solution shell under every concrete
task/model key. Legacy
`.html` objects remain for backward compatibility. Generated solution JSON must be uploaded before
`generated/data.js`, so the matrix never links to a missing object.

On narrow screens the sticky rank and participant columns are compact. Cost,
token and accuracy columns are hidden, leaving the score sum and task results
visible immediately; the complete metrics remain available on wider screens.
Catalog cards contain equally styled links to the full problem set and
leaderboard, while the rest of each card also opens the leaderboard.

For the qualifying stage's answer-only tasks 1–6, the approved bulk operation
for every zero-score selected result is explicit and idempotent. Partial-credit
results keep their specific organizer comments:

```bash
python scripts/approve_qualifying_wrong_answers.py
python scripts/approve_qualifying_wrong_answers.py --apply
```

It preserves scores, replaces the shared final comment with `Неверный ответ.`
and clears the editorial GPT-review flag.

To change an existing competition's score scale, preview and then apply the
explicit migration:

```bash
python scripts/migrate_score_scale.py \
  --competition math-cup-2026-qualifying \
  --max-score 4 \
  --score-step 1
python scripts/migrate_score_scale.py \
  --competition math-cup-2026-qualifying \
  --max-score 4 \
  --score-step 1 \
  --apply
```

The command updates only the named competition's metadata and evaluation
sidecars. It rescales scores proportionally, rounds half up to an integer,
writes atomically, and is idempotent. The migration currently requires
`--score-step 1`.

The former scoring-host compatibility exporter is retired. Its timer must stay
disabled, and Nginx must not serve public files from the scoring domain:

```bash
sudo systemctl disable --now public-results-export.timer
```

The active scoring-host Nginx configuration uses:

```nginx
location = /results { return 410; }
location ^~ /results/ { return 410; }
```

The standalone Object Storage site is the only public results surface. Generate
and publish its sanitized snapshot explicitly until a separate S3 bridge is
implemented and verified.

## Evaluation-pool CSV

The web UI can export and import manual checks without touching model run logs:

- competition-level export: `GET /competition/<competition_id>/evaluations.csv`;
- task-level export: `GET /competition/<competition_id>/problem/<problem_id>/evaluations.csv`;
- add `?evaluator=<name>` to export only one reviewer's checks;
- import CSV from the same competition or task pages.

CSV rows are matched by `competition_id`, `problem_id`, `run_id` and
`result_id`. Within a result, an imported named reviewer replaces that
reviewer's current check (and the same `evaluation_id` is also replaced).
Rows without a reviewer remain distinct by `evaluation_id` for legacy
compatibility.

## Server sync

Private configuration:

```text
config/server.env
```

Template:

```text
config/server.env.example
```

Push:

```bash
python scripts/sync_logs.py push
```

Pull:

```bash
python scripts/sync_logs.py pull
```

Dry run:

```bash
python scripts/sync_logs.py push --dry-run
python scripts/sync_logs.py pull --dry-run
```

The script requires local `rsync` and SSH access. Push uses `--ignore-existing`; this protects existing remote files but does not implement conflict resolution. Detailed user instructions are in root `SERVER.md`.

## Server-side flagship runs

The flagships introduced in the 2026-08-01 snapshot can be launched for the
2026 final with live tqdm progress:

```bash
python scripts/run_new_models_math_cup_2026_final.py
python scripts/run_new_models_math_cup_2026_final.py --yes
```

The script defaults to Math Cup 2026 final tasks and the seven newly selected
models: `claude-fable-5`, `claude-opus-5`, `gemini-3.1-pro-preview`,
`GigaChat-3-Ultra`, `grok-4.5`, `gpt-5.6-sol` and `aliceai-llm`. It is dry-run by
default, prints a cost estimate, and writes each `runner.py` stdout/stderr log
under `run-output/new-models-2026-final/`. Run logs themselves go to the
configured `--logs-dir`, normally `/opt/olympiad-scorer/shared/logs`.

For arbitrary competitions or one-off task batches, use the generic launcher:

```bash
python scripts/run_model_batch.py \
  --competition math-cup-2026-qualifying \
  --problems 01 \
  --models all
```

`--models all` runs all active configured models from `models/*/versions.py`.
Without an explicit token budget the launcher uses the common 256,000-token
benchmark budget. An explicit `--max-tokens` overrides that default for every
selected pair; adapters split larger totals across preserved-state continuation
requests only when a provider API requires it.
Claude treats that value as its primary reasoning/output budget. If all of it
is consumed by thinking without visible text, the adapter preserves the signed
assistant blocks and makes one separately logged final-answer request of up to
16,384 tokens with thinking disabled, matching the rule published on the
results site.
`--models new` is the narrower operational shortcut for only the seven models
introduced in the 2026-08-01 snapshot.
Add `--detach --yes` on the server to start the run in a new session, write
progress to `<output-dir>/launcher.log`, and allow the SSH connection to close
without stopping child `runner.py` processes.
The batch launcher does not equate a clean `runner.py` process exit with model
success: it reads the emitted run JSON and reports failure unless the run is
completed and every selected result contains a non-empty answer without an
error.

## Formatting math in published final comments

The reviewed one-off migration for approved Math Cup final comments is dry-run
by default and applies only when the stored text still matches the audited
original exactly:

```bash
python scripts/format_final_comment_math.py
python scripts/format_final_comment_math.py --apply
```

It converts formula fragments to the `$...$` LaTeX form used by the public
Markdown/KaTeX renderer. It refuses comments awaiting review and refuses to
overwrite a later human edit.

## Generated artifacts

Model runs and review results are project data and are versioned:

- `logs/**/*.json`;
- `data/results/**/*.json`;
- curated result CSV files under `data/results/`.

Normal generated files still ignored by Git are caches, virtual environments and
ad-hoc exports outside the tracked data tree.

Before committing new logs/results, scan for accidental credentials. Provider
tokens, Authorization headers, cookies and private server config must never be
committed.
