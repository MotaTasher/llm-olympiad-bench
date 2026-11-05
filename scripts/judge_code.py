"""Prepare, explicitly submit, or refresh code under the authenticated Yandex admin."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from judging.records import atomic_write_json, make_judgment, make_solution, solution_path, write_judgment, write_solution
from judging.yandex_contest import connect, get_submission, submission_plan, submit


def submit_once(client, solution: dict, plan: dict, *, jobs: Path, execute: bool, upload=None) -> dict:
    if not execute:
        return {"state": "dry_run", "plan": plan}
    if solution["author"]["type"] != "model":
        raise ValueError("Imported participant sources must not be resubmitted")
    job_path = solution_path(jobs, solution)
    job_path.parent.mkdir(parents=True, exist_ok=True)
    # Permanent outbox marker: unknown POST outcomes must be reconciled, never retried blindly.
    fd = os.open(job_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    job = {"schema_version": 1, "state": "submitting", "plan": plan, "submission_id": None}
    with os.fdopen(fd, "w") as stream:
        json.dump(job, stream, ensure_ascii=False, indent=2)
        stream.flush(); os.fsync(stream.fileno())
    try:
        submission_id = submit(client, solution, plan, upload=upload)
    except Exception:
        job["state"] = "outcome_unknown"
        atomic_write_json(job_path, job)
        raise RuntimeError("Submission outcome unknown; reconcile existing admin submissions before retrying") from None
    job.update(state="submitted", submission_id=submission_id)
    atomic_write_json(job_path, job)
    return job


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Local source artifact only; no Yandex/model calls")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--language", required=True, choices=["cpp", "python"])
    prepare.add_argument("--competition", required=True)
    prepare.add_argument("--task", required=True)
    prepare.add_argument("--author-id", required=True)
    prepare.add_argument("--author-name", required=True)
    prepare.add_argument("--result-id", required=True, help="Stable original generation result_id")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--model-key", required=True)
    send = sub.add_parser("submit", help="Dry run unless --execute is explicitly supplied")
    send.add_argument("--solution", type=Path, required=True)
    send.add_argument("--contest", type=int, required=True)
    send.add_argument("--problem-id", required=True)
    send.add_argument("--alias", required=True)
    send.add_argument("--compiler-id")
    send.add_argument("--kit-dir", type=Path)
    send.add_argument("--execute", action="store_true")
    refresh = sub.add_parser("refresh", help="Read one existing submission report, no rejudge")
    refresh.add_argument("--solution", type=Path, required=True)
    refresh.add_argument("--contest", type=int, required=True)
    refresh.add_argument("--submission", type=int, required=True)
    refresh.add_argument("--kit-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "prepare":
        # read_bytes preserves CRLF and trailing whitespace for the source hash.
        solution = make_solution(competition_id=args.competition, task_id=args.task,
                                 author={"id": args.author_id, "name": args.author_name, "type": "model"},
                                 code=args.source.read_bytes().decode("utf-8"), language=args.language,
                                 origin={"kind": "model_generation"},
                                 generation={"result_id": args.result_id, "run_id": args.run_id, "model_key": args.model_key})
        print(write_solution(ROOT / "data/code_solutions", solution))
        return
    solution = json.loads(args.solution.read_text())
    if args.command == "submit":
        plan = submission_plan(solution, contest_id=args.contest, problem_id=args.problem_id,
                               problem_alias=args.alias, compiler_id=args.compiler_id)
        client = None
        if args.execute:
            if not args.kit_dir:
                parser.error("--execute needs --kit-dir")
            client = connect(args.kit_dir)
        import requests
        job = submit_once(client, solution, plan, jobs=ROOT / "data/judge_jobs", execute=args.execute, upload=requests.post)
        print(json.dumps(job, ensure_ascii=False, indent=2))
    else:
        detail = get_submission(connect(args.kit_dir), args.submission, args.contest)
        report = detail["submissionReport"]
        if report["contestId"] != args.contest or report.get("sourceCode") != solution["source"]["code"]:
            raise ValueError("Report does not match contest / exact source")
        job_path = solution_path(ROOT / "data/judge_jobs", solution)
        if job_path.exists():
            job = json.loads(job_path.read_text())
            if job.get("submission_id") not in (None, args.submission) or report["problemId"] != job["plan"]["problem_id"]:
                raise ValueError("Report does not match the saved submission plan")
        elif (solution["origin"].get("kind") != "yandex_contest"
              or solution["origin"].get("contest_id") != args.contest
              or solution["origin"].get("submission_id") != args.submission):
            raise ValueError("A matching outbox or original imported submission is required")
        judgment = make_judgment(solution, detail)
        print(write_judgment(ROOT / "data/judge_results", solution, judgment))


if __name__ == "__main__":
    main()
