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
