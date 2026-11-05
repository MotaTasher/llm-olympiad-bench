"""Read existing accepted submissions through Contest Kit; never submit or rejudge."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from judging.records import atomic_write_json, make_judgment, make_solution, write_judgment, write_solution
from judging.yandex_contest import connect, get_submission, list_submissions


def import_winners(client, snapshot: dict, *, sources: Path, judgments: Path) -> dict:
    contest_id = snapshot["contest_id"]
    for team in snapshot["teams"]:
        rows = list(list_submissions(client, contest_id, participant_id=team["yandex_participant_id"]))
        solutions = []
        for task in snapshot["tasks"]:
            candidates = [row for row in rows
                          if row["participant"]["id"] == team["yandex_participant_id"]
                          and row["problem"]["title"] == task["short"] and row["verdict"] == "OK"
                          and row["status"].lower() == "finished" and not row.get("ignoredInMonitor")
                          and 0 <= row["timeFromStart"] <= snapshot["duration_minutes"] * 60000]
            if not candidates:
                raise ValueError(f'No accepted contest submission: {team["id"]} / {task["short"]}')
            selected = min(candidates, key=lambda row: (row["timeFromStart"], row["id"]))
            detail = get_submission(client, selected["id"], contest_id)
            report = detail["submissionReport"]
            if (report["contestId"] != contest_id or report["participantId"] != team["yandex_participant_id"]
                    or report["problemAlias"] != task["short"] or detail["verdict"] != "OK"):
                raise ValueError("Submission identity/verdict changed during import")
            compiler_id = report["compilerId"]
            language = "cpp" if "cpp" in compiler_id else "python" if "python" in compiler_id or "pypy" in compiler_id else None
            if language is None:
                raise ValueError(f"Unsupported import compiler: {compiler_id}")
            solution = make_solution(
                competition_id=snapshot["id"], task_id=task["id"],
                author={"type": "team", "id": team["id"], "name": team["name"]},
                code=report["sourceCode"], language=language,
                origin={"kind": "yandex_contest", "contest_id": contest_id,
                        "submission_id": selected["id"], "selection": "first_accepted_in_contest"},
            )
            judgment = make_judgment(solution, detail, summary=selected)
            write_solution(sources, solution)
            write_judgment(judgments, solution, judgment)
            solutions.append({"solution_id": solution["id"], "submission_id": selected["id"]})
        team["code_solutions"] = solutions
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit-dir", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "data/public_results/algo-cup-2026-qualifying.json")
    args = parser.parse_args()
    snapshot = import_winners(connect(args.kit_dir), json.loads(args.snapshot.read_text()),
                              sources=ROOT / "data/code_solutions", judgments=ROOT / "data/judge_results")
    atomic_write_json(args.snapshot, snapshot)
    print(f"Imported {sum(len(t['code_solutions']) for t in snapshot['teams'])} existing accepted solutions; no submissions")


if __name__ == "__main__":
    main()
