from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.export_public_results import (
    atomic_write_text,
    public_score,
    select_public_attempt,
    solution_document,
    total_tokens,
)


class PublicResultsExportTests(unittest.TestCase):
    def test_prefers_newest_reviewed_success_over_newer_unreviewed_success(self) -> None:
        newest_unreviewed = {
            "successful_answer": True,
            "evaluations": [],
            "result": {"answer": "new"},
        }
        reviewed = {
            "successful_answer": True,
            "evaluations": [{"score": 2, "max_score": 2}],
            "result": {"answer": "reviewed"},
        }
        failed = {
            "successful_answer": False,
            "evaluations": [{"score": 2, "max_score": 2}],
            "result": {"answer": ""},
        }

        selected = select_public_attempt(
            {"attempts": [newest_unreviewed, reviewed, failed]},
        )

        self.assertIs(selected, reviewed)

    def test_falls_back_to_newest_success_when_no_review_exists(self) -> None:
        newest = {
            "successful_answer": True,
            "evaluations": [],
            "result": {"answer": "new"},
        }
        older = {
            "successful_answer": True,
            "evaluations": [],
            "result": {"answer": "old"},
        }
        self.assertIs(select_public_attempt({"attempts": [newest, older]}), newest)

    def test_public_score_is_median_normalized_to_one_hundred(self) -> None:
        attempt = {
            "evaluations": [
                {"score": 1, "max_score": 2},
                {"score": 2, "max_score": 2},
                {"score": 3, "max_score": 4},
            ]
        }
        self.assertEqual(public_score(attempt, 2), 75)

    def test_solution_document_excludes_private_review_fields(self) -> None:
        attempt = {
            "model_key": "openai:gpt-test",
            "result_id": "res_public",
            "run_id": "private-run",
            "result_index": 0,
            "evaluations": [
                {
                    "score": 1,
                    "max_score": 2,
                    "evaluator": "private reviewer",
                    "feedback": "private feedback",
                }
            ],
            "result": {
                "answer": "Model answer",
                "cost_usd": 0.25,
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "latency_ms": 1234,
                "raw_response": {"secret": "not public"},
            },
        }
        document = solution_document(
            competition={
                "competition_id": "cup",
                "competition_title": "Cup",
                "metadata": {"stage": "Final"},
            },
            problem={
                "problem_id": "task",
                "problem_title": "Task",
                "statement": "Statement",
                "solution": "Official solution",
            },
            column={
                "model_key": "openai:gpt-test",
                "model_id": "gpt-test",
                "short_label": "GPT Test",
                "provider": "openai",
                "provider_label": "OpenAI",
            },
            attempt=attempt,
            score=50,
        )
        serialized = str(document)
        self.assertNotIn("private reviewer", serialized)
        self.assertNotIn("private feedback", serialized)
        self.assertNotIn("private-run", serialized)
        self.assertNotIn("raw_response", serialized)
        self.assertEqual(document["result"]["answer"], "Model answer")
        self.assertEqual(document["result"]["tokens"], 30)

    def test_total_tokens_uses_structured_usage_first(self) -> None:
        self.assertEqual(
            total_tokens(
                {
                    "usage": {"total_tokens": 42},
                    "prompt_tokens": 10,
                    "completion_tokens": 20,
                }
            ),
            42,
        )

    def test_atomic_public_files_are_world_readable(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "public.json"
            atomic_write_text(path, "{}\n")
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)


if __name__ == "__main__":
    unittest.main()
