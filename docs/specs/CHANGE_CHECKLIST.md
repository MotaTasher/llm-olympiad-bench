# Change checklist for agents

## Before editing

- Read `AGENTS.md` and this spec index.
- Identify the contract and persisted artifacts affected.
- Inspect actual code and existing examples.
- Check for credentials or private server data before copying files.

## During editing

- Preserve backward compatibility unless the task explicitly removes it.
- Keep provider-specific logic inside its adapter.
- Keep model answers and human evaluations separate.
- Do not alter generated logs/sidecars to make a test pass.
- Add or update user documentation when commands or behavior change.
- Add or update specs when contracts, paths or ownership change.

## Before finishing

```bash
python -m compileall -q runner.py models scripts scoring
python scripts/validate_problem_data.py data/competitions --all --strict
python scripts/export_scoring.py --all --output /tmp/olympiad-scorer-check.csv
```

Also run subsystem-specific checks:

- web: Flask test-client request;
- import: strict validation of the new competition;
- sync: `--dry-run` only unless real remote access is explicitly requested;
- provider: real API test only when credentials and permission are available.

## Final report

State:

- files changed;
- behavior changed;
- validation results;
- known compatibility decisions;
- anything not tested.
