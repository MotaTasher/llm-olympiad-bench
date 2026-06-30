from __future__ import annotations

import csv
from datetime import timedelta
import io
import os
from pathlib import Path
import secrets
import sys
from urllib.parse import urlsplit
import warnings

import click
from flask import (
    Flask,
    Response,
    abort,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_login import (
    LoginManager,
    current_user,
    login_user,
    logout_user,
)
from flask_wtf import CSRFProtect, FlaskForm
from flask_wtf.csrf import CSRFError
from wtforms import PasswordField, StringField, SubmitField
from wtforms.validators import DataRequired

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from .auth import (
        authenticate_user,
        auth_db_path,
        create_user,
        get_active_user_for_session,
        list_users,
        reset_password,
        set_user_active,
    )
    from .cost_estimator import (
        cost_context,
    )
    from .repository import (
        anonymized_attempts,
        build_catalog,
        cell_state,
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
    from scoring.auth import (  # type: ignore
        authenticate_user,
        auth_db_path,
        create_user,
        get_active_user_for_session,
        list_users,
        reset_password,
        set_user_active,
    )
    from scoring.cost_estimator import (  # type: ignore
        cost_context,
    )
    from scoring.repository import (  # type: ignore
        anonymized_attempts,
        build_catalog,
        cell_state,
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


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_session_hours() -> float:
    try:
        value = float(os.environ.get("SCORER_SESSION_HOURS", "12"))
    except ValueError:
        return 12.0
    return value if value > 0 else 12.0


secret_key = os.environ.get("SCORER_SECRET_KEY")
if not secret_key:
    secret_key = secrets.token_urlsafe(48)
    warnings.warn(
        "SCORER_SECRET_KEY is not set; using a temporary per-process Flask session key.",
        RuntimeWarning,
        stacklevel=2,
    )
app.config["SECRET_KEY"] = secret_key
app.config.setdefault("LOGS_DIR", Path(os.environ.get("SCORER_LOGS_DIR", LOGS_DIR)))
app.config.setdefault("RESULTS_DIR", Path(os.environ.get("SCORER_RESULTS_DIR", RESULTS_DIR)))
app.config.setdefault(
    "COMPETITIONS_DIR",
    Path(os.environ.get("SCORER_COMPETITIONS_DIR", COMPETITIONS_DIR)),
)
app.config.setdefault("AUTH_DB", Path(os.environ.get("SCORER_AUTH_DB", "")) if os.environ.get("SCORER_AUTH_DB") else None)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = env_bool("SCORER_COOKIE_SECURE", False)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=env_session_hours())

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)
csrf = CSRFProtect(app)


class LoginForm(FlaskForm):
    username = StringField("Логин", validators=[DataRequired()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    submit = SubmitField("Войти")


@login_manager.user_loader
def load_user(user_id: str):
    return get_active_user_for_session(auth_db_path(app), user_id)


def is_safe_next(target: str | None) -> bool:
    if not target:
        return False
    parts = urlsplit(target)
    return not parts.scheme and not parts.netloc and target.startswith("/") and not target.startswith("//")


def login_redirect_target() -> str:
    full_path = request.full_path if request.query_string else request.path
    return url_for("login", next=full_path if is_safe_next(full_path) else "/")


def wants_login_redirect() -> bool:
    return request.method == "GET"


@app.before_request
def require_authenticated_user():
    allowed_endpoints = {"login", "static"}
    if request.endpoint in allowed_endpoints:
        return None
    if current_user.is_authenticated:
        return None
    if wants_login_redirect():
        return redirect(login_redirect_target())
    abort(401)


@app.errorhandler(CSRFError)
def handle_csrf_error(error: CSRFError):
    response = make_response("Ошибка CSRF: обновите страницу и повторите запрос.", 400)
    response.mimetype = "text/plain"
    return response


@app.get("/login")
@app.post("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))
    form = LoginForm()
    next_url = request.args.get("next") or request.form.get("next")
    safe_next = next_url if is_safe_next(next_url) else ""
    if form.validate_on_submit():
        user = authenticate_user(auth_db_path(app), form.username.data or "", form.password.data or "")
        if user:
            session.permanent = True
            login_user(user, remember=False)
            return redirect(safe_next or url_for("index"))
        flash("Неверный логин или пароль", "error")
    return render_template("login.html", form=form, next_url=safe_next)


@app.post("/logout")
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("login"))


@app.cli.group("user")
def user_cli():
    """Manage scoring-site reviewer accounts."""


@user_cli.command("create")
@click.argument("username")
def user_create(username: str):
    try:
        user, password = create_user(auth_db_path(app), username)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    print(f"User created: {user.username}")
    print(f"Password: {password}")
    print("Save this password now. It will not be shown again.")


@user_cli.command("reset-password")
@click.argument("username")
def user_reset_password(username: str):
    try:
        user, password = reset_password(auth_db_path(app), username)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    print(f"Password reset: {user.username}")
    print(f"Password: {password}")
    print("Save this password now. It will not be shown again.")


@user_cli.command("disable")
@click.argument("username")
def user_disable(username: str):
    try:
        user = set_user_active(auth_db_path(app), username, False)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    print(f"User disabled: {user.username}")


@user_cli.command("enable")
@click.argument("username")
def user_enable(username: str):
    try:
        user = set_user_active(auth_db_path(app), username, True)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    print(f"User enabled: {user.username}")


@user_cli.command("list")
def user_list():
    rows = list_users(auth_db_path(app))
    if not rows:
        print("No users.")
        return
    for row in rows:
        print(f"{row['username']}\t{row['status']}\t{row['created_at']}\t{row['updated_at']}")


def catalog() -> dict:
    return build_catalog(
        competitions_dir=Path(app.config["COMPETITIONS_DIR"]),
        logs_dir=Path(app.config["LOGS_DIR"]),
        results_dir=Path(app.config["RESULTS_DIR"]),
    )


def catalog_for_reviewer(reviewer: str) -> dict:
    data = catalog()
    scope_catalog_to_reviewer(data, reviewer)
    return data


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


def evaluation_visible_to_reviewer(evaluation: dict, reviewer: str) -> bool:
    return evaluation.get("evaluator") == reviewer


def attempt_for_reviewer(attempt: dict | None, reviewer: str) -> dict | None:
    if not attempt:
        return None
    visible_evaluations = [
        evaluation
        for evaluation in attempt.get("evaluations", [])
        if evaluation_visible_to_reviewer(evaluation, reviewer)
    ]
    visible = {**attempt}
    visible["evaluations"] = visible_evaluations
    visible["evaluation_count"] = len(visible_evaluations)
    latest = visible_evaluations[-1] if visible_evaluations else None
    visible["evaluation"] = latest
    visible["score"] = latest.get("score") if latest else None
    visible["score_category"] = latest.get("score_category") if latest else None
    return visible


def state_for_reviewer(state: dict | None, reviewer: str) -> dict | None:
    if not state:
        return None
    visible_attempts = [attempt_for_reviewer(attempt, reviewer) for attempt in state.get("attempts", [])]
    latest = state.get("latest")
    latest_result_id = latest.get("result_id") if latest else None
    visible_latest = None
    if latest_result_id:
        visible_latest = next(
            (attempt for attempt in visible_attempts if attempt and attempt.get("result_id") == latest_result_id),
            None,
        )
    visible = {**state}
    visible["attempts"] = visible_attempts
    visible["latest"] = visible_latest
    return visible


def attempts_for_reviewer(attempts: list[dict], reviewer: str) -> list[dict]:
    return [attempt for attempt in (attempt_for_reviewer(attempt, reviewer) for attempt in attempts) if attempt]


def attempt_has_reviewer_evaluation(attempt: dict, evaluation_id: str, reviewer: str) -> bool:
    return any(
        evaluation.get("evaluation_id") == evaluation_id and evaluation_visible_to_reviewer(evaluation, reviewer)
        for evaluation in attempt.get("evaluations", [])
    )


def scope_catalog_to_reviewer(data: dict, reviewer: str) -> None:
    for competition in data.get("competitions", []):
        scored_count = 0
        answer_count = 0
        model_keys_seen: set[str] = set()
        latest_run = ""
        for problem_id in competition.get("problem_order", []):
            problem = competition["problems"][problem_id]
            visible_states = []
            for state in problem.get("model_states", []):
                visible_attempts = attempts_for_reviewer(state.get("attempts") or [], reviewer)
                visible_state = cell_state(state, visible_attempts, float(problem["max_score"]))
                visible_states.append(visible_state)
                for attempt in visible_attempts:
                    model_keys_seen.add(state["model_key"])
                    answer_count += 1
                    if attempt.get("score") is not None:
                        scored_count += 1
                    if attempt.get("run_timestamp") and attempt["run_timestamp"] > latest_run:
                        latest_run = attempt["run_timestamp"]
            problem["model_states"] = visible_states
        competition["model_count"] = len(model_keys_seen)
        competition["answer_count"] = answer_count
        competition["scored_count"] = scored_count
        competition["progress_percent"] = int((scored_count / answer_count) * 100) if answer_count else 0
        competition["latest_timestamp"] = latest_run


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
    data = catalog_for_reviewer(current_user.username)
    return render_template(
        "index.html",
        competitions=data["competitions"],
        competition_groups=data.get("competition_groups", []),
        warnings=data["warnings"],
        cost_context=cost_context(data["competitions"]),
    )


@app.get("/competition/<competition_id>")
def competition_page(competition_id: str):
    competition_id = clean_id(competition_id)
    data = catalog_for_reviewer(current_user.username)
    competition = data["competition_map"].get(competition_id)
    if not competition:
        abort(404)
    return render_template(
        "competition.html",
        competition=competition,
        warnings=data["warnings"],
        cost_context=cost_context([competition]),
    )


@app.get("/competition/<competition_id>/stats")
def competition_stats_page(competition_id: str):
    competition_id = clean_id(competition_id)
    data = catalog_for_reviewer(current_user.username)
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
    data = catalog_for_reviewer(current_user.username)
    competition = data["competition_map"].get(competition_id)
    problem = find_problem(data, competition_id, problem_id)
    if not competition or not problem:
        abort(404)
    state = state_for_reviewer(selected_state(problem, request.args.get("model")), current_user.username)
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
    data = catalog_for_reviewer(current_user.username)
    competition = data["competition_map"].get(competition_id)
    problem = find_problem(data, competition_id, problem_id)
    if not competition or not problem:
        abort(404)
    previous_id, next_id = neighbor_problem_ids(competition, problem_id)
    attempts = attempts_for_reviewer(anonymized_attempts(problem, seed), current_user.username)
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


def serve_competition_asset(competition_id: str, asset_path: str) -> Response:
    competition_id = clean_id(competition_id)
    return send_from_directory(
        Path(app.config["COMPETITIONS_DIR"]) / competition_id / "assets",
        asset_path,
    )


@app.get("/competition/<competition_id>/problem/assets/<path:asset_path>")
def problem_directory_asset(competition_id: str, asset_path: str):
    return serve_competition_asset(competition_id, asset_path)


@app.get("/competition/<competition_id>/problem/<problem_id>/assets/<path:asset_path>")
def problem_asset(competition_id: str, problem_id: str, asset_path: str):
    clean_id(problem_id)
    return serve_competition_asset(competition_id, asset_path)


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
    evaluator = current_user.username
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
    if evaluation_id and not attempt_has_reviewer_evaluation(attempt, evaluation_id, current_user.username):
        abort(403)
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
