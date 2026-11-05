from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import runner
from models.base import SolveResult
from models.rosters import load_roster, roster_specs
from scoring.repository import build_catalog, competition_model_columns
from scripts.export_contest_preview import build_preview
from scripts.export_public_results import export_competition

ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False) + "\n")


class ModelRosterTests(unittest.TestCase):
    def test_cohorts_are_independent_of_changed_global_defaults(self):
        with patch("scoring.repository.configured_model_columns", side_effect=AssertionError("Global defaults consulted")):
            old = competition_model_columns({"model_roster": "benchmark-2026-08-01"})
            new = competition_model_columns({"model_roster": "flagships-2026-11-05"})
        self.assertEqual(len(old), 10)
        self.assertIn("openai:gpt-5.6-sol", old)
        self.assertNotIn("openai:gpt-6-astra", old)
        self.assertEqual(len(new), 9)
        self.assertEqual(len({column["provider"] for column in new.values()}), 9)
        self.assertIn("openai:gpt-6-astra", new)
        self.assertIn("anthropic:claude-fable-5-1", new)
        self.assertNotIn("anthropic:claude-opus-5", new)

    def test_rosters_validate_ids_and_fail_instead_of_falling_back(self):
        with self.assertRaises(ValueError):
            load_roster("../escape")
        with self.assertRaises(ValueError):
            competition_model_columns({"model_roster": "missing-cohort"})
        with TemporaryDirectory() as directory:
            root = Path(directory)
            roster = load_roster("flagships-2026-11-05")
            roster["models"].append(roster["models"][0])
            write_json(root / (roster["id"] + ".json"), roster)
            with self.assertRaises(ValueError):
                load_roster(roster["id"], directory=root)

    def test_runner_all_and_aliases_use_the_selected_competition_versions(self):
        old = load_roster("benchmark-2026-08-01")
        new = load_roster("flagships-2026-11-05")
        self.assertEqual(runner.requested_aliases("all", roster=new), roster_specs(new))
        self.assertEqual(runner.requested_aliases("gpt,claude", roster=old), ["openai:gpt-5.6-sol", "anthropic:claude-fable-5"])
        self.assertEqual(runner.requested_aliases("gpt,claude", roster=new), ["openai:gpt-6-astra", "anthropic:claude-fable-5-1"])
        with self.assertRaises(ValueError):
            runner.requested_aliases("openai:gpt-6-astra", roster=old)

    def test_runner_records_the_effective_roster_without_calling_any_provider(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); problem = root / "cup/task_01.json"
            write_json(problem.parent / "competition.json", {"schema_version": 1, "id": "cup", "title": "Cup", "metadata": {"model_roster": "benchmark-2026-08-01"}})
            write_json(problem, {"schema_version": 1, "id": "task_01", "statement": "Problem"})
            class FakeModel:
                model_id = "gpt-5.6-sol"
                def solve(self, problem, max_tokens=None):
                    return SolveResult(model=self.model_id, answer="fixture", prompt_tokens=1, completion_tokens=1, cost_usd=0, latency_ms=1, raw_response={})
            with patch("runner.create_model", return_value=FakeModel()) as create, patch("runner.print_progress"):
                result = runner.run_problem(problem_file=problem, models_value="gpt", logs_dir=root / "logs")
            self.assertEqual(create.call_args.args[0], "openai:gpt-5.6-sol")
            self.assertEqual(result.log["requested_models"], ["openai:gpt-5.6-sol"])
            persisted = json.loads(result.log_path.read_text())
            self.assertEqual(persisted["model_roster"]["id"], "benchmark-2026-08-01")
            self.assertEqual(len(persisted["model_roster"]["sha256"]), 64)
            self.assertEqual(next(model for model in persisted["model_roster"]["snapshot"]["models"] if model["provider"] == "openai")["model_id"], "gpt-5.6-sol")

    def test_old_and_new_results_keep_separate_keys_in_scoring_and_export(self):
        with TemporaryDirectory() as directory:
            root = Path(directory); competitions = root / "competitions"; logs = root / "logs"
            originals = {}
            for competition_id, roster_id in [("old-cup", "benchmark-2026-08-01"), ("new-cup", "flagships-2026-11-05")]:
                write_json(competitions / competition_id / "competition.json", {
                    "schema_version": 1, "id": competition_id, "title": competition_id,
                    "metadata": {"model_roster": roster_id, "max_score": 1},
                })
                write_json(competitions / competition_id / "task_01.json", {
                    "schema_version": 1, "id": "task_01", "statement": "Solve this", "title": "Task 1",
                })
                for index, model in enumerate(["gpt-5.6-sol", "gpt-6-astra"]):
                    run_id = "run-" + str(index); path = logs / competition_id / "task_01" / (run_id + ".json")
                    write_json(path, {"schema_version": 2, "run_id": run_id, "competition_id": competition_id,
                                      "problem_id": "task_01", "timestamp": "2026-11-05T00:00:00Z",
                                      "results": [{"result_id": "res-" + str(index), "provider": "openai", "model": model,
                                                   "requested_model_id": model, "answer": model + " exact answer", "error": None}]})
                    originals[path] = path.read_bytes()
            with patch("scoring.repository.configured_model_columns", return_value={}):
                catalog = build_catalog(competitions_dir=competitions, logs_dir=logs, results_dir=root / "scores")
            for competition_id, expected_model, excluded_model in [("old-cup", "gpt-5.6-sol", "gpt-6-astra"), ("new-cup", "gpt-6-astra", "gpt-5.6-sol")]:
                competition = catalog["competition_map"][competition_id]
                states = {s["model_key"]: s for s in competition["problems"]["task_01"]["model_states"]}
                self.assertEqual(states["openai:" + expected_model]["attempt_count"], 1)
                self.assertNotIn("openai:" + excluded_model, states)
                projection = export_competition(competition, output_dir=root / "public" / competition_id)
                names = [row["name"] for row in projection["participants"]]
                self.assertIn("GPT-5.6 Sol" if competition_id == "old-cup" else "GPT-6 Astra", names)
                self.assertEqual(projection["modelRoster"], competition["metadata"]["model_roster"])
            for path, content in originals.items():
                self.assertEqual(path.read_bytes(), content)

    def test_existing_competitions_are_pinned_and_algo_has_one_empty_model_per_provider(self):
        for path in (ROOT / "data/competitions").glob("*/competition.json"):
            manifest = json.loads(path.read_text())
            self.assertEqual(manifest["metadata"]["model_roster"], "benchmark-2026-08-01")
        snapshot = json.loads((ROOT / "data/public_results/algo-cup-2026-qualifying.json").read_text())
        competition = build_preview(snapshot)["competitions"][0]
        models = [row for row in competition["participants"] if row["type"] == "model"]
        self.assertEqual(len(models), 9)
        self.assertEqual(len({row["modelFamily"] for row in models}), 9)
        self.assertTrue(all(row["scores"] == [None] * 4 and row["runStatus"] == "not_started" for row in models))


if __name__ == "__main__":
    unittest.main()
