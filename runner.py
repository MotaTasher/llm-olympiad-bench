from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import os
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

MODEL_VERSION_MODULES = {
    "openai": "models.gpt.versions",
    "anthropic": "models.claude.versions",
    "deepseek": "models.deepseek.versions",
    "gigachat": "models.gigachat.versions",
    "yandexgpt": "models.yandexgpt.versions",
}

MODEL_ENV_VARS = {
    "OPENAI_MODEL",
    "ANTHROPIC_MODEL",
    "GIGACHAT_MODEL",
    "YANDEX_MODEL",
    "DEEPSEEK_MODEL",
}


@dataclass(frozen=True)
class RunSettings:
    reasoning_budget_tokens: int | None = None
    max_final_tokens: int | None = None


@dataclass(frozen=True)
class ProblemRunResult:
    run_id: str
    log_path: Path
    log: dict[str, Any]
    results: list[dict[str, Any]]
    table_rows: list[dict[str, Any]]


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


def create_model(
    alias: str,
    *,
    reasoning_budget_tokens: int | None = None,
    max_final_tokens: int | None = None,
) -> BaseModel:
    raw = alias.strip()
    key, _, model_id = raw.partition(":")
    key = key.lower()
    if key not in MODEL_CLASSES:
        known = ", ".join(sorted(MODEL_CLASSES))
        raise ValueError(f"Unknown model alias '{alias}'. Known aliases: {known}")
    module_name, class_name = MODEL_CLASSES[key]
    module = importlib.import_module(module_name)
    model_class = getattr(module, class_name)
    kwargs = {
        "reasoning_budget_tokens": reasoning_budget_tokens,
        "max_final_tokens": max_final_tokens,
    }
    if any(value is not None for value in kwargs.values()):
        return model_class(model=model_id or None, **kwargs)
    return model_class(model=model_id) if model_id else model_class()


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
    key = alias.strip().split(":", 1)[0].lower()
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


def active_model_specs() -> list[str]:
    specs = []
    for provider, module_name in MODEL_VERSION_MODULES.items():
        module = importlib.import_module(module_name)
        for model_id in getattr(module, "VERSIONS", []) or []:
            specs.append(f"{provider}:{model_id}")
    return specs


def requested_aliases(value: str) -> list[str]:
    aliases = []
    for item in [part.strip() for part in value.split(",") if part.strip()]:
        if item.lower() in {"all", "site", "configured"}:
            aliases.extend(active_model_specs())
        else:
            aliases.append(item)
    result = []
    seen = set()
    for alias in aliases:
        if alias not in seen:
            result.append(alias)
            seen.add(alias)
    return result


def positive_optional_int(value: str | int | None, *, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{name} must be a positive integer") from exc
    if parsed <= 0:
        raise SystemExit(f"{name} must be a positive integer")
    return parsed


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


def format_duration(ms: int) -> str:
    if ms < 1000:
        return f"{ms}ms"
    seconds = ms / 1000
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, remainder = divmod(int(seconds), 60)
    return f"{minutes}m{remainder:02d}s"


def print_progress(message: str) -> None:
    print(message, flush=True)


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
        default=None,
        help=(
            "Comma-separated aliases/specs. Examples: gpt,claude or "
            "openai:gpt-5.5,anthropic:claude-opus-4-8. Use 'all' to run every "
            "active model shown in the scoring UI. Defaults to RUNNER_MODELS "
            "from config/models.env."
        ),
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
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help=(
            "Maximum completion/output tokens passed to every selected adapter. "
            "Defaults to RUNNER_MAX_TOKENS or provider-specific env settings."
        ),
    )
    return parser.parse_args()


def run_problem(
    *,
    problem_file: Path | str,
    models_value: str,
    logs_dir: Path | str = "logs",
    competition: str | None = None,
    competition_title: str | None = None,
    run_id_suffix: str | None = None,
    command: list[str] | None = None,
    cli_metadata: dict[str, Any] | None = None,
    settings: RunSettings | None = None,
    max_tokens: int | None = None,
) -> ProblemRunResult:
    problem_file = Path(problem_file)
    (
        problem_text,
        problem_data,
        competition_data,
        source_competition_id,
        source_competition_title,
        source_problem_id,
        problem_title,
    ) = load_problem_input(problem_file)
    competition_id = slugify_id(competition or source_competition_id)
    resolved_competition_title = competition_title or source_competition_title
    problem_id = slugify_id(source_problem_id)
    now = datetime.now(UTC)
    timestamp = isoformat_z(now)
    git = git_metadata()
    git_hash = str(git.get("hash") or "")
    run_id = build_run_id(now, run_id_suffix or problem_title)
    aliases = requested_aliases(models_value)
    logs_dir = Path(logs_dir)
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
            command or sys.argv,
            aliases,
            cli_metadata or {
                "problem": str(problem_file),
                "competition": competition,
                "competition_title": competition_title,
                "models": models_value,
                "run_id": run_id_suffix,
                "logs_dir": str(logs_dir),
                "max_tokens": max_tokens,
            },
        ),
        "requested_models": aliases,
        "competition_id": competition_id,
        "competition_title": resolved_competition_title,
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
            "max_tokens": max_tokens,
            "reasoning_budget_tokens": (
                settings.reasoning_budget_tokens if settings else None
            ),
            "max_final_tokens": settings.max_final_tokens if settings else None,
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
    total_models = len(aliases)
    print_progress(
        f"Run {run_id}: {competition_id}/{problem_id}, "
        f"{total_models} model(s), max_tokens={max_tokens or 'provider-default'}"
    )
    for result_index, alias in enumerate(aliases):
        ordinal = f"[{result_index + 1}/{total_models}]"
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
        model_label = alias
        print_progress(f"{ordinal} START {model_label}")
        try:
            if settings and (
                settings.reasoning_budget_tokens is not None
                or settings.max_final_tokens is not None
            ):
                model = create_model(
                    alias,
                    reasoning_budget_tokens=settings.reasoning_budget_tokens,
                    max_final_tokens=settings.max_final_tokens,
                )
            else:
                model = create_model(alias)
            model_label = model.model_id
            skeleton["adapter_class"] = f"{model.__class__.__module__}.{model.__class__.__name__}"
            skeleton["requested_model_id"] = model.model_id
            skeleton["model"] = model.model_id
            write_log(
                log,
                logs_dir,
                competition_id=competition_id,
                problem_id=problem_id,
            )
            result = model.solve(problem_text, max_tokens=max_tokens)
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
        token_count = result.prompt_tokens + result.completion_tokens
        if result.error:
            print_progress(
                f"{ordinal} ERROR {model_label} in {format_duration(measured_ms)}: "
                f"{short_error or 'unknown error'}"
            )
        else:
            print_progress(
                f"{ordinal} DONE  {model_label} in {format_duration(measured_ms)} "
                f"tokens={token_count} cost_usd={result.cost_usd:.6f}"
            )
        table_rows.append(
            {
                "model": result.model,
                "tokens": token_count,
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
    return ProblemRunResult(
        run_id=run_id,
        log_path=log_path,
        log=log,
        results=results,
        table_rows=table_rows,
    )


def main() -> int:
    args = parse_args()
    load_env(allow_model_env_overrides=args.allow_env_model_overrides)
    models_value = args.models or os.environ.get("RUNNER_MODELS") or os.environ.get("OLYMPIAD_MODELS")
    if not models_value:
        raise SystemExit(
            "models are required. Pass --models or set RUNNER_MODELS in config/models.env"
        )
    max_tokens = positive_optional_int(
        args.max_tokens if args.max_tokens is not None else os.environ.get("RUNNER_MAX_TOKENS"),
        name="--max-tokens",
    )
    try:
        run_result = run_problem(
            problem_file=Path(args.problem),
            models_value=models_value,
            logs_dir=Path(args.logs_dir),
            competition=args.competition,
            competition_title=args.competition_title,
            run_id_suffix=args.run_id,
            command=sys.argv,
            cli_metadata={
                "problem": str(args.problem),
                "competition": args.competition,
                "competition_title": args.competition_title,
                "models": models_value,
                "run_id": args.run_id,
                "logs_dir": args.logs_dir,
                "allow_env_model_overrides": args.allow_env_model_overrides,
                "max_tokens": max_tokens,
            },
            max_tokens=max_tokens,
        )
    except DataLoadError as exc:
        raise SystemExit(str(exc)) from exc
    log = run_result.log
    run_id = run_result.run_id
    competition_id = str(log["competition_id"])
    competition_title = str(log["competition_title"])
    problem_id = str(log["problem_id"])
    problem_title = str(log["problem_title"])
    timestamp = str(log["timestamp"])
    git_hash = str(log.get("git_hash") or "")
    log_path = run_result.log_path
    table_rows = run_result.table_rows
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
