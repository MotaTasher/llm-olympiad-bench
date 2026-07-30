from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


def rounded_rescaled_score(score: Any, old_max_score: Any, new_max_score: float) -> int:
    value = float(score)
    old_max = float(old_max_score)
    if not math.isfinite(value) or not math.isfinite(old_max) or old_max <= 0:
        raise ValueError(f"Invalid score scale: score={score!r}, max_score={old_max_score!r}")
    scaled = Decimal(str(value)) / Decimal(str(old_max)) * Decimal(str(new_max_score))
    rounded = int(scaled.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return max(0, min(int(new_max_score), rounded))


def score_category(score: int, max_score: float) -> str:
    if score <= 0:
        return "zero"
    if score >= max_score:
        return "full"
    return "partial"


def migrate_evaluation(entry: dict[str, Any], new_max_score: float) -> bool:
    if entry.get("score") is None:
        return False
    old_score = entry.get("score")
    old_max_score = entry.get("max_score")
    if old_max_score is None:
        raise ValueError("Evaluation with a score has no max_score")
    new_score = rounded_rescaled_score(old_score, old_max_score, new_max_score)
    changed = (
        old_score != new_score
        or float(old_max_score) != float(new_max_score)
        or entry.get("score_category") != score_category(new_score, new_max_score)
    )
    entry["score"] = new_score
    entry["max_score"] = int(new_max_score)
    entry["score_category"] = score_category(new_score, new_max_score)
    return changed


def migrate_sidecar(payload: dict[str, Any], new_max_score: float) -> int:
    changed = 0
    pool = payload.get("evaluation_pool")
    if isinstance(pool, dict):
        for evaluations in pool.values():
            if not isinstance(evaluations, list):
                continue
            changed += sum(
                migrate_evaluation(entry, new_max_score)
                for entry in evaluations
                if isinstance(entry, dict)
            )
    snapshots = payload.get("evaluations")
    if isinstance(snapshots, dict):
        for entry in snapshots.values():
            if isinstance(entry, dict):
                migrate_evaluation(entry, new_max_score)
    return changed


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def set_score_metadata(path: Path, max_score: float, score_step: float, *, apply: bool) -> bool:
    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.setdefault("metadata", {})
    changed = (
        metadata.get("max_score") != max_score
        or metadata.get("score_step") != score_step
    )
    metadata["max_score"] = int(max_score)
    metadata["score_step"] = int(score_step)
    if changed and apply:
        atomic_write_json(path, payload)
    return changed


def migrate_competition(
    *,
    competitions_dir: Path,
    results_dir: Path,
    competition_id: str,
    max_score: float,
    score_step: float,
    apply: bool,
) -> dict[str, int]:
    competition_dir = competitions_dir / competition_id
    manifest = competition_dir / "competition.json"
    if not manifest.is_file():
        raise FileNotFoundError(f"Competition manifest not found: {manifest}")
    metadata_files_changed = int(
        set_score_metadata(manifest, max_score, score_step, apply=apply)
    )
    for problem_path in sorted(competition_dir.glob("*.json")):
        if problem_path.name == "competition.json":
            continue
        metadata_files_changed += int(
            set_score_metadata(problem_path, max_score, score_step, apply=apply)
        )

    sidecar_files_changed = 0
    evaluations_changed = 0
    sidecar_root = results_dir / competition_id
    for sidecar_path in sorted(sidecar_root.rglob("*.json")) if sidecar_root.exists() else []:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        changed = migrate_sidecar(payload, max_score)
        if not changed:
            continue
        sidecar_files_changed += 1
        evaluations_changed += changed
        if apply:
            atomic_write_json(sidecar_path, payload)
    return {
        "metadata_files_changed": metadata_files_changed,
        "sidecar_files_changed": sidecar_files_changed,
        "evaluations_changed": evaluations_changed,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rescale one competition's score data.")
    parser.add_argument("--competition", required=True)
    parser.add_argument("--max-score", type=float, required=True)
    parser.add_argument("--score-step", type=float, required=True)
    parser.add_argument("--competitions-dir", type=Path, default=Path("data/competitions"))
    parser.add_argument("--results-dir", type=Path, default=Path("data/results"))
    parser.add_argument("--apply", action="store_true", help="Write changes; otherwise run a dry check.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.max_score <= 0 or not args.max_score.is_integer():
        raise SystemExit("--max-score must be a positive integer")
    if args.score_step != 1:
        raise SystemExit("--score-step must be 1; migrated scores are rounded to integers")
    summary = migrate_competition(
        competitions_dir=args.competitions_dir,
        results_dir=args.results_dir,
        competition_id=args.competition,
        max_score=args.max_score,
        score_step=args.score_step,
        apply=args.apply,
    )
    mode = "Applied" if args.apply else "Dry run"
    print(
        f"{mode}: {args.competition}: "
        f"{summary['metadata_files_changed']} metadata file(s), "
        f"{summary['sidecar_files_changed']} sidecar file(s), "
        f"{summary['evaluations_changed']} evaluation(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
