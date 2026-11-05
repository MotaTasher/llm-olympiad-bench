"""Publish official team standings and unstarted model rows; no network calls."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scoring.repository import competition_model_columns
from models.rosters import load_roster
from scripts.export_public_results import atomic_write_text, model_name, public_model_slug, safe_component
from judging.records import validate_solution


def build_preview(snapshot: dict[str, Any]) -> dict[str, Any]:
    tasks = snapshot["tasks"]
    teams = snapshot["teams"]
    if not tasks or len(teams) != 3 or snapshot["scoring_system"] != "acm":
        raise ValueError("An ACM preview needs tasks and exactly three official teams")
    if [team["rank"] for team in teams] != [1, 2, 3]:
        raise ValueError("Keep the official top-three order")
    for team in teams:
        if len(team["scores"]) != len(tasks) or any(score not in (0, 1) for score in team["scores"]):
            raise ValueError("ACM scores must contain one solved flag per task")
        if sum(team["scores"]) != team["solved"] or team["penalty"] < 0:
            raise ValueError("Invalid official team totals")
    if teams != sorted(teams, key=lambda team: (-team["solved"], team["penalty"])):
        raise ValueError("Official ranks disagree with solved count / penalty")

    participants = [
        {
            **team, "type": "team", "medal": ("🥇", "🥈", "🥉")[index],
            "points": team["solved"],
            "accuracy": round(team["solved"] / len(tasks) * 100, 1),
            "cost": None, "tokens": None,
        }
        for index, team in enumerate(teams)
    ]
    for participant in participants:
        references = participant.pop("code_solutions", [])
        participant.pop("yandex_participant_id", None)
        if references:
            if len(references) != len(tasks):
                raise ValueError("Each team needs one selected solution per task")
            participant["solutions"] = [f'code/solutions/{reference["solution_id"]}.json' for reference in references]
    for key, column in competition_model_columns({"model_roster": snapshot["model_roster"]}).items():
        participants.append({
            "id": safe_component(key, "model"), "slug": public_model_slug(column),
            "type": "model", "name": model_name(column),
            "provider": column["provider_label"], "runStatus": "not_started",
            "modelKey": key, "modelFamily": column["provider"],
            "scores": [None] * len(tasks), "solutions": [None] * len(tasks),
            "points": None, "solved": None, "penalty": None,
            "accuracy": None, "cost": None, "tokens": None,
        })
    competition_id = snapshot["id"]
    release = {
        "id": competition_id, "benchmarkId": "algo-cup", "series": snapshot["series"],
        "year": snapshot["year"], "stageLabel": snapshot["stage"],
        "title": f'{snapshot["title"]} · {snapshot["stage"]}',
        "description": snapshot["official_title"], "competitionIds": [competition_id],
    }
    competition = {
        "id": competition_id, "series": "algo-cup", "seriesLabel": snapshot["series"],
        "editionLabel": f'{snapshot["year"]} · {snapshot["stage"]}',
        "title": snapshot["title"], "stage": snapshot["stage"], "date": snapshot["date"],
        "description": "Результаты топ-3 команд из Яндекс Контеста. Модели пока не запускались.",
        "scoringSystem": "acm", "solutionFormat": "code", "runStatus": "not_started",
        "sourceUrl": snapshot["source"], "contestId": snapshot["contest_id"],
        "taskCount": len(tasks), "tasks": tasks, "participants": participants,
        "modelRoster": snapshot["model_roster"],
        "competitionRules": [
            "Команды решали четыре задачи по программированию в течение трёх часов.",
            "В таблице опубликованы три лучшие команды по официальному монитору Яндекс Контеста 103053. За принятую задачу — 1 балл; при равенстве числа решённых задач выше команда с меньшим штрафом.",
            "Результаты моделей пока отсутствуют: прочерк означает, что запуск не проводился, а не нулевой балл.",
        ],
        "modelLaunchRules": [
            "Запуски моделей для этого этапа ещё не проводились.",
            "Планируемый формат ответа — исходный код решения. Модель получает условие текстом и отвечает текстом; инструменты, поиск и исполнение кода во время генерации не используются.",
            "Проверка сгенерированного кода планируется отдельно в Яндекс Контесте. Язык, компилятор и параметры запуска будут зафиксированы до начала проверки.",
        ],
    }
    return {
        "releases": [release], "competitions": [competition],
        "catalog": [{
            "id": competition_id, "series": snapshot["series"], "year": snapshot["year"],
            "title": snapshot["title"], "stageLabel": snapshot["stage"],
            "taskLabel": f"{len(tasks)} задачи", "competitionId": competition_id, "accent": "dark",
        }],
    }


def export_code_documents(snapshot: dict[str, Any], *, sources: Path, judgments: Path, output: Path) -> int:
    count = 0
    for team in snapshot["teams"]:
        references = team.get("code_solutions", [])
        if references and len(references) != len(snapshot["tasks"]):
            raise ValueError("Missing selected team solution")
        for task, reference in zip(snapshot["tasks"], references):
            solution_id = safe_component(reference["solution_id"], "solution")
            relative = Path(snapshot["id"]) / task["id"]
            source = json.loads((sources / relative / (solution_id + ".json")).read_text())
            validate_solution(source)
            judgment = json.loads((judgments / relative / solution_id / f'{int(reference["submission_id"])}.json').read_text())
            if (source["author"]["id"] != team["id"] or source["problem_id"] != task["id"]
                    or source["competition_id"] != snapshot["id"] or judgment["solution_id"] != source["id"]
                    or judgment["contest_id"] != snapshot["contest_id"] or judgment["problem_alias"] != task["short"]
                    or judgment["status"] != "finished" or judgment["verdict"] != "OK"
                    or judgment["ignored_in_monitor"]):
                raise ValueError("Selected accepted submission does not match team / task / contest")
            document = {
                "schemaVersion": 1, "format": "code",
                "competition": {"id": snapshot["id"], "title": snapshot["title"], "stage": snapshot["stage"]},
                "task": {k: task[k] for k in ("id", "title", "maxScore", "sourceUrl")},
                "author": {k: source["author"][k] for k in ("id", "type", "name")},
                "source": {k: source["source"][k] for k in ("code", "language", "filename", "sha256")},
                "result": {"score": judgment["score"], "verdict": "Принято · OK"},
                "judge": {k: judgment[k] for k in ("judge", "contest_id", "submission_id", "compiler_id", "compiler_name",
                           "status", "verdict", "metrics", "submitted_at", "time_from_start_ms")},
            }
            atomic_write_text(output / "solutions" / (solution_id + ".json"), json.dumps(document, ensure_ascii=False, indent=2) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "data/public_results/algo-cup-2026-qualifying.json")
    parser.add_argument("--output", type=Path, default=ROOT / "public_results/contest-previews.js")
    parser.add_argument("--code-output", type=Path, default=ROOT / "public_results/code")
    parser.add_argument("--sources", type=Path, default=ROOT / "data/code_solutions")
    parser.add_argument("--judgments", type=Path, default=ROOT / "data/judge_results")
    parser.add_argument("--rosters-output", type=Path, default=ROOT / "public_results/model-rosters.js")
    args = parser.parse_args()
    snapshot = json.loads(args.source.read_text(encoding="utf-8"))
    document = build_preview(snapshot)
    count = export_code_documents(snapshot, sources=args.sources, judgments=args.judgments, output=args.code_output)
    public_rosters = {}
    for path in sorted((ROOT / "data/competitions").glob("*/competition.json")):
        manifest = json.loads(path.read_text())
        roster_id = manifest.get("metadata", {}).get("model_roster")
        if roster_id:
            public_rosters[manifest["id"]] = public_roster(roster_id)
    public_rosters[snapshot["id"]] = public_roster(snapshot["model_roster"])
    atomic_write_text(args.rosters_output, "window.COMPETITION_MODEL_ROSTERS = " + json.dumps(public_rosters, ensure_ascii=False, indent=2) + ";\n")
    atomic_write_text(args.output, "window.CONTEST_PREVIEWS = " + json.dumps(document, ensure_ascii=False, indent=2) + ";\n")
    print(f"Prepared {len(document['competitions'])} contest preview and {count} code documents; no model or judge calls")


def public_roster(roster_id: str) -> dict[str, Any]:
    roster = load_roster(roster_id)
    return {"id": roster["id"], "asOf": roster["as_of"], "models": [
        {"provider": model["provider"], "modelId": model["model_id"], "name": model["display_name"]}
        for model in roster["models"]
    ]}


if __name__ == "__main__":
    main()
