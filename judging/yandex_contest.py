"""Read-only kit connection, report import and explicit administrative submission."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from judging.records import LANGUAGES, validate_solution


def connect(kit_dir: Path):
    if not (kit_dir / "contest_kit/http.py").is_file():
        raise ValueError("--kit-dir must contain contest_kit/http.py")
    sys.path.insert(0, str(kit_dir.resolve()))
    auth = importlib.import_module("contest_kit.auth")
    client = importlib.import_module("contest_kit.http").Client
    return client(auth.resolve())


def list_submissions(client, contest_id: int, *, participant_id: int | None = None):
    page = 0
    while True:
        payload = client.json("GET", f"/api/admin/contest/{contest_id}/submission",
                              params={"filter": f"participantId={participant_id}" if participant_id else "",
                                      "limit": 100, "offset": page},
                              referer=f"/contests/{contest_id}/submissions")
        items = payload.get("items") or []
        yield from items
        if len(items) < 100:
            return
        page += 1


def get_submission(client, submission_id: int, contest_id: int):
    return client.json("GET", f"/api/admin/submission/{submission_id}",
                       referer=f"/contests/{contest_id}/submissions")


def submission_plan(solution: dict[str, Any], *, contest_id: int, problem_id: str,
                    problem_alias: str, compiler_id: str | None = None) -> dict[str, Any]:
    validate_solution(solution)
    compiler_id = compiler_id or LANGUAGES[solution["source"]["language"]]["compiler_id"]
    allowed = {"cpp": {"gcc14_cpp23", "gcc_cpp20"}, "python": {"python3_13", "pypy3_7_1_0"}}
    if compiler_id not in allowed[solution["source"]["language"]]:
        raise ValueError("Compiler does not match the supported source language")
    return {
        "solution_id": solution["id"], "contest_id": int(contest_id),
        "problem_id": problem_id, "problem_alias": problem_alias,
        "compiler_id": compiler_id, "filename": solution["source"]["filename"],
        "source_sha256": solution["source"]["sha256"], "submit_as": "authenticated_admin",
    }


def submit(client, solution: dict[str, Any], plan: dict[str, Any], *, upload) -> int:
    """Caller must persist an outbox marker before this non-idempotent action."""
    validate_solution(solution)
    if plan["solution_id"] != solution["id"] or plan["source_sha256"] != solution["source"]["sha256"]:
        raise ValueError("Submission plan does not match source")
    contest_id = plan["contest_id"]
    referer = f"/contests/{contest_id}/submissions"
    settings = client.json("GET", f"/api/admin/contest/{contest_id}", referer=referer)
    if plan["compiler_id"] not in settings.get("compilers", []):
        raise ValueError("Compiler is not enabled in this contest")
    problems = client.json("GET", f"/api/admin/contests/{contest_id}/problemset", referer=referer)
    if not any(p["id"] == plan["problem_id"] and p["title"] == plan["problem_alias"] for p in problems["problems"]):
        raise ValueError("Problem does not match this contest / alias")
    target = client.json("GET", "/api/admin/upload-file", referer=referer,
                         params={"contentType": "text/plain", "fileName": plan["filename"]})
    # A separate HTTP session avoids forwarding the admin cookie to object storage.
    response = upload(target["url"], data=target["fields"],
                      files={"file": (plan["filename"], solution["source"]["code"].encode("utf-8"), "text/plain")}, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError("Source upload failed; signed URL intentionally omitted")
    result = client.json("POST", f"/api/admin/contest/{contest_id}/submission/submit", referer=referer,
                         json={"problemId": plan["problem_id"], "compilerId": plan["compiler_id"],
                               "fileName": plan["filename"], "s3Id": target["key"]})
    return int(result["id"])
