from __future__ import annotations

import hashlib
import importlib
import json
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


PROVIDER_LABELS = {
    "anthropic": "Anthropic",
    "deepseek": "DeepSeek",
    "gigachat": "GigaChat",
    "openai": "OpenAI",
    "unknown": "unknown",
    "yandexgpt": "YandexGPT",
}

STATUS_META = {
    "not_run": ("Не запускалась", "cell-not-run", "Пусто"),
    "error": ("Ошибка", "cell-error", "!"),
    "unscored": ("Не проверено", "cell-unscored", "Ждёт"),
    "zero": ("0 баллов", "cell-zero", "0"),
    "partial": ("Частично", "cell-partial", "Частично"),
    "full": ("Максимум", "cell-full", "Макс."),
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


def max_score_for(competition: dict[str, Any], problem: dict[str, Any]) -> float:
    for source in (problem, competition):
        metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        value = metadata.get("max_score")
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
            return float(value)
        if isinstance(value, str):
            try:
                parsed = float(value)
            except ValueError:
                continue
            if parsed > 0:
                return parsed
    return 10.0


def score_category(score: Any, max_score: float) -> str | None:
    if score is None or score == "":
        return None
    try:
        value = float(score)
    except (TypeError, ValueError):
        return None
    if value == 0:
        return "zero"
    if value >= max_score:
        return "full"
    if 0 < value < max_score:
        return "partial"
    return None


def configured_model_columns() -> dict[str, dict[str, Any]]:
    columns: dict[str, dict[str, Any]] = {}
    providers = {
        "anthropic": "models.claude.versions",
        "deepseek": "models.deepseek.versions",
        "gigachat": "models.gigachat.versions",
        "openai": "models.gpt.versions",
        "yandexgpt": "models.yandexgpt.versions",
    }
    for provider, module_name in providers.items():
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue
        for model_id in getattr(module, "VERSIONS", []) or []:
            key = model_key(provider, str(model_id))
            columns.setdefault(
                key,
                {
                    "model_key": key,
                    "provider": provider,
                    "model_id": str(model_id),
                    "label": str(model_id),
                    "configured": True,
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
    if "gigachat" in lower:
        return "gigachat"
    if "yandex" in lower or "alice" in lower:
        return "yandexgpt"
    return "unknown"


def model_key(provider: str | None, model_id: str | None) -> str:
    provider = provider or "unknown"
    model_id = model_id or "unknown"
    return f"{provider}:{model_id}"


def display_score(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


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
    return {
        **entry,
        "evaluation_id": str(evaluation_id),
        "result_id": result_id,
        "result_index": entry.get("result_index", result.get("result_index")),
        "model_key": entry.get("model_key") or model_key(
            entry.get("provider") or result.get("provider") or infer_provider(str(result.get("model") or "")),
            entry.get("model") or result.get("requested_model_id") or result.get("model") or "unknown",
        ),
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
    provider = result.get("provider") or infer_provider(str(result.get("model") or ""))
    requested_model = result.get("requested_model_id") or result.get("model") or "unknown"
    key = model_key(str(provider), str(requested_model))
    return {
        "model_key": key,
        "provider": str(provider),
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
    details = [
        f"Модель: {column['label']}",
        f"Состояние: {state['status_label']}",
        f"Оценка: {display_score(score)} / {display_score(max_score)}",
        f"Последняя попытка: {latest.get('run_timestamp') if latest else '—'}",
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
    for competition in competitions.values():
        model_columns = dict(configured)
        answer_count = 0
        scored_count = 0
        latest_run = ""
        model_keys_seen: set[str] = set()
        for problem_id in competition["problem_order"]:
            problem = competition["problems"][problem_id]
            for attempts in problem["attempts_by_model"].values():
                for attempt in attempts:
                    key = attempt["model_key"]
                    model_keys_seen.add(key)
                    model_columns.setdefault(
                        key,
                        {
                            "model_key": key,
                            "provider": attempt["provider"],
                            "model_id": attempt["model_id"],
                            "label": attempt["model_id"],
                            "configured": False,
                        },
                    )
                    answer_count += 1
                    if attempt.get("score") is not None:
                        scored_count += 1
                    if attempt.get("run_timestamp") and attempt["run_timestamp"] > latest_run:
                        latest_run = attempt["run_timestamp"]
            ordered_columns = sorted(
                model_columns.values(),
                key=lambda item: (item["provider"], item["model_id"]),
            )
            problem["model_states"] = [
                cell_state(column, problem["attempts_by_model"].get(column["model_key"], []), float(problem["max_score"]))
                for column in ordered_columns
            ]
        competition["model_columns"] = sorted(
            model_columns.values(),
            key=lambda item: (item["provider"], item["model_id"]),
        )
        competition["problem_count"] = len(competition["problem_order"])
        competition["model_count"] = len(model_keys_seen)
        competition["answer_count"] = answer_count
        competition["scored_count"] = scored_count
        competition["progress_percent"] = int((scored_count / answer_count) * 100) if answer_count else 0
        competition["latest_timestamp"] = latest_run
    competition_list = sorted(
        competitions.values(),
        key=lambda item: (
            item.get("date") or item.get("latest_timestamp") or "",
            item.get("competition_title") or "",
        ),
        reverse=True,
    )
    return {
        "competitions": competition_list,
        "competition_map": competitions,
        "warnings": warnings,
    }


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
    task_rows = []
    for problem_id in competition.get("problem_order", []):
        problem = competition["problems"][problem_id]
        task_cells = {}
        for state in problem.get("model_states", []):
            model_key_value = state["model_key"]
            model = model_stats.setdefault(
                model_key_value,
                {
                    "model_key": model_key_value,
                    "provider": state.get("provider"),
                    "model_id": state.get("model_id"),
                    "label": state.get("label"),
                    "answer_count": 0,
                    "scored_count": 0,
                    "score_sum": 0.0,
                    "max_score_sum": 0.0,
                    "full_count": 0,
                    "problem_ids": set(),
                    "tasks": [],
                },
            )
            attempts = state.get("attempts") or []
            successful = [attempt for attempt in attempts if attempt.get("successful_answer")]
            scored = [attempt for attempt in successful if attempt.get("score") is not None]
            model["answer_count"] += len(successful)
            if successful:
                model["problem_ids"].add(problem_id)
            score_sum = 0.0
            max_score_sum = 0.0
            for attempt in scored:
                score = float(attempt.get("score") or 0)
                max_score = float(attempt.get("max_score") or problem["max_score"] or 10)
                model["score_sum"] += score
                model["max_score_sum"] += max_score
                model["scored_count"] += 1
                score_sum += score
                max_score_sum += max_score
                if score >= max_score:
                    model["full_count"] += 1
            average = (score_sum / len(scored)) if scored else None
            percent = (score_sum / max_score_sum * 100) if max_score_sum else None
            latest = state.get("latest")
            cell = {
                "attempt_count": len(successful),
                "scored_count": len(scored),
                "average_score": average,
                "average_percent": percent,
                "latest_run": latest.get("run_id") if latest else None,
                "status": state.get("status"),
            }
            task_cells[model_key_value] = cell
            model["tasks"].append(
                {
                    "problem_id": problem_id,
                    "problem_title": problem["problem_title"],
                    "number": problem.get("number"),
                    **cell,
                }
            )
        task_rows.append({"problem": problem, "cells": task_cells})

    model_rows = []
    for model in model_stats.values():
        scored_count = model["scored_count"]
        answer_count = model["answer_count"]
        model_rows.append(
            {
                **model,
                "problem_count": len(model["problem_ids"]),
                "average_score": (model["score_sum"] / scored_count) if scored_count else None,
                "average_percent": (
                    model["score_sum"] / model["max_score_sum"] * 100
                    if model["max_score_sum"]
                    else None
                ),
                "coverage_percent": (
                    answer_count / max(1, competition.get("problem_count", 0)) * 100
                ),
            }
        )
    model_rows.sort(
        key=lambda item: (
            item["average_percent"] if item["average_percent"] is not None else -1,
            item["scored_count"],
            item["answer_count"],
        ),
        reverse=True,
    )
    return {
        "models": model_rows,
        "tasks": task_rows,
        "model_columns": competition.get("model_columns", []),
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
    previous_values = pool.get(result_id)
    previous = {}
    if isinstance(previous_values, list) and previous_values:
        previous = sorted(previous_values, key=lambda item: item.get("updated_at") or item.get("created_at") or "")[-1]
    elif isinstance(payload["evaluations"].get(result_id), dict):
        previous = payload["evaluations"][result_id]
    elif isinstance(payload["evaluations"].get(str(result_index)), dict):
        previous = payload["evaluations"][str(result_index)]
    updated_at = utc_now()
    evaluator_value = evaluator if evaluator not in {None, ""} else previous.get("evaluator", "")
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
