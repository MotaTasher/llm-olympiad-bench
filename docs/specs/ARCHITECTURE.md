# Architecture

## Main execution flow

```text
canonical problem file
   │
   ├─ olympiad_data.resolve_problem() reads parent competition.json
   └─ olympiad_data.load_problem() reads statement
   │
runner derives log metadata from CompetitionRecord + ProblemRecord
   │
runner creates schema_version=2 run-log with status=running
   │
runner creates one result_id/result status=running before each model call
   │
BaseModel.solve(problem_text)
   │
SolveResult
   │
runner atomically updates the JSON after each result and final status
   │
logs/<competition_id>/<problem_id>/<run_id>.json
```

Adapters run sequentially. One provider failure should become a result with `error`, allowing other providers and log writing to continue.
The runner uses `models/telemetry.py` for safe command/runtime metadata, prompt/problem hashes, recursive secret redaction and same-directory temporary-file writes followed by `os.replace`.

## Scoring flow

```text
data/competitions + logs/**/*.json + data/results/**/*.json
   │
scoring/repository.py builds a catalog in one pass
   │
competition → problem → model state → attempts/evaluation
   │
reviewer submits POST /score
   │
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Run logs remain the source of model answers. Sidecars are the source of manual scoring. The web app merges them only for display.
New sidecars use `schema_version: 2` and key evaluations by `result_id`; old sidecars keyed by string result index remain readable.

## Dataset export flow

```text
logs/**/*.json + data/results/**/*.json
   │
scripts/export_scoring.py
   │
CSV or JSONL
```

The preferred join key is:

```text
competition_id + problem_id + run_id + result_id
```

For old logs and old sidecars, export and UI fall back to string `result_index`. Changing ordering of `results[]` after scoring breaks legacy association. Treat completed run logs as immutable.

## Environment-loading order

`runner.load_env()` performs:

1. root `.env` for backward compatibility;
2. all `models/*/secrets/.env` and `models/*/secrets/*.env`;
3. removal of inherited model-selection variables unless `--allow-env-model-overrides` is used;
4. `config/models.env` with override enabled.

The intended separation is:

- credentials in provider `secrets/.env`;
- runtime parameters and `RUNNER_MODELS` in `config/models.env`;
- default model identifiers in `models/<provider>/versions.py`.

`RUNNER_MODELS=all` expands to every active `VERSIONS` entry from
`models/*/versions.py`, matching the configured columns in the scoring UI.
Explicit CLI `--models` values override `RUNNER_MODELS` for that run.
The active benchmark set is one strongest model per provider; retired
budget/free-tier IDs may remain documented as legacy versions but do not create
scoring UI columns from historical logs.

## Identity rules

Competition metadata for new JSON problem runs is resolved from, in order:

1. explicit CLI overrides;
2. parent `competition.json`.

Problem identity is resolved from the problem JSON `id`, which must match the filename stem in canonical data. IDs written to log paths are slugified to lowercase while preserving Unicode word characters, digits, underscores, dots and hyphens.

## Compatibility boundaries

The implementation currently supports:

- canonical JSON problem field `statement`;
- direct problem JSON files under a competition directory;
- raw Markdown/text files for ad hoc runner use with fallback `default` metadata;
- legacy root-level `logs/*.json`, shown as competition `legacy`.

New persisted problem data must use only the canonical competition directory form.
