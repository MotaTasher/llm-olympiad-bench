from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from judging.records import make_judgment, make_solution, validate_solution, write_solution
from judging.yandex_contest import list_submissions, submission_plan, submit
from scripts.export_contest_preview import export_code_documents
from scripts.import_contest_winners import import_winners
from scripts.judge_code import submit_once

ROOT = Path(__file__).resolve().parents[1]


def example(language="cpp"):
    return make_solution(competition_id="cup", task_id="task_01",
                         author={"type": "model", "id": "model-x", "name": "Model X"},
                         code='int main() { return 0; }\r\n' if language == "cpp" else 'print("$<script>")\r\n',
                         language=language, origin={"kind": "model_generation"},
                         generation={"result_id": "res_test", "run_id": "run_test", "model_key": "test:model"})


class CodeJudgingTests(unittest.TestCase):
    def test_exact_source_and_hash_are_immutable(self):
        solution = example("python")
        source_text = 'api_key = "fixture_not_a_credential"\r\nprint("$<script>")\r\n'
        solution = make_solution(competition_id="cup", task_id="task_01", author=solution["author"],
                                 code=source_text, language="python", origin={"kind": "model_generation"})
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_solution(root, solution)
            loaded = json.loads(path.read_text())
            self.assertEqual(loaded["source"]["code"], source_text)
            validate_solution(loaded)
            self.assertEqual(write_solution(root, solution), path)
            mutated = copy.deepcopy(solution)
            mutated["source"]["code"] += "# changed"
            with self.assertRaises(ValueError):
                validate_solution(mutated)
        with self.assertRaises(ValueError):
            make_solution(competition_id="../escape", task_id="task_01", author=solution["author"],
                          code="pass", language="python", origin={})

    def test_default_compilers_and_language_validation(self):
        for language, compiler in [("cpp", "gcc14_cpp23"), ("python", "python3_13")]:
            plan = submission_plan(example(language), contest_id=103053, problem_id="group/task", problem_alias="A")
            self.assertEqual(plan["compiler_id"], compiler)
            self.assertEqual(plan["submit_as"], "authenticated_admin")
        with self.assertRaises(ValueError):
            submission_plan(example(), contest_id=103053, problem_id="group/task", problem_alias="A", compiler_id="python3_13")

    def test_dry_run_makes_no_calls_or_outbox_writes(self):
        client = Mock(); upload = Mock(); solution = example()
        plan = submission_plan(solution, contest_id=103053, problem_id="group/task", problem_alias="A")
        with TemporaryDirectory() as directory:
            jobs = Path(directory) / "jobs"
            self.assertEqual(submit_once(client, solution, plan, jobs=jobs, execute=False, upload=upload)["state"], "dry_run")
            self.assertFalse(jobs.exists())
        client.assert_not_called(); self.assertEqual(client.mock_calls, []); upload.assert_not_called()

    def test_admin_submit_checks_contest_and_uses_separate_upload(self):
        client = Mock(); upload = Mock(return_value=Mock(status_code=204))
        client.json.side_effect = [
            {"compilers": ["gcc14_cpp23"]},
            {"problems": [{"id": "group/task", "title": "A"}]},
            {"url": "https://storage.example/signed", "fields": {"policy": "private"}, "key": "uploads/key"},
            {"id": 123},
        ]
        solution = example(); plan = submission_plan(solution, contest_id=103053, problem_id="group/task", problem_alias="A")
        self.assertEqual(submit(client, solution, plan, upload=upload), 123)
        post = client.json.call_args
        self.assertEqual(post.args[0], "POST")
        self.assertEqual(set(post.kwargs["json"]), {"problemId", "compilerId", "fileName", "s3Id"})
        self.assertNotIn("participantId", post.kwargs["json"])
        self.assertNotIn("headers", upload.call_args.kwargs)
        self.assertEqual(upload.call_args.kwargs["files"]["file"][1], solution["source"]["code"].encode())

    def test_wrong_problem_is_never_uploaded(self):
        client = Mock(); upload = Mock()
        client.json.side_effect = [{"compilers": ["gcc14_cpp23"]}, {"problems": [{"id": "other", "title": "A"}]}]
        with self.assertRaises(ValueError):
            submit(client, example(), submission_plan(example(), contest_id=103053, problem_id="group/task", problem_alias="A"), upload=upload)
        upload.assert_not_called()

    def test_uncertain_submit_is_recorded_and_never_automatically_repeated(self):
        solution = example(); plan = submission_plan(solution, contest_id=103053, problem_id="group/task", problem_alias="A")
        with TemporaryDirectory() as directory, patch("scripts.judge_code.submit", side_effect=TimeoutError("signed secret")) as sending:
            jobs = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "outcome unknown"):
                submit_once(Mock(), solution, plan, jobs=jobs, execute=True)
            record = json.loads(next(jobs.rglob("*.json")).read_text())
            self.assertEqual(record["state"], "outcome_unknown")
            self.assertNotIn("signed secret", json.dumps(record))
            with self.assertRaises(FileExistsError):
                submit_once(Mock(), solution, plan, jobs=jobs, execute=True)
            sending.assert_called_once()

    def test_report_metrics_keep_zero_and_do_not_publish_private_test_data(self):
        detail = {
            "submissionReport": {"id": 123, "contestId": 103053, "problemAlias": "A", "compilerId": "gcc14_cpp23",
                                 "compilerName": "C++23", "status": "finished", "absoluteTime": 1793772428388,
                                 "timeFromStart": 428388, "ip": "private", "sourceCode": "private"},
            "verdict": "OK", "slaveHost": "private", "compileLog": "private",
            "tests": [{"runningTime": 20, "memoryUsed": 100, "testName": "hidden-test"}],
        }
        record = make_judgment(example(), detail, summary={"usedTimeMillis": 0, "usedMemoryBytes": 0})
        self.assertEqual(record["metrics"], {"time_ms": 0, "memory_bytes": 0})
        self.assertNotIn("private", json.dumps(record)); self.assertNotIn("hidden-test", json.dumps(record))
        self.assertEqual(make_judgment(example(), detail)["metrics"], {"time_ms": 20, "memory_bytes": 100})
        detail["submissionReport"]["status"] = "running"
        self.assertIsNone(make_judgment(example(), detail)["score"])

    def test_submission_pagination_uses_page_index_not_record_offset(self):
        client = Mock(); client.json.side_effect = [{"items": [{}] * 100}, {"items": [{"id": 101}]}]
        self.assertEqual(len(list(list_submissions(client, 103053, participant_id=42))), 101)
        self.assertEqual([call.kwargs["params"]["offset"] for call in client.json.call_args_list], [0, 1])

    def test_public_export_contains_twelve_real_accepted_solutions(self):
        snapshot = json.loads((ROOT / "data/public_results/algo-cup-2026-qualifying.json").read_text())
        with TemporaryDirectory() as directory:
            output = Path(directory)
            count = export_code_documents(snapshot, sources=ROOT / "data/code_solutions", judgments=ROOT / "data/judge_results", output=output)
            self.assertEqual(count, 12)
            for path in (output / "solutions").glob("*.json"):
                document = json.loads(path.read_text())
                self.assertEqual(document["judge"]["verdict"], "OK")
                self.assertTrue(document["source"]["code"].strip())
                self.assertIsNotNone(document["judge"]["metrics"]["time_ms"])
                self.assertIsNotNone(document["judge"]["metrics"]["memory_bytes"])
                for key in ["ip", "slaveHost", "tests", "compileLog", "cookie", "csrf", "source_url"]:
                    self.assertNotIn(key, document["judge"])

    def test_import_selects_first_accepted_in_contest_and_checks_author(self):
        base = {"id": "cup", "contest_id": 103053, "duration_minutes": 180,
                "tasks": [{"id": "task_01", "short": "A"}],
                "teams": [{"id": "winner", "name": "Winner", "yandex_participant_id": 42}]}
        common = {"participant": {"id": 42}, "problem": {"title": "A"}, "verdict": "OK", "status": "FINISHED", "ignoredInMonitor": False}
        rows = [dict(common, id=3, timeFromStart=1000), dict(common, id=2, timeFromStart=500),
                dict(common, id=1, timeFromStart=100, verdict="WrongAnswer")]
        report = {"id": 2, "contestId": 103053, "participantId": 42, "problemAlias": "A", "compilerId": "gcc14_cpp23",
                  "compilerName": "C++23", "status": "finished", "sourceCode": "int main() {}"}
        with TemporaryDirectory() as directory, patch("scripts.import_contest_winners.list_submissions", return_value=iter(rows)), \
                patch("scripts.import_contest_winners.get_submission", return_value={"submissionReport": report, "verdict": "OK"}) as fetch:
            snapshot = import_winners(Mock(), base, sources=Path(directory)/"sources", judgments=Path(directory)/"judgments")
            self.assertEqual(fetch.call_args.args[1], 2)
            self.assertEqual(snapshot["teams"][0]["code_solutions"][0]["submission_id"], 2)


if __name__ == "__main__":
    unittest.main()
