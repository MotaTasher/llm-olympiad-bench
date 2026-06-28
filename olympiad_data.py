from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


COMPETITION_MANIFEST = "competition.json"
ASSETS_DIR = "assets"


class DataLoadError(ValueError):
    pass


@dataclass(frozen=True)
class CompetitionRecord:
    path: Path
    manifest_path: Path
    id: str
    title: str
    data: dict[str, Any]


@dataclass(frozen=True)
class ProblemRecord:
    path: Path
    id: str
    title: str
    statement: str
    data: dict[str, Any]
    number: int | str | None = None


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as exc:
        raise DataLoadError(f"{path}: not valid UTF-8: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise DataLoadError(
            f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc
    except OSError as exc:
        raise DataLoadError(f"{path}: cannot read file: {exc}") from exc
    if not isinstance(value, dict):
        raise DataLoadError(f"{path}: top-level JSON value must be an object")
    return value


def _non_empty_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def display_problem_title(data: dict[str, Any], problem_id: str) -> str:
    title = _non_empty_string(data.get("title"))
    if title:
        return title
    number = data.get("number")
    if isinstance(number, int) or (isinstance(number, str) and number.strip()):
        return f"Задача {number}"
    return problem_id


def _number_sort_key(value: int | str | None) -> tuple[int, int | str]:
    if isinstance(value, bool) or value is None:
        return (1, "")
    if isinstance(value, int):
        return (0, value)
    if isinstance(value, str) and value.strip():
        stripped = value.strip()
        if stripped.isdigit():
            return (0, int(stripped))
        return (0, stripped)
    return (1, "")


def problem_sort_key(problem: ProblemRecord) -> tuple[tuple[int, int | str], str]:
    return (_number_sort_key(problem.number), problem.id)


def load_competition(path: Path | str) -> CompetitionRecord:
    competition_path = Path(path)
    manifest_path = (
        competition_path
        if competition_path.name == COMPETITION_MANIFEST
        else competition_path / COMPETITION_MANIFEST
    )
    if not manifest_path.exists():
        raise DataLoadError(f"{manifest_path}: competition.json is required")
    data = _read_json_object(manifest_path)
    competition_id = _non_empty_string(data.get("id"))
    if not competition_id:
        raise DataLoadError(f"{manifest_path}: id must be a non-empty string")
    root = manifest_path.parent
    if root.name != competition_id:
        raise DataLoadError(
            f"{manifest_path}: id {competition_id!r} must match directory name {root.name!r}"
        )
    title = _non_empty_string(data.get("title"))
    if not title:
        raise DataLoadError(f"{manifest_path}: title must be a non-empty string")
    return CompetitionRecord(
        path=root,
        manifest_path=manifest_path,
        id=competition_id,
        title=title,
        data=data,
    )


def load_problem(path: Path | str) -> ProblemRecord:
    problem_path = Path(path)
    data = _read_json_object(problem_path)
    problem_id = _non_empty_string(data.get("id"))
    if not problem_id:
        raise DataLoadError(f"{problem_path}: id must be a non-empty string")
    statement = _non_empty_string(data.get("statement"))
    if not statement:
        raise DataLoadError(f"{problem_path}: statement must be a non-empty string")
    number = data.get("number")
    if not (number is None or isinstance(number, (int, str))):
        raise DataLoadError(f"{problem_path}: number must be an integer, string, or null")
    return ProblemRecord(
        path=problem_path,
        id=problem_id,
        title=display_problem_title(data, problem_id),
        statement=statement,
        data=data,
        number=number,
    )


def _is_ignored_child(path: Path) -> bool:
    name = path.name
    return name.startswith(".") or name.startswith("~") or name.endswith(".tmp")


def _problem_json_paths(competition_path: Path) -> list[Path]:
    paths: list[Path] = []
    for path in competition_path.iterdir():
        if _is_ignored_child(path):
            continue
        if path.is_dir():
            continue
        if path.name == COMPETITION_MANIFEST:
            continue
        if path.suffix.lower() == ".json":
            paths.append(path)
    return sorted(paths)


def list_competitions(root: Path | str) -> list[CompetitionRecord]:
    root_path = Path(root)
    competitions: list[CompetitionRecord] = []
    for path in sorted(root_path.iterdir()):
        if _is_ignored_child(path) or not path.is_dir() or path.name == ASSETS_DIR:
            continue
        manifest = path / COMPETITION_MANIFEST
        if manifest.exists():
            competitions.append(load_competition(path))
    return competitions


def list_problems(competition_path: Path | str) -> list[ProblemRecord]:
    root = Path(competition_path)
    problems = [load_problem(path) for path in _problem_json_paths(root)]
    return sorted(problems, key=problem_sort_key)


def resolve_problem(path: Path | str) -> tuple[CompetitionRecord, ProblemRecord]:
    problem = load_problem(path)
    competition = load_competition(problem.path.parent)
    return competition, problem


def validate_competition(path: Path | str) -> CompetitionRecord:
    competition = load_competition(path)
    list_problems(competition.path)
    return competition
