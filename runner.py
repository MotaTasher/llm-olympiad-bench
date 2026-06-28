from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models.base import BaseModel
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
) -> tuple[str, dict[str, Any], str, str, str, str]:
    if problem_file.suffix.lower() == ".json":
        competition, problem = resolve_problem(problem_file)
        return (
            problem.statement,
            problem.data,
            competition.id,
            competition.title,
            problem.id,
            problem.title,
        )
    text = problem_file.read_text(encoding="utf-8")
    data = {"id": problem_file.stem, "statement": text}
    return text, data, "default", "default", problem_file.stem, problem_file.stem


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
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def slugify_run_name(value: str) -> str:
    slug = re.sub(r"[^\w.-]+", "_", value.strip(), flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_.-")
    return slug or "run"


def slugify_id(value: str) -> str:
    return slugify_run_name(value).lower()


def build_run_id(timestamp: datetime, run_name: str) -> str:
    timestamp_id = timestamp.strftime("%Y_%m_%d_%H_%M_%S")
    return f"{timestamp_id}_{slugify_run_name(run_name)}"


def write_log(
    log: dict[str, Any],
    logs_dir: Path,
    *,
    competition_id: str,
    problem_id: str,
) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_dir = logs_dir / competition_id / problem_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{log['run_id']}.json"
    log_path.write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return log_path


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
    timestamp = now.isoformat().replace("+00:00", "Z")
    git_hash = get_git_hash()
    run_id = build_run_id(now, args.run_id or problem_title)

    results = []
    table_rows = []
    for alias in [item.strip() for item in args.models.split(",") if item.strip()]:
        model = create_model(alias)
        result = model.solve(problem_text)
        results.append(result.to_log_dict())
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

    log = {
        "run_id": run_id,
        "timestamp": timestamp,
        "git_hash": git_hash,
        "competition_id": competition_id,
        "competition_title": competition_title,
        "problem_id": problem_id,
        "problem_title": problem_title,
        "problem_file": str(problem_file),
        "problem_text": problem_text,
        "problem": problem_data,
        "results": results,
    }
    log_path = write_log(
        log,
        Path(args.logs_dir),
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
