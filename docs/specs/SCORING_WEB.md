# Scoring web application

## Runtime

Entry point:

```bash
python scoring/app.py
```

Development URL:

```text
http://127.0.0.1:8000
```

The current app uses Flask debug mode and binds only to loopback. It is not a production deployment configuration.

The app resolves paths from the repository root inferred from `scoring/app.py`:

```python
BASE_DIR = Path(__file__).resolve().parents[1]
LOGS_DIR = BASE_DIR / "logs"
RESULTS_DIR = BASE_DIR / "data" / "results"
```

This lets the same code run from a local shell and from a systemd service whose
working directory is the repository root.

## Routes

| Method/path | Behavior |
| --- | --- |
| `GET /` | groups logs by competition |
| `GET /competition/<competition_id>` | lists problems with run and score counts |
| `GET /competition/<competition_id>/problem/<problem_id>` | lists runs and shows problem text |
| `GET /competition/<competition_id>/problem/<problem_id>/run/<run_id>` | review page for model answers |
| `GET /run/<run_id>` | legacy lookup and redirect |
| `POST /score` | writes one evaluation into the score sidecar |

## Discovery behavior

`iter_log_paths()` scans `logs/**/*.json`, skipping hidden/service paths and old
`*.evaluation.json` files. Invalid JSON is skipped silently by listing
functions. This means a missing run in the UI may be a malformed file rather
than an absent file.

Metadata fallback logic supports old logs:

- missing competition ID may come from path or become `legacy`;
- missing problem ID may come from path, nested problem metadata or filename;
- missing titles fall back to IDs.

## Persistence

The score route loads the selected run, uses `result_index`, and writes:

```text
data/results/<competition_id>/<problem_id>/<run_id>.json
```

The route expects score input convertible to `int`. The UI contract is score `0–10`; server-side range enforcement is currently not explicit in `app.py`.

## Web-change validation

Compile:

```bash
python -m compileall -q scoring
```

Smoke test:

```bash
python - <<'PY'
from scoring.app import app
client = app.test_client()
response = client.get("/")
assert response.status_code == 200
print("ok")
PY
```

For persistence changes, create a temporary run/sidecar fixture outside tracked data or use a temporary working directory. Verify that the run log remains unchanged.
