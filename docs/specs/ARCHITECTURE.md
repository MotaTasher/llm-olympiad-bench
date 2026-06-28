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
runner.create_model(alias)
   │
BaseModel.solve(problem_text)
   │
SolveResult
   │
runner.write_log()
   │
logs/<competition_id>/<problem_id>/<run_id>.json
```

Adapters run sequentially. One provider failure should become a result with `error`, allowing other providers and log writing to continue.

## Scoring flow

```text
logs/**/*.json
   │
scoring/app.py discovers and groups runs
   │
reviewer submits POST /score
   │
data/results/<competition_id>/<problem_id>/<run_id>.json
```

Run logs remain the source of model answers. Sidecars are the source of manual scoring. The web app merges them only for display.

## Dataset export flow

```text
logs/**/*.json + data/results/**/*.json
   │
scripts/export_scoring.py
   │
CSV or JSONL
```

The join key is:

```text
competition_id + problem_id + run_id + result_index
```

Changing ordering of `results[]` after scoring breaks that association. Treat completed run logs as immutable.

## Environment-loading order

`runner.load_env()` performs:

1. root `.env` for backward compatibility;
2. all `models/*/secrets/.env` and `models/*/secrets/*.env`;
3. removal of inherited model-selection variables unless `--allow-env-model-overrides` is used;
4. `config/models.env` with override enabled.

The intended separation is:

- credentials in provider `secrets/.env`;
- runtime parameters in `config/models.env`;
- default model identifiers in `models/<provider>/versions.py`.

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
