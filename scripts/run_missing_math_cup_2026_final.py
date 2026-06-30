from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.common import SYSTEM_PROMPT
from models.pricing import estimate_cost, estimate_tokens
from runner import active_model_specs, provider_for_alias


COMPETITION_ID = "math-cup-2026-final"
DEFAULT_MAX_TOKENS = 320_000
DEFAULT_TASK_COUNT = 9


@dataclass(frozen=True)
class MissingPair:
    problem_id: str
    model: str
    reason: str
    attempts: int
    latest_log: str | None


def json_data(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def model_candidates(result: dict[str, Any]) -> list[str]:
    provider = str(result.get("provider") or "")
    alias = str(result.get("alias") or "")
    model_id = str(
        result.get("requested_model_id")
        or result.get("resolved_model_id")
        or result.get("model")
        or ""
    )
    candidates = []
    if alias:
        candidates.append(alias)
    if provider and model_id:
        candidates.append(f"{provider}:{model_id}")
    if provider and result.get("model"):
        candidates.append(f"{provider}:{result['model']}")
    return candidates


def find_missing_pairs(
    *,
    logs_dir: Path,
    models: list[str],
    problems: list[str],
) -> list[MissingPair]:
    states: dict[tuple[str, str], dict[str, Any]] = {
        (problem_id, model): {
            "success": False,
            "errors": [],
            "empty": 0,
            "attempts": 0,
            "latest": None,
        }
        for problem_id in problems
        for model in models
    }
    competition_logs = logs_dir / COMPETITION_ID
    for path in sorted(competition_logs.glob("task_*/*.json")):
        payload = json_data(path)
        if not payload:
            continue
        problem_id = str(payload.get("problem_id") or path.parent.name)
        for result in payload.get("results", []):
            key = next(
                (
                    candidate
                    for candidate in model_candidates(result)
                    if (problem_id, candidate) in states
                ),
                None,
            )
            if not key:
                continue
            state = states[(problem_id, key)]
            state["attempts"] += 1
            state["latest"] = path.name
            answer = str(result.get("answer") or "").strip()
            if answer and not result.get("error"):
                state["success"] = True
            elif result.get("error"):
                state["errors"].append(str(result["error"]).replace("\n", " ")[:160])
            else:
                state["empty"] += 1

    missing = []
    for problem_id in problems:
        for model in models:
            state = states[(problem_id, model)]
            if state["success"]:
                continue
            if not state["attempts"]:
                reason = "no attempts"
            elif state["errors"]:
                reason = f"error: {state['errors'][-1]}"
            else:
                reason = "empty answer"
            missing.append(
                MissingPair(
                    problem_id=problem_id,
                    model=model,
                    reason=reason,
                    attempts=int(state["attempts"]),
                    latest_log=state["latest"],
                )
            )
    return missing


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def estimate_missing_cost(
    *,
    data_dir: Path,
    missing: list[MissingPair],
    max_tokens: int,
) -> tuple[float, dict[str, float], dict[str, float]]:
    total = 0.0
    by_provider: dict[str, float] = {}
    by_model: dict[str, float] = {}
    for pair in missing:
        provider, _, model_id = pair.model.partition(":")
        problem_path = data_dir / COMPETITION_ID / f"{pair.problem_id}.json"
        problem = json_data(problem_path) or {}
        input_tokens = estimate_tokens(
            f"{SYSTEM_PROMPT}\n\n{problem.get('statement') or ''}"
        )
        cost = estimate_cost(
            provider,
            model_id,
            input_tokens=input_tokens,
            output_tokens=max_tokens,
        )
        usd = float(cost.get("total") or 0.0)
        total += usd
        by_provider[provider] = by_provider.get(provider, 0.0) + usd
        by_model[pair.model] = by_model.get(pair.model, 0.0) + usd
    return total, by_provider, by_model


async def run_one(
    *,
    pair: MissingPair,
    args: argparse.Namespace,
    run_group: str,
    semaphore: asyncio.Semaphore,
) -> int:
    async with semaphore:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        problem_path = (
            Path(args.data_dir)
            / COMPETITION_ID
            / f"{pair.problem_id}.json"
        )
        suffix = (
            f"{run_group}_{pair.problem_id}_{safe_name(pair.model)}_"
            f"{args.max_tokens}"
        )
        command = [
            sys.executable,
            "runner.py",
            "--problem",
            str(problem_path),
            "--models",
            pair.model,
            "--max-tokens",
            str(args.max_tokens),
            "--logs-dir",
            str(Path(args.logs_dir)),
            "--run-id",
            suffix,
        ]
        log_path = output_dir / f"{pair.problem_id}__{safe_name(pair.model)}.log"
        started = datetime.now(UTC).isoformat()
        with log_path.open("w", encoding="utf-8") as stream:
            stream.write(
                f"START {started} {pair.problem_id} {pair.model}\n"
                f"COMMAND {' '.join(command)}\n"
            )
            stream.flush()
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=stream,
                stderr=asyncio.subprocess.STDOUT,
                cwd=Path(args.repo_dir),
                env=os.environ.copy(),
            )
            code = await process.wait()
            finished = datetime.now(UTC).isoformat()
            stream.write(
                f"\nDONE {finished} {pair.problem_id} {pair.model} exit={code}\n"
            )
        print(f"DONE {pair.problem_id} {pair.model} exit={code}", flush=True)
        return code


async def run_all(args: argparse.Namespace, missing: list[MissingPair]) -> int:
    run_group = args.run_group or datetime.now(UTC).strftime("retry_320k_%Y%m%d_%H%M%S")
    workers = args.workers if args.workers is not None else len(missing)
    semaphore = asyncio.Semaphore(max(1, workers))
    print(
        f"Launching {len(missing)} pair(s), workers={max(1, workers)}, "
        f"max_tokens={args.max_tokens}, run_group={run_group}",
        flush=True,
    )
    codes = await asyncio.gather(
        *[
            run_one(pair=pair, args=args, run_group=run_group, semaphore=semaphore)
            for pair in missing
        ]
    )
    return 0 if all(code == 0 for code in codes) else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retry missing Math Cup 2026 final model-task pairs in parallel."
    )
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--logs-dir", default="/opt/olympiad-scorer/shared/logs")
    parser.add_argument("--data-dir", default="data/competitions")
    parser.add_argument("--output-dir", default="run-output/missing-2026-final-320k")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument("--workers", type=int, default=None)
    parser.add_argument("--run-group", default=None)
    parser.add_argument(
        "--models",
        default="all",
        help="Comma-separated model specs, or all active models.",
    )
    parser.add_argument(
        "--problems",
        default=",".join(f"task_{index:02d}" for index in range(1, DEFAULT_TASK_COUNT + 1)),
        help="Comma-separated problem ids.",
    )
    parser.add_argument("--yes", action="store_true", help="Actually launch API calls.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    models = (
        active_model_specs()
        if args.models == "all"
        else [item.strip() for item in args.models.split(",") if item.strip()]
    )
    problems = [item.strip() for item in args.problems.split(",") if item.strip()]
    missing = find_missing_pairs(
        logs_dir=Path(args.logs_dir),
        models=models,
        problems=problems,
    )
    print(f"Missing successful non-empty answers: {len(missing)}")
    for pair in missing:
        print(
            f"{pair.problem_id}\t{pair.model}\t{pair.reason}\t"
            f"attempts={pair.attempts}\tlatest={pair.latest_log or '-'}"
        )
    total, by_provider, by_model = estimate_missing_cost(
        data_dir=Path(args.data_dir),
        missing=missing,
        max_tokens=args.max_tokens,
    )
    print("\nEstimated max cost:")
    for provider, amount in sorted(by_provider.items()):
        print(f"provider\t{provider}\t${amount:.4f}")
    for model, amount in sorted(by_model.items()):
        print(f"model\t{model}\t${amount:.4f}")
    print(f"total\t${total:.4f}")
    print(f"total_plus_20pct\t${total * 1.2:.4f}")

    if not missing:
        return 0
    if not args.yes:
        print("\nDry-run only. Re-run with --yes to launch API calls.")
        return 0
    return asyncio.run(run_all(args, missing))


if __name__ == "__main__":
    raise SystemExit(main())
