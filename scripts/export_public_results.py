from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scoring.repository import build_catalog  # noqa: E402


DEFAULT_COMPETITION_IDS = (
    "math-cup-2026-qualifying",
    "math-cup-2026-final",
)

MODEL_NAME_PREFIXES = {
    "anthropic": "Claude",
    "deepseek": "DeepSeek",
    "gigachat": "GigaChat",
    "google": "Gemini",
    "openai": "",
    "xai": "Grok",
    "yandexgpt": "",
    "zai": "GLM",
    "kimi": "Kimi",
}

PUBLIC_ASSET_PREFIX = "generated/assets/"
LOCAL_ASSET_REFERENCE = re.compile(r"(?<![A-Za-z0-9_./-])(?:\./)?assets/([A-Za-z0-9._/-]+)")
INLINE_CODE_URL = re.compile(r"`(https?://[^`\s]+)`")
BARE_URL = re.compile(r"(?<![\w\"'(/=:])https?://[^\s<>\]\[)]+")


def rewrite_public_markdown(value: Any, *, competition_id: str) -> str:
    """Make local competition assets and plain URLs work in solution documents."""
    text = str(value or "")
    asset_prefix = f"{PUBLIC_ASSET_PREFIX}{safe_component(competition_id, 'competition')}/"
    text = LOCAL_ASSET_REFERENCE.sub(lambda match: asset_prefix + match.group(1), text)

    # Marked renders Markdown links, but does not consistently autolink bare URLs.
    # URLs already inside Markdown links or angle-bracket autolinks are left alone.
    text = INLINE_CODE_URL.sub(lambda match: f"[{match.group(1)}]({match.group(1)})", text)
    text = BARE_URL.sub(lambda match: f"[{match.group(0)}]({match.group(0)})", text)
    return text


def copy_public_assets(
    *,
    competition: dict[str, Any],
    output_dir: Path,
) -> None:
    """Copy the competition's local assets into the generated public projection."""
    problem_paths = [
        Path(problem.get("path", ""))
        for problem in competition.get("problems", {}).values()
        if problem.get("path")
    ]
    if not problem_paths:
        return
    source_assets = problem_paths[0].parent / "assets"
    if not source_assets.is_dir():
        return
    destination = output_dir / "assets" / safe_component(competition["competition_id"], "competition")
    for source in source_assets.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(source_assets)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def public_score(
    attempt: dict[str, Any],
    max_score: float,
    *,
    round_to_integer: bool = False,
) -> float | int | None:
    finalization = attempt.get("finalization")
    if not isinstance(finalization, dict):
        return None
    value = finite_number(finalization.get("score"))
    final_max = finite_number(finalization.get("max_score")) or max_score
    if value is None or final_max <= 0:
        return None
    value = max(0.0, min(max_score, value / final_max * max_score))
    if round_to_integer:
        return int(math.floor(value + 0.5))
    value = round(value, 1)
    return int(value) if value.is_integer() else value


def select_public_attempt(state: dict[str, Any]) -> dict[str, Any] | None:
    successful = [
        attempt
        for attempt in state.get("attempts") or []
        if attempt.get("successful_answer")
    ]
    return next(
        (attempt for attempt in successful if attempt.get("finalization")),
        next(
            (attempt for attempt in successful if attempt.get("evaluations")),
            successful[0] if successful else None,
        ),
    )


def total_tokens(result: dict[str, Any]) -> int | None:
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    value = finite_number(usage.get("total_tokens"))
    if value is None:
        prompt = finite_number(result.get("prompt_tokens")) or finite_number(usage.get("input_tokens"))
        completion = finite_number(result.get("completion_tokens")) or finite_number(usage.get("output_tokens"))
        if prompt is not None or completion is not None:
            value = (prompt or 0) + (completion or 0)
    return max(0, int(value)) if value is not None else None


def safe_component(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "")).strip("-._")
    return cleaned or fallback


def public_task_slug(value: Any) -> str:
    """Return the stable task segment used by clean public solution URLs."""
    raw = str(value or "")
    match = re.fullmatch(r"task[_-]?0*(\d+)", raw, flags=re.IGNORECASE)
    if match:
        return f"task{int(match.group(1))}"
    return safe_component(raw, "task").lower()


def public_model_slug(column: dict[str, Any]) -> str:
    """Return a provider-free model segment used by clean public URLs."""
    slug = safe_component(
        column.get("model_id") or column.get("short_label") or column.get("model_key"),
        "model",
    ).lower()
    # The benchmark adapter suffix distinguishes its runtime preset, while the
    # public model name and requested route remain GPT-5.6.
    if slug.endswith("-sol"):
        slug = slug.removesuffix("-sol")
    return slug


def stable_result_id(
    attempt: dict[str, Any],
    *,
    competition_id: str,
    problem_id: str,
) -> str:
    existing = attempt.get("result_id")
    if existing:
        return safe_component(existing, "result")
    identity = "\0".join(
        (
            competition_id,
            problem_id,
            str(attempt.get("run_id") or ""),
            str(attempt.get("result_index") or ""),
            str(attempt.get("model_key") or ""),
        )
    )
    return f"legacy-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def model_name(column: dict[str, Any]) -> str:
    short = str(column.get("short_label") or column.get("model_id") or "Модель")
    prefix = MODEL_NAME_PREFIXES.get(str(column.get("provider") or ""), "")
    if not prefix or short.casefold().startswith(prefix.casefold()):
        return short
    return f"{prefix} {short}"


def public_review(
    value: Any,
    *,
    fallback_max_score: float,
    competition_id: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    score = finite_number(value.get("score"))
    max_score = finite_number(value.get("max_score")) or fallback_max_score
    feedback = rewrite_public_markdown(
        value.get("feedback"),
        competition_id=competition_id,
    ).strip()
    if score is None and not feedback:
        return None
    return {
        "score": int(score) if score is not None and score.is_integer() else score,
        "maxScore": int(max_score) if max_score.is_integer() else max_score,
        "feedback": feedback,
    }


def format_date(value: Any) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return str(value)
    months = (
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    )
    return f"{parsed.day} {months[parsed.month - 1]} {parsed.year}"


def atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def solution_document(
    *,
    competition: dict[str, Any],
    problem: dict[str, Any],
    column: dict[str, Any],
    attempt: dict[str, Any],
    score: float | int | None,
) -> dict[str, Any]:
    result = attempt["result"]
    cost = finite_number(result.get("cost_usd"))
    latency = finite_number(result.get("latency_ms"))
    max_score = float(problem.get("max_score") or 0)
    competition_id = competition["competition_id"]
    expert_reviews = [
        review
        for evaluation in attempt.get("evaluations") or []
        if (
            review := public_review(
                evaluation,
                fallback_max_score=max_score,
                competition_id=competition_id,
            )
        )
    ]
    final_review = public_review(
        attempt.get("finalization"),
        fallback_max_score=max_score,
        competition_id=competition_id,
    )
    return {
        "schemaVersion": 2,
        "competition": {
            "id": competition["competition_id"],
            "title": competition["competition_title"],
            "stage": (competition.get("metadata") or {}).get("stage") or "",
        },
        "task": {
            "id": problem["problem_id"],
            "title": problem["problem_title"],
            "statement": rewrite_public_markdown(
                problem.get("statement"),
                competition_id=competition["competition_id"],
            ),
            "officialSolution": rewrite_public_markdown(
                problem.get("solution"),
                competition_id=competition["competition_id"],
            ),
            "maxScore": int(max_score) if max_score.is_integer() else max_score,
        },
        "model": {
            "id": safe_component(column.get("model_key"), "model"),
            "name": model_name(column),
            "provider": column.get("provider_label") or column.get("provider") or "",
        },
        "review": {
            "final": final_review,
            "experts": expert_reviews,
        },
        "result": {
            "resultId": stable_result_id(
                attempt,
                competition_id=competition["competition_id"],
                problem_id=problem["problem_id"],
            ),
            "answer": result.get("answer") or "",
            "score": score,
            "verdict": (
                "На проверке"
                if score is None
                else "Полное решение"
                if score >= max_score
                else "Частичное решение"
                if score > 0
                else "Не зачтено"
            ),
            "cost": round(cost, 6) if cost is not None else None,
            "tokens": total_tokens(result),
            "latencyMs": int(latency) if latency is not None else None,
        },
    }


def export_competition(
    competition: dict[str, Any],
    *,
    output_dir: Path,
) -> dict[str, Any]:
    copy_public_assets(competition=competition, output_dir=output_dir)
    tasks = []
    task_max_scores: list[float] = []
    for index, problem_id in enumerate(competition["problem_order"], start=1):
        problem = competition["problems"][problem_id]
        max_score = float(problem["max_score"])
        task_max_scores.append(max_score)
        tasks.append(
            {
                "id": problem_id,
                "slug": public_task_slug(problem_id),
                "short": f"{index:02d}",
                "title": problem["problem_title"],
                "maxScore": int(max_score) if max_score.is_integer() else max_score,
            }
        )

    participants = []
    for rank, column in enumerate(competition["model_columns"], start=1):
        scores: list[float | int | None] = []
        solutions: list[str | None] = []
        costs: list[float] = []
        tokens: list[int] = []
        for problem_id in competition["problem_order"]:
            problem = competition["problems"][problem_id]
            state = next(
                item
                for item in problem["model_states"]
                if item["model_key"] == column["model_key"]
            )
            attempt = select_public_attempt(state)
            if attempt is None:
                scores.append(None)
                solutions.append(None)
                continue
            score = public_score(
                attempt,
                float(problem["max_score"]),
                round_to_integer=competition["competition_id"] == "math-cup-2026-qualifying",
            )
            result_id = stable_result_id(
                attempt,
                competition_id=competition["competition_id"],
                problem_id=problem_id,
            )
            relative_path = (
                Path("generated")
                / "solutions"
                / safe_component(competition["competition_id"], "competition")
                / f"{result_id}.json"
            )
            document = solution_document(
                competition=competition,
                problem=problem,
                column=column,
                attempt=attempt,
                score=score,
            )
            atomic_write_text(
                output_dir
                / "solutions"
                / safe_component(competition["competition_id"], "competition")
                / f"{result_id}.json",
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            )
            scores.append(score)
            solutions.append(relative_path.as_posix())
            cost = finite_number(attempt["result"].get("cost_usd"))
            token_count = total_tokens(attempt["result"])
            if cost is not None:
                costs.append(cost)
            if token_count is not None:
                tokens.append(token_count)

        scored = [float(score) for score in scores if score is not None]
        scored_with_max = [
            (float(score), task_max_scores[index])
            for index, score in enumerate(scores)
            if score is not None
        ]
        points = round(sum(scored), 1) if scored else None
        participant_id = safe_component(column["model_key"], "model")
        participants.append(
            {
                "id": participant_id,
                "slug": public_model_slug(column),
                "type": "model",
                "rank": rank,
                "name": model_name(column),
                "provider": column.get("provider_label") or column.get("provider") or "",
                "scores": scores,
                "solutions": solutions,
                "solved": sum(score >= max_score for score, max_score in scored_with_max),
                "points": int(points) if points is not None and points.is_integer() else points,
                "accuracy": (
                    round(
                        sum(score / max_score * 100 for score, max_score in scored_with_max)
                        / len(scored_with_max),
                        1,
                    )
                    if scored_with_max
                    else None
                ),
                "cost": round(sum(costs), 6) if costs else None,
                "tokens": sum(tokens) if tokens else None,
            }
        )

    metadata = competition.get("metadata") or {}
    return {
        "id": competition["competition_id"],
        "series": safe_component(metadata.get("series") or "competition", "competition").lower(),
        "seriesLabel": metadata.get("series") or "Соревнование",
        "editionLabel": str(metadata.get("year") or ""),
        "title": competition["competition_title"],
        "stage": metadata.get("stage") or competition["competition_title"],
        "date": format_date(competition.get("date")),
        "description": competition.get("description") or "",
        "taskCount": len(tasks),
        "tasks": tasks,
        "participants": participants,
    }


def export_public_results(
    *,
    competitions_dir: Path,
    logs_dir: Path,
    results_dir: Path,
    output_dir: Path,
    competition_ids: tuple[str, ...] = DEFAULT_COMPETITION_IDS,
) -> dict[str, Any]:
    catalog = build_catalog(
        competitions_dir=competitions_dir,
        logs_dir=logs_dir,
        results_dir=results_dir,
    )
    missing = [
        competition_id
        for competition_id in competition_ids
        if competition_id not in catalog["competition_map"]
    ]
    if missing:
        raise ValueError(f"Unknown competition ids: {', '.join(missing)}")

    document = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "competitions": [
            export_competition(
                catalog["competition_map"][competition_id],
                output_dir=output_dir,
            )
            for competition_id in competition_ids
        ],
    }
    atomic_write_text(
        output_dir / "data.js",
        "window.RESULTS_DATA_GENERATED = "
        + json.dumps(document, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
    )
    return document


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a sanitized, read-only snapshot for public_results.",
    )
    parser.add_argument("--competitions-dir", type=Path, default=Path("data/competitions"))
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--results-dir", type=Path, default=Path("data/results"))
    parser.add_argument("--output-dir", type=Path, default=Path("public_results/generated"))
    parser.add_argument(
        "--competition",
        action="append",
        dest="competition_ids",
        help="Competition id to publish; repeat to publish multiple stages.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    document = export_public_results(
        competitions_dir=args.competitions_dir,
        logs_dir=args.logs_dir,
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        competition_ids=tuple(args.competition_ids or DEFAULT_COMPETITION_IDS),
    )
    solution_count = sum(
        bool(path)
        for competition in document["competitions"]
        for participant in competition["participants"]
        for path in participant["solutions"]
    )
    print(
        f"Exported {len(document['competitions'])} competitions and "
        f"{solution_count} model solutions to {args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
