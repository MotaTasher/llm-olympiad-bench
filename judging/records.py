from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LANGUAGES = {
    "cpp": {"extension": ".cpp", "compiler_id": "gcc14_cpp23"},
    "python": {"extension": ".py", "compiler_id": "python3_13"},
}
LANGUAGE_ALIASES = {"c++": "cpp", "c++23": "cpp", "c++20": "cpp", "py": "python", "python3": "python"}


def atomic_write_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write allowlisted records without transforming code strings or their hash."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def component(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", value):
        raise ValueError("Unsafe record identifier")
    return value


def normalize_language(language: str) -> str:
    language = LANGUAGE_ALIASES.get(language.lower(), language.lower())
    if language not in LANGUAGES:
        raise ValueError("Supported submission languages: cpp, python")
    return language


def extract_source(answer: str, language: str) -> str:
    """Accept plain source or one complete source-only Markdown fence; never execute."""
    language = normalize_language(language)
    if "```" not in answer:
        return answer
    match = re.fullmatch(r"\s*```([A-Za-z0-9+._-]*)[^\S\n]*\r?\n([\s\S]*?)\r?\n```\s*", answer)
    if not match or "```" in match.group(2):
        raise ValueError("Expected a single source file without prose or multiple code blocks")
    label = match.group(1).lower()
    if label and normalize_language(label) != language:
        raise ValueError("Code fence language does not match the requested compiler language")
    return match.group(2)


def make_solution(*, competition_id: str, task_id: str, author: dict[str, str],
                  code: str, language: str, origin: dict[str, Any],
                  generation: dict[str, str] | None = None) -> dict[str, Any]:
    language = normalize_language(language)
    if not code.strip() or len(code.encode("utf-8")) > 262144:
        raise ValueError("Source must be non-empty and at most 262144 UTF-8 bytes")
    if author["type"] not in ("team", "model"):
        raise ValueError("Code author must be a team or model")
    component(competition_id); component(task_id); component(author["id"])
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    identity_parts = [competition_id, task_id, author["id"], language, digest]
    if generation is not None:
        # Equal source from different immutable model runs still needs separate attribution.
        identity_parts.extend([generation["result_id"], generation["run_id"], generation["model_key"]])
    identity = json.dumps(identity_parts, ensure_ascii=False)
    solution_id = "code_" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    return {
        "schema_version": 1, "id": solution_id, "format": "code",
        "competition_id": competition_id, "problem_id": task_id,
        "author": {k: author[k] for k in ("type", "id", "name")},
        "source": {"language": language, "filename": "solution" + LANGUAGES[language]["extension"],
                   "code": code, "sha256": digest, "encoding": "utf-8"},
        "origin": {k: origin[k] for k in ("kind", "contest_id", "submission_id", "selection") if k in origin},
        "generation": {k: generation[k] for k in ("result_id", "run_id", "model_key")} if generation is not None else None,
    }


def validate_solution(solution: dict[str, Any]) -> None:
    rebuilt = make_solution(competition_id=solution["competition_id"], task_id=solution["problem_id"],
                            author=solution["author"], code=solution["source"]["code"],
                            language=solution["source"]["language"], origin=solution["origin"],
                            generation=solution.get("generation"))
    if solution != rebuilt:
        raise ValueError("Code artifact does not match its immutable content hash/schema")


def solution_path(root: Path, solution: dict[str, Any]) -> Path:
    return root / component(solution["competition_id"]) / component(solution["problem_id"]) / (component(solution["id"]) + ".json")


def write_solution(root: Path, solution: dict[str, Any]) -> Path:
    validate_solution(solution)
    path = solution_path(root, solution)
    if path.exists():
        if json.loads(path.read_text()) != solution:
            raise ValueError("Refusing to overwrite a different code artifact")
    else:
        atomic_write_json(path, solution)
    return path


def finite_metric(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return value


def make_judgment(solution: dict[str, Any], detail: dict[str, Any], *,
                  summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Allowlist only public metrics; exclude IP, host, logs and per-test data."""
    validate_solution(solution)
    report = detail["submissionReport"]
    summary = summary or {}
    tests = detail.get("tests") or []
    def metric(summary_key: str, test_key: str) -> int | float | None:
        value = finite_metric(summary.get(summary_key))
        if value is not None:
            return value
        values = [finite_metric(test.get(test_key)) for test in tests]
        return max((v for v in values if v is not None), default=None)
    timestamp = report.get("absoluteTime")
    submitted_at = datetime.fromtimestamp(timestamp / 1000, UTC).isoformat() if isinstance(timestamp, (int, float)) else None
    status = str(report.get("status") or summary.get("status") or "unknown").lower()
    verdict = detail.get("verdict")
    return {
        "schema_version": 1, "solution_id": solution["id"],
        "competition_id": solution["competition_id"], "problem_id": solution["problem_id"],
        "judge": "yandex_contest", "contest_id": int(report["contestId"]),
        "problem_alias": report["problemAlias"], "submission_id": int(report["id"]),
        "compiler_id": report["compilerId"], "compiler_name": report["compilerName"],
        "status": status, "verdict": verdict,
        "score": (1 if verdict == "OK" else 0) if status == "finished" else None,
        "metrics": {"time_ms": metric("usedTimeMillis", "runningTime"),
                    "memory_bytes": metric("usedMemoryBytes", "memoryUsed")},
        "submitted_at": submitted_at, "time_from_start_ms": finite_metric(report.get("timeFromStart")),
        "ignored_in_monitor": bool(detail.get("ignoredInMonitor", summary.get("ignoredInMonitor", False))),
        "source_url": f'https://admin.contest.yandex.ru/submissions/{int(report["id"])}',
    }


def write_judgment(root: Path, solution: dict[str, Any], judgment: dict[str, Any]) -> Path:
    if judgment["solution_id"] != solution["id"]:
        raise ValueError("Judgment belongs to another solution")
    path = solution_path(root, solution).with_suffix("") / f'{int(judgment["submission_id"])}.json'
    atomic_write_json(path, judgment)
    return path
