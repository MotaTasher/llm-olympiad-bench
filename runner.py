from __future__ import annotations

import argparse
import importlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from models.base import BaseModel


MODEL_CLASSES = {
    "gpt": ("models.gpt", "GPTModel"),
    "openai": ("models.gpt", "GPTModel"),
    "claude": ("models.claude", "ClaudeModel"),
    "anthropic": ("models.claude", "ClaudeModel"),
    "gigachat": ("models.gigachat", "GigaChatModel"),
    "sber": ("models.gigachat", "GigaChatModel"),
    "alice": ("models.alice", "AliceModel"),
    "yandex": ("models.yandexgpt", "YandexGPTModel"),
    "yandexgpt": ("models.yandexgpt", "YandexGPTModel"),
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


def load_env() -> None:
    load_env_file(Path(".env"))
    secret_paths = set(Path("models").glob("*/secrets/*.env"))
    secret_paths.update(Path("models").glob("*/secrets/.env"))
    for path in sorted(secret_paths):
        load_env_file(path, override=True)


def load_problem(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        data = json.loads(text)
        problem_text = data.get("text")
        if not isinstance(problem_text, str) or not problem_text.strip():
            raise ValueError(f"{path} must contain a non-empty JSON field: text")
        return problem_text, data
    return text, {"text": text}


def create_model(alias: str) -> BaseModel:
    key = alias.strip().lower()
    if key not in MODEL_CLASSES:
        known = ", ".join(sorted(MODEL_CLASSES))
        raise ValueError(f"Unknown model alias '{alias}'. Known aliases: {known}")
    module_name, class_name = MODEL_CLASSES[key]
    module = importlib.import_module(module_name)
    model_class = getattr(module, class_name)
    return model_class()


def write_log(log: dict[str, Any], logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{log['run_id']}.json"
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
        headers = ["model", "tokens", "cost_usd", "latency_ms", "status"]
        print(" | ".join(headers))
        for row in rows:
            print(" | ".join(str(row[h]) for h in headers))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run olympiad problem through selected LLMs.")
    parser.add_argument("--problem", required=True, help="Path to .json problem or .md file")
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated aliases: gpt,claude,gigachat,yandexgpt/alice",
    )
    parser.add_argument("--run-id", default=None, help="Optional log id")
    parser.add_argument("--logs-dir", default="logs", help="Where to write run JSON logs")
    return parser.parse_args()


def main() -> int:
    load_env()
    args = parse_args()

    problem_file = Path(args.problem)
    problem_text, problem_data = load_problem(problem_file)
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")

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
        "problem_file": str(problem_file),
        "problem_text": problem_text,
        "problem": problem_data,
        "timestamp": timestamp,
        "results": results,
    }
    log_path = write_log(log, Path(args.logs_dir))
    print_table(table_rows)
    print(f"\nLog written: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
