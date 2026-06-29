# Instructions for coding agents

This is the primary instruction file for Codex and other repository agents.

## Mandatory first step

Before changing code or data, read:

1. [`docs/specs/INDEX.md`](docs/specs/INDEX.md)
2. the specifications linked there for the subsystem you will touch
3. the relevant source files and tests/validation commands

Do not start implementation from this file alone. `docs/specs/` is the project map and contract index.

## Project purpose

The project runs several text-only LLM adapters on olympiad problems, stores comparable run logs, provides a Flask UI for manual scoring, and exports scored datasets.

## Non-negotiable contracts

- Model requests are **text-only**. Do not add tools, browsing, code execution, function calling, or provider-side search without an explicit project-wide contract change.
- A model adapter returns `SolveResult`; provider/network errors are captured in `SolveResult.error`, not raised through `runner.py`.
- Run logs are immutable model-output records under `logs/<competition_id>/<problem_id>/<run_id>.json`; new logs use `schema_version: 2`, stable `result_id`, structured telemetry, and atomic incremental writes.
- Human evaluations are stored separately under `data/results/<competition_id>/<problem_id>/<run_id>.json`; new sidecars use `schema_version: 2` and key evaluations by `result_id`.
- Credentials belong only in `models/<provider>/secrets/.env` or private environment variables. Never print, commit, copy, or move secret values.
- Problem sets use `data/competitions/<competition_id>/competition.json` and direct child files `data/competitions/<competition_id>/<problem_id>.json`.
- Task files must not contain `competition_id` or `competition_title`; ownership comes from the parent competition directory.

## Change workflow

1. Read the spec index and identify affected contracts.
2. Inspect the implementation; do not trust documentation over code when they disagree.
3. Make the smallest compatible change.
4. Run the relevant validation commands.
5. Update documentation in the same change.
6. Report exactly what changed, what was verified, and what could not be verified.

## Documentation update matrix

| Changed area | Documentation that must be reviewed |
| --- | --- |
| repository layout or a new subsystem | `docs/specs/PROJECT_MAP.md`, `docs/specs/INDEX.md` |
| problem, competition, log, or score JSON | `docs/specs/DATA_CONTRACTS.md`, `docs/ADDING_PROBLEMS.md` |
| `runner.py` or CLI flags | `README.md`, `docs/specs/ARCHITECTURE.md`, `docs/LOCAL_SETUP.md` |
| model adapter, aliases, env loading, text-only policy | `docs/specs/MODEL_ADAPTERS.md`, provider README |
| Flask routes, templates, score persistence | `docs/specs/SCORING_WEB.md`, `docs/LOCAL_SETUP.md` |
| server sync or export scripts | `SERVER.md`, `docs/specs/OPERATIONS.md` |
| dependencies or setup commands | `requirements.txt`, `README.md`, `docs/LOCAL_SETUP.md` |
| recurring failure mode | `docs/specs/TROUBLESHOOTING.md` |

A code change is incomplete when its affected documentation is stale.

## Validation

Run from the repository root:

```bash
python -m compileall -q runner.py models scripts scoring
python scripts/validate_problem_data.py data/competitions --all --strict
python scripts/export_scoring.py --all --output /tmp/olympiad-scorer-check.csv
```

For web changes, also run the Flask test-client smoke check described in `docs/LOCAL_SETUP.md`.

Provider API smoke tests are optional when credentials are unavailable. In that case, verify import/compile behavior and state that external calls were not tested.

## Fast fault localization

Use [`docs/specs/TROUBLESHOOTING.md`](docs/specs/TROUBLESHOOTING.md). Start with the persisted artifact:

- no log file: `runner.py`, env loading, adapter creation
- log exists with `error`: provider adapter or credentials/runtime configuration
- log is valid but absent from UI: `scoring/app.py`, working directory/path, malformed metadata
- score not saved: `/score` route, sidecar path, write permissions
- export misses rows: sidecar/run IDs or `scripts/export_scoring.py`
- sync fails: `scripts/sync_logs.py`, `config/server.env`, SSH/rsync

## Repository hygiene

Logs and scoring sidecars are versioned project data. Before committing new files
under `logs/` or `data/results/`, scan for accidental credentials. Do not modify
existing generated logs, scoring sidecars, notebooks, or sample datasets unless
the task requires it. Never add `__pycache__`, `.DS_Store`, `__MACOSX`, virtual
environments, private server config, or real secret files to an archive or
commit.
