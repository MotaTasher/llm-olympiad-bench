from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for


LOGS_DIR = Path("logs")

app = Flask(__name__)


def list_logs() -> list[dict]:
    runs = []
    for path in sorted(LOGS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            runs.append(
                {
                    "run_id": data.get("run_id", path.stem),
                    "timestamp": data.get("timestamp", ""),
                    "problem_file": data.get("problem_file", ""),
                    "count": len(data.get("results", [])),
                }
            )
        except Exception:
            continue
    return runs


def load_run(run_id: str) -> dict:
    path = LOGS_DIR / f"{run_id}.json"
    if not path.exists():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def save_run(run_id: str, data: dict) -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    (LOGS_DIR / f"{run_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@app.get("/")
def index():
    return render_template("index.html", runs=list_logs())


@app.get("/run/<run_id>")
def review_run(run_id: str):
    return render_template("review.html", run=load_run(run_id))


@app.post("/score")
def score():
    run_id = request.form["run_id"]
    model = request.form["model"]
    data = load_run(run_id)
    for result in data.get("results", []):
        if result.get("model") == model:
            result["score"] = int(request.form["score"])
            result["scored_by"] = request.form.get("scored_by") or None
            result["score_comment"] = request.form.get("comment") or None
            result["scored_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            break
    save_run(run_id, data)
    return redirect(url_for("review_run", run_id=run_id))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
