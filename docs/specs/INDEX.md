# Project specification index

Verified against the repository on **2026-06-29**.

This directory is the first stop for coding agents. It describes the current implementation, stable contracts, file ownership, validation commands, and fault-localization paths.

## Reading order

1. [`PROJECT_MAP.md`](PROJECT_MAP.md) — where each subsystem lives.
2. Read the specification matching the requested change.
3. Read [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) before debugging.
4. Read [`CHANGE_CHECKLIST.md`](CHANGE_CHECKLIST.md) before finishing.

## Task-to-spec map

| Task | Read first |
| --- | --- |
| change repository layout or add a subsystem | [`PROJECT_MAP.md`](PROJECT_MAP.md), [`ARCHITECTURE.md`](ARCHITECTURE.md) |
| change problem import or JSON fields | [`DATA_CONTRACTS.md`](DATA_CONTRACTS.md), [`../ADDING_PROBLEMS.md`](../ADDING_PROBLEMS.md) |
| change `runner.py` or log generation | [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DATA_CONTRACTS.md`](DATA_CONTRACTS.md) |
| add or modify a model provider | [`MODEL_ADAPTERS.md`](MODEL_ADAPTERS.md) |
| change Flask UI or scoring persistence | [`SCORING_WEB.md`](SCORING_WEB.md), [`DATA_CONTRACTS.md`](DATA_CONTRACTS.md) |
| change sync/export/secret checks | [`OPERATIONS.md`](OPERATIONS.md) |
| diagnose a failure | [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) |
| prepare a final agent response | [`CHANGE_CHECKLIST.md`](CHANGE_CHECKLIST.md) |

## Sources of truth

Use this priority when information conflicts:

1. executable code and current file layout;
2. persisted JSON examples and validation behavior;
3. files in `docs/specs/`;
4. user-facing README files;
5. notebooks and old logs.

When code and specs disagree, do not silently follow either one. Determine intended compatibility, update the implementation or the spec as required, and report the discrepancy.

## Stable boundaries

The following are cross-subsystem contracts and require coordinated updates:

- `BaseModel.solve(problem: str) -> SolveResult`;
- problem and competition JSON fields;
- run-log structure;
- scoring sidecar structure;
- model aliases in `runner.py`;
- text-only request policy;
- `logs/` and `data/results/` directory layout.

Current active benchmark columns are documented in
[`MODEL_ADAPTERS.md`](MODEL_ADAPTERS.md) and
[`SCORING_WEB.md`](SCORING_WEB.md); after adding Gemini/Grok/GLM the configured
set is 8 provider groups and 16 active model columns.

## Documentation maintenance rule

Every implementation change must review the update matrix in root [`AGENTS.md`](../../AGENTS.md). Update the relevant spec in the same change. When a new recurring failure is discovered, add it to `TROUBLESHOOTING.md`.
