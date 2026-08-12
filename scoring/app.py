from __future__ import annotations

import csv
from copy import deepcopy
from datetime import date, timedelta
import io
import json
import math
import os
import re
from pathlib import Path
import secrets
import sys
import threading
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
from wtforms import PasswordField, StringField
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
    from .presentation import MONTHS_GENITIVE, format_datetime_parts
    from .repository import (
        anonymized_attempts,
        build_catalog,
        cell_state,
        checks_statistics,
        competition_statistics,
        delete_evaluation,
        delete_finalization,
        finalization_statistics,
        find_attempt,
        find_problem,
        format_score_value,
        iter_evaluation_rows,
        model_states_for_review,
        neighbor_problem_ids,
        next_unscored_attempt,
        progress_counts_for_model_states,
        safe_id,
        save_evaluation,
        save_finalization,
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
    from scoring.presentation import MONTHS_GENITIVE, format_datetime_parts  # type: ignore
    from scoring.repository import (  # type: ignore
        anonymized_attempts,
        build_catalog,
        cell_state,
        checks_statistics,
        competition_statistics,
        delete_evaluation,
        delete_finalization,
        finalization_statistics,
        find_attempt,
        find_problem,
        format_score_value,
        iter_evaluation_rows,
        model_states_for_review,
        neighbor_problem_ids,
        next_unscored_attempt,
        progress_counts_for_model_states,
        safe_id,
        save_evaluation,
        save_finalization,
        selected_state,
        upsert_imported_evaluation,
    )

LOGS_DIR = BASE_DIR / "logs"
RESULTS_DIR = BASE_DIR / "data" / "results"
COMPETITIONS_DIR = BASE_DIR / "data" / "competitions"
GEOGEBRA_DIR = BASE_DIR / "data" / "geogebra"
GEOGEBRA_VIEWER_DIR = BASE_DIR / "scripts" / "geogebra_viewer"

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
app.config.setdefault("GEOGEBRA_DIR", Path(os.environ.get("SCORER_GEOGEBRA_DIR", GEOGEBRA_DIR)))
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


_catalog_cache_lock = threading.RLock()
_catalog_cache_signature: tuple | None = None
_catalog_cache_value: dict | None = None


def json_tree_signature(root: Path) -> tuple:
    root = root.resolve()
    if not root.exists():
        return (str(root), "missing")
    entries = []
    for path in sorted(root.rglob("*.json")):
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((str(path.relative_to(root)), stat.st_mtime_ns, stat.st_size))
    return (str(root), tuple(entries))


def catalog_source_signature() -> tuple:
    return tuple(
        json_tree_signature(Path(app.config[key]))
        for key in ("COMPETITIONS_DIR", "LOGS_DIR", "RESULTS_DIR")
    )


def clear_catalog_cache() -> None:
    global _catalog_cache_signature, _catalog_cache_value
    with _catalog_cache_lock:
        _catalog_cache_signature = None
        _catalog_cache_value = None


def catalog() -> dict:
    global _catalog_cache_signature, _catalog_cache_value
    signature = catalog_source_signature()
    with _catalog_cache_lock:
        if _catalog_cache_value is not None and _catalog_cache_signature == signature:
            return _catalog_cache_value
        data = build_catalog(
            competitions_dir=Path(app.config["COMPETITIONS_DIR"]),
            logs_dir=Path(app.config["LOGS_DIR"]),
            results_dir=Path(app.config["RESULTS_DIR"]),
        )
        _catalog_cache_signature = signature
        _catalog_cache_value = data
        return data


def catalog_for_reviewer(reviewer: str) -> dict:
    data = deepcopy(catalog())
    scope_catalog_to_reviewer(data, reviewer)
    return data


@app.template_filter("competition_date")
def competition_date(value) -> str:
    if not value:
        return ""
    if not isinstance(value, str):
        return str(value)
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return value
    return f"{parsed.day} {MONTHS_GENITIVE[parsed.month - 1]}"


@app.template_filter("competition_card_description")
def competition_card_description(value) -> str:
    if not value:
        return ""
    text = str(value).strip()
    prefix = "Полное название:"
    if not text.startswith(prefix):
        return text
    remainder = text[len(prefix):].strip()
    _, separator, tail = remainder.partition(".")
    if not separator:
        return ""
    return tail.strip()


app.jinja_env.globals["datetime_parts"] = format_datetime_parts
app.jinja_env.filters["score_value"] = format_score_value


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
        competition.update(progress_counts_for_model_states(competition["problems"], competition["problem_order"]))
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


def first_unscored_attempt_index(attempts: list[dict]) -> int | None:
    for index, attempt in enumerate(attempts, start=1):
        if attempt.get("score") is None:
            return index
    return None


def anonymous_index_for_attempt(problem: dict, seed: str | None, result_id: str | None, reviewer: str) -> int | None:
    if not seed or not result_id:
        return None
    attempts = attempts_for_reviewer(anonymized_attempts(problem, seed), reviewer)
    for index, attempt in enumerate(attempts, start=1):
        if attempt.get("result_id") == result_id:
            return index
    return None


def redirect_to_next_unscored_after_save(
    *,
    mode: str | None,
    competition_id: str,
    problem_id: str,
    current_model_key: str,
    anonymous_seed: str | None,
    reviewer: str,
):
    data = catalog_for_reviewer(reviewer)
    problem = find_problem(data, competition_id, problem_id)
    if not problem:
        return None
    attempt = next_unscored_attempt(problem, current_model_key)
    if not attempt:
        return None
    if mode == "anonymous":
        index = anonymous_index_for_attempt(problem, anonymous_seed, attempt.get("result_id"), reviewer)
        if index is None:
            return None
        return redirect(
            url_for(
                "anonymous_problem_page",
                competition_id=competition_id,
                problem_id=problem_id,
                seed=anonymous_seed,
                n=index,
                _anchor=f"attempt-{attempt['result_id']}",
            )
        )
    return redirect(
        url_for(
            "problem_page",
            competition_id=competition_id,
            problem_id=problem_id,
            model=attempt["model_key"],
            attempt=attempt["result_id"],
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
    visible_groups = [
        group
        for group in data.get("competition_groups", [])
        if group.get("year") is not None
    ]
    visible_competitions = [
        competition
        for group in visible_groups
        for competition in group.get("competitions", [])
    ]
    return render_template(
        "index.html",
        competitions=visible_competitions,
        competition_groups=visible_groups,
        warnings=data["warnings"],
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


@app.get("/competition/<competition_id>/checks")
def competition_checks_page(competition_id: str):
    competition_id = clean_id(competition_id)
    data = catalog()
    competition = data["competition_map"].get(competition_id)
    if not competition:
        abort(404)
    rows = iter_evaluation_rows(data, competition_id=competition_id)
    return render_template(
        "checks.html",
        competition=competition,
        checks=checks_statistics(competition, rows),
        warnings=data["warnings"],
    )


@app.get("/competition/<competition_id>/finalization")
def competition_finalization_page(competition_id: str):
    competition_id = clean_id(competition_id)
    data = catalog()
    competition = data["competition_map"].get(competition_id)
    if not competition:
        abort(404)
    return render_template(
        "finalization.html",
        competition=competition,
        finalization=finalization_statistics(competition),
        warnings=data["warnings"],
    )


@app.get("/competition/<competition_id>/finalization/<problem_id>/<result_id>")
def finalization_detail_page(competition_id: str, problem_id: str, result_id: str):
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    data = catalog()
    competition = data["competition_map"].get(competition_id)
    problem = find_problem(data, competition_id, problem_id)
    if not competition or not problem:
        abort(404)
    attempt = next(
        (
            attempt
            for state in problem.get("model_states", [])
            for attempt in state.get("attempts", [])
            if attempt.get("result_id") == result_id
        ),
        None,
    )
    if not attempt:
        abort(404)
    return render_template(
        "finalize.html",
        competition=competition,
        problem=problem,
        attempt=attempt,
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
    scene_file = geogebra_scene_file(
        competition_id,
        problem_id,
        state.get("model_key") if state else None,
        attempt.get("result_id") if attempt else None,
    )
    return render_template(
        "problem.html",
        competition=competition,
        problem=problem,
        model_tabs=model_states_for_review(problem),
        selected_state=state,
        selected_attempt=attempt,
        previous_id=previous_id,
        next_id=next_id,
        warnings=data["warnings"],
        geogebra_scene_name=scene_file.name if scene_file else None,
    )


@app.get("/competition/<competition_id>/problem/<problem_id>/anonymous")
def anonymous_problem_page(competition_id: str, problem_id: str):
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    seed = request.args.get("seed")
    if not seed:
        seed = secrets.token_urlsafe(8)
        data = catalog_for_reviewer(current_user.username)
        problem = find_problem(data, competition_id, problem_id)
        index = 1
        if problem:
            attempts = attempts_for_reviewer(anonymized_attempts(problem, seed), current_user.username)
            index = first_unscored_attempt_index(attempts) or 1
        return redirect(
            url_for(
                "anonymous_problem_page",
                competition_id=competition_id,
                problem_id=problem_id,
                seed=seed,
                n=index,
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
    next_unscored_index = None
    if attempts and selected_index:
        for offset in range(1, len(attempts) + 1):
            index = (selected_index - 1 + offset) % len(attempts) + 1
            if attempts[index - 1].get("score") is None:
                next_unscored_index = index
                break
    scene_available = False
    if selected_attempt:
        selected_result_id = str(selected_attempt.get("result_id") or "")
        scene_available = geogebra_scene_file(
            competition_id,
            problem_id,
            geogebra_model_key_for_result(problem, selected_result_id),
            selected_result_id,
        ) is not None
    return render_template(
        "anonymous_problem.html",
        competition=competition,
        problem=problem,
        attempts=attempts,
        selected_attempt=selected_attempt,
        geogebra_scene_available=scene_available,
        selected_index=selected_index,
        next_index=next_unscored_index or ((selected_index % len(attempts) + 1) if attempts else None),
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


def geogebra_scene_file(
    competition_id: str,
    problem_id: str,
    model_key: str | None = None,
    result_id: str | None = None,
) -> Path | None:
    """Most specific scene wins: attempt, then model, then the whole problem.

    Scenes are hand-written and live outside the benchmark data contracts; a
    missing scene is the normal case, not an error.
    """
    directory = Path(app.config["GEOGEBRA_DIR"]) / competition_id
    if not directory.is_dir():
        return None

    candidates: list[str] = []
    if result_id:
        candidates.append(f"{problem_id}_{result_id}")
    if model_key:
        # model_key is "provider:model_id"; both parts may appear in a filename.
        flat = model_key.replace(":", "_").replace("/", "_")
        candidates.append(f"{problem_id}_{flat}")
        if ":" in model_key:
            candidates.append(f"{problem_id}_{model_key.split(':', 1)[1].replace('/', '_')}")
    candidates.append(problem_id)

    for stem in candidates:
        # Reject anything that could escape the competition directory.
        if "/" in stem or "\\" in stem or ".." in stem:
            continue
        candidate = directory / f"{stem}.json"
        if candidate.is_file():
            return candidate
    return None


# Vendor names that must never reach an anonymous review page. The scene text
# is written by hand and mentions the model it explains, so it has to be
# scrubbed before it is served there.
GEOGEBRA_VENDOR_WORDS = (
    "claude", "opus", "fable", "haiku", "sonnet", "anthropic",
    "gpt", "openai", "o3", "o4",
    "gemini", "google", "grok", "xai", "glm", "zai", "zhipu",
    "gigachat", "сбер", "sber", "kimi", "moonshot", "deepseek",
    "alice", "алиса", "yandex", "яндекс", "qwen", "llama", "mistral",
)
GEOGEBRA_VENDOR_RE = re.compile(
    r"(?iu)\b(?:" + "|".join(GEOGEBRA_VENDOR_WORDS) + r")\b"
    r"(?:[\s\-]*(?:[\d.]+|sol|flash|ultra|pro|mini|max|lite|preview|thinking|build|k\d))*"
)


def _scrub_vendor(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _scrub_vendor(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_vendor(item) for item in value]
    if isinstance(value, str):
        return GEOGEBRA_VENDOR_RE.sub("модель", value)
    return value


def anonymize_scene(scene: Any) -> Any:
    """Strip model identity from a scene without touching its geometry.

    Only the scene's own title is replaced; step titles keep their meaning and
    are merely scrubbed, because they are what a reviewer follows.
    """
    cleaned = _scrub_vendor(scene)
    if isinstance(cleaned, dict):
        cleaned["title"] = "Построение по этому решению"
        cleaned.pop("source", None)
    return cleaned


def geogebra_model_key_for_result(problem: dict, result_id: str) -> str | None:
    for state in problem.get("model_states", []):
        for attempt in state.get("attempts", []):
            if str(attempt.get("result_id")) == result_id:
                return state.get("model_key")
    return None


@app.get("/geogebra/anonymous/<competition_id>/<problem_id>/<result_id>")
def geogebra_anonymous_scene(competition_id: str, problem_id: str, result_id: str):
    """Scene for the anonymous review page: same construction, no model name.

    The reviewer must not learn which model wrote the answer, so the scene is
    looked up by the attempt and every vendor mention is removed. Commands are
    left alone: they carry geometry, not identity.
    """
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    result_id = clean_id(result_id)

    data = catalog_for_reviewer(current_user.username)
    problem = find_problem(data, competition_id, problem_id)
    if not problem:
        abort(404)
    path = geogebra_scene_file(
        competition_id,
        problem_id,
        geogebra_model_key_for_result(problem, result_id),
        result_id,
    )
    if path is None:
        abort(404)
    try:
        scene = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return Response(
            json.dumps({"error": f"сцена не читается: {error}"}, ensure_ascii=False),
            status=500,
            mimetype="application/json",
        )
    return Response(
        json.dumps({"scene": anonymize_scene(scene)}, ensure_ascii=False),
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/geogebra/viewer.js")
def geogebra_viewer_js():
    return send_from_directory(GEOGEBRA_VIEWER_DIR, "viewer.js", mimetype="application/javascript")


@app.get("/geogebra/scene/<competition_id>/<problem_id>")
def geogebra_scene(competition_id: str, problem_id: str):
    competition_id = clean_id(competition_id)
    problem_id = clean_id(problem_id)
    path = geogebra_scene_file(
        competition_id,
        problem_id,
        request.args.get("model"),
        request.args.get("result_id"),
    )
    if path is None:
        abort(404)
    try:
        scene = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return Response(
            json.dumps({"error": f"сцена не читается: {error}"}, ensure_ascii=False),
            status=500,
            mimetype="application/json",
        )
    return Response(
        json.dumps({"scene": scene, "name": path.name}, ensure_ascii=False),
        mimetype="application/json",
        headers={"Cache-Control": "no-store"},
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
    if not math.isfinite(score_value) or not (0 <= score_value <= max_score):
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
    flash("Проверка сохранена.", "info")
    next_redirect = redirect_to_next_unscored_after_save(
        mode=mode,
        competition_id=competition_id,
        problem_id=problem_id,
        current_model_key=attempt["model_key"],
        anonymous_seed=anonymous_seed,
        reviewer=evaluator,
    )
    if next_redirect is not None:
        return next_redirect
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


@app.post("/finalization")
def save_final_score():
    competition_id = clean_id(request.form.get("competition_id", ""))
    problem_id = clean_id(request.form.get("problem_id", ""))
    run_id = clean_id(request.form.get("run_id", ""))
    result_id = request.form.get("result_id", "")
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
    feedback = (request.form.get("feedback") or "").strip()
    feedback_review_required = request.form.get("feedback_review_required") == "1"
    try:
        value = float(request.form.get("score", ""))
    except ValueError:
        flash("Итоговая оценка должна быть числом.", "error")
        return redirect(url_for("finalization_detail_page", competition_id=competition_id, problem_id=problem_id, result_id=result_id))
    max_score = float(problem["max_score"])
    if not math.isfinite(value) or not 0 <= value <= max_score:
        flash(f"Итоговая оценка должна быть в диапазоне от 0 до {max_score:g}.", "error")
        return redirect(url_for("finalization_detail_page", competition_id=competition_id, problem_id=problem_id, result_id=result_id))
    if not attempt.get("evaluation_count"):
        flash("Нельзя финализировать ответ без индивидуальной проверки.", "error")
        return redirect(url_for("finalization_detail_page", competition_id=competition_id, problem_id=problem_id, result_id=result_id))
    score_value: float | int = int(value) if value.is_integer() else value
    save_finalization(
        results_dir=Path(app.config["RESULTS_DIR"]),
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        result_id=result_id,
        result_index=int(attempt["result_index"]),
        model_key_value=attempt["model_key"],
        model=attempt["model_id"],
        score=score_value,
        max_score=max_score,
        feedback=feedback,
        feedback_review_required=feedback_review_required,
        updated_by=current_user.username,
    )
    flash("Итоговая оценка сохранена.", "info")
    return redirect(url_for("finalization_detail_page", competition_id=competition_id, problem_id=problem_id, result_id=result_id))


@app.post("/finalization/delete")
def delete_final_score():
    competition_id = clean_id(request.form.get("competition_id", ""))
    problem_id = clean_id(request.form.get("problem_id", ""))
    run_id = clean_id(request.form.get("run_id", ""))
    result_id = request.form.get("result_id", "")
    if delete_finalization(
        results_dir=Path(app.config["RESULTS_DIR"]),
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        result_id=result_id,
    ):
        flash("Ручная финализация снята.", "info")
    else:
        flash("Ручная финализация не найдена.", "error")
    return redirect(url_for("finalization_detail_page", competition_id=competition_id, problem_id=problem_id, result_id=result_id))


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
