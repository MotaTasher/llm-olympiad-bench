from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runner
from models.base import SolveResult
from olympiad_data import DataLoadError, list_problems, load_competition
from scripts.validate_problem_data import Finding, validate_competition_dir


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class TempCompetition(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.competition = self.tmp / "sample_competition"
        self.competition.mkdir()
        write_json(
            self.competition / "competition.json",
            {
                "schema_version": 1,
                "id": "sample_competition",
                "title": "Sample Competition",
                "metadata": {},
            },
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp)

    def write_problem(self, problem_id: str, **overrides: object) -> Path:
        data = {
            "schema_version": 1,
            "id": problem_id,
            "number": None,
            "statement": f"Statement for {problem_id}",
            "metadata": {},
        }
        data.update(overrides)
        path = self.competition / f"{problem_id}.json"
        write_json(path, data)
        return path


class LoaderTests(TempCompetition):
    def test_load_competition(self) -> None:
        competition = load_competition(self.competition)
        self.assertEqual(competition.id, "sample_competition")
        self.assertEqual(competition.title, "Sample Competition")

    def test_list_problems_sorts_by_number_then_id(self) -> None:
        self.write_problem("task_b", number=2, title="B")
        self.write_problem("task_a", number=1, title="A")
        self.write_problem("task_c", title="C")
        self.assertEqual([problem.id for problem in list_problems(self.competition)], ["task_a", "task_b", "task_c"])

    def test_problem_title_fallback_and_unknown_fields_are_preserved(self) -> None:
        self.write_problem("task_01", number=7, extra_field={"kept": True})
        problem = list_problems(self.competition)[0]
        self.assertEqual(problem.title, "Задача 7")
        self.assertEqual(problem.data["extra_field"], {"kept": True})

    def test_bad_json_error_includes_path(self) -> None:
        bad_path = self.competition / "broken.json"
        bad_path.write_text("{", encoding="utf-8")
        with self.assertRaises(DataLoadError) as caught:
            list_problems(self.competition)
        self.assertIn(str(bad_path), str(caught.exception))

    def test_competition_id_must_match_directory(self) -> None:
        write_json(
            self.competition / "competition.json",
            {"schema_version": 1, "id": "other", "title": "Other"},
        )
        with self.assertRaises(DataLoadError):
            load_competition(self.competition)

    def test_assets_are_ignored(self) -> None:
        self.write_problem("task_01")
        write_json(self.competition / "assets" / "not_a_problem.json", {"bad": True})
        self.assertEqual([problem.id for problem in list_problems(self.competition)], ["task_01"])


class ValidatorTests(TempCompetition):
    def test_filename_must_match_problem_id(self) -> None:
        write_json(
            self.competition / "wrong_name.json",
            {"schema_version": 1, "id": "task_01", "statement": "Text"},
        )
        findings: list[Finding] = []
        validate_competition_dir(self.competition, findings)
        self.assertTrue(any("filename stem must equal id" in item.message for item in findings))


class RunnerTests(TempCompetition):
    def test_runner_log_metadata_comes_from_canonical_files(self) -> None:
        problem_path = self.write_problem("task_01", title="Runner Task")
        logs_dir = self.tmp / "logs"

        class FakeModel:
            def solve(self, problem: str) -> SolveResult:
                return SolveResult(
                    model="fake-model",
                    answer=f"answer to {problem}",
                    prompt_tokens=1,
                    completion_tokens=2,
                    cost_usd=0.0,
                    latency_ms=3,
                    raw_response={},
                )

        argv = [
            "runner.py",
            "--problem",
            str(problem_path),
            "--models",
            "fake",
            "--run-id",
            "unit",
            "--logs-dir",
            str(logs_dir),
        ]
        with patch.object(sys, "argv", argv), patch.object(runner, "load_env"), patch.object(runner, "create_model", return_value=FakeModel()):
            self.assertEqual(runner.main(), 0)

        log_path = next(logs_dir.rglob("*.json"))
        log = json.loads(log_path.read_text(encoding="utf-8"))
        self.assertEqual(log["competition_id"], "sample_competition")
        self.assertEqual(log["competition_title"], "Sample Competition")
        self.assertEqual(log["problem_id"], "task_01")
        self.assertEqual(log["problem_title"], "Runner Task")


class RealDataTests(unittest.TestCase):
    def test_real_data_validates(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/validate_problem_data.py",
                "data/competitions",
                "--all",
                "--strict",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_legacy_problem_directories_remain(self) -> None:
        self.assertFalse((Path("data") / "problems").exists())
        self.assertFalse(any(Path("data/competitions").glob("*/problems")))


if __name__ == "__main__":
    unittest.main()
