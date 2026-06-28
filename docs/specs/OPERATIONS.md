# Operational scripts

## Secret preflight

```bash
python scripts/check_secrets.py --models gpt,claude,deepseek,gigachat,yandexgpt
```

The command checks required variable presence and must never print values.

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

Normal generated files are ignored by Git:

- `logs/**/*.json`;
- `data/results/**/*.json`;
- exported CSV/JSONL;
- caches and virtual environments.

Existing sample logs may still be present in a distributed archive for UI demonstration.
