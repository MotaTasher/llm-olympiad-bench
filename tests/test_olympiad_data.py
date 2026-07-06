from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import runner
from models.base import SolveResult
from models.gpt import gpt as gpt_module
from models.telemetry import normalize_run_log, redact
from olympiad_data import DataLoadError, list_problems, load_competition
from scoring.repository import build_catalog, find_attempt, save_evaluation
from scripts.export_scoring import rows_from_logs
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
            @property
            def model_id(self) -> str:
                return "fake-model"

            def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
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
        self.assertEqual(log["schema_version"], 2)
        self.assertEqual(log["status"], "completed")
        self.assertEqual(log["competition_id"], "sample_competition")
        self.assertEqual(log["competition_title"], "Sample Competition")
        self.assertEqual(log["problem_id"], "task_01")
        self.assertEqual(log["problem_title"], "Runner Task")
        self.assertEqual(log["results"][0]["status"], "success")
        self.assertRegex(log["results"][0]["result_id"], r"^res_")
        self.assertIn("system_prompt", log)

    def test_runner_writes_running_log_before_model_call_and_keeps_prior_success(self) -> None:
        problem_path = self.write_problem("task_01", title="Runner Task")
        logs_dir = self.tmp / "logs"
        seen_during_call: dict[str, object] = {}

        class GoodModel:
            @property
            def model_id(self) -> str:
                return "good-model"

            def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
                log_path = next(logs_dir.rglob("*.json"))
                data = json.loads(log_path.read_text(encoding="utf-8"))
                seen_during_call["run_status"] = data["status"]
                seen_during_call["result_status"] = data["results"][0]["status"]
                seen_during_call["result_id"] = data["results"][0]["result_id"]
                return SolveResult(
                    model="good-model",
                    answer="ok",
                    prompt_tokens=1,
                    completion_tokens=2,
                    cost_usd=0.0,
                    latency_ms=3,
                    raw_response={"usage": {"total_tokens": 3}},
                )

        class BadModel:
            @property
            def model_id(self) -> str:
                return "bad-model"

            def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
                raise RuntimeError("boom Authorization: secret")

        def factory(alias: str):
            return GoodModel() if alias == "good" else BadModel()

        argv = [
            "runner.py",
            "--problem",
            str(problem_path),
            "--models",
            "good,bad",
            "--run-id",
            "unit",
            "--logs-dir",
            str(logs_dir),
        ]
        with patch.object(sys, "argv", argv), patch.object(runner, "load_env"), patch.object(runner, "create_model", side_effect=factory):
            self.assertEqual(runner.main(), 0)

        self.assertEqual(seen_during_call["run_status"], "running")
        self.assertEqual(seen_during_call["result_status"], "running")
        self.assertRegex(str(seen_during_call["result_id"]), r"^res_")
        log = json.loads(next(logs_dir.rglob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(log["status"], "partial")
        self.assertEqual(log["results"][0]["status"], "success")
        self.assertEqual(log["results"][1]["status"], "error")
        self.assertEqual(log["results"][0]["answer"], "ok")
        self.assertNotIn("secret", json.dumps(log, ensure_ascii=False).lower())

    def test_runner_passes_max_tokens_to_model_and_runtime_metadata(self) -> None:
        problem_path = self.write_problem("task_01", title="Runner Task")
        logs_dir = self.tmp / "logs"
        seen: dict[str, object] = {}

        class FakeModel:
            @property
            def model_id(self) -> str:
                return "fake-model"

            def solve(self, problem: str, max_tokens: int | None = None) -> SolveResult:
                seen["max_tokens"] = max_tokens
                return SolveResult(
                    model="fake-model",
                    answer="ok",
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
            "--max-tokens",
            "1234",
        ]
        with patch.object(sys, "argv", argv), patch.object(runner, "load_env"), patch.object(runner, "create_model", return_value=FakeModel()):
            self.assertEqual(runner.main(), 0)

        self.assertEqual(seen["max_tokens"], 1234)
        log = json.loads(next(logs_dir.rglob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual(log["runtime"]["cli"]["max_tokens"], 1234)
        self.assertEqual(log["runtime_settings"]["max_tokens"], 1234)

    def test_gpt_responses_continues_empty_output_until_visible_answer(self) -> None:
        calls: list[dict[str, object]] = []

        class UsageDetails:
            def __init__(self, reasoning_tokens: int | None = None, cached_tokens: int | None = None) -> None:
                self.reasoning_tokens = reasoning_tokens
                self.cached_tokens = cached_tokens

        class Usage:
            def __init__(self, input_tokens: int, output_tokens: int, reasoning_tokens: int) -> None:
                self.input_tokens = input_tokens
                self.output_tokens = output_tokens
                self.total_tokens = input_tokens + output_tokens
                self.output_tokens_details = UsageDetails(reasoning_tokens=reasoning_tokens)
                self.input_tokens_details = UsageDetails(cached_tokens=0)

        class FakeResponse:
            def __init__(self, response_id: str, output_text: str, usage: Usage) -> None:
                self.id = response_id
                self.model = "gpt-5.5"
                self.status = "completed"
                self.output_text = output_text
                self.usage = usage

            def model_dump(self) -> dict[str, object]:
                return {
                    "id": self.id,
                    "model": self.model,
                    "status": self.status,
                    "output_text": self.output_text,
                    "usage": {
                        "input_tokens": self.usage.input_tokens,
                        "output_tokens": self.usage.output_tokens,
                        "total_tokens": self.usage.total_tokens,
                        "output_tokens_details": {
                            "reasoning_tokens": self.usage.output_tokens_details.reasoning_tokens
                        },
                    },
                }

        class FakeResponses:
            def create(self, **kwargs: object) -> FakeResponse:
                calls.append(kwargs)
                if len(calls) == 1:
                    return FakeResponse("resp_1", "", Usage(10, 100, 100))
                return FakeResponse("resp_2", "FINAL_SOLUTION", Usage(3, 20, 5))

        class FakeClient:
            def __init__(self, api_key: str, **kwargs: object) -> None:
                self.api_key = api_key
                self.kwargs = kwargs
                self.responses = FakeResponses()

        with (
            patch.dict(sys.modules, {"openai": types.SimpleNamespace(OpenAI=FakeClient)}),
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False),
            patch.object(gpt_module, "OPENAI_MAX_OUTPUT_TOKENS_BY_MODEL", {"gpt-5.5": 100}),
        ):
            result = gpt_module.GPTModel(model="gpt-5.5").solve("ORIGINAL_PROBLEM", max_tokens=250)

        self.assertIsNone(result.error)
        self.assertEqual(result.answer, "FINAL_SOLUTION")
        self.assertEqual(result.request["timeout_seconds"], gpt_module.OPENAI_DEFAULT_TIMEOUT_SECONDS)
        self.assertEqual([call["max_output_tokens"] for call in calls], [100, 100])
        self.assertEqual(calls[0]["input"], "ORIGINAL_PROBLEM")
        self.assertNotIn("previous_response_id", calls[0])
        self.assertEqual(calls[1]["previous_response_id"], "resp_1")
        self.assertEqual(calls[1]["input"], gpt_module.OPENAI_CONTINUATION_INPUT)
        self.assertEqual(result.prompt_tokens, 13)
        self.assertEqual(result.completion_tokens, 120)
        self.assertEqual(result.usage["reasoning_tokens"], 105)
        self.assertTrue(result.raw_response["multi_request"]["stopped_after_visible_output"])
        self.assertEqual(result.raw_response["multi_request"]["requests"], 2)

    def test_redactor_preserves_token_counts_but_removes_credentials(self) -> None:
        data = {
            "Authorization": "Bearer abc",
            "api_key": "abc",
            "prompt_tokens": 10,
            "max_tokens": 20,
            "nested": {
                "client_secret": "hidden",
                "completion_tokens": 30,
                "output_tokens_details": {"reasoning_tokens": 40},
                "completionTokensDetails": {"reasoningTokens": 50},
            },
        }
        redacted = redact(data)
        self.assertEqual(redacted["Authorization"], "[REDACTED]")
        self.assertEqual(redacted["api_key"], "[REDACTED]")
        self.assertEqual(redacted["prompt_tokens"], 10)
        self.assertEqual(redacted["max_tokens"], 20)
        self.assertEqual(redacted["nested"]["completion_tokens"], 30)
        self.assertEqual(redacted["nested"]["output_tokens_details"]["reasoning_tokens"], 40)
        self.assertEqual(redacted["nested"]["completionTokensDetails"]["reasoningTokens"], 50)

    def test_solve_result_extracts_reasoning_usage_before_redaction(self) -> None:
        openai_style = SolveResult(
            model="fake-model",
            answer="ok",
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            latency_ms=1,
            raw_response={
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 22,
                    "output_tokens_details": {"reasoning_tokens": 7},
                }
            },
        ).to_log_dict()
        yandex_style = SolveResult(
            model="fake-model",
            answer="ok",
            prompt_tokens=0,
            completion_tokens=0,
            cost_usd=0.0,
            latency_ms=1,
            raw_response={
                "result": {
                    "usage": {
                        "inputTextTokens": 12,
                        "completionTokens": 23,
                        "completionTokensDetails": {"reasoningTokens": 8},
                    }
                }
            },
        ).to_log_dict()

        self.assertEqual(openai_style["usage"]["reasoning_tokens"], 7)
        self.assertEqual(openai_style["usage"]["raw"]["output_tokens_details"]["reasoning_tokens"], 7)
        self.assertEqual(yandex_style["usage"]["input_tokens"], 12)
        self.assertEqual(yandex_style["usage"]["output_tokens"], 23)
        self.assertEqual(yandex_style["usage"]["reasoning_tokens"], 8)
        self.assertEqual(yandex_style["usage"]["raw"]["completionTokensDetails"]["reasoningTokens"], 8)

    def test_old_log_normalizes_without_mutating_schema(self) -> None:
        old = {
            "run_id": "legacy",
            "problem": {"id": "task", "text": "Statement"},
            "results": [{"model": "GigaChat", "answer": "A", "prompt_tokens": 1, "completion_tokens": 2, "latency_ms": 3}],
        }
        normalized = normalize_run_log(old)
        self.assertEqual(normalized["schema_version"], 1)
        self.assertEqual(normalized["results"][0]["usage"]["input_tokens"], 1)
        self.assertIsNone(normalized["results"][0]["usage"]["reasoning_tokens"])


class ScoringRepositoryTests(TempCompetition):
    def test_catalog_contains_canonical_problem_without_logs_and_statuses(self) -> None:
        self.write_problem("task_01", title="No Logs")
        logs_dir = self.tmp / "logs"
        results_dir = self.tmp / "results"
        catalog = build_catalog(
            competitions_dir=self.tmp,
            logs_dir=logs_dir,
            results_dir=results_dir,
        )
        problem = catalog["competition_map"]["sample_competition"]["problems"]["task_01"]
        self.assertTrue(problem["model_states"])
        self.assertTrue(any(state["status"] == "not_run" for state in problem["model_states"]))

    def test_sidecar_v2_save_and_invalid_result_id_protection(self) -> None:
        self.write_problem("task_01", title="Task", metadata={"max_score": 5})
        logs_dir = self.tmp / "logs"
        results_dir = self.tmp / "results"
        write_json(
            logs_dir / "sample_competition" / "task_01" / "run.json",
            {
                "schema_version": 2,
                "run_id": "run",
                "timestamp": "2026-06-29T00:00:00Z",
                "competition_id": "sample_competition",
                "competition_title": "Sample Competition",
                "problem_id": "task_01",
                "problem_title": "Task",
                "results": [
                    {
                        "result_id": "res_a",
                        "result_index": 0,
                        "provider": "openai",
                        "model": "gpt-5.5",
                        "requested_model_id": "gpt-5.5",
                        "answer": "answer",
                        "error": None,
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "cost_usd": 0,
                        "latency_ms": 1,
                        "raw_response": {},
                    }
                ],
            },
        )
        catalog = build_catalog(competitions_dir=self.tmp, logs_dir=logs_dir, results_dir=results_dir)
        found = find_attempt(
            catalog,
            competition_id="sample_competition",
            problem_id="task_01",
            run_id="run",
            result_id="res_a",
        )
        self.assertIsNotNone(found)
        self.assertIsNone(
            find_attempt(
                catalog,
                competition_id="sample_competition",
                problem_id="task_01",
                run_id="run",
                result_id="res_b",
            )
        )
        before = (logs_dir / "sample_competition" / "task_01" / "run.json").read_bytes()
        save_evaluation(
            results_dir=results_dir,
            competition_id="sample_competition",
            problem_id="task_01",
            run_id="run",
            result_id="res_a",
            result_index=0,
            model_key_value="openai:gpt-5.5",
            model="gpt-5.5",
            evaluator="judge",
            score=3,
            max_score=5,
            feedback="ok",
        )
        sidecar = json.loads((results_dir / "sample_competition" / "task_01" / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(sidecar["schema_version"], 2)
        self.assertIn("res_a", sidecar["evaluations"])
        after = (logs_dir / "sample_competition" / "task_01" / "run.json").read_bytes()
        self.assertEqual(before, after)

    def test_legacy_sidecar_by_index_and_export(self) -> None:
        self.write_problem("task_01", title="Task")
        logs_dir = self.tmp / "logs"
        results_dir = self.tmp / "results"
        write_json(
            logs_dir / "legacy_root.json",
            {
                "run_id": "legacy_root",
                "timestamp": "2026-06-29T00:00:00Z",
                "problem": {"id": "task_01", "title": "Task", "text": "S"},
                "results": [
                    {
                        "provider": "gigachat",
                        "model": "GigaChat-2-Max",
                        "requested_model_id": "GigaChat-2-Max",
                        "answer": "A",
                        "prompt_tokens": 1,
                        "completion_tokens": 2,
                        "cost_usd": 0,
                        "latency_ms": 4,
                    }
                ],
            },
        )
        write_json(
            results_dir / "legacy" / "task_01" / "legacy_root.json",
            {
                "evaluations": {
                    "0": {"score": 10, "evaluator": "old", "feedback": "good", "updated_at": "now"}
                }
            },
        )
        catalog = build_catalog(competitions_dir=self.tmp, logs_dir=logs_dir, results_dir=results_dir)
        legacy_problem = catalog["competition_map"]["legacy"]["problems"]["task_01"]
        scored_states = [state for state in legacy_problem["model_states"] if state["attempt_count"]]
        self.assertEqual(scored_states[0]["status"], "full")
        rows = rows_from_logs(logs_dir, results_dir, only_scored=False)
        self.assertEqual(rows[0]["score"], 10)
        self.assertIn("result_id", rows[0])

    def test_flask_pages_and_score_flow(self) -> None:
        try:
            from scoring.app import app as scoring_app
            from scoring.auth import create_user
        except ModuleNotFoundError as exc:
            if exc.name in {"flask", "flask_login", "flask_wtf", "wtforms"}:
                self.skipTest("Flask is not installed in this interpreter")
            raise
        self.write_problem("task_01", title="Task", metadata={"max_score": 4})
        logs_dir = self.tmp / "logs"
        results_dir = self.tmp / "results"
        write_json(
            logs_dir / "sample_competition" / "task_01" / "run.json",
            {
                "schema_version": 2,
                "run_id": "run",
                "timestamp": "2026-06-29T00:00:00Z",
                "competition_id": "sample_competition",
                "competition_title": "Sample Competition",
                "problem_id": "task_01",
                "problem_title": "Task",
                "results": [
                    {
                        "result_id": "res_a",
                        "result_index": 0,
                        "provider": "openai",
                        "model": "gpt-5.5",
                        "requested_model_id": "gpt-5.5",
                        "answer": "answer",
                        "error": None,
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "cost_usd": 0,
                        "latency_ms": 1,
                        "raw_response": {},
                    }
                ],
            },
        )
        old_config = {
            "COMPETITIONS_DIR": scoring_app.config["COMPETITIONS_DIR"],
            "LOGS_DIR": scoring_app.config["LOGS_DIR"],
            "RESULTS_DIR": scoring_app.config["RESULTS_DIR"],
            "AUTH_DB": scoring_app.config.get("AUTH_DB"),
            "TESTING": scoring_app.config.get("TESTING"),
            "WTF_CSRF_TIME_LIMIT": scoring_app.config.get("WTF_CSRF_TIME_LIMIT"),
        }
        scoring_app.config.update(
            COMPETITIONS_DIR=self.tmp,
            LOGS_DIR=logs_dir,
            RESULTS_DIR=results_dir,
            AUTH_DB=self.tmp / "auth.sqlite3",
            TESTING=True,
            WTF_CSRF_TIME_LIMIT=None,
        )
        try:
            _, password = create_user(scoring_app.config["AUTH_DB"], "repo-smoke")
            client = scoring_app.test_client()
            login_page = client.get("/login").get_data(as_text=True)
            csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', login_page).group(1)
            login = client.post(
                "/login",
                data={"username": "repo-smoke", "password": password, "csrf_token": csrf},
                follow_redirects=False,
            )
            self.assertEqual(login.status_code, 302)
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
            response = client.get("/competition/sample_competition")
            self.assertEqual(response.status_code, 200)
            self.assertIn("Sample Competition".encode(), response.data)
            self.assertIn('aria-label="'.encode(), response.data)
            response = client.get("/competition/sample_competition/problem/task_01?model=openai:gpt-5.5")
            self.assertEqual(response.status_code, 200)
            self.assertIn("answer".encode(), response.data)
            csrf = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', response.get_data(as_text=True)).group(1)
            bad = client.post(
                "/score",
                data={
                    "competition_id": "sample_competition",
                    "problem_id": "task_01",
                    "run_id": "run",
                    "result_id": "res_a",
                    "model_key": "openai:gpt-5.5",
                    "score": "5",
                },
                follow_redirects=False,
            )
            self.assertEqual(bad.status_code, 400)
            self.assertFalse((results_dir / "sample_competition" / "task_01" / "run.json").exists())
            ok = client.post(
                "/score",
                data={
                    "csrf_token": csrf,
                    "competition_id": "sample_competition",
                    "problem_id": "task_01",
                    "run_id": "run",
                    "result_id": "res_a",
                    "model_key": "openai:gpt-5.5",
                    "evaluator": "browser-ignored",
                    "score": "4",
                    "feedback": "ok",
                },
                follow_redirects=False,
            )
            self.assertEqual(ok.status_code, 302)
            self.assertIn("model=openai:gpt-5.5", ok.headers["Location"])
            sidecar = json.loads((results_dir / "sample_competition" / "task_01" / "run.json").read_text(encoding="utf-8"))
            self.assertIn("res_a", sidecar["evaluations"])
            self.assertEqual(sidecar["evaluation_pool"]["res_a"][0]["evaluator"], "repo-smoke")
            legacy = client.get("/run/run")
            self.assertEqual(legacy.status_code, 302)
        finally:
            scoring_app.config.update(old_config)


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
