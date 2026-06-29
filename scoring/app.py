from __future__ import annotations

import csv
import io
from pathlib import Path
import secrets
import sys

from flask import Flask, Response, abort, flash, redirect, render_template, request, url_for

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from .repository import (
        anonymized_attempts,
        build_catalog,
        competition_statistics,
        delete_evaluation,
        find_attempt,
        find_problem,
        iter_evaluation_rows,
        neighbor_problem_ids,
        safe_id,
        save_evaluation,
        selected_state,
        upsert_imported_evaluation,
    )
except ImportError:  # pragma: no cover - direct `python scoring/app.py`
    from scoring.repository import (  # type: ignore
        anonymized_attempts,
        build_catalog,
        competition_statistics,
        delete_evaluation,
        find_attempt,
        find_problem,
        iter_evaluation_rows,
        neighbor_problem_ids,
        safe_id,
        save_evaluation,
        selected_state,
        upsert_imported_evaluation,
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


def selected_attempt_for(state: dict | None, attempt_id: str | None) -> dict | None:
    if not state:
        return None
    attempts = state.get("attempts") or []
    if attempt_id:
        for attempt in attempts:
            if attempt.get("result_id") == attempt_id or attempt.get("run_id") == attempt_id:
                return attempt
    return state.get("latest")


def positive_int(value: str | None, default: int = 1) -> int:
    try:
        parsed = int(value or "")
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def score_redirect(
    *,
    mode: str | None,
    competition_id: str,
    problem_id: str,
    model_key: str,
    result_id: str,
    anonymous_seed: str | None,
    anonymous_index: str | None,
):
    if mode == "anonymous":
        return redirect(
            url_for(
                "anonymous_problem_page",
                competition_id=competition_id,
                problem_id=problem_id,
                seed=anonymous_seed,
                n=anonymous_index,
                _anchor=f"attempt-{result_id}",
            )
        )
    return redirect(
        url_for(
            "problem_page",
            competition_id=competition_id,
            problem_id=problem_id,
            model=model_key,
            attempt=result_id,
        )
    )


def parse_optional_float(value: str | None) -> float | int | None:
    if value is None or value == "":
        return None
    parsed = float(value)
    return int(parsed) if parsed.is_integer() else parsed


@app.get("/")
def index():
    data = catalog()
    return render_template(
        "index.html",
        competitions=data["competitions"],
        competition_groups=data.get("competition_groups", []),
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


@app.get("/competition/<competition_id>/stats")
def competition_stats_page(competition_id: str):
    competition_id = clean_id(competition_id)
    data = catalog()
    competition = data["competition_map"].get(competition_id)
    if not competition:
        abort(404)
    stats = competition_statistics(competition)
    selected_model = request.args.get("model")
    return render_template(
        "stats.html",
        competition=competition,
        stats=stats,
        selected_model=selected_model,
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
    attempt = selected_attempt_for(state, request.args.get("attempt"))
    previous_id, next_id = neighbor_problem_ids(competition, problem_id)
    return render_template(
        "problem.html",
        competition=competition,
        problem=problem,
        selected_state=state,
        selected_attempt=attempt,
        previous_id=previous_id,
        next_id=next_id,
        warnings=data["warnings"],
    )


@app.get("/competition/<competition_id>/problem/<problem_id>/anonymous")
def anonymous_problem_page(competition_id: str, problem_id: str):
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    seed = request.args.get("seed")
    if not seed:
        return redirect(
            url_for(
                "anonymous_problem_page",
                competition_id=competition_id,
                problem_id=problem_id,
                seed=secrets.token_urlsafe(8),
                n=1,
            )
        )
    data = catalog()
    competition = data["competition_map"].get(competition_id)
    problem = find_problem(data, competition_id, problem_id)
    if not competition or not problem:
        abort(404)
    previous_id, next_id = neighbor_problem_ids(competition, problem_id)
    attempts = anonymized_attempts(problem, seed)
    selected_index = min(positive_int(request.args.get("n")), len(attempts)) if attempts else 0
    selected_attempt = attempts[selected_index - 1] if selected_index else None
    return render_template(
        "anonymous_problem.html",
        competition=competition,
        problem=problem,
        attempts=attempts,
        selected_attempt=selected_attempt,
        selected_index=selected_index,
        next_index=(selected_index % len(attempts) + 1) if attempts else None,
        seed=seed,
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
                        attempt=attempt.get("result_id"),
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
                                attempt=attempt.get("result_id"),
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
    anonymous_seed = request.form.get("anonymous_seed")
    anonymous_index = request.form.get("anonymous_index")
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
    mode = request.form.get("mode")
    evaluator = request.form.get("evaluator", "").strip()
    if not evaluator:
        flash("Введите имя проверяющего.", "error")
        return score_redirect(
            mode=mode,
            competition_id=competition_id,
            problem_id=problem_id,
            model_key=model_key or attempt["model_key"],
            result_id=attempt["result_id"],
            anonymous_seed=anonymous_seed,
            anonymous_index=anonymous_index,
        )
    try:
        score_value = float(request.form.get("score", ""))
    except ValueError:
        flash("Оценка должна быть числом.", "error")
        return score_redirect(
            mode=mode,
            competition_id=competition_id,
            problem_id=problem_id,
            model_key=model_key or attempt["model_key"],
            result_id=attempt["result_id"],
            anonymous_seed=anonymous_seed,
            anonymous_index=anonymous_index,
        )
    max_score = float(problem["max_score"])
    if not (0 <= score_value <= max_score):
        flash(f"Оценка должна быть в диапазоне от 0 до {max_score:g}.", "error")
        return score_redirect(
            mode=mode,
            competition_id=competition_id,
            problem_id=problem_id,
            model_key=model_key or attempt["model_key"],
            result_id=attempt["result_id"],
            anonymous_seed=anonymous_seed,
            anonymous_index=anonymous_index,
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
        evaluator=evaluator,
        score=score,
        max_score=max_score,
        feedback=request.form.get("feedback"),
    )
    flash("Проверка добавлена.", "info")
    return score_redirect(
        mode=mode,
        competition_id=competition_id,
        problem_id=problem_id,
        model_key=model_key or attempt["model_key"],
        result_id=attempt["result_id"],
        anonymous_seed=anonymous_seed,
        anonymous_index=anonymous_index,
    )


@app.post("/score/delete")
def delete_score():
    competition_id = clean_id(request.form.get("competition_id", ""))
    problem_id = clean_id(request.form.get("problem_id", ""))
    run_id = clean_id(request.form.get("run_id", ""))
    result_id = request.form.get("result_id", "")
    evaluation_id = request.form.get("evaluation_id", "")
    model_key = request.form.get("model_key", "")
    mode = request.form.get("mode")
    anonymous_seed = request.form.get("anonymous_seed")
    anonymous_index = request.form.get("anonymous_index")
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
    _, attempt = found
    if delete_evaluation(
        results_dir=Path(app.config["RESULTS_DIR"]),
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        result_id=result_id,
        evaluation_id=evaluation_id,
    ):
        flash("Проверка удалена.", "info")
    else:
        flash("Проверка не найдена.", "error")
    return score_redirect(
        mode=mode,
        competition_id=competition_id,
        problem_id=problem_id,
        model_key=model_key or attempt["model_key"],
        result_id=attempt["result_id"],
        anonymous_seed=anonymous_seed,
        anonymous_index=anonymous_index,
    )


EVALUATION_CSV_FIELDS = [
    "competition_id",
    "competition_title",
    "problem_id",
    "problem_title",
    "run_id",
    "result_id",
    "result_index",
    "evaluation_id",
    "evaluator",
    "score",
    "max_score",
    "score_category",
    "feedback",
    "created_at",
    "updated_at",
    "model_key",
    "model",
]


def evaluations_csv_response(rows: list[dict], filename: str) -> Response:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=EVALUATION_CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/competition/<competition_id>/evaluations.csv")
def competition_evaluations_csv(competition_id: str):
    competition_id = clean_id(competition_id)
    rows = iter_evaluation_rows(catalog(), competition_id=competition_id, evaluator=request.args.get("evaluator"))
    return evaluations_csv_response(rows, f"{competition_id}_evaluations.csv")


@app.get("/competition/<competition_id>/problem/<problem_id>/evaluations.csv")
def problem_evaluations_csv(competition_id: str, problem_id: str):
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    rows = iter_evaluation_rows(
        catalog(),
        competition_id=competition_id,
        problem_id=problem_id,
        evaluator=request.args.get("evaluator"),
    )
    return evaluations_csv_response(rows, f"{competition_id}_{problem_id}_evaluations.csv")


def import_evaluations_from_request(competition_id: str, problem_id: str | None = None):
    upload = request.files.get("csv_file")
    if not upload:
        flash("Нужен CSV-файл с проверками.", "error")
        return
    try:
        text = upload.stream.read().decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
    except Exception as exc:
        flash(f"Не удалось прочитать CSV: {exc}", "error")
        return
    data = catalog()
    imported = 0
    skipped = 0
    for row in rows:
        row_competition_id = row.get("competition_id") or competition_id
        row_problem_id = row.get("problem_id") or problem_id
        if row_competition_id != competition_id or not row_problem_id or (problem_id and row_problem_id != problem_id):
            skipped += 1
            continue
        run_id = row.get("run_id") or ""
        result_id = row.get("result_id") or ""
        found = find_attempt(
            data,
            competition_id=competition_id,
            problem_id=row_problem_id,
            run_id=run_id,
            result_id=result_id,
        )
        if not found:
            skipped += 1
            continue
        problem, attempt = found
        try:
            score_value = parse_optional_float(row.get("score"))
            max_score = parse_optional_float(row.get("max_score")) or float(problem["max_score"])
        except ValueError:
            skipped += 1
            continue
        upsert_imported_evaluation(
            results_dir=Path(app.config["RESULTS_DIR"]),
            competition_id=competition_id,
            problem_id=row_problem_id,
            run_id=run_id,
            result_id=result_id,
            result_index=int(attempt["result_index"]),
            model_key_value=attempt["model_key"],
            model=attempt["model_id"],
            evaluation={
                **row,
                "score": score_value,
                "max_score": max_score,
            },
        )
        imported += 1
    flash(f"Импортировано проверок: {imported}. Пропущено строк: {skipped}.", "info")


@app.post("/competition/<competition_id>/evaluations/import")
def import_competition_evaluations(competition_id: str):
    competition_id = clean_id(competition_id)
    import_evaluations_from_request(competition_id)
    return redirect(url_for("competition_page", competition_id=competition_id))


@app.post("/competition/<competition_id>/problem/<problem_id>/evaluations/import")
def import_problem_evaluations(competition_id: str, problem_id: str):
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    import_evaluations_from_request(competition_id, problem_id)
    return redirect(url_for("anonymous_problem_page", competition_id=competition_id, problem_id=problem_id))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
