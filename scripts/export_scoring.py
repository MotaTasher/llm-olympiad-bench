from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


DEFAULT_LOGS_DIR = Path("logs")
DEFAULT_RESULTS_DIR = Path("data/results")


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def path_competition_id(path: Path, logs_dir: Path) -> str:
    try:
        parts = path.relative_to(logs_dir).parts
    except ValueError:
        return "legacy"
    if len(parts) >= 3:
        return parts[0]
    return "legacy"


def path_problem_id(path: Path, logs_dir: Path) -> str:
    try:
        parts = path.relative_to(logs_dir).parts
    except ValueError:
        return path.stem
    if len(parts) >= 3:
        return parts[1]
    return path.stem


def value_from_problem(data: dict[str, Any], key: str) -> str:
    problem = data.get("problem")
    if isinstance(problem, dict):
        value = problem.get(key)
        if isinstance(value, str):
            return value
    return ""


def sidecar_path(results_dir: Path, competition_id: str, problem_id: str, run_id: str) -> Path:
    return results_dir / competition_id / problem_id / f"{run_id}.json"


def sidecar_evaluation(
    results_dir: Path,
    competition_id: str,
    problem_id: str,
    run_id: str,
    result_index: int,
) -> dict[str, Any]:
    data = load_json(sidecar_path(results_dir, competition_id, problem_id, run_id))
    if not data:
        return {}
    evaluations = data.get("evaluations")
    if isinstance(evaluations, dict):
        evaluation = evaluations.get(str(result_index))
        if isinstance(evaluation, dict):
            return evaluation
    if result_index == 0 and any(data.get(key) for key in ("score", "feedback", "evaluator")):
        return {
            "score": data.get("score"),
            "evaluator": data.get("evaluator"),
            "feedback": data.get("feedback"),
            "updated_at": data.get("updated_at"),
        }
    return {}


def rows_from_logs(logs_dir: Path, results_dir: Path, only_scored: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(logs_dir.rglob("*.json")):
        data = load_json(path)
        if not data:
            continue
        competition_id = data.get("competition_id") or path_competition_id(path, logs_dir)
        problem_id = data.get("problem_id") or path_problem_id(path, logs_dir)
        problem_title = data.get("problem_title") or value_from_problem(data, "title") or problem_id
        problem_text = data.get("problem_text") or value_from_problem(data, "text")
        raw_results = data.get("results", [])
        if isinstance(raw_results, list) and raw_results:
            results = [item for item in raw_results if isinstance(item, dict)]
        else:
            answer = data.get("answer") or data.get("solution") or data.get("response") or data.get("output")
            results = [{"model": data.get("model") or data.get("run_id", path.stem), "answer": answer}] if answer else []

        run_id = data.get("run_id", path.stem)
        for result_index, result in enumerate(results):
            evaluation = sidecar_evaluation(
                results_dir,
                str(competition_id),
                str(problem_id),
                str(run_id),
                result_index,
            )
            score = result.get("score")
            if score is None:
                score = evaluation.get("score")
            scored_by = result.get("scored_by") or evaluation.get("evaluator")
            scored_at = result.get("scored_at") or evaluation.get("updated_at")
            score_comment = result.get("score_comment") or evaluation.get("feedback")
            if only_scored and score is None:
                continue
            rows.append(
                {
                    "competition_id": competition_id,
                    "competition_title": data.get("competition_title") or competition_id,
                    "problem_id": problem_id,
                    "problem_title": problem_title,
                    "run_id": run_id,
                    "result_index": result_index,
                    "timestamp": data.get("timestamp", ""),
                    "git_hash": data.get("git_hash", ""),
                    "problem_file": data.get("problem_file", ""),
                    "problem_text": problem_text,
                    "model": result.get("model", ""),
                    "answer": result.get("answer", ""),
                    "error": result.get("error"),
                    "prompt_tokens": result.get("prompt_tokens", 0),
                    "completion_tokens": result.get("completion_tokens", 0),
                    "cost_usd": result.get("cost_usd", 0.0),
                    "latency_ms": result.get("latency_ms", 0),
                    "score": score,
                    "scored_by": scored_by,
                    "scored_at": scored_at,
                    "score_comment": score_comment,
                    "log_path": str(path),
                    "result_path": str(sidecar_path(results_dir, str(competition_id), str(problem_id), str(run_id))),
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
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
