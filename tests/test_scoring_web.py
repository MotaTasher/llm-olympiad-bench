from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import runner
from scoring.app import app as scoring_app
from scoring.repository import build_catalog, configured_model_columns


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class ScoringWebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.logs_dir = self.tmp / "logs"
        self.results_dir = self.tmp / "results"
        self.competitions_dir = self.tmp / "competitions"
        self.old_config = {
            "COMPETITIONS_DIR": scoring_app.config["COMPETITIONS_DIR"],
            "LOGS_DIR": scoring_app.config["LOGS_DIR"],
            "RESULTS_DIR": scoring_app.config["RESULTS_DIR"],
            "TESTING": scoring_app.config.get("TESTING"),
        }
        scoring_app.config.update(
            COMPETITIONS_DIR=self.competitions_dir,
            LOGS_DIR=self.logs_dir,
            RESULTS_DIR=self.results_dir,
            TESTING=True,
        )
        self.client = scoring_app.test_client()

    def tearDown(self) -> None:
        scoring_app.config.update(self.old_config)
        shutil.rmtree(self.tmp)

    def write_competition(self, competition_id: str, *, title: str, date: str | None = None) -> Path:
        path = self.competitions_dir / competition_id
        write_json(
            path / "competition.json",
            {
                "schema_version": 1,
                "id": competition_id,
                "title": title,
                "date": date,
                "metadata": {"max_score": 10},
            },
        )
        write_json(
            path / "task_01.json",
            {
                "schema_version": 1,
                "id": "task_01",
                "number": 1,
                "title": "Task One",
                "statement": "STATEMENT_TOKEN with $x_1+x_2$",
                "answer": "ANSWER_TOKEN",
                "solution": "SOLUTION_TOKEN",
                "metadata": {"max_score": 10},
            },
        )
        return path

    def write_run(
        self,
        *,
        competition_id: str = "math_2026",
        model_id: str = "gpt-5.5",
        provider: str = "openai",
        result_id: str = "res_a",
        answer: str = "MODEL_ANSWER_TOKEN",
        run_id: str = "run_active",
        timestamp: str = "2026-06-20T00:00:00Z",
    ) -> None:
        write_json(
            self.logs_dir / competition_id / "task_01" / f"{run_id}.json",
            {
                "schema_version": 2,
                "run_id": run_id,
                "timestamp": timestamp,
                "completed_at": timestamp,
                "competition_id": competition_id,
                "competition_title": "Math 2026",
                "problem_id": "task_01",
                "problem_title": "Task One",
                "results": [
                    {
                        "result_id": result_id,
                        "result_index": 0,
                        "provider": provider,
                        "model": model_id,
                        "requested_model_id": model_id,
                        "resolved_model_id": model_id,
                        "answer": answer,
                        "error": None,
                        "status": "success",
                        "prompt_tokens": 1,
                        "completion_tokens": 2,
                        "cost_usd": 0,
                        "latency_ms": 3,
                        "raw_response": {},
                    }
                ],
            },
        )

    def test_problem_page_is_single_column_statement_reference_answer_order(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()

        response = self.client.get("/competition/math_2026/problem/task_01?model=openai:gpt-5.5")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertLess(html.index("Условие"), html.index("Показать эталонное решение"))
        self.assertLess(html.index("Показать эталонное решение"), html.index("Ответ модели"))
        self.assertLess(html.index("Ответ модели"), html.index("MODEL_ANSWER_TOKEN"))
        self.assertIn('<div class="rendered scrollable-content" data-markdown>STATEMENT_TOKEN', html)
        self.assertIn("data-score-form", html)

    def test_anonymous_page_uses_same_sequence_and_full_width_selector(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()

        response = self.client.get("/competition/math_2026/problem/task_01/anonymous?seed=fixed&n=1")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        self.assertLess(html.index("Условие"), html.index("Показать эталонное решение"))
        self.assertLess(html.index("Показать эталонное решение"), html.index("Решение 1"))
        self.assertLess(html.index("Решение 1"), html.index("MODEL_ANSWER_TOKEN"))
        self.assertLess(html.index("MODEL_ANSWER_TOKEN"), html.index("Выбор решения"))
        self.assertIn('<div class="answer-layout">', html)

    def test_blank_evaluator_does_not_create_sidecar_and_nonblank_saves(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run()
        sidecar_path = self.results_dir / "math_2026" / "task_01" / "run_active.json"

        blank = self.client.post(
            "/score",
            data={
                "competition_id": "math_2026",
                "problem_id": "task_01",
                "run_id": "run_active",
                "result_id": "res_a",
                "model_key": "openai:gpt-5.5",
                "evaluator": "   ",
                "score": "7",
            },
            follow_redirects=True,
        )
        self.assertEqual(blank.status_code, 200)
        self.assertIn("Введите имя проверяющего.", blank.get_data(as_text=True))
        self.assertFalse(sidecar_path.exists())

        ok = self.client.post(
            "/score",
            data={
                "competition_id": "math_2026",
                "problem_id": "task_01",
                "run_id": "run_active",
                "result_id": "res_a",
                "model_key": "openai:gpt-5.5",
                "evaluator": " Judge ",
                "score": "7",
                "feedback": "ok",
            },
            follow_redirects=False,
        )
        self.assertEqual(ok.status_code, 302)
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["evaluation_pool"]["res_a"][0]["evaluator"], "Judge")

    def test_active_model_catalog_contains_only_strong_models(self) -> None:
        expected = {
            "openai:gpt-5.5",
            "anthropic:claude-opus-4-8",
            "deepseek:deepseek-v4-pro",
            "gigachat:GigaChat-2-Max",
            "yandexgpt:yandexgpt-5.1",
        }
        self.assertEqual(set(runner.active_model_specs()), expected)
        self.assertEqual(set(configured_model_columns()), expected)

    def test_weak_historical_model_does_not_create_scoring_column(self) -> None:
        self.write_competition("math_2026", title="Math 2026", date="2026-06-01")
        self.write_run(model_id="gpt-5.4-mini", result_id="res_weak", run_id="run_weak")
        self.write_run(
            model_id="yandexgpt-5.1/latest",
            provider="yandexgpt",
            result_id="res_yandex",
            run_id="run_yandex",
            answer="YANDEX_ALIAS_ANSWER",
        )

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        competition = catalog["competition_map"]["math_2026"]
        model_keys = [column["model_key"] for column in competition["model_columns"]]
        self.assertNotIn("openai:gpt-5.4-mini", model_keys)
        self.assertIn("yandexgpt:yandexgpt-5.1", model_keys)

        problem = competition["problems"]["task_01"]
        active_attempts = {
            state["model_key"]: state["attempt_count"]
            for state in problem["model_states"]
        }
        self.assertEqual(active_attempts["openai:gpt-5.5"], 0)
        self.assertEqual(active_attempts["yandexgpt:yandexgpt-5.1"], 1)

        html = self.client.get("/competition/math_2026").get_data(as_text=True)
        self.assertNotIn("gpt-5.4-mini", html)

    def test_competitions_group_by_year_and_sort_newest_first(self) -> None:
        self.write_competition("2026_05_math_cup_cs_space", title="May Cup", date=None)
        self.write_competition("math_2026_june", title="June Cup", date="2026-06-01")
        self.write_competition("math_2025_winter", title="Winter Cup", date="2025-12-01")
        self.write_competition("legacy_examples", title="Legacy Examples", date=None)
        self.write_run(competition_id="2026_05_math_cup_cs_space", run_id="may_run")
        self.write_run(competition_id="math_2026_june", run_id="june_run", timestamp="2026-06-10T00:00:00Z")
        self.write_run(competition_id="math_2025_winter", run_id="winter_run", timestamp="2025-12-10T00:00:00Z")

        catalog = build_catalog(
            competitions_dir=self.competitions_dir,
            logs_dir=self.logs_dir,
            results_dir=self.results_dir,
        )
        groups = catalog["competition_groups"]
        self.assertEqual([group["year"] for group in groups], [2026, 2025, None])
        self.assertEqual(
            [item["competition_id"] for item in groups[0]["competitions"]],
            ["math_2026_june", "2026_05_math_cup_cs_space"],
        )
        self.assertEqual(groups[-1]["competitions"][0]["competition_id"], "legacy_examples")


if __name__ == "__main__":
    unittest.main()
