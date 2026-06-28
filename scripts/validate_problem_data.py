from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from olympiad_data import ASSETS_DIR, COMPETITION_MANIFEST


@dataclass
class Finding:
    level: str
    path: Path
    message: str

    def render(self) -> str:
        return f"{self.level} {self.path}: {self.message}"


def read_json(path: Path, findings: list[Finding]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        findings.append(Finding("ERROR", path, f"not valid UTF-8: {exc}"))
        return None
    except json.JSONDecodeError as exc:
        findings.append(
            Finding(
                "ERROR",
                path,
                f"invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            )
        )
        return None
    except OSError as exc:
        findings.append(Finding("ERROR", path, f"cannot read file: {exc}"))
        return None
    if not isinstance(value, dict):
        findings.append(Finding("ERROR", path, "top-level JSON value must be an object"))
        return None
    return value


def non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_optional_string(
    data: dict[str, Any], path: Path, field: str, findings: list[Finding]
) -> None:
    value = data.get(field)
    if value is not None and not isinstance(value, str):
        findings.append(Finding("ERROR", path, f"{field} must be a string or null"))


def validate_competition_manifest(path: Path, findings: list[Finding]) -> str | None:
    data = read_json(path, findings)
    if data is None:
        return None

    if not isinstance(data.get("schema_version"), int):
        findings.append(Finding("ERROR", path, "schema_version must be an integer"))

    competition_id = data.get("id")
    if not non_empty_string(competition_id):
        findings.append(Finding("ERROR", path, "id must be a non-empty string"))
        competition_id = None
    elif path.parent.name != competition_id.strip():
        findings.append(
            Finding(
                "ERROR",
                path,
                f"id must match directory name: {competition_id!r} != {path.parent.name!r}",
            )
        )

    if not non_empty_string(data.get("title")):
        findings.append(Finding("ERROR", path, "title must be a non-empty string"))

    for field in ("description", "date", "source"):
        validate_optional_string(data, path, field, findings)
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        findings.append(Finding("ERROR", path, "metadata must be an object when present"))

    return competition_id.strip() if isinstance(competition_id, str) else None


def validate_problem_file(path: Path, findings: list[Finding]) -> tuple[str | None, Any]:
    data = read_json(path, findings)
    if data is None:
        return None, None

    if not isinstance(data.get("schema_version"), int):
        findings.append(Finding("ERROR", path, "schema_version must be an integer"))

    problem_id = data.get("id")
    if not non_empty_string(problem_id):
        findings.append(Finding("ERROR", path, "id must be a non-empty string"))
        problem_id = None
    elif path.stem != problem_id.strip():
        findings.append(
            Finding(
                "ERROR",
                path,
                f"filename stem must equal id: {path.stem!r} != {problem_id!r}",
            )
        )

    if "competition_id" in data:
        findings.append(Finding("ERROR", path, "competition_id is not allowed in problem files"))
    if "competition_title" in data:
        findings.append(Finding("ERROR", path, "competition_title is not allowed in problem files"))

    if "title" in data and data.get("title") is not None and not non_empty_string(data.get("title")):
        findings.append(Finding("ERROR", path, "title must be a non-empty string when present"))

    if not non_empty_string(data.get("statement")):
        findings.append(Finding("ERROR", path, "statement must be a non-empty string"))

    number = data.get("number")
    if number is not None and not isinstance(number, (int, str)):
        findings.append(Finding("ERROR", path, "number must be an integer, string, or null"))

    validate_optional_string(data, path, "answer", findings)
    validate_optional_string(data, path, "solution", findings)
    tags = data.get("tags")
    if tags is not None and (
        not isinstance(tags, list) or any(not isinstance(item, str) for item in tags)
    ):
        findings.append(Finding("ERROR", path, "tags must be a list of strings"))
    metadata = data.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        findings.append(Finding("ERROR", path, "metadata must be an object when present"))

    return problem_id.strip() if isinstance(problem_id, str) else None, number


def should_ignore_child(path: Path) -> bool:
    name = path.name
    return name.startswith(".") or name.startswith("~") or name.endswith(".tmp")


def problem_paths(competition_dir: Path, findings: list[Finding]) -> list[Path]:
    paths: list[Path] = []
    for path in sorted(competition_dir.iterdir()):
        if should_ignore_child(path):
            continue
        if path.name == ASSETS_DIR and path.is_dir():
            continue
        if path.name == "problems" and path.is_dir():
            findings.append(Finding("ERROR", path, "legacy problems/ directory is not allowed"))
            continue
        if path.is_dir():
            continue
        if path.name == COMPETITION_MANIFEST:
            continue
        if path.suffix.lower() == ".json":
            paths.append(path)
    return paths


def validate_competition_dir(path: Path, findings: list[Finding]) -> tuple[int, int]:
    if not path.exists():
        findings.append(Finding("ERROR", path, "target does not exist"))
        return 0, 0
    if not path.is_dir():
        findings.append(Finding("ERROR", path, "target must be a competition directory"))
        return 0, 0

    manifest = path / COMPETITION_MANIFEST
    if not manifest.exists():
        findings.append(Finding("ERROR", manifest, "competition.json is required"))
        competition_id = None
    else:
        competition_id = validate_competition_manifest(manifest, findings)

    paths = problem_paths(path, findings)
    if not paths:
        findings.append(Finding("ERROR", path, "at least one problem JSON file is required"))

    seen_ids: dict[str, Path] = {}
    seen_numbers: dict[Any, Path] = {}
    valid_problem_ids = 0
    for problem_path in paths:
        problem_id, number = validate_problem_file(problem_path, findings)
        if problem_id:
            valid_problem_ids += 1
            previous = seen_ids.get(problem_id)
            if previous is not None:
                findings.append(
                    Finding("ERROR", problem_path, f"duplicate id {problem_id!r}; first seen in {previous}")
                )
            else:
                seen_ids[problem_id] = problem_path
        if number is not None:
            previous = seen_numbers.get(number)
            if previous is not None:
                findings.append(
                    Finding(
                        "ERROR",
                        problem_path,
                        f"duplicate number {number!r}; first seen in {previous}",
                    )
                )
            else:
                seen_numbers[number] = problem_path

    if competition_id and competition_id != path.name:
        findings.append(Finding("ERROR", path, "competition directory name mismatch"))

    return len(paths), valid_problem_ids


def competition_targets(target: Path, all_competitions: bool, findings: list[Finding]) -> list[Path]:
    if all_competitions:
        if not target.exists() or not target.is_dir():
            findings.append(Finding("ERROR", target, "--all target must be a directory"))
            return []
        return [
            path
            for path in sorted(target.iterdir())
            if path.is_dir() and not should_ignore_child(path) and path.name != ASSETS_DIR
        ]
    return [target]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate canonical Olympiad Scorer competition and problem JSON files."
    )
    parser.add_argument("target", help="Competition directory, or data/competitions with --all")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Validate every competition directory directly below target.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Accepted for compatibility; canonical validation is always strict.",
    )
    args = parser.parse_args()

    target = Path(args.target)
    findings: list[Finding] = []
    targets = competition_targets(target, args.all, findings)
    if args.all and not targets and not findings:
        findings.append(Finding("ERROR", target, "no competition directories found"))

    problem_count = 0
    valid_problem_ids = 0
    for competition_dir in targets:
        count, valid = validate_competition_dir(competition_dir, findings)
        problem_count += count
        valid_problem_ids += valid

    for finding in findings:
        print(finding.render())

    error_count = sum(finding.level == "ERROR" for finding in findings)
    warning_count = sum(finding.level == "WARN" for finding in findings)
    print(
        f"Checked {len(targets)} competition(s), {problem_count} problem file(s), "
        f"{valid_problem_ids} with readable IDs; {error_count} error(s), "
        f"{warning_count} warning(s)."
    )
    return 1 if error_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
