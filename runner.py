from __future__ import annotations

import argparse
import importlib
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models.base import BaseModel
from models.common import SYSTEM_PROMPT, error_result
from models.telemetry import (
    RUN_LOG_SCHEMA_VERSION,
    SYSTEM_PROMPT_VERSION,
    atomic_write_json,
    git_metadata,
    isoformat_z,
    monotonic_ms,
    normalize_legacy_result,
    runtime_metadata,
    sha256_json,
    sha256_text,
    stable_result_id,
)
from olympiad_data import DataLoadError, resolve_problem


MODEL_CLASSES = {
    "gpt": ("models.gpt", "GPTModel"),
    "openai": ("models.gpt", "GPTModel"),
    "claude": ("models.claude", "ClaudeModel"),
    "anthropic": ("models.claude", "ClaudeModel"),
    "deepseek": ("models.deepseek", "DeepSeekModel"),
    "ds": ("models.deepseek", "DeepSeekModel"),
    "gigachat": ("models.gigachat", "GigaChatModel"),
    "sber": ("models.gigachat", "GigaChatModel"),
    "alice": ("models.yandexgpt", "AliceModel"),
    "yandex": ("models.yandexgpt", "YandexGPTModel"),
    "yandexgpt": ("models.yandexgpt", "YandexGPTModel"),
}

MODEL_ENV_VARS = {
    "OPENAI_MODEL",
    "ANTHROPIC_MODEL",
    "GIGACHAT_MODEL",
    "YANDEX_MODEL",
    "DEEPSEEK_MODEL",
}


def load_env_file(path: Path, override: bool = False) -> None:
    if not path.exists():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(path, override=override)
        return
    except Exception:
        pass

    import os

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


def load_env(*, allow_model_env_overrides: bool = False) -> None:
    import os

    explicit_model_env = {
        name: os.environ[name] for name in MODEL_ENV_VARS if name in os.environ
    }
    load_env_file(Path(".env"))
    secret_paths = set(Path("models").glob("*/secrets/*.env"))
    secret_paths.update(Path("models").glob("*/secrets/.env"))
    for path in sorted(secret_paths):
        load_env_file(path, override=True)

    # .env and model-local secrets are for credentials. Ignore stale model
    # selections left there; versions.py/config/models.env own model choice.
    for name in MODEL_ENV_VARS:
        if not allow_model_env_overrides:
            os.environ.pop(name, None)
        elif name not in explicit_model_env:
            os.environ.pop(name, None)
    if allow_model_env_overrides:
        os.environ.update(explicit_model_env)

    load_env_file(Path("config/models.env"), override=True)


def load_problem_input(
    problem_file: Path,
) -> tuple[str, dict[str, Any], dict[str, Any], str, str, str, str]:
    if problem_file.suffix.lower() == ".json":
        competition, problem = resolve_problem(problem_file)
        return (
            problem.statement,
            problem.data,
            competition.data,
            competition.id,
            competition.title,
            problem.id,
            problem.title,
        )
    text = problem_file.read_text(encoding="utf-8")
    data = {"id": problem_file.stem, "statement": text}
    return text, data, {}, "default", "default", problem_file.stem, problem_file.stem


def create_model(alias: str) -> BaseModel:
    key = alias.strip().lower()
    if key not in MODEL_CLASSES:
        known = ", ".join(sorted(MODEL_CLASSES))
        raise ValueError(f"Unknown model alias '{alias}'. Known aliases: {known}")
    module_name, class_name = MODEL_CLASSES[key]
    module = importlib.import_module(module_name)
    model_class = getattr(module, class_name)
    return model_class()


def get_git_hash() -> str:
    return str(git_metadata().get("hash") or "")


def slugify_run_name(value: str) -> str:
    slug = re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_.-")
    return slug or "run"


def slugify_id(value: str) -> str:
    return slugify_run_name(value).lower()


def build_run_id(timestamp: datetime, run_name: str) -> str:
    timestamp_id = timestamp.strftime("%Y_%m_%d_%H_%M_%S")
    return f"{timestamp_id}_{slugify_run_name(run_name)}"


def log_path_for(
    logs_dir: Path,
    *,
    competition_id: str,
    problem_id: str,
    run_id: str,
) -> Path:
    return logs_dir / competition_id / problem_id / f"{run_id}.json"


def write_log(
    log: dict[str, Any],
    logs_dir: Path,
    *,
    competition_id: str,
    problem_id: str,
) -> Path:
    log_path = log_path_for(
        logs_dir,
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=str(log["run_id"]),
    )
    return atomic_write_json(log_path, log)


def provider_for_alias(alias: str) -> str:
    key = alias.strip().lower()
    if key in {"gpt", "openai"}:
        return "openai"
    if key in {"claude", "anthropic"}:
        return "anthropic"
    if key in {"deepseek", "ds"}:
        return "deepseek"
    if key in {"gigachat", "sber"}:
        return "gigachat"
    if key in {"alice", "yandex", "yandexgpt"}:
        return "yandexgpt"
    return "unknown"


def requested_aliases(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def initial_result(
    *,
    run_id: str,
    result_index: int,
    alias: str,
    provider: str,
    adapter_class: str | None = None,
    requested_model_id: str | None = None,
) -> dict[str, Any]:
    result_id = stable_result_id(run_id, result_index, alias, requested_model_id)
    return {
        "result_id": result_id,
        "result_index": result_index,
        "provider": provider,
        "alias": alias,
        "adapter_class": adapter_class,
        "requested_model_id": requested_model_id,
        "resolved_model_id": None,
        "model": requested_model_id or alias,
        "attempt": 1,
        "started_at": isoformat_z(),
        "completed_at": None,
        "status": "running",
        "request": {},
        "answer": "",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cost_usd": 0.0,
        "latency_ms": 0,
        "raw_response": {},
        "usage": {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "reasoning_tokens": None,
            "cached_input_tokens": None,
            "cache_creation_input_tokens": None,
            "raw": {},
            "source": None,
        },
        "timing": {
            "wall_ms": None,
            "monotonic_ms": None,
            "time_to_first_token_ms": None,
            "reasoning_ms": None,
            "retry_durations_ms": [],
            "attempts_total_ms": None,
            "source": "runner",
        },
        "cost": {
            "currency": "USD",
            "input": None,
            "output": None,
            "cached_input": None,
            "reasoning": None,
            "total": None,
            "pricing_source": None,
            "pricing_version": None,
            "estimated": None,
            "exchange_rate": None,
        },
        "finish_reason": None,
        "provider_request_id": None,
        "response_id": None,
        "provider_timestamp": None,
        "error": None,
        "error_info": None,
        "score": None,
        "scored_by": None,
        "scored_at": None,
        "score_comment": None,
    }


def finalize_result(
    skeleton: dict[str, Any],
    result: Any,
    *,
    competition_id: str,
    problem_id: str,
    run_id: str,
    measured_ms: int,
) -> dict[str, Any]:
    if hasattr(result, "to_log_dict"):
        payload = result.to_log_dict()
    elif isinstance(result, dict):
        payload = result
    else:
        payload = error_result(str(skeleton.get("model") or skeleton.get("alias")), RuntimeError("Adapter returned invalid result")).to_log_dict()
    payload = normalize_legacy_result(
        payload,
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
        result_index=int(skeleton["result_index"]),
        provider=str(skeleton.get("provider") or "unknown"),
    )
    timing = payload.get("timing") if isinstance(payload.get("timing"), dict) else {}
    if not timing.get("wall_ms"):
        timing["wall_ms"] = measured_ms
    if not timing.get("monotonic_ms"):
        timing["monotonic_ms"] = measured_ms
    if not timing.get("attempts_total_ms"):
        timing["attempts_total_ms"] = measured_ms
    return {
        **skeleton,
        **payload,
        "result_id": skeleton["result_id"],
        "result_index": skeleton["result_index"],
        "provider": payload.get("provider") or skeleton.get("provider"),
        "alias": skeleton.get("alias"),
        "adapter_class": skeleton.get("adapter_class") or payload.get("adapter_class"),
        "requested_model_id": payload.get("requested_model_id") or skeleton.get("requested_model_id"),
        "resolved_model_id": payload.get("resolved_model_id") or payload.get("model") or skeleton.get("requested_model_id"),
        "model": payload.get("model") or skeleton.get("model"),
        "status": "error" if payload.get("error") else "success",
        "completed_at": isoformat_z(),
        "timing": timing,
        "latency_ms": payload.get("latency_ms") or measured_ms,
    }


def run_status(results: list[dict[str, Any]]) -> str:
    if any(item.get("status") == "running" for item in results):
        return "running"
    if not results:
        return "failed"
    success_count = sum(1 for item in results if item.get("status") == "success")
    if success_count == len(results):
        return "completed"
    if success_count:
        return "partial"
    return "failed"


def print_table(rows: list[dict[str, Any]]) -> None:
    try:
        from tabulate import tabulate

        print(tabulate(rows, headers="keys", tablefmt="github"))
    except Exception:
        headers = ["model", "tokens", "cost_usd", "latency_ms", "status", "error"]
        print(" | ".join(headers))
        for row in rows:
            print(" | ".join(str(row.get(h, "")) for h in headers))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run olympiad problem through selected LLMs.")
    parser.add_argument("--problem", required=True, help="Path to .json problem or .md file")
    parser.add_argument(
        "--competition",
        default=None,
        help="Competition id override. Defaults to parent competition.json or 'default'.",
    )
    parser.add_argument(
        "--competition-title",
        default=None,
        help="Human-readable competition title override.",
    )
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated aliases: gpt,claude,gigachat,yandexgpt/alice",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional run name suffix. Final log id is YYYY_MM_DD_HH_MM_SS_<name>",
    )
    parser.add_argument("--logs-dir", default="logs", help="Where to write run JSON logs")
    parser.add_argument(
        "--allow-env-model-overrides",
        action="store_true",
        help="Allow inherited OPENAI_MODEL/GIGACHAT_MODEL/YANDEX_MODEL env vars to override versions.py",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env(allow_model_env_overrides=args.allow_env_model_overrides)

    problem_file = Path(args.problem)
    try:
        (
            problem_text,
            problem_data,
            competition_data,
            source_competition_id,
            source_competition_title,
            source_problem_id,
            problem_title,
        ) = load_problem_input(problem_file)
    except DataLoadError as exc:
        raise SystemExit(str(exc)) from exc
    competition_id = slugify_id(args.competition or source_competition_id)
    competition_title = args.competition_title or source_competition_title
    problem_id = slugify_id(source_problem_id)
    now = datetime.now(UTC)
    timestamp = isoformat_z(now)
    git = git_metadata()
    git_hash = str(git.get("hash") or "")
    run_id = build_run_id(now, args.run_id or problem_title)
    aliases = requested_aliases(args.models)
    logs_dir = Path(args.logs_dir)
    log_path = log_path_for(
        logs_dir,
        competition_id=competition_id,
        problem_id=problem_id,
        run_id=run_id,
    )
    if log_path.exists():
        try:
            import json

            existing_data = json.loads(log_path.read_text(encoding="utf-8"))
        except Exception:
            existing_data = {}
        if existing_data.get("status") == "running":
            print(f"Existing unfinished run-log found and will be overwritten atomically: {log_path}")

    started_mono = monotonic_ms()
    log = {
        "schema_version": RUN_LOG_SCHEMA_VERSION,
        "run_id": run_id,
        "timestamp": timestamp,
        "started_at": timestamp,
        "completed_at": None,
        "duration_ms": None,
        "status": "running",
        "git_hash": git_hash,
        "git": git,
        "runtime": runtime_metadata(
            sys.argv,
            aliases,
            {
                "problem": str(problem_file),
                "competition": args.competition,
                "competition_title": args.competition_title,
                "models": args.models,
                "run_id": args.run_id,
                "logs_dir": args.logs_dir,
                "allow_env_model_overrides": args.allow_env_model_overrides,
            },
        ),
        "requested_models": aliases,
        "competition_id": competition_id,
        "competition_title": competition_title,
        "competition": competition_data,
        "problem_id": problem_id,
        "problem_number": problem_data.get("number"),
        "problem_title": problem_title,
        "problem_file": str(problem_file),
        "problem_text": problem_text,
        "problem": problem_data,
        "problem_hash": sha256_json(problem_data),
        "problem_text_hash": sha256_text(problem_text),
        "system_prompt": {
            "version": SYSTEM_PROMPT_VERSION,
            "sha256": sha256_text(SYSTEM_PROMPT),
            "text": SYSTEM_PROMPT,
        },
        "runtime_settings": {
            "text_only": True,
            "sequential": True,
        },
        "results": [],
    }
    write_log(
        log,
        logs_dir,
        competition_id=competition_id,
        problem_id=problem_id,
    )

    results = []
    table_rows = []
    for result_index, alias in enumerate(aliases):
        provider = provider_for_alias(alias)
        skeleton = initial_result(
            run_id=run_id,
            result_index=result_index,
            alias=alias,
            provider=provider,
        )
        log["results"].append(skeleton)
        write_log(
            log,
            logs_dir,
            competition_id=competition_id,
            problem_id=problem_id,
        )
        call_start = time.monotonic()
        try:
            model = create_model(alias)
            skeleton["adapter_class"] = f"{model.__class__.__module__}.{model.__class__.__name__}"
            skeleton["requested_model_id"] = model.model_id
            skeleton["model"] = model.model_id
            write_log(
                log,
                logs_dir,
                competition_id=competition_id,
                problem_id=problem_id,
            )
            result = model.solve(problem_text)
        except Exception as exc:
            result = error_result(skeleton.get("requested_model_id") or alias, exc)
        measured_ms = int((time.monotonic() - call_start) * 1000)
        finalized = finalize_result(
            skeleton,
            result,
            competition_id=competition_id,
            problem_id=problem_id,
            run_id=run_id,
            measured_ms=measured_ms,
        )
        log["results"][result_index] = finalized
        log["status"] = run_status(log["results"])
        write_log(
            log,
            logs_dir,
            competition_id=competition_id,
            problem_id=problem_id,
        )
        results.append(finalized)
        status = "error" if result.error else "ok"
        short_error = ""
        if result.error:
            short_error = result.error.replace("\n", " ")[:120]
        table_rows.append(
            {
                "model": result.model,
                "tokens": result.prompt_tokens + result.completion_tokens,
                "cost_usd": f"{result.cost_usd:.6f}",
                "latency_ms": result.latency_ms,
                "status": status,
                "error": short_error,
            }
        )

    log["completed_at"] = isoformat_z()
    log["duration_ms"] = monotonic_ms() - started_mono
    log["status"] = run_status(log["results"])
    log_path = write_log(
        log,
        logs_dir,
        competition_id=competition_id,
        problem_id=problem_id,
    )
    print_table(table_rows)
    print(f"\nRun ID: {run_id}")
    print(f"Competition: {competition_id} ({competition_title})")
    print(f"Problem: {problem_id} ({problem_title})")
    print(f"Timestamp: {timestamp}")
    print(f"Git hash: {git_hash or 'n/a'}")
    print(f"Log written: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
