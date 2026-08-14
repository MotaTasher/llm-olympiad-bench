from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scoring.repository import (  # noqa: E402
    build_catalog,
    finalization_statistics,
    save_finalization,
)


COMPETITION_ID = "math-cup-2026-qualifying"
PROBLEM_IDS = {f"task_{index:02d}" for index in range(1, 7)}
FINAL_FEEDBACK = "Неверный ответ."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Approve the standard final comment for non-full answers in "
            "Math Cup 2026 qualifying tasks 1–6."
        ),
    )
    parser.add_argument("--competitions-dir", type=Path, default=Path("data/competitions"))
    parser.add_argument("--logs-dir", type=Path, default=Path("logs"))
    parser.add_argument("--results-dir", type=Path, default=Path("data/results"))
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog = build_catalog(
        competitions_dir=args.competitions_dir,
        logs_dir=args.logs_dir,
        results_dir=args.results_dir,
    )
    competition = catalog["competition_map"][COMPETITION_ID]
    targets: list[tuple[dict, dict, dict]] = []
    for row in finalization_statistics(competition)["tasks"]:
        problem = row["problem"]
        if problem["problem_id"] not in PROBLEM_IDS:
            continue
        for cell in row["cells"].values():
            attempt = cell["attempt"]
            final = attempt.get("finalization") if attempt else None
            if not final or float(final["score"]) >= float(problem["max_score"]):
                continue
            targets.append((problem, attempt, final))

    print(f"Would approve {len(targets)} non-full answers with: {FINAL_FEEDBACK}")
    if not args.apply:
        return 0
    for problem, attempt, final in targets:
        save_finalization(
            results_dir=args.results_dir,
            competition_id=COMPETITION_ID,
            problem_id=problem["problem_id"],
            run_id=attempt["run_id"],
            result_id=attempt["result_id"],
            result_index=int(attempt["result_index"]),
            model_key_value=attempt["model_key"],
            model=attempt["model_id"],
            score=final["score"],
            max_score=float(problem["max_score"]),
            feedback=FINAL_FEEDBACK,
            updated_by="bulk-approved",
            feedback_review_required=False,
        )
    print(f"Approved {len(targets)} final comments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
