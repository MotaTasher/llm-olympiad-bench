from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from models.common import SYSTEM_PROMPT
from models.pricing import estimate_cost, estimate_tokens


COMPETITION_ID = "math-cup-2026-final"
DEFAULT_TASK_COUNT = 9
DEFAULT_OUTPUT_DIR = "run-output/new-models-2026-final"
DEFAULT_LOGS_DIR = "/opt/olympiad-scorer/shared/logs"

MODEL_CAPS = {
    "google:gemini-3.1-pro-preview": 256_000,
    "google:gemini-3.5-flash": 256_000,
    "xai:grok-4.3": 256_000,
    "xai:grok-build-0.1": 256_000,
    "zai:glm-5.2": 128_000,
    "zai:glm-4.7-flash": 128_000,
}

DEFAULT_PROVIDER_WORKERS = {
    "google": 2,
    "xai": 2,
    "zai": 2,
}


@dataclass(frozen=True)
class Pair:
    problem_id: str
    model: str
    max_tokens: int

    @property
    def provider(self) -> str:
        return self.model.split(":", 1)[0]


@dataclass(frozen=True)
class RunOutcome:
    pair: Pair
    code: int
    elapsed_s: float
    log_path: Path


def json_data(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in value)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def problem_ids(value: str) -> list[str]:
    result = []
    for item in parse_csv(value):
        if item.isdigit():
            result.append(f"task_{int(item):02d}")
        else:
            result.append(item)
    return result


def model_specs(value: str) -> list[str]:
    if value.lower() in {"new", "all"}:
        return list(MODEL_CAPS)
    return parse_csv(value)


def cap_for(model: str, requested_cap: int | None) -> int:
    known_cap = MODEL_CAPS.get(model)
    if requested_cap is None:
        if known_cap is None:
            raise SystemExit(f"No default cap configured for {model}; pass --max-tokens")
        return known_cap
    return min(int(requested_cap), known_cap) if known_cap is not None else int(requested_cap)


def model_candidates(result: dict[str, Any]) -> set[str]:
    provider = str(result.get("provider") or "")
    alias = str(result.get("alias") or "")
    model_id = str(
        result.get("requested_model_id")
        or result.get("resolved_model_id")
        or result.get("model")
        or ""
    )
    candidates = set()
    if alias:
        candidates.add(alias)
    if provider and model_id:
        candidates.add(f"{provider}:{model_id}")
    if provider and result.get("model"):
        candidates.add(f"{provider}:{result['model']}")
    return candidates


def successful_pairs(*, logs_dir: Path, models: list[str], problems: list[str]) -> set[tuple[str, str]]:
    expected = {(problem_id, model) for problem_id in problems for model in models}
    found: set[tuple[str, str]] = set()
    for path in sorted((logs_dir / COMPETITION_ID).glob("task_*/*.json")):
        payload = json_data(path)
        if not payload:
            continue
        problem_id = str(payload.get("problem_id") or path.parent.name)
        for result in payload.get("results", []) or []:
            if not str(result.get("answer") or "").strip() or result.get("error"):
                continue
            for candidate in model_candidates(result):
                key = (problem_id, candidate)
                if key in expected:
                    found.add(key)
    return found


def build_pairs(args: argparse.Namespace) -> list[Pair]:
    problems = problem_ids(args.problems)
    models = model_specs(args.models)
    succeeded = (
        successful_pairs(logs_dir=Path(args.logs_dir), models=models, problems=problems)
        if args.only_missing
        else set()
    )
    pairs = []
    for problem_id in problems:
        for model in models:
            if (problem_id, model) in succeeded:
                continue
            pairs.append(Pair(problem_id=problem_id, model=model, max_tokens=cap_for(model, args.max_tokens)))
    return pairs


def estimate_pairs_cost(*, data_dir: Path, pairs: list[Pair]) -> tuple[float, dict[str, float], dict[str, float]]:
    total = 0.0
    by_provider: dict[str, float] = {}
    by_model: dict[str, float] = {}
    for pair in pairs:
        provider, _, model_id = pair.model.partition(":")
        problem_path = data_dir / COMPETITION_ID / f"{pair.problem_id}.json"
        problem = json_data(problem_path) or {}
        input_tokens = estimate_tokens(f"{SYSTEM_PROMPT}\n\n{problem.get('statement') or ''}")
        cost = estimate_cost(
            provider,
            model_id,
            input_tokens=input_tokens,
            output_tokens=pair.max_tokens,
        )
        usd = float(cost.get("total") or 0.0)
        total += usd
        by_provider[provider] = by_provider.get(provider, 0.0) + usd
        by_model[pair.model] = by_model.get(pair.model, 0.0) + usd
    return total, by_provider, by_model


def provider_worker_limits(value: str) -> dict[str, int]:
    limits = dict(DEFAULT_PROVIDER_WORKERS)
    if not value:
        return limits
    for item in parse_csv(value):
        provider, sep, raw_limit = item.partition("=")
        if not sep:
            raise SystemExit("--provider-workers items must look like google=2")
        parsed = int(raw_limit)
        if parsed <= 0:
            raise SystemExit("--provider-workers values must be positive")
        limits[provider.strip().lower()] = parsed
    return limits


class Progress:
    def __init__(self, total: int) -> None:
        self._bar = None
        try:
            from tqdm import tqdm

            self._bar = tqdm(total=total, unit="run", dynamic_ncols=True)
        except Exception:
            self._bar = None
            self._done = 0
            self._total = total

    def write(self, message: str) -> None:
        if self._bar is not None:
            self._bar.write(message)
        else:
            print(message, flush=True)

    def update(self, amount: int = 1) -> None:
        if self._bar is not None:
            self._bar.update(amount)
        else:
            self._done += amount
            print(f"progress {self._done}/{self._total}", flush=True)

    def close(self) -> None:
        if self._bar is not None:
            self._bar.close()


async def run_one(
    *,
    pair: Pair,
    args: argparse.Namespace,
    run_group: str,
    provider_semaphores: dict[str, asyncio.Semaphore],
    global_semaphore: asyncio.Semaphore,
    progress: Progress,
) -> RunOutcome:
    provider_semaphore = provider_semaphores.setdefault(pair.provider, asyncio.Semaphore(1))
    async with global_semaphore, provider_semaphore:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        problem_path = Path(args.data_dir) / COMPETITION_ID / f"{pair.problem_id}.json"
        run_id = f"{run_group}_{pair.problem_id}_{safe_name(pair.model)}_{pair.max_tokens}"
        log_path = output_dir / f"{pair.problem_id}__{safe_name(pair.model)}__{pair.max_tokens}.log"
        command = [
            sys.executable,
            "runner.py",
            "--problem",
            str(problem_path),
            "--models",
            pair.model,
            "--max-tokens",
            str(pair.max_tokens),
            "--logs-dir",
            str(Path(args.logs_dir)),
            "--run-id",
            run_id,
        ]
        started_at = datetime.now(UTC).isoformat()
        progress.write(f"START {pair.problem_id} {pair.model} cap={pair.max_tokens}")
        start = monotonic()
        with log_path.open("w", encoding="utf-8") as stream:
            stream.write(f"START {started_at} {pair.problem_id} {pair.model} cap={pair.max_tokens}\n")
            stream.write(f"COMMAND {' '.join(command)}\n")
            stream.flush()
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=stream,
                stderr=asyncio.subprocess.STDOUT,
                cwd=Path(args.repo_dir),
                env=os.environ.copy(),
            )
            code = await process.wait()
            elapsed = monotonic() - start
            stream.write(
                f"\nDONE {datetime.now(UTC).isoformat()} {pair.problem_id} {pair.model} "
                f"cap={pair.max_tokens} exit={code} elapsed_s={elapsed:.1f}\n"
            )
        progress.write(
            f"{'OK' if code == 0 else 'FAIL'} {pair.problem_id} {pair.model} "
            f"exit={code} elapsed={elapsed:.1f}s log={log_path}"
        )
        progress.update(1)
        return RunOutcome(pair=pair, code=code, elapsed_s=elapsed, log_path=log_path)


async def run_all(args: argparse.Namespace, pairs: list[Pair]) -> int:
    run_group = args.run_group or datetime.now(UTC).strftime("new_models_%Y%m%d_%H%M%S")
    provider_limits = provider_worker_limits(args.provider_workers)
    provider_semaphores = {
        provider: asyncio.Semaphore(limit) for provider, limit in provider_limits.items()
    }
    global_semaphore = asyncio.Semaphore(max(1, args.workers))
    progress = Progress(len(pairs))
    progress.write(
        f"Launching {len(pairs)} pair(s), workers={args.workers}, "
        f"provider_workers={provider_limits}, run_group={run_group}"
    )
    try:
        outcomes = await asyncio.gather(
            *[
                run_one(
                    pair=pair,
                    args=args,
                    run_group=run_group,
                    provider_semaphores=provider_semaphores,
                    global_semaphore=global_semaphore,
                    progress=progress,
                )
                for pair in pairs
            ]
        )
    finally:
        progress.close()
    failed = [outcome for outcome in outcomes if outcome.code != 0]
    if failed:
        print("Failed pair(s):", flush=True)
        for outcome in failed:
            print(
                f"{outcome.pair.problem_id}\t{outcome.pair.model}\t"
                f"exit={outcome.code}\t{outcome.log_path}",
                flush=True,
            )
        return 1
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run new Gemini/Grok/GLM Math Cup 2026 final model-task pairs with live progress."
    )
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--logs-dir", default=DEFAULT_LOGS_DIR)
    parser.add_argument("--data-dir", default="data/competitions")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--models", default="new", help="new/all or comma-separated model specs")
    parser.add_argument(
        "--problems",
        default=",".join(f"task_{index:02d}" for index in range(1, DEFAULT_TASK_COUNT + 1)),
        help="Comma-separated problem ids; bare numbers like 01 are accepted.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Optional global cap. Known model caps still apply.",
    )
    parser.add_argument("--workers", type=int, default=6, help="Global subprocess concurrency.")
    parser.add_argument(
        "--provider-workers",
        default="google=2,xai=2,zai=2",
        help="Comma-separated per-provider concurrency, e.g. google=1,xai=2,zai=2.",
    )
    parser.add_argument("--run-group", default=None)
    parser.add_argument("--only-missing", action="store_true", help="Skip pairs with existing successful answers.")
    parser.add_argument("--yes", action="store_true", help="Actually launch API calls.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pairs = build_pairs(args)
    total, by_provider, by_model = estimate_pairs_cost(data_dir=Path(args.data_dir), pairs=pairs)
    print(f"Pair count: {len(pairs)}")
    for provider, value in sorted(by_provider.items()):
        print(f"provider\t{provider}\t${value:.4f}")
    for model, value in sorted(by_model.items()):
        print(f"model\t{model}\t${value:.4f}")
    print(f"total\t${total:.4f}")
    print(f"total_plus_20pct\t${total * 1.2:.4f}")
    if not pairs:
        print("Nothing to run.")
        return 0
    if not args.yes:
        print("Dry run only. Pass --yes to launch API calls.")
        for pair in pairs:
            print(f"{pair.problem_id}\t{pair.model}\tcap={pair.max_tokens}")
        return 0
    return asyncio.run(run_all(args, pairs))


if __name__ == "__main__":
    raise SystemExit(main())
