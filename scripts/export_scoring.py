from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from models.telemetry import normalize_run_log
from scoring.repository import (
    canonical_model_key,
    canonical_provider,
    evaluation_for_result,
    max_score_for,
    read_sidecars,
    score_category,
    sidecar_path,
)


DEFAULT_LOGS_DIR = Path("logs")
DEFAULT_RESULTS_DIR = Path("data/results")


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return value if isinstance(value, dict) else None


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


def json_field(value: Any) -> str:
    if value is None or value == "":
        return ""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def rows_from_logs(logs_dir: Path, results_dir: Path, only_scored: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    sidecars = read_sidecars(results_dir, warnings)
    for path in iter_log_paths(logs_dir):
        raw = load_json(path)
        if not raw:
            continue
        run = normalize_run_log(raw, path, logs_dir)
        competition_id = str(run.get("competition_id") or "legacy")
        problem_id = str(run.get("problem_id") or path.stem)
        run_id = str(run.get("run_id") or path.stem)
        problem = run.get("problem") if isinstance(run.get("problem"), dict) else {}
        competition = run.get("competition") if isinstance(run.get("competition"), dict) else {}
        max_score = max_score_for(competition, problem)
        sidecar = sidecars.get((competition_id, problem_id, run_id))
        for result_index, result in enumerate(run.get("results", [])):
            if not isinstance(result, dict):
                continue
            evaluation = evaluation_for_result(result, sidecar)
            score = evaluation.get("score") if evaluation else result.get("score")
            if only_scored and score is None:
                continue
            usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
            timing = result.get("timing") if isinstance(result.get("timing"), dict) else {}
            cost = result.get("cost") if isinstance(result.get("cost"), dict) else {}
            requested_model_id = result.get("requested_model_id") or result.get("model")
            provider = canonical_provider(result.get("provider"), requested_model_id)
            model_key_value = canonical_model_key(provider, requested_model_id)
            rows.append(
                {
                    "competition_id": competition_id,
                    "competition_title": run.get("competition_title") or competition_id,
                    "problem_id": problem_id,
                    "problem_title": run.get("problem_title") or problem_id,
                    "run_id": run_id,
                    "result_index": result.get("result_index", result_index),
                    "timestamp": run.get("timestamp", ""),
                    "git_hash": run.get("git_hash", ""),
                    "problem_file": run.get("problem_file", ""),
                    "problem_text": run.get("problem_text", ""),
                    "model": result.get("model", ""),
                    "answer": result.get("answer", ""),
                    "error": result.get("error"),
                    "prompt_tokens": result.get("prompt_tokens", 0),
                    "completion_tokens": result.get("completion_tokens", 0),
                    "cost_usd": result.get("cost_usd", 0.0),
                    "latency_ms": result.get("latency_ms", 0),
                    "score": score,
                    "scored_by": (evaluation or {}).get("evaluator") or result.get("scored_by"),
                    "scored_at": (evaluation or {}).get("updated_at") or result.get("scored_at"),
                    "score_comment": (evaluation or {}).get("feedback") or result.get("score_comment"),
                    "log_path": str(path),
                    "result_path": str(sidecar_path(results_dir, competition_id, problem_id, run_id)),
                    "schema_version": run.get("schema_version"),
                    "result_id": result.get("result_id"),
                    "provider": provider,
                    "model_key": model_key_value,
                    "requested_model_id": result.get("requested_model_id"),
                    "resolved_model_id": result.get("resolved_model_id"),
                    "result_status": result.get("status"),
                    "total_tokens": usage.get("total_tokens"),
                    "reasoning_tokens": usage.get("reasoning_tokens"),
                    "cached_tokens": usage.get("cached_input_tokens"),
                    "finish_reason": result.get("finish_reason"),
                    "provider_request_id": result.get("provider_request_id"),
                    "timing": json_field(timing),
                    "timing_wall_ms": timing.get("wall_ms"),
                    "timing_monotonic_ms": timing.get("monotonic_ms"),
                    "time_to_first_token_ms": timing.get("time_to_first_token_ms"),
                    "reasoning_ms": timing.get("reasoning_ms"),
                    "cost": json_field(cost),
                    "cost_currency": cost.get("currency"),
                    "cost_total": cost.get("total"),
                    "cost_estimated": cost.get("estimated"),
                    "max_score": max_score,
                    "score_category": score_category(score, max_score),
                    "problem_hash": run.get("problem_hash"),
                    "problem_text_hash": run.get("problem_text_hash"),
                    "system_prompt_hash": (run.get("system_prompt") or {}).get("sha256") if isinstance(run.get("system_prompt"), dict) else "",
                    "evaluation_source": (evaluation or {}).get("_source"),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Export scored model answers from logs.")
    parser.add_argument("--logs-dir", default=str(DEFAULT_LOGS_DIR))
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument(
        "--format",
        choices=["csv", "jsonl"],
        default="csv",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output path. Defaults to data/results/scoring_dataset.<format>.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Include unscored answers too. By default only scored answers are exported.",
    )
    args = parser.parse_args()

    output = Path(args.output) if args.output else DEFAULT_RESULTS_DIR / f"scoring_dataset.{args.format}"
    rows = rows_from_logs(
        Path(args.logs_dir),
        Path(args.results_dir),
        only_scored=not args.all,
    )
    if args.format == "csv":
        write_csv(output, rows)
    else:
        write_jsonl(output, rows)
    print(f"Exported {len(rows)} rows to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
