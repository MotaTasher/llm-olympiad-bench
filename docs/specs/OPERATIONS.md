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
all 9 configured model rows, and one JSON document for every selected
successful answer. The public UI selects exactly one record at a time through
benchmark, year and stage buttons. For each model/problem cell the selection
policy is:

1. newest successful attempt that has at least one evaluation;
2. otherwise, newest successful attempt without a public score;
3. otherwise, no link for the cell.

When several evaluations exist on the selected result, each score is converted
to the task's current absolute scale and the public score is their median.
Math Cup 2026 qualifying uses the integer `0..4` scale and half-up rounding;
the final keeps its existing `0..2` scale. Run logs and sidecars remain
unchanged during export. The public documents omit
reviewer identities, feedback, raw provider responses, request payloads, errors,
and internal paths.

The exporter also copies selected competition assets into
`generated/assets/<competition_id>/` and rewrites local `assets/...` references
in statements and official solutions to those public files. Plain HTTP(S) links
in published Markdown are normalized to clickable links. The public HTML pages
use the local CS Space SVG as their favicon.

Each exported model row also contains `points`, the sum of all non-null
absolute task scores for that stage. The public table uses this field for its
default descending order; it is distinct from `solved`, which remains the count
of perfect-score cells for compatibility.

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

On the production host, install
`deploy/systemd/public-results-export.{service,timer}` in `/etc/systemd/system/`
and enable the timer. It refreshes the deployed release every minute from the
same log, result, and competition paths used by the scoring service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now public-results-export.timer
sudo systemctl start public-results-export.service
```

Inspect it with:

```bash
systemctl status public-results-export.timer --no-pager
journalctl -u public-results-export.service -n 50 --no-pager
```

The generic Nginx `/results/` location must use `Cache-Control: no-cache` so
HTML and `generated/data.js` are revalidated. Static asset locations
`/results/assets/`, `/results/vendor/` and `/results/generated/assets/` should
use `Cache-Control: public, max-age=604800`; this keeps backgrounds, logos,
fonts and exported problem images across page transitions.
Release directories reuse stable asset names, while `generated/data.js` changes
in place every minute. HTML also carries a query-string asset version as a
second cache-busting layer for clients that retained an older release.

## Evaluation-pool CSV

The web UI can export and import manual checks without touching model run logs:

- competition-level export: `GET /competition/<competition_id>/evaluations.csv`;
- task-level export: `GET /competition/<competition_id>/problem/<problem_id>/evaluations.csv`;
- add `?evaluator=<name>` to export only one reviewer's checks;
- import CSV from the same competition or task pages.

CSV rows are matched by `competition_id`, `problem_id`, `run_id` and
`result_id`. Existing rows with the same `evaluation_id` are replaced; rows
without `evaluation_id` create new checks.

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

`--models all` runs all 9 active configured models from
`models/*/versions.py`. Without an explicit token budget the launcher uses the
common 128,000-token benchmark budget; GigaChat and Alice remain on their
documented API caps of 8,192 and 8,000. An explicit `--max-tokens` overrides
those defaults for every selected pair; Grok and GLM split larger totals across
preserved-state continuation requests.
`--models new` is the narrower operational shortcut for only the seven models
introduced in the 2026-08-01 snapshot.
Add `--detach --yes` on the server to start the run in a new session, write
progress to `<output-dir>/launcher.log`, and allow the SSH connection to close
without stopping child `runner.py` processes.

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
