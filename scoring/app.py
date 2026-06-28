from __future__ import annotations

from pathlib import Path
import sys

from flask import Flask, abort, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from .repository import (
        build_catalog,
        find_attempt,
        find_problem,
        neighbor_problem_ids,
        safe_id,
        save_evaluation,
        selected_state,
    )
except ImportError:  # pragma: no cover - direct `python scoring/app.py`
    from scoring.repository import (  # type: ignore
        build_catalog,
        find_attempt,
        find_problem,
        neighbor_problem_ids,
        safe_id,
        save_evaluation,
        selected_state,
    )

LOGS_DIR = BASE_DIR / "logs"
RESULTS_DIR = BASE_DIR / "data" / "results"
COMPETITIONS_DIR = BASE_DIR / "data" / "competitions"

app = Flask(__name__)
app.secret_key = "local-dev-scoring"
app.config.setdefault("LOGS_DIR", LOGS_DIR)
app.config.setdefault("RESULTS_DIR", RESULTS_DIR)
app.config.setdefault("COMPETITIONS_DIR", COMPETITIONS_DIR)


def catalog() -> dict:
    return build_catalog(
        competitions_dir=Path(app.config["COMPETITIONS_DIR"]),
        logs_dir=Path(app.config["LOGS_DIR"]),
        results_dir=Path(app.config["RESULTS_DIR"]),
    )


def clean_id(value: str) -> str:
    try:
        return safe_id(value)
    except ValueError:
        abort(404)


@app.get("/")
def index():
    data = catalog()
    return render_template(
        "index.html",
        competitions=data["competitions"],
        warnings=data["warnings"],
    )


@app.get("/competition/<competition_id>")
def competition_page(competition_id: str):
    competition_id = clean_id(competition_id)
    data = catalog()
    competition = data["competition_map"].get(competition_id)
    if not competition:
        abort(404)
    return render_template(
        "competition.html",
        competition=competition,
        warnings=data["warnings"],
    )


@app.get("/competition/<competition_id>/problem/<problem_id>")
def problem_page(competition_id: str, problem_id: str):
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    data = catalog()
    competition = data["competition_map"].get(competition_id)
    problem = find_problem(data, competition_id, problem_id)
    if not competition or not problem:
        abort(404)
    state = selected_state(problem, request.args.get("model"))
    previous_id, next_id = neighbor_problem_ids(competition, problem_id)
    return render_template(
        "problem.html",
        competition=competition,
        problem=problem,
        selected_state=state,
        selected_attempt=state.get("latest") if state else None,
        previous_id=previous_id,
        next_id=next_id,
        warnings=data["warnings"],
    )


@app.get("/competition/<competition_id>/problem/<problem_id>/run/<run_id>")
def review_run(competition_id: str, problem_id: str, run_id: str):
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    run_id = clean_id(run_id)
    data = catalog()
    problem = find_problem(data, competition_id, problem_id)
    if not problem:
        abort(404)
    for state in problem.get("model_states", []):
        for attempt in state.get("attempts", []):
            if attempt.get("run_id") == run_id:
                return redirect(
                    url_for(
                        "problem_page",
                        competition_id=competition_id,
                        problem_id=problem_id,
                        model=state["model_key"],
                    )
                )
    abort(404)


@app.get("/run/<run_id>")
def legacy_review_run(run_id: str):
    run_id = clean_id(run_id)
    data = catalog()
    for competition in data["competitions"]:
        for problem_id in competition.get("problem_order", []):
            problem = competition["problems"][problem_id]
            for state in problem.get("model_states", []):
                for attempt in state.get("attempts", []):
                    if attempt.get("run_id") == run_id:
                        return redirect(
                            url_for(
                                "problem_page",
                                competition_id=competition["competition_id"],
                                problem_id=problem["problem_id"],
                                model=state["model_key"],
                            )
                        )
    abort(404)


@app.post("/score")
def score():
    competition_id = clean_id(request.form.get("competition_id", ""))
    problem_id = clean_id(request.form.get("problem_id", ""))
    run_id = clean_id(request.form.get("run_id", ""))
    result_id = request.form.get("result_id", "")
    model_key = request.form.get("model_key", "")
    data = catalog()
    found = find_attempt(
        data,
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        result_id=result_id,
    )
    if not found:
        abort(400, "result_id does not match this run")
    problem, attempt = found
    try:
        score_value = float(request.form.get("score", ""))
    except ValueError:
        flash("Оценка должна быть числом.", "error")
        return redirect(
            url_for(
                "problem_page",
                competition_id=competition_id,
                problem_id=problem_id,
                model=model_key or attempt["model_key"],
            )
        )
    max_score = float(problem["max_score"])
    if not (0 <= score_value <= max_score):
        flash(f"Оценка должна быть в диапазоне от 0 до {max_score:g}.", "error")
        return redirect(
            url_for(
                "problem_page",
                competition_id=competition_id,
                problem_id=problem_id,
                model=model_key or attempt["model_key"],
            )
        )
    if score_value.is_integer():
        score: float | int = int(score_value)
    else:
        score = score_value
    save_evaluation(
        results_dir=Path(app.config["RESULTS_DIR"]),
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        result_id=result_id,
        result_index=int(attempt["result_index"]),
        model_key_value=attempt["model_key"],
        model=attempt["model_id"],
        evaluator=request.form.get("evaluator"),
        score=score,
        max_score=max_score,
        feedback=request.form.get("feedback"),
    )
    return redirect(
        url_for(
            "problem_page",
            competition_id=competition_id,
            problem_id=problem_id,
            model=model_key or attempt["model_key"],
        )
    )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
