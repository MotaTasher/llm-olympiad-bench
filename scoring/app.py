from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, url_for


LOGS_DIR = Path("logs")

app = Flask(__name__)


def iter_log_paths() -> list[Path]:
    return sorted(LOGS_DIR.rglob("*.json"), reverse=True)


def load_log(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    data["_log_path"] = str(path)
    return data


def log_competition_id(data: dict, path: Path) -> str:
    value = data.get("competition_id")
    if isinstance(value, str) and value.strip():
        return value
    try:
        parts = path.relative_to(LOGS_DIR).parts
    except ValueError:
        parts = ()
    if len(parts) >= 3:
        return parts[0]
    return "legacy"


def log_competition_title(data: dict, competition_id: str) -> str:
    value = data.get("competition_title")
    if isinstance(value, str) and value.strip():
        return value
    return "Старые прогоны" if competition_id == "legacy" else competition_id


def log_problem_id(data: dict, path: Path) -> str:
    value = data.get("problem_id")
    if isinstance(value, str) and value.strip():
        return value
    try:
        parts = path.relative_to(LOGS_DIR).parts
    except ValueError:
        parts = ()
    if len(parts) >= 3:
        return parts[1]
    problem = data.get("problem")
    if isinstance(problem, dict):
        value = problem.get("id")
        if isinstance(value, str) and value.strip():
            return value
    return path.stem


def log_problem_title(data: dict, problem_id: str) -> str:
    value = data.get("problem_title")
    if isinstance(value, str) and value.strip():
        return value
    problem = data.get("problem")
    if isinstance(problem, dict):
        value = problem.get("title")
        if isinstance(value, str) and value.strip():
            return value
    return problem_id


def list_competitions() -> list[dict]:
    competitions: dict[str, dict] = {}
    for path in iter_log_paths():
        data = load_log(path)
        if not data:
            continue
        competition_id = log_competition_id(data, path)
        item = competitions.setdefault(
            competition_id,
            {
                "competition_id": competition_id,
                "competition_title": log_competition_title(data, competition_id),
                "problem_ids": set(),
                "run_count": 0,
                "scored_count": 0,
                "latest_timestamp": "",
            },
        )
        problem_id = log_problem_id(data, path)
        item["problem_ids"].add(problem_id)
        item["run_count"] += 1
        item["scored_count"] += sum(
            1 for result in data.get("results", []) if result.get("score") is not None
        )
        timestamp = data.get("timestamp", "")
        if timestamp > item["latest_timestamp"]:
            item["latest_timestamp"] = timestamp

    result = []
    for item in competitions.values():
        item = dict(item)
        item["problem_count"] = len(item.pop("problem_ids"))
        result.append(item)
    return sorted(result, key=lambda item: item["latest_timestamp"], reverse=True)


def list_problems(competition_id: str) -> list[dict]:
    problems: dict[str, dict] = {}
    for path in iter_log_paths():
        data = load_log(path)
        if not data or log_competition_id(data, path) != competition_id:
            continue
        problem_id = log_problem_id(data, path)
        item = problems.setdefault(
            problem_id,
            {
                "competition_id": competition_id,
                "competition_title": log_competition_title(data, competition_id),
                "problem_id": problem_id,
                "problem_title": log_problem_title(data, problem_id),
                "run_count": 0,
                "answer_count": 0,
                "scored_count": 0,
                "latest_timestamp": "",
            },
        )
        results = data.get("results", [])
        item["run_count"] += 1
        item["answer_count"] += len(results)
        item["scored_count"] += sum(1 for result in results if result.get("score") is not None)
        timestamp = data.get("timestamp", "")
        if timestamp > item["latest_timestamp"]:
            item["latest_timestamp"] = timestamp
    return sorted(problems.values(), key=lambda item: item["problem_title"])


def list_runs(competition_id: str, problem_id: str) -> list[dict]:
    runs = []
    for path in iter_log_paths():
        data = load_log(path)
        if not data:
            continue
        if log_competition_id(data, path) != competition_id:
            continue
        if log_problem_id(data, path) != problem_id:
            continue
        results = data.get("results", [])
        scored_count = sum(1 for result in results if result.get("score") is not None)
        runs.append(
            {
                "competition_id": competition_id,
                "problem_id": problem_id,
                "run_id": data.get("run_id", path.stem),
                "timestamp": data.get("timestamp", ""),
                "problem_file": data.get("problem_file", ""),
                "answer_count": len(results),
                "scored_count": scored_count,
                "path": path,
            }
        )
    return sorted(runs, key=lambda item: item["timestamp"], reverse=True)


def find_run_path(competition_id: str, problem_id: str, run_id: str) -> Path | None:
    direct = LOGS_DIR / competition_id / problem_id / f"{run_id}.json"
    if direct.exists():
        return direct
    legacy = LOGS_DIR / f"{run_id}.json"
    if competition_id == "legacy" and legacy.exists():
        return legacy
    for path in iter_log_paths():
        data = load_log(path)
        if not data:
            continue
        if data.get("run_id", path.stem) != run_id:
            continue
        if log_competition_id(data, path) == competition_id and log_problem_id(data, path) == problem_id:
            return path
    return None


def load_run(competition_id: str, problem_id: str, run_id: str) -> dict:
    path = find_run_path(competition_id, problem_id, run_id)
    if not path:
        raise FileNotFoundError(run_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("competition_id", competition_id)
    data.setdefault("competition_title", log_competition_title(data, competition_id))
    data.setdefault("problem_id", problem_id)
    data.setdefault("problem_title", log_problem_title(data, problem_id))
    return data


def save_run(competition_id: str, problem_id: str, run_id: str, data: dict) -> None:
    path = find_run_path(competition_id, problem_id, run_id)
    if not path:
        path = LOGS_DIR / competition_id / problem_id / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_logs() -> list[dict]:
    runs = []
    for path in iter_log_paths():
        try:
            data = load_log(path)
            if not data:
                continue
            competition_id = log_competition_id(data, path)
            problem_id = log_problem_id(data, path)
            runs.append(
                {
                    "competition_id": competition_id,
                    "problem_id": problem_id,
                    "run_id": data.get("run_id", path.stem),
                    "timestamp": data.get("timestamp", ""),
                    "problem_file": data.get("problem_file", ""),
                    "count": len(data.get("results", [])),
                }
            )
        except Exception:
            continue
    return runs


@app.get("/")
def index():
    return render_template("index.html", competitions=list_competitions())


@app.get("/competition/<competition_id>")
def competition_page(competition_id: str):
    problems = list_problems(competition_id)
    if not problems:
        abort(404)
    return render_template(
        "competition.html",
        competition_id=competition_id,
        competition_title=problems[0].get("competition_title", competition_id),
        problems=problems,
    )


@app.get("/competition/<competition_id>/problem/<problem_id>")
def problem_page(competition_id: str, problem_id: str):
    runs = list_runs(competition_id, problem_id)
    if not runs:
        abort(404)
    run = load_run(competition_id, problem_id, runs[0]["run_id"])
    return render_template(
        "problem.html",
        competition_id=competition_id,
        competition_title=run.get("competition_title", competition_id),
        problem_id=problem_id,
        problem_title=run.get("problem_title", problem_id),
        problem_text=run.get("problem_text", ""),
        runs=runs,
    )


@app.get("/competition/<competition_id>/problem/<problem_id>/run/<run_id>")
def review_run(competition_id: str, problem_id: str, run_id: str):
    return render_template("review.html", run=load_run(competition_id, problem_id, run_id))


@app.get("/run/<run_id>")
def legacy_review_run(run_id: str):
    for run in list_logs():
        if run["run_id"] == run_id:
            return redirect(
                url_for(
                    "review_run",
                    competition_id=run["competition_id"],
                    problem_id=run["problem_id"],
                    run_id=run_id,
                )
            )
    abort(404)


@app.post("/score")
def score():
    run_id = request.form["run_id"]
    competition_id = request.form["competition_id"]
    problem_id = request.form["problem_id"]
    model = request.form["model"]
    data = load_run(competition_id, problem_id, run_id)
    for result in data.get("results", []):
        if result.get("model") == model:
            result["score"] = int(request.form["score"])
            result["scored_by"] = request.form.get("scored_by") or None
            result["score_comment"] = request.form.get("comment") or None
            result["scored_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
            break
    save_run(competition_id, problem_id, run_id, data)
    return redirect(
        url_for(
            "review_run",
            competition_id=competition_id,
            problem_id=problem_id,
            run_id=run_id,
        )
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
