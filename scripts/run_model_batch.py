from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from runner import active_model_specs  # noqa: E402
from scripts.run_new_models_math_cup_2026_final import (  # noqa: E402
    DEFAULT_LOGS_DIR,
    DEFAULT_PROVIDER_WORKERS,
    MODEL_CAPS as NEW_MODEL_CAPS,
    Progress,
    json_data,
    model_candidates,
    parse_csv,
    provider_worker_limits,
    safe_name,
)
from models.common import SYSTEM_PROMPT  # noqa: E402
from models.pricing import estimate_cost, estimate_tokens  # noqa: E402


MODEL_CAPS = {
    "openai:gpt-5.5": 128_000,
    "openai:gpt-5.4-mini": 128_000,
    "anthropic:claude-opus-4-8": 128_000,
    "anthropic:claude-haiku-4-5-20251001": 64_000,
    "deepseek:deepseek-v4-pro": 320_000,
    "deepseek:deepseek-v4-flash": 320_000,
    "yandexgpt:yandexgpt-5.1": 8_000,
    "yandexgpt:yandexgpt-5-lite": 8_000,
    "gigachat:GigaChat-2-Max": 8_192,
    "gigachat:GigaChat-2": 8_192,
    **NEW_MODEL_CAPS,
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


def problem_ids(value: str) -> list[str]:
    result = []
    for item in parse_csv(value):
        if item.isdigit():
            result.append(f"task_{int(item):02d}")
        else:
            result.append(item)
    return result


def model_specs(value: str) -> list[str]:
    if value.lower() == "new":
        return list(NEW_MODEL_CAPS)
    if value.lower() in {"all", "site", "configured"}:
        return active_model_specs()
    return parse_csv(value)


def cap_for(model: str, requested_cap: int | None) -> int:
    known_cap = MODEL_CAPS.get(model)
    if requested_cap is None:
        if known_cap is None:
            raise SystemExit(f"No default cap configured for {model}; pass --max-tokens")
        return known_cap
    return min(int(requested_cap), known_cap) if known_cap is not None else int(requested_cap)


def default_output_dir(competition: str) -> str:
    return f"run-output/{competition}-model-batch"


def successful_pairs(
    *,
    competition: str,
    logs_dir: Path,
    models: list[str],
    problems: list[str],
) -> set[tuple[str, str]]:
    expected = {(problem_id, model) for problem_id in problems for model in models}
    found: set[tuple[str, str]] = set()
    for path in sorted((logs_dir / competition).glob("task_*/*.json")):
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
        successful_pairs(
            competition=args.competition,
            logs_dir=Path(args.logs_dir),
            models=models,
            problems=problems,
        )
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


def estimate_pairs_cost(*, args: argparse.Namespace, pairs: list[Pair]) -> tuple[float, dict[str, float], dict[str, float]]:
    total = 0.0
    by_provider: dict[str, float] = {}
    by_model: dict[str, float] = {}
    for pair in pairs:
        provider, _, model_id = pair.model.partition(":")
        problem_path = Path(args.data_dir) / args.competition / f"{pair.problem_id}.json"
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
        problem_path = Path(args.data_dir) / args.competition / f"{pair.problem_id}.json"
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
        progress.write(f"START {args.competition}/{pair.problem_id} {pair.model} cap={pair.max_tokens}")
        start = monotonic()
        with log_path.open("w", encoding="utf-8") as stream:
            stream.write(f"START {started_at} {args.competition}/{pair.problem_id} {pair.model} cap={pair.max_tokens}\n")
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
                f"\nDONE {datetime.now(UTC).isoformat()} {args.competition}/{pair.problem_id} "
                f"{pair.model} cap={pair.max_tokens} exit={code} elapsed_s={elapsed:.1f}\n"
            )
        progress.write(
            f"{'OK' if code == 0 else 'FAIL'} {pair.problem_id} {pair.model} "
            f"exit={code} elapsed={elapsed:.1f}s log={log_path}"
        )
        progress.update(1)
        return RunOutcome(pair=pair, code=code, elapsed_s=elapsed, log_path=log_path)


async def run_all(args: argparse.Namespace, pairs: list[Pair]) -> int:
    run_group = args.run_group or datetime.now(UTC).strftime(f"{safe_name(args.competition)}_%Y%m%d_%H%M%S")
    provider_limits = provider_worker_limits(args.provider_workers)
    provider_semaphores = {
        provider: asyncio.Semaphore(limit) for provider, limit in provider_limits.items()
    }
    global_semaphore = asyncio.Semaphore(max(1, args.workers))
    progress = Progress(len(pairs))
    progress.write(
        f"Launching {len(pairs)} pair(s), competition={args.competition}, workers={args.workers}, "
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


def detached_args(args: argparse.Namespace) -> list[str]:
    command = [sys.executable, str(Path(__file__).resolve())]
    skip = {"detach", "yes"}
    for key, value in vars(args).items():
        if key in skip:
            continue
        flag = "--" + key.replace("_", "-")
        if isinstance(value, bool):
            if value:
                command.append(flag)
        elif value is not None:
            command.extend([flag, str(value)])
    command.append("--yes")
    return command


def detach(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "launcher.log"
    command = detached_args(args)
    with log_path.open("ab") as stream:
        stream.write(
            f"\nDETACH {datetime.now(UTC).isoformat()} COMMAND {' '.join(command)}\n".encode("utf-8")
        )
        process = subprocess.Popen(
            command,
            cwd=Path(args.repo_dir),
            stdout=stream,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=os.environ.copy(),
        )
    print(f"pid\t{process.pid}")
    print(f"log\t{log_path}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run model-task pairs for any competition with cost estimate, progress and optional detach."
    )
    parser.add_argument("--competition", required=True, help="Competition id under data/competitions.")
    parser.add_argument("--repo-dir", default=".")
    parser.add_argument("--logs-dir", default=DEFAULT_LOGS_DIR)
    parser.add_argument("--data-dir", default="data/competitions")
    parser.add_argument("--output-dir", default=None)
    parser.add_argument("--models", default="new", help="new/all or comma-separated model specs")
    parser.add_argument(
        "--problems",
        default="task_01",
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
        default=",".join(f"{provider}={limit}" for provider, limit in DEFAULT_PROVIDER_WORKERS.items()),
        help="Comma-separated per-provider concurrency, e.g. google=1,xai=2,zai=2.",
    )
    parser.add_argument("--run-group", default=None)
    parser.add_argument("--only-missing", action="store_true", help="Skip pairs with existing successful answers.")
    parser.add_argument("--detach", action="store_true", help="Start in a new session and write launcher.log, then exit.")
    parser.add_argument("--yes", action="store_true", help="Actually launch API calls.")
    args = parser.parse_args(argv)
    if args.output_dir is None:
        args.output_dir = default_output_dir(args.competition)
    return args


def main() -> int:
    args = parse_args()
    if args.detach:
        if not args.yes:
            print("Dry detach only. Pass --yes with --detach to launch API calls.")
            print(
                "Log path would be "
                f"{Path(args.output_dir) / 'launcher.log'}"
            )
            return 0
        return detach(args)
    pairs = build_pairs(args)
    total, by_provider, by_model = estimate_pairs_cost(args=args, pairs=pairs)
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
