from __future__ import annotations

import hashlib
import importlib
import json
import math
import re
import statistics
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models.telemetry import (
    SIDECAR_SCHEMA_VERSION,
    atomic_write_json,
    normalize_run_log,
)
from olympiad_data import (
    COMPETITION_MANIFEST,
    DataLoadError,
    display_problem_title,
    load_competition,
    load_problem,
    problem_sort_key,
)
from scoring.presentation import format_datetime_parts


PROVIDER_ORDER = [
    "anthropic",
    "deepseek",
    "google",
    "gigachat",
    "xai",
    "zai",
    "openai",
    "yandexgpt",
]

PROVIDER_LABELS = {
    "anthropic": "Claude",
    "deepseek": "DeepSeek",
    "google": "Gemini",
    "gigachat": "GigaChat",
    "openai": "OpenAI",
    "unknown": "unknown",
    "xai": "Grok",
    "yandexgpt": "Яндекс",
    "zai": "GLM",
}

SHORT_MODEL_LABELS = {
    ("anthropic", "claude-opus-4-8"): "Opus 4.8",
    ("anthropic", "claude-haiku-4-5-20251001"): "Haiku 4.5",
    ("deepseek", "deepseek-v4-pro"): "V4 Pro",
    ("deepseek", "deepseek-v4-flash"): "V4 Flash",
    ("google", "gemini-3.1-pro-preview"): "3.1 Pro",
    ("google", "gemini-3.5-flash"): "3.5 Flash",
    ("gigachat", "GigaChat-2-Max"): "2 Max",
    ("gigachat", "GigaChat-2"): "2",
    ("xai", "grok-4.3"): "4.3",
    ("xai", "grok-build-0.1"): "Build 0.1",
    ("zai", "glm-5.2"): "5.2",
    ("zai", "glm-4.7-flash"): "4.7 Flash",
    ("openai", "gpt-5.5"): "GPT-5.5",
    ("openai", "gpt-5.4-mini"): "GPT-5.4 mini",
    ("yandexgpt", "yandexgpt-5.1"): "5.1",
    ("yandexgpt", "yandexgpt-5-lite"): "5 Lite",
}

PROVIDER_MODULES = {
    "anthropic": "models.claude.versions",
    "deepseek": "models.deepseek.versions",
    "google": "models.gemini.versions",
    "gigachat": "models.gigachat.versions",
    "xai": "models.grok.versions",
    "zai": "models.glm.versions",
    "openai": "models.gpt.versions",
    "yandexgpt": "models.yandexgpt.versions",
}

STATUS_META = {
    "not_run": ("Не запускалась", "cell-not-run", ""),
    "error": ("Ошибка", "cell-error", ""),
    "unscored": ("Ожидает проверки", "cell-unscored", "?"),
    "zero": ("0 баллов", "cell-zero", ""),
    "partial": ("Частичный балл", "cell-partial", ""),
    "full": ("Максимальный балл", "cell-full", ""),
}

SCORE_CLASS_BY_CATEGORY = {
    "not_run": "cell-not-run",
    "error": "cell-error",
    "unscored": "cell-unscored",
    "zero": "cell-zero",
    "partial": "cell-partial",
    "full": "cell-full",
}

AGGREGATE_MODES = {
    "median": "Медиана",
    "avg": "Среднее",
    "max": "Максимум",
    "min": "Минимум",
}

DEFAULT_AGGREGATE_MODE = "median"

YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
MONTH_NAMES = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def safe_id(value: str) -> str:
    if not value or "/" in value or "\\" in value or value in {".", ".."}:
        raise ValueError("invalid id")
    return value


def load_json(path: Path, warnings: list[str]) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"{path}: не удалось прочитать JSON: {exc}")
        return None
    if not isinstance(data, dict):
        warnings.append(f"{path}: верхний уровень JSON должен быть объектом")
        return None
    return data


def iter_log_paths(logs_dir: Path) -> list[Path]:
    if not logs_dir.exists():
        return []
    paths = []
    for path in logs_dir.rglob("*.json"):
        try:
            parts = path.relative_to(logs_dir).parts
        except ValueError:
            continue
        if any(part.startswith(".") or part.startswith("_") for part in parts):
            continue
        if path.name.endswith(".evaluation.json"):
            continue
        paths.append(path)
    return sorted(paths)


def positive_finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        try:
            parsed = float(value)
        except ValueError:
            return None
    else:
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def max_score_for(competition: dict[str, Any], problem: dict[str, Any]) -> float:
    for source in (problem, competition):
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        parsed = positive_finite_number(metadata.get("max_score"))
        if parsed is not None:
            return parsed
    return 10.0


def score_step_for(competition: dict[str, Any], problem: dict[str, Any], max_score: float) -> float:
    safe_max = positive_finite_number(max_score) or 1.0
    for source in (problem, competition):
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        parsed = positive_finite_number(metadata.get("score_step"))
        if parsed is not None and parsed <= safe_max:
            return parsed
    return min(1.0, safe_max)


def half_score_for(max_score: float, score_step: float, *, tolerance: float = 1e-9) -> float | None:
    if not math.isfinite(max_score) or not math.isfinite(score_step) or max_score <= 0 or score_step <= 0:
        return None
    half = max_score / 2
    ratio = half / score_step
    if math.isclose(ratio, round(ratio), rel_tol=tolerance, abs_tol=tolerance):
        return half
    return None


def score_ticks_for(max_score: float, score_step: float, *, tolerance: float = 1e-9) -> list[float]:
    if not math.isfinite(max_score) or not math.isfinite(score_step) or max_score <= 0 or score_step <= 0:
        return [0.0, max(0.0, max_score if math.isfinite(max_score) else 0.0)]
    ticks = [0.0]
    current = score_step
    while current < max_score and not math.isclose(current, max_score, rel_tol=tolerance, abs_tol=tolerance):
        ticks.append(current)
        current += score_step
    if not math.isclose(ticks[-1], max_score, rel_tol=tolerance, abs_tol=tolerance):
        ticks.append(max_score)
    else:
        ticks[-1] = max_score
    return ticks


def score_category(score: Any, max_score: float, *, tolerance: float = 1e-9) -> str | None:
    if score is None or score == "":
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    if abs(value) <= tolerance:
        return "zero"
    if value >= max_score - tolerance:
        return "full"
    if value > 0:
        return "partial"
    return None


def provider_order(provider: str) -> int:
    try:
        return PROVIDER_ORDER.index(provider)
    except ValueError:
        return len(PROVIDER_ORDER)


def readable_model_label(model_id: str) -> str:
    return " ".join(str(model_id).replace("_", " ").replace("-", " ").split()) or "unknown"


def model_presentation(provider: str, model_id: str, *, model_order: int | None = None) -> dict[str, Any]:
    return {
        "provider_label": PROVIDER_LABELS.get(provider, provider or "unknown"),
        "provider_order": provider_order(provider),
        "model_order": model_order if model_order is not None else 10_000,
        "short_label": SHORT_MODEL_LABELS.get((provider, model_id), readable_model_label(model_id)),
    }


def model_column_sort_key(item: dict[str, Any]) -> tuple[int, int, str, str]:
    return (
        int(item.get("provider_order", provider_order(str(item.get("provider") or "")))),
        int(item.get("model_order", 10_000)),
        str(item.get("provider") or ""),
        str(item.get("model_id") or ""),
    )


def model_groups_for(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    by_provider: dict[str, dict[str, Any]] = {}
    for column in columns:
        provider = str(column.get("provider") or "unknown")
        group = by_provider.get(provider)
        if group is None:
            group = {
                "provider": provider,
                "label": column.get("provider_label") or PROVIDER_LABELS.get(provider, provider),
                "provider_order": column.get("provider_order", provider_order(provider)),
                "models": [],
            }
            by_provider[provider] = group
            groups.append(group)
        group["models"].append(column)
    groups.sort(key=lambda item: (int(item.get("provider_order", 10_000)), str(item.get("provider") or "")))
    return groups


def configured_model_columns() -> dict[str, dict[str, Any]]:
    columns: dict[str, dict[str, Any]] = {}
    for provider, module_name in PROVIDER_MODULES.items():
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for model_order_value, model_id in enumerate(getattr(module, "VERSIONS", []) or []):
            model_id = str(model_id)
            key = model_key(provider, str(model_id))
            columns.setdefault(
                key,
                {
                    "model_key": key,
                    "provider": provider,
                    "model_id": model_id,
                    "label": model_id,
                    "configured": True,
                    **model_presentation(provider, model_id, model_order=model_order_value),
                },
            )
    return columns


def infer_provider(model_id: str) -> str:
    lower = model_id.lower()
    if lower.startswith(("gpt-", "o1", "o3", "o4", "chat")):
        return "openai"
    if lower.startswith("claude-"):
        return "anthropic"
    if lower.startswith("deepseek"):
        return "deepseek"
    if lower.startswith("gemini-"):
        return "google"
    if "gigachat" in lower:
        return "gigachat"
    if lower.startswith("grok-"):
        return "xai"
    if lower.startswith("glm-"):
        return "zai"
    if "yandex" in lower or "alice" in lower:
        return "yandexgpt"
    return "unknown"


def canonical_provider(provider: str | None, model_id: str | None = None) -> str:
    value = (provider or "").lower()
    if value in {"gemini", "google"}:
        return "google"
    if value in {"grok", "xai"}:
        return "xai"
    if value in {"glm", "zai", "zhipu"}:
        return "zai"
    if value:
        return value
    return infer_provider(str(model_id or ""))


def model_key(provider: str | None, model_id: str | None) -> str:
    provider = canonical_provider(provider, model_id) or "unknown"
    model_id = model_id or "unknown"
    return f"{provider}:{model_id}"


ACTIVE_MODEL_ALIASES = {
    model_key("yandexgpt", "yandexgpt-5.1/latest"): model_key("yandexgpt", "yandexgpt-5.1"),
    model_key("xai", "grok-code-fast-1"): model_key("xai", "grok-build-0.1"),
}


def canonical_model_key(provider: str | None, model_id: str | None) -> str:
    provider = canonical_provider(provider, model_id)
    key = model_key(provider, model_id)
    return ACTIVE_MODEL_ALIASES.get(key, key)


def display_score(value: Any) -> str:
    if value is None or value == "":
        return "—"
    parsed = parse_score(value)
    if parsed is None:
        return str(value)
    return format_score_value(parsed)


def parse_score(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def format_score_value(value: float | int | None) -> str:
    if value is None:
        return ""
    parsed = float(value)
    if not math.isfinite(parsed):
        return ""
    if math.isclose(parsed, round(parsed), rel_tol=1e-9, abs_tol=1e-9):
        return str(int(round(parsed)))
    return f"{parsed:.2f}".rstrip("0").rstrip(".")


def aggregate_scores(scores: list[float]) -> dict[str, float | None]:
    if not scores:
        return {mode: None for mode in AGGREGATE_MODES}
    ordered = [float(score) for score in scores]
    return {
        "median": float(statistics.median(ordered)),
        "avg": sum(ordered) / len(ordered),
        "max": max(ordered),
        "min": min(ordered),
    }


def timestamp_key(value: str | None) -> str:
    return value or ""


def read_sidecars(results_dir: Path, warnings: list[str]) -> dict[tuple[str, str, str], dict[str, Any]]:
    sidecars: dict[tuple[str, str, str], dict[str, Any]] = {}
    if not results_dir.exists():
        return sidecars
    for path in sorted(results_dir.rglob("*.json")):
        data = load_json(path, warnings)
        if not data:
            continue
        try:
            parts = path.relative_to(results_dir).parts
        except ValueError:
            parts = ()
        competition_id = str(data.get("competition_id") or (parts[0] if len(parts) >= 3 else "legacy"))
        problem_id = str(data.get("problem_id") or (parts[1] if len(parts) >= 3 else path.parent.name))
        run_id = str(data.get("run_id") or path.stem)
        evaluations = data.get("evaluations")
        if not isinstance(evaluations, dict):
            evaluations = {}
            if any(data.get(key) is not None for key in ("score", "feedback", "evaluator")):
                evaluations["0"] = {
                    "score": data.get("score"),
                    "feedback": data.get("feedback"),
                    "evaluator": data.get("evaluator"),
                    "updated_at": data.get("updated_at"),
                }
        data["evaluations"] = evaluations
        pool = data.get("evaluation_pool")
        data["evaluation_pool"] = pool if isinstance(pool, dict) else {}
        sidecars[(competition_id, problem_id, run_id)] = data
    return sidecars


def sidecar_path(results_dir: Path, competition_id: str, problem_id: str, run_id: str) -> Path:
    return results_dir / safe_id(competition_id) / safe_id(problem_id) / f"{safe_id(run_id)}.json"


def stable_legacy_evaluation_id(run_id: str | None, result_id: str, source: str) -> str:
    digest = hashlib.sha1(f"{run_id or ''}:{result_id}:{source}".encode("utf-8")).hexdigest()[:16]
    return f"legacy_{digest}"


def normalize_evaluation(
    entry: dict[str, Any],
    *,
    result: dict[str, Any],
    run_id: str | None,
    source: str,
) -> dict[str, Any]:
    result_id = str(result.get("result_id") or entry.get("result_id") or "")
    updated_at = entry.get("updated_at") or entry.get("scored_at") or ""
    created_at = entry.get("created_at") or updated_at
    evaluation_id = entry.get("evaluation_id") or stable_legacy_evaluation_id(run_id, result_id, source)
    entry_model_key = entry.get("model_key")
    if entry_model_key and ":" in str(entry_model_key):
        entry_provider, entry_model_id = str(entry_model_key).split(":", 1)
        normalized_model_key = canonical_model_key(entry_provider, entry_model_id)
    else:
        normalized_model_key = canonical_model_key(
            entry.get("provider") or result.get("provider") or infer_provider(str(result.get("model") or "")),
            entry.get("model") or result.get("requested_model_id") or result.get("model") or "unknown",
        )
    return {
        **entry,
        "evaluation_id": str(evaluation_id),
        "result_id": result_id,
        "result_index": entry.get("result_index", result.get("result_index")),
        "model_key": normalized_model_key,
        "model": entry.get("model") or result.get("requested_model_id") or result.get("model") or "unknown",
        "evaluator": entry.get("evaluator") or entry.get("scored_by") or "",
        "score": entry.get("score"),
        "max_score": entry.get("max_score"),
        "score_category": entry.get("score_category"),
        "feedback": entry.get("feedback") if entry.get("feedback") is not None else entry.get("score_comment") or "",
        "created_at": created_at,
        "updated_at": updated_at,
        "_source": source,
    }


def evaluation_pool_for_result(result: dict[str, Any], sidecar: dict[str, Any] | None) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    result_id = str(result.get("result_id") or "")
    result_index = str(result.get("result_index"))
    run_id = sidecar.get("run_id") if isinstance(sidecar, dict) else None
    pool = sidecar.get("evaluation_pool") if isinstance(sidecar, dict) else None
    if isinstance(pool, dict):
        for key in (result_id, result_index):
            values = pool.get(key)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, dict):
                        entries.append(
                            normalize_evaluation(value, result=result, run_id=run_id, source="sidecar_pool")
                        )
                if key == result_id:
                    break

    evaluations = sidecar.get("evaluations") if isinstance(sidecar, dict) else None
    if isinstance(evaluations, dict):
        legacy = evaluations.get(result_id)
        source = "sidecar_result_id"
        if not isinstance(legacy, dict):
            legacy = evaluations.get(result_index)
            source = "sidecar_result_index"
        if isinstance(legacy, dict) and not entries:
            entries.append(normalize_evaluation(legacy, result=result, run_id=run_id, source=source))

    if result.get("score") is not None and not entries:
        entries.append(
            normalize_evaluation(
                {
                    "score": result.get("score"),
                    "evaluator": result.get("scored_by"),
                    "feedback": result.get("score_comment"),
                    "updated_at": result.get("scored_at"),
                },
                result=result,
                run_id=run_id,
                source="run_log_legacy",
            )
        )
    return sorted(entries, key=lambda item: item.get("updated_at") or item.get("created_at") or "")


def evaluation_for_result(result: dict[str, Any], sidecar: dict[str, Any] | None) -> dict[str, Any] | None:
    pool = evaluation_pool_for_result(result, sidecar)
    if not pool:
        return None
    latest = {**pool[-1]}
    latest["evaluation_pool"] = pool
    latest["evaluation_count"] = len(pool)
    return latest


def is_successful_answer(result: dict[str, Any]) -> bool:
    return not result.get("error") and bool(str(result.get("answer") or "").strip())


def run_attempt(
    *,
    run: dict[str, Any],
    result: dict[str, Any],
    evaluation: dict[str, Any] | None,
    max_score: float,
) -> dict[str, Any]:
    provider = canonical_provider(result.get("provider"), str(result.get("model") or ""))
    requested_model = result.get("requested_model_id") or result.get("model") or "unknown"
    key = canonical_model_key(str(provider), str(requested_model))
    return {
        "model_key": key,
        "provider": provider,
        "model_id": str(requested_model),
        "run_id": run.get("run_id"),
        "run_timestamp": run.get("completed_at") or run.get("timestamp") or run.get("started_at"),
        "log_path": run.get("_log_path"),
        "result": result,
        "result_id": result.get("result_id"),
        "result_index": result.get("result_index"),
        "evaluation": evaluation,
        "evaluations": evaluation.get("evaluation_pool", []) if evaluation else [],
        "evaluation_count": evaluation.get("evaluation_count", 0) if evaluation else 0,
        "score": evaluation.get("score") if evaluation else None,
        "score_category": score_category(evaluation.get("score") if evaluation else None, max_score),
        "successful_answer": is_successful_answer(result),
        "error": result.get("error"),
        "sort_key": timestamp_key(result.get("completed_at") or run.get("completed_at") or run.get("timestamp")),
    }


def classify_state(attempts: list[dict[str, Any]], max_score: float) -> dict[str, Any]:
    if not attempts:
        status = "not_run"
        latest = None
    else:
        attempts = sorted(attempts, key=lambda item: item["sort_key"])
        latest = attempts[-1]
        if not latest["successful_answer"]:
            status = "error"
        else:
            category = score_category(latest.get("score"), max_score)
            status = category or "unscored"
    label, css_class, symbol = STATUS_META[status]
    scored_success = next(
        (
            attempt
            for attempt in reversed(sorted(attempts, key=lambda item: item["sort_key"]))
            if attempt["successful_answer"] and attempt.get("score") is not None
        ),
        None,
    )
    return {
        "status": status,
        "status_label": label,
        "css_class": css_class,
        "symbol": symbol,
        "latest": latest,
        "attempt_count": len(attempts),
        "has_prior_scored_success": latest is not None and not latest["successful_answer"] and scored_success is not None,
        "prior_scored_success": scored_success,
    }


def cell_state(column: dict[str, Any], attempts: list[dict[str, Any]], max_score: float) -> dict[str, Any]:
    state = classify_state(attempts, max_score)
    latest = state["latest"]
    score = latest.get("score") if latest else None
    latency = latest["result"].get("latency_ms") if latest else None
    usage = latest["result"].get("usage") if latest and isinstance(latest["result"].get("usage"), dict) else {}
    total_tokens = usage.get("total_tokens") if usage else None
    if total_tokens is None and latest:
        prompt = latest["result"].get("prompt_tokens")
        completion = latest["result"].get("completion_tokens")
        if isinstance(prompt, int) and isinstance(completion, int):
            total_tokens = prompt + completion
    latest_timestamp = format_datetime_parts(latest.get("run_timestamp") if latest else None)["text"] if latest else "—"
    details = [
        f"Модель: {column['label']}",
        f"Состояние: {state['status_label']}",
        f"Оценка: {display_score(score)} / {display_score(max_score)}",
        f"Последняя попытка: {latest_timestamp or '—'}",
        f"Попыток: {state['attempt_count']}",
        f"Latency: {display_score(latency)} ms" if latency is not None else "Latency: —",
        f"Total tokens: {display_score(total_tokens)}",
    ]
    if latest and latest.get("error"):
        details.append(f"Ошибка: {str(latest['error'])[:180]}")
    if state["has_prior_scored_success"]:
        previous = state["prior_scored_success"]
        details.append(
            "Ранее был оценённый ответ: "
            f"{display_score(previous.get('score'))} / {display_score(max_score)}"
        )
    return {
        **column,
        **state,
        "attempts": sorted(attempts, key=lambda item: item["sort_key"], reverse=True),
        "score": score,
        "cell_text": format_score_value(score) if score is not None else state["symbol"],
        "max_score": max_score,
        "tooltip": "\n".join(details),
        "aria_label": "; ".join(details),
    }


def canonical_competitions(competitions_dir: Path, warnings: list[str]) -> dict[str, dict[str, Any]]:
    competitions: dict[str, dict[str, Any]] = {}
    if not competitions_dir.exists():
        return competitions
    for path in sorted(competitions_dir.iterdir()):
        if not path.is_dir() or path.name.startswith(".") or path.name.startswith("_"):
            continue
        if not (path / COMPETITION_MANIFEST).exists():
            continue
        try:
            competition = load_competition(path)
        except DataLoadError as exc:
            warnings.append(str(exc))
            continue
        item = {
            "competition_id": competition.id,
            "competition_title": competition.title,
            "description": competition.data.get("description"),
            "date": competition.data.get("date"),
            "metadata": competition.data.get("metadata") if isinstance(competition.data.get("metadata"), dict) else {},
            "competition": competition.data,
            "problems": {},
            "problem_order": [],
            "legacy": False,
            "warnings": [],
        }
        problem_records = []
        for problem_path in sorted(path.glob("*.json")):
            if problem_path.name == COMPETITION_MANIFEST:
                continue
            try:
                problem = load_problem(problem_path)
            except DataLoadError as exc:
                warnings.append(str(exc))
                continue
            problem_records.append(problem)
        for problem in sorted(problem_records, key=problem_sort_key):
            max_score = max_score_for(competition.data, problem.data)
            score_step = score_step_for(competition.data, problem.data, max_score)
            score_ticks = score_ticks_for(max_score, score_step)
            item["problems"][problem.id] = {
                "competition_id": competition.id,
                "competition_title": competition.title,
                "problem_id": problem.id,
                "problem_title": problem.title,
                "number": problem.number,
                "statement": problem.statement,
                "answer": problem.data.get("answer") or problem.data.get("expected_answer"),
                "solution": problem.data.get("solution"),
                "metadata": problem.data.get("metadata") if isinstance(problem.data.get("metadata"), dict) else {},
                "problem": problem.data,
                "path": str(problem.path),
                "max_score": max_score,
                "score_step": score_step,
                "half_score": half_score_for(max_score, score_step),
                "score_ticks": score_ticks,
                "score_interval_count": max(1, len(score_ticks) - 1),
                "runs": [],
                "attempts_by_model": {},
            }
            item["problem_order"].append(problem.id)
        competitions[competition.id] = item
    return competitions


def ensure_legacy_problem(
    competitions: dict[str, dict[str, Any]],
    run: dict[str, Any],
) -> dict[str, Any]:
    competition = competitions.setdefault(
        "legacy",
        {
            "competition_id": "legacy",
            "competition_title": "Старые прогоны",
            "description": "Логи, которые не удалось связать с каноническими соревнованиями.",
            "date": None,
            "metadata": {},
            "competition": {},
            "problems": {},
            "problem_order": [],
            "legacy": True,
            "warnings": [],
        },
    )
    problem_id = str(run.get("problem_id") or "unknown")
    if problem_id not in competition["problems"]:
        problem = run.get("problem") if isinstance(run.get("problem"), dict) else {}
        competition["problems"][problem_id] = {
            "competition_id": "legacy",
            "competition_title": "Старые прогоны",
            "problem_id": problem_id,
            "problem_title": run.get("problem_title") or display_problem_title(problem, problem_id),
            "number": problem.get("number"),
            "statement": run.get("problem_text") or problem.get("statement") or problem.get("text") or "",
            "answer": problem.get("answer") or problem.get("expected_answer"),
            "solution": problem.get("solution"),
            "metadata": {},
            "problem": problem,
            "path": run.get("problem_file") or "",
            "max_score": 10.0,
            "score_step": 1.0,
            "half_score": 5.0,
            "score_ticks": score_ticks_for(10.0, 1.0),
            "score_interval_count": 10,
            "runs": [],
            "attempts_by_model": {},
        }
        competition["problem_order"].append(problem_id)
    return competition["problems"][problem_id]


def attach_run(
    competitions: dict[str, dict[str, Any]],
    sidecars: dict[tuple[str, str, str], dict[str, Any]],
    run: dict[str, Any],
) -> None:
    competition_id = str(run.get("competition_id") or "legacy")
    problem_id = str(run.get("problem_id") or "unknown")
    problem = competitions.get(competition_id, {}).get("problems", {}).get(problem_id)
    if problem is None:
        problem = ensure_legacy_problem(competitions, run)
        run = {**run, "competition_id": "legacy", "competition_title": "Старые прогоны"}
        competition_id = "legacy"
        problem_id = str(problem["problem_id"])
    problem["runs"].append(run)
    sidecar = sidecars.get((competition_id, problem_id, str(run.get("run_id"))))
    for result in run.get("results", []):
        if not isinstance(result, dict):
            continue
        evaluation = evaluation_for_result(result, sidecar)
        attempt = run_attempt(
            run=run,
            result=result,
            evaluation=evaluation,
            max_score=float(problem["max_score"]),
        )
        problem["attempts_by_model"].setdefault(attempt["model_key"], []).append(attempt)


def finalize_catalog(competitions: dict[str, dict[str, Any]], warnings: list[str]) -> dict[str, Any]:
    configured = configured_model_columns()
    active_keys = set(configured)
    for competition in competitions.values():
        model_columns = dict(configured)
        ordered_columns = sorted(model_columns.values(), key=model_column_sort_key)
        answer_count = 0
        scored_count = 0
        latest_run = ""
        model_keys_seen: set[str] = set()
        for problem_id in competition["problem_order"]:
            problem = competition["problems"][problem_id]
            for key, attempts in problem["attempts_by_model"].items():
                if key not in active_keys:
                    continue
                for attempt in attempts:
                    model_keys_seen.add(key)
                    answer_count += 1
                    if attempt.get("score") is not None:
                        scored_count += 1
                    if attempt.get("run_timestamp") and attempt["run_timestamp"] > latest_run:
                        latest_run = attempt["run_timestamp"]
            problem["model_states"] = [
                cell_state(column, problem["attempts_by_model"].get(column["model_key"], []), float(problem["max_score"]))
                for column in ordered_columns
            ]
        competition["model_columns"] = ordered_columns
        competition["model_groups"] = model_groups_for(ordered_columns)
        competition["problem_count"] = len(competition["problem_order"])
        competition["model_count"] = len(model_keys_seen)
        competition["answer_count"] = answer_count
        competition["scored_count"] = scored_count
        competition["progress_percent"] = int((scored_count / answer_count) * 100) if answer_count else 0
        competition["latest_timestamp"] = latest_run
    competition_list = sorted(competitions.values(), key=competition_sort_key)
    return {
        "competitions": competition_list,
        "competition_groups": group_competitions_by_year(competition_list),
        "competition_map": competitions,
        "warnings": warnings,
    }


def extract_year_from_text(value: Any) -> int | None:
    if value is None:
        return None
    match = YEAR_PATTERN.search(str(value))
    return int(match.group(1)) if match else None


def competition_year(competition: dict[str, Any]) -> int | None:
    for key in ("date", "competition_id", "competition_title"):
        year = extract_year_from_text(competition.get(key))
        if year is not None:
            return year
    return None


def numeric_date_score(value: Any, *, allow_month_name: bool = False) -> int:
    if value is None:
        return 0
    text = str(value)
    match = re.search(r"((?:19|20)\d{2})(?:[-_.](\d{1,2}))?(?:[-_.](\d{1,2}))?", text)
    if match:
        year = int(match.group(1))
        month = int(match.group(2) or 0)
        day = int(match.group(3) or 0)
        if not (0 <= month <= 12 and 0 <= day <= 31):
            return 0
        return year * 10000 + month * 100 + day
    if not allow_month_name:
        return 0
    year_match = YEAR_PATTERN.search(text)
    if not year_match:
        return 0
    lower = text.lower()
    month = 0
    for name, number in MONTH_NAMES.items():
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", lower):
            month = number
            break
    if not month:
        return 0
    year = int(year_match.group(1))
    day = 0
    return year * 10000 + month * 100 + day


def competition_date_order_score(competition: dict[str, Any]) -> int:
    date_score = numeric_date_score(competition.get("date"))
    if date_score % 10000:
        return date_score
    return numeric_date_score(competition.get("competition_id"), allow_month_name=True)


def competition_inner_sort_key(competition: dict[str, Any]) -> tuple[int, int, str, str]:
    order_score = competition_date_order_score(competition)
    return (
        0 if order_score else 1,
        order_score,
        str(competition.get("competition_title") or "").lower(),
        str(competition.get("competition_id") or "").lower(),
    )


def competition_sort_key(competition: dict[str, Any]) -> tuple[int, int, int, int, str, str]:
    year = competition_year(competition)
    return (
        1 if year is None else 0,
        -(year or 0),
        *competition_inner_sort_key(competition),
    )


def group_competitions_by_year(competitions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[int | None, list[dict[str, Any]]] = {}
    for competition in competitions:
        year = competition_year(competition)
        competition["display_year"] = year
        groups.setdefault(year, []).append(competition)
    years = sorted((year for year in groups if year is not None), reverse=True)
    result = [
        {"year": year, "competitions": sorted(groups[year], key=competition_inner_sort_key)}
        for year in years
    ]
    if None in groups:
        result.append(
            {"year": None, "competitions": sorted(groups[None], key=competition_inner_sort_key)}
        )
    return result


def build_catalog(
    *,
    competitions_dir: Path,
    logs_dir: Path,
    results_dir: Path,
) -> dict[str, Any]:
    warnings: list[str] = []
    competitions = canonical_competitions(competitions_dir, warnings)
    sidecars = read_sidecars(results_dir, warnings)
    for path in iter_log_paths(logs_dir):
        data = load_json(path, warnings)
        if not data:
            continue
        run = normalize_run_log(data, path, logs_dir)
        attach_run(competitions, sidecars, run)
    return finalize_catalog(competitions, warnings)


def find_problem(catalog: dict[str, Any], competition_id: str, problem_id: str) -> dict[str, Any] | None:
    competition = catalog.get("competition_map", {}).get(competition_id)
    if not competition:
        return None
    return competition.get("problems", {}).get(problem_id)


def selected_state(problem: dict[str, Any], model_key_value: str | None) -> dict[str, Any] | None:
    states = problem.get("model_states") or []
    if model_key_value:
        for state in states:
            if state["model_key"] == model_key_value:
                return state
    for state in states:
        if state.get("attempt_count"):
            return state
    return states[0] if states else None


def model_states_for_review(problem: dict[str, Any]) -> list[dict[str, Any]]:
    states = list(problem.get("model_states") or [])
    pending = [state for state in states if state.get("attempt_count") and state.get("score") is None]
    reviewed = [state for state in states if state.get("attempt_count") and state.get("score") is not None]
    not_run = [state for state in states if not state.get("attempt_count")]
    return [*pending, *reviewed, *not_run]


def next_unscored_attempt(problem: dict[str, Any], current_model_key: str | None) -> dict[str, Any] | None:
    states = list(problem.get("model_states") or [])
    if not states:
        return None
    start_index = next(
        (index for index, state in enumerate(states) if state.get("model_key") == current_model_key),
        -1,
    )
    ordered_states = states[start_index + 1 :] + states[: start_index + 1] if start_index >= 0 else states
    for state in ordered_states:
        if state.get("model_key") == current_model_key:
            continue
        for attempt in state.get("attempts") or []:
            if attempt.get("successful_answer") and attempt.get("score") is None:
                return attempt
    return None


def anonymized_attempts(problem: dict[str, Any], seed: str) -> list[dict[str, Any]]:
    attempts = []
    for state in problem.get("model_states", []):
        for attempt in state.get("attempts", []):
            if not attempt.get("successful_answer"):
                continue
            result_id = str(attempt.get("result_id") or "")
            digest = hashlib.sha256(f"{seed}:{result_id}".encode("utf-8")).hexdigest()
            attempts.append({**attempt, "_anon_sort": digest})
    attempts = sorted(attempts, key=lambda item: item["_anon_sort"])
    for index, attempt in enumerate(attempts, start=1):
        attempt["anonymous_label"] = f"Решение {index}"
    return attempts


def competition_statistics(competition: dict[str, Any]) -> dict[str, Any]:
    model_stats: dict[str, dict[str, Any]] = {}
    for problem_id in competition.get("problem_order", []):
        problem = competition["problems"][problem_id]
        for state in problem.get("model_states", []):
            model_key_value = state["model_key"]
            model = model_stats.setdefault(
                model_key_value,
                {
                    "model_key": model_key_value,
                    "provider": state.get("provider"),
                    "model_id": state.get("model_id"),
                    "label": state.get("label"),
                    "short_label": state.get("short_label") or state.get("label"),
                    "provider_label": state.get("provider_label") or state.get("provider"),
                    "solution_count": 0,
                    "scored_solution_count": 0,
                    "evaluation_count": 0,
                    "solution_percent_sum": 0.0,
                    "full_solution_count": 0,
                    "problem_ids": set(),
                    "tasks": [],
                },
            )
            attempts = state.get("attempts") or []
            successful = [attempt for attempt in attempts if attempt.get("successful_answer")]
            model["solution_count"] += len(successful)
            if successful:
                model["problem_ids"].add(problem_id)

            task_solution_count = len(successful)
            task_scored_solution_count = 0
            task_evaluation_count = 0
            task_score_sum = 0.0
            task_percent_sum = 0.0
            latest_solution = None
            for attempt in successful:
                if attempt.get("run_timestamp") and (
                    latest_solution is None or attempt["run_timestamp"] > latest_solution
                ):
                    latest_solution = attempt["run_timestamp"]
                evaluation_scores = []
                evaluation_percents = []
                for evaluation in attempt.get("evaluations", []):
                    try:
                        score = float(evaluation.get("score"))
                        max_score = float(evaluation.get("max_score") or problem.get("max_score") or 10)
                    except (TypeError, ValueError):
                        continue
                    if not (math.isfinite(score) and math.isfinite(max_score) and max_score > 0):
                        continue
                    evaluation_scores.append(score)
                    evaluation_percents.append(score / max_score * 100)
                if not evaluation_percents:
                    continue
                solution_score = sum(evaluation_scores) / len(evaluation_scores)
                solution_percent = sum(evaluation_percents) / len(evaluation_percents)
                task_scored_solution_count += 1
                task_evaluation_count += len(evaluation_percents)
                task_score_sum += solution_score
                task_percent_sum += solution_percent
                model["scored_solution_count"] += 1
                model["evaluation_count"] += len(evaluation_percents)
                model["solution_percent_sum"] += solution_percent
                if math.isclose(solution_percent, 100.0, rel_tol=1e-9, abs_tol=1e-9):
                    model["full_solution_count"] += 1

            model["tasks"].append(
                {
                    "problem_id": problem_id,
                    "problem_title": problem["problem_title"],
                    "number": problem.get("number"),
                    "solution_count": task_solution_count,
                    "scored_solution_count": task_scored_solution_count,
                    "evaluation_count": task_evaluation_count,
                    "average_score": (
                        task_score_sum / task_scored_solution_count
                        if task_scored_solution_count
                        else None
                    ),
                    "max_score": float(problem.get("max_score") or 10),
                    "average_percent": (
                        task_percent_sum / task_scored_solution_count
                        if task_scored_solution_count
                        else None
                    ),
                    "latest_solution": latest_solution,
                    "status": state.get("status"),
                }
            )

    model_rows = []
    for model in model_stats.values():
        scored_solution_count = model["scored_solution_count"]
        solution_count = model["solution_count"]
        model_rows.append(
            {
                **model,
                "problem_count": len(model["problem_ids"]),
                "average_percent": (
                    model["solution_percent_sum"] / scored_solution_count
                    if scored_solution_count
                    else None
                ),
                "coverage_percent": (
                    solution_count / max(1, competition.get("problem_count", 0)) * 100
                ),
            }
        )
    model_rows.sort(
        key=lambda item: (
            item["average_percent"] if item["average_percent"] is not None else -1,
            item["scored_solution_count"],
            item["solution_count"],
        ),
        reverse=True,
    )
    return {
        "models": model_rows,
        "model_columns": competition.get("model_columns", []),
    }


def attempt_state_for_aggregate(state: dict[str, Any] | None) -> tuple[str, str, str]:
    if not state or not state.get("attempt_count"):
        return "not_run", SCORE_CLASS_BY_CATEGORY["not_run"], "Модель не запускалась"
    status = str(state.get("status") or "not_run")
    if status == "error":
        return "error", SCORE_CLASS_BY_CATEGORY["error"], state.get("aria_label") or "Ошибка ответа модели"
    if status == "unscored":
        return "unscored", SCORE_CLASS_BY_CATEGORY["unscored"], "Ожидает проверки"
    return status, SCORE_CLASS_BY_CATEGORY.get(status, "cell-unscored"), state.get("aria_label") or ""


def aggregate_payload(
    *,
    mode: str,
    value: float | None,
    max_score: float,
    problem_title: str,
    model_label: str,
    evaluation_count: int,
    fallback_class: str,
    fallback_text: str,
    fallback_label: str,
) -> dict[str, Any]:
    label = AGGREGATE_MODES[mode]
    if value is None:
        return {
            "value": None,
            "text": fallback_text,
            "category": None,
            "css_class": fallback_class,
            "aria_label": f"{problem_title}; {model_label}; {fallback_label}",
        }
    category = score_category(value, max_score) or "partial"
    text = format_score_value(value)
    return {
        "value": value,
        "text": text,
        "category": category,
        "css_class": SCORE_CLASS_BY_CATEGORY[category],
        "aria_label": (
            f"{problem_title}; {model_label}; {label}: {text}; "
            f"проверок: {evaluation_count}; максимум: {format_score_value(max_score)}"
        ),
    }


def checks_statistics(competition: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    scores_by_cell: dict[tuple[str, str], list[float]] = {}
    max_scores_by_cell: dict[tuple[str, str], float] = {}
    for row in rows:
        score = parse_score(row.get("score"))
        if score is None:
            continue
        key = (row.get("problem_id") or "", row.get("model_key") or "")
        scores_by_cell.setdefault(key, []).append(score)
        max_score = parse_score(row.get("max_score"))
        if max_score is not None:
            max_scores_by_cell[key] = max_score

    task_rows = []
    for problem_id in competition.get("problem_order", []):
        problem = competition["problems"][problem_id]
        states_by_model = {
            state.get("model_key"): state
            for state in problem.get("model_states", [])
        }
        cells = {}
        for model in competition.get("model_columns", []):
            model_key_value = model["model_key"]
            key = (problem_id, model_key_value)
            scores = scores_by_cell.get(key, [])
            max_score = max_scores_by_cell.get(key, float(problem.get("max_score") or 10))
            attempt_state, fallback_class, fallback_label = attempt_state_for_aggregate(states_by_model.get(model_key_value))
            fallback_text = "?" if attempt_state == "unscored" else ""
            values = aggregate_scores(scores)
            aggregates = {
                mode: aggregate_payload(
                    mode=mode,
                    value=values[mode],
                    max_score=max_score,
                    problem_title=problem.get("problem_title") or problem_id,
                    model_label=f"{model.get('provider_label') or model.get('provider')} {model.get('short_label') or model.get('label')}",
                    evaluation_count=len(scores),
                    fallback_class=fallback_class,
                    fallback_text=fallback_text,
                    fallback_label=fallback_label,
                )
                for mode in AGGREGATE_MODES
            }
            cells[model_key_value] = {
                "problem_id": problem_id,
                "model_key": model_key_value,
                "max_score": max_score,
                "attempt_state": attempt_state,
                "evaluation_count": len(scores),
                "aggregates": aggregates,
                "initial": aggregates[DEFAULT_AGGREGATE_MODE],
            }
        task_rows.append({"problem": problem, "cells": cells})

    sorted_rows = sorted(
        rows,
        key=lambda item: (
            item.get("problem_id") or "",
            item.get("model_key") or "",
            item.get("updated_at") or item.get("created_at") or "",
            item.get("evaluator") or "",
        ),
    )
    return {
        "mode": DEFAULT_AGGREGATE_MODE,
        "mode_label": AGGREGATE_MODES[DEFAULT_AGGREGATE_MODE],
        "modes": AGGREGATE_MODES,
        "tasks": task_rows,
        "rows": sorted_rows,
        "row_count": len(sorted_rows),
    }


def neighbor_problem_ids(competition: dict[str, Any], problem_id: str) -> tuple[str | None, str | None]:
    order = competition.get("problem_order") or []
    if problem_id not in order:
        return None, None
    index = order.index(problem_id)
    previous_id = order[index - 1] if index > 0 else None
    next_id = order[index + 1] if index + 1 < len(order) else None
    return previous_id, next_id


def find_attempt(
    catalog: dict[str, Any],
    *,
    competition_id: str,
    problem_id: str,
    run_id: str,
    result_id: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    problem = find_problem(catalog, competition_id, problem_id)
    if not problem:
        return None
    for state in problem.get("model_states", []):
        for attempt in state.get("attempts", []):
            if attempt.get("run_id") == run_id and attempt.get("result_id") == result_id:
                return problem, attempt
    return None


def load_sidecar_payload(results_dir: Path, competition_id: str, problem_id: str, run_id: str) -> dict[str, Any]:
    path = sidecar_path(results_dir, competition_id, problem_id, run_id)
    warnings: list[str] = []
    payload = load_json(path, warnings) if path.exists() else None
    if not payload:
        payload = {}
    evaluations = payload.get("evaluations")
    if not isinstance(evaluations, dict):
        evaluations = {}
    payload["evaluations"] = evaluations
    pool = payload.get("evaluation_pool")
    if not isinstance(pool, dict):
        pool = {}
    payload["evaluation_pool"] = pool
    return payload


def sync_latest_evaluation_snapshot(payload: dict[str, Any], result_id: str) -> None:
    pool = payload.setdefault("evaluation_pool", {})
    evaluations = payload.setdefault("evaluations", {})
    values = pool.get(result_id)
    if isinstance(values, list) and values:
        latest = sorted(values, key=lambda item: item.get("updated_at") or item.get("created_at") or "")[-1]
        evaluations[result_id] = {
            key: value
            for key, value in latest.items()
            if not str(key).startswith("_")
        }
    else:
        evaluations.pop(result_id, None)


def stamp_sidecar(
    payload: dict[str, Any],
    *,
    competition_id: str,
    problem_id: str,
    run_id: str,
    updated_at: str,
) -> None:
    payload.update(
        {
            "schema_version": SIDECAR_SCHEMA_VERSION,
            "competition_id": competition_id,
            "problem_id": problem_id,
            "run_id": run_id,
            "updated_at": updated_at,
        }
    )


def save_evaluation(
    *,
    results_dir: Path,
    competition_id: str,
    problem_id: str,
    run_id: str,
    result_id: str,
    result_index: int,
    model_key_value: str,
    model: str,
    evaluator: str | None,
    score: float,
    max_score: float,
    feedback: str | None,
) -> dict[str, Any]:
    path = sidecar_path(results_dir, competition_id, problem_id, run_id)
    payload = load_sidecar_payload(results_dir, competition_id, problem_id, run_id)
    pool = payload.setdefault("evaluation_pool", {})
    updated_at = utc_now()
    evaluator_value = (evaluator or "").strip()
    entry = {
        "evaluation_id": f"ev_{uuid.uuid4().hex}",
        "result_id": result_id,
        "result_index": result_index,
        "model_key": model_key_value,
        "model": model,
        "evaluator": evaluator_value,
        "score": score,
        "max_score": max_score,
        "score_category": score_category(score, max_score),
        "feedback": feedback or "",
        "created_at": updated_at,
        "updated_at": updated_at,
    }
    values = pool.setdefault(result_id, [])
    if not isinstance(values, list):
        values = []
        pool[result_id] = values
    values.append(entry)
    sync_latest_evaluation_snapshot(payload, result_id)
    stamp_sidecar(
        payload,
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        updated_at=updated_at,
    )
    atomic_write_json(path, payload)
    return payload


def delete_evaluation(
    *,
    results_dir: Path,
    competition_id: str,
    problem_id: str,
    run_id: str,
    result_id: str,
    evaluation_id: str,
) -> bool:
    path = sidecar_path(results_dir, competition_id, problem_id, run_id)
    if not path.exists():
        return False
    payload = load_sidecar_payload(results_dir, competition_id, problem_id, run_id)
    pool = payload.setdefault("evaluation_pool", {})
    values = pool.get(result_id)
    if not isinstance(values, list):
        return False
    next_values = [
        item
        for item in values
        if not (isinstance(item, dict) and str(item.get("evaluation_id")) == str(evaluation_id))
    ]
    if len(next_values) == len(values):
        return False
    if next_values:
        pool[result_id] = next_values
    else:
        pool.pop(result_id, None)
    updated_at = utc_now()
    sync_latest_evaluation_snapshot(payload, result_id)
    stamp_sidecar(
        payload,
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        updated_at=updated_at,
    )
    atomic_write_json(path, payload)
    return True


def upsert_imported_evaluation(
    *,
    results_dir: Path,
    competition_id: str,
    problem_id: str,
    run_id: str,
    result_id: str,
    result_index: int,
    model_key_value: str,
    model: str,
    evaluation: dict[str, Any],
) -> None:
    path = sidecar_path(results_dir, competition_id, problem_id, run_id)
    payload = load_sidecar_payload(results_dir, competition_id, problem_id, run_id)
    pool = payload.setdefault("evaluation_pool", {})
    now = utc_now()
    entry = {
        "evaluation_id": str(evaluation.get("evaluation_id") or f"ev_{uuid.uuid4().hex}"),
        "result_id": result_id,
        "result_index": result_index,
        "model_key": evaluation.get("model_key") or model_key_value,
        "model": evaluation.get("model") or model,
        "evaluator": evaluation.get("evaluator") or "",
        "score": evaluation.get("score"),
        "max_score": evaluation.get("max_score"),
        "score_category": evaluation.get("score_category"),
        "feedback": evaluation.get("feedback") or "",
        "created_at": evaluation.get("created_at") or now,
        "updated_at": evaluation.get("updated_at") or now,
    }
    if entry["score_category"] is None and entry["score"] is not None and entry["max_score"] is not None:
        entry["score_category"] = score_category(entry["score"], float(entry["max_score"]))
    values = pool.setdefault(result_id, [])
    if not isinstance(values, list):
        values = []
        pool[result_id] = values
    replaced = False
    for index, item in enumerate(values):
        if isinstance(item, dict) and str(item.get("evaluation_id")) == entry["evaluation_id"]:
            values[index] = entry
            replaced = True
            break
    if not replaced:
        values.append(entry)
    sync_latest_evaluation_snapshot(payload, result_id)
    stamp_sidecar(
        payload,
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        updated_at=now,
    )
    atomic_write_json(path, payload)


def iter_evaluation_rows(
    catalog: dict[str, Any],
    *,
    competition_id: str | None = None,
    problem_id: str | None = None,
    evaluator: str | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    evaluator_filter = (evaluator or "").strip()
    for competition in catalog.get("competitions", []):
        if competition_id and competition.get("competition_id") != competition_id:
            continue
        for current_problem_id in competition.get("problem_order", []):
            if problem_id and current_problem_id != problem_id:
                continue
            problem = competition["problems"][current_problem_id]
            for state in problem.get("model_states", []):
                for attempt in state.get("attempts", []):
                    for evaluation in attempt.get("evaluations", []):
                        if evaluator_filter and evaluation.get("evaluator") != evaluator_filter:
                            continue
                        rows.append(
                            {
                                "competition_id": competition["competition_id"],
                                "competition_title": competition.get("competition_title") or "",
                                "problem_id": problem["problem_id"],
                                "problem_title": problem.get("problem_title") or "",
                                "run_id": attempt.get("run_id") or "",
                                "result_id": attempt.get("result_id") or "",
                                "result_index": attempt.get("result_index"),
                                "evaluation_id": evaluation.get("evaluation_id") or "",
                                "evaluator": evaluation.get("evaluator") or "",
                                "score": evaluation.get("score"),
                                "max_score": evaluation.get("max_score") or problem.get("max_score"),
                                "score_category": evaluation.get("score_category") or "",
                                "feedback": evaluation.get("feedback") or "",
                                "created_at": evaluation.get("created_at") or "",
                                "updated_at": evaluation.get("updated_at") or "",
                                "model_key": attempt.get("model_key") or "",
                                "model": attempt.get("model_id") or "",
                            }
                        )
    return rows
