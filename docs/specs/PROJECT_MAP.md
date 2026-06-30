# Project map

## Root files

| Path | Responsibility |
| --- | --- |
| `README.md` | concise user onboarding and navigation |
| `AGENTS.md` | primary Codex/general-agent rules |
| `CLAUDE.md` | Claude entry point |
| `CODEX.md` | explicit Codex pointer to `AGENTS.md` |
| `SERVER.md` | user workflow for server sync |
| `requirements.txt` | Python runtime dependencies |
| `runner.py` | CLI orchestration, adapter selection, log writing |
| `olympiad_data.py` | shared competition/problem loading and canonical directory scanning |
| `.gitignore` | blocks credentials, caches and runtime artifacts |

## Runtime subsystems

```text
models/
  base.py                 BaseModel and SolveResult contract
  common.py               shared prompt, env helpers, text-only guard, serialization
  telemetry.py            run-log schema v2 helpers, redaction, hashing, atomic writes, legacy normalization
  <provider>/
    <provider>.py         provider API integration
    versions.py           available/default model identifiers
    README.md             provider-specific setup
    secrets/.env          local credentials; never committed

scoring/
  app.py                  Flask routes, redirects and score request validation
  auth.py                 SQLite-backed reviewer accounts, password hashes and Flask-Login users
  repository.py           one-pass catalog builder, log/sidecar merge, model-cell status logic
  cost_estimator.py       local best-effort cost estimate for configured model runs
  README.md               closed scoring-site auth and user-management operations
  templates/              HTML pages

scripts/
  check_secrets.py        credential presence checks without printing values
  validate_problem_data.py problem/competition JSON validation
  export_scoring.py       merge run logs and sidecars into CSV/JSONL
  sync_logs.py            rsync push/pull for logs and score sidecars
```

## Data directories

| Path | Contents | Mutability |
| --- | --- | --- |
| `data/competitions/` | source competitions and problem sets | versioned source data |
| `logs/` | model run records | generated, versioned benchmark data |
| `data/results/` | manual score sidecars and exports | generated, versioned review data |
| `notebooks/` | exploratory/manual workflows | not authoritative |
| `config/models.env` | non-secret runtime configuration | versioned |
| `config/server.env` | private SSH/rsync targets | local only |
| `instance/` | local Flask instance files such as `scorer-auth.sqlite3` | runtime private data, ignored |

## Canonical problem-set layout

```text
data/competitions/<competition_id>/
  competition.json
  <problem_id>.json
  assets/
```

`assets/` is optional. Problem JSON files are direct children of the competition directory. `competition.json`, hidden files, temporary files, `assets/`, directories and unknown non-JSON files are not treated as problems.

## Ownership rules

- Problem text and metadata: `data/competitions/`.
- Generated model answers: `logs/`.
- Human evaluation: `data/results/`.
- Provider details: corresponding `models/<provider>/` directory.
- Shared API policy, result serialization and telemetry helpers: `models/common.py`, `models/base.py` and `models/telemetry.py`.
- User documentation: root README, `docs/` and provider READMEs.
- Agent contracts: `AGENTS.md`, `CLAUDE.md`, `CODEX.md`, `docs/specs/`.
- Scoring user accounts: `instance/scorer-auth.sqlite3` by default or `SCORER_AUTH_DB`.
