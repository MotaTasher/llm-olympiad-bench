# Troubleshooting and fault localization

Start from the first missing or incorrect persisted artifact, not from the UI symptom.

| Symptom | Likely layer | Inspect | First checks |
| --- | --- | --- | --- |
| runner exits before writing any log | CLI/problem parsing/model construction | `runner.py` | file exists, JSON parses, alias is known |
| log exists and one result has `error` | provider adapter/config | `models/<provider>/`, secret file, `config/models.env` | credential presence, model ID, endpoint, account access |
| all adapters fail similarly | shared environment or prompt/request logic | `runner.load_env`, `models/common.py` | env precedence, forbidden request keys, dependency versions |
| run file exists but is absent from site | log discovery/metadata | `scoring/app.py`, JSON file | launch from repo root, valid JSON, correct path depth |
| site is completely empty | no readable logs | `logs/` | `find logs -type f`, parse each JSON |
| score form returns an error | route input or run lookup | `POST /score`, `find_run_path` | IDs, result index, integer score |
| score appears then disappears | sidecar path/write/sync issue | `data/results/`, `save_result_sidecar` | write permissions, matching IDs, remote pull overwrite |
| export omits an evaluated answer | join-key mismatch | run log, sidecar, `export_scoring.py` | competition/problem/run IDs and result index |
| wrong model version runs | env precedence | `versions.py`, `config/models.env`, shell | inherited env and `--allow-env-model-overrides` |
| task text is empty or truncated | import/data contract | problem JSON, source PDF | `statement`, JSON escaping, import report |
| sync command fails immediately | local config/tooling | `sync_logs.py`, `config/server.env` | remote value, `rsync` installed, SSH port |
| sync connects but cannot write | server permissions/path | remote target | SSH user, absolute path, directory permissions |

## Minimal diagnostic commands

```bash
python -m compileall -q runner.py models scripts scoring
python scripts/validate_problem_data.py data/competitions --all --strict
python scripts/check_secrets.py --models gpt,claude,deepseek,gigachat,yandexgpt
find logs -type f -name '*.json' | sort
find data/results -type f -name '*.json' | sort
```

Check all JSON files without modifying them:

```bash
python - <<'PY'
import json
from pathlib import Path

for root in (Path("data/competitions"), Path("logs"), Path("data/results")):
    for path in root.rglob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"ERROR {path}: {exc}")
PY
```

## Error-reporting rule for agents

A useful final report names:

1. the failing layer;
2. the first incorrect artifact or exception;
3. the root cause if proven;
4. the fix;
5. the validation performed;
6. external behavior not tested, such as provider API calls or remote SSH.
