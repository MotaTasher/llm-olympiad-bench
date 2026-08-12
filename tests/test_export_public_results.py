from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.export_public_results import (
    atomic_write_text,
    public_model_slug,
    public_score,
    public_task_slug,
    rewrite_public_markdown,
    select_public_attempt,
    solution_document,
    total_tokens,
)


class PublicResultsExportTests(unittest.TestCase):
    def test_clean_route_slugs_match_public_url_contract(self) -> None:
        self.assertEqual(public_task_slug("task_01"), "task1")
        self.assertEqual(public_task_slug("task-12"), "task12")
        self.assertEqual(
            public_model_slug({"model_id": "gpt-5.6-sol"}),
            "gpt-5.6",
        )
        self.assertEqual(
            public_model_slug({"model_id": "Claude Fable 5"}),
            "claude-fable-5",
        )

    def test_public_markdown_rewrites_assets_and_plain_links(self) -> None:
        rendered = rewrite_public_markdown(
            "![figure](assets/task_09_diagram.png) see `https://arxiv.org/abs/1234`",
            competition_id="math-cup-2026-final",
        )
        self.assertIn(
            "generated/assets/math-cup-2026-final/task_09_diagram.png",
            rendered,
        )
        self.assertIn(
            "[https://arxiv.org/abs/1234](https://arxiv.org/abs/1234)",
            rendered,
        )

    def test_prefers_finalized_success_over_reviewed_and_unreviewed_success(self) -> None:
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
        finalized = {
            "successful_answer": True,
            "evaluations": [{"score": 1, "max_score": 2}],
            "finalization": {"score": 2, "max_score": 2},
            "result": {"answer": "finalized"},
        }
        failed = {
            "successful_answer": False,
            "evaluations": [{"score": 2, "max_score": 2}],
            "result": {"answer": ""},
        }

        selected = select_public_attempt(
            {"attempts": [newest_unreviewed, reviewed, finalized, failed]},
        )

        self.assertIs(selected, finalized)

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

    def test_public_score_uses_only_effective_finalization(self) -> None:
        attempt = {
            "evaluations": [
                {"score": 1, "max_score": 2},
                {"score": 2, "max_score": 2},
                {"score": 3, "max_score": 4},
            ],
            "finalization": {"score": 1, "max_score": 2},
        }
        self.assertEqual(public_score(attempt, 2), 1)
        self.assertEqual(public_score(attempt, 2, round_to_integer=True), 1)
        self.assertIsNone(public_score({"evaluations": attempt["evaluations"]}, 2))

    def test_solution_document_publishes_only_shared_final_review(self) -> None:
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
            "finalization": {
                "score": 1,
                "max_score": 2,
                "feedback": "organizer feedback",
                "updated_by": "private organizer",
            },
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
                "max_score": 2,
            },
            column={
                "model_key": "openai:gpt-test",
                "model_id": "gpt-test",
                "short_label": "GPT Test",
                "provider": "openai",
                "provider_label": "OpenAI",
            },
            attempt=attempt,
            score=1,
        )
        serialized = str(document)
        self.assertNotIn("private reviewer", serialized)
        self.assertNotIn("private feedback", serialized)
        self.assertNotIn("private organizer", serialized)
        self.assertNotIn("private-run", serialized)
        self.assertNotIn("raw_response", serialized)
        self.assertEqual(
            document["review"],
            {"final": {"score": 1, "maxScore": 2, "feedback": "organizer feedback"}},
        )
        self.assertNotIn("experts", document["review"])
        self.assertEqual(document["schemaVersion"], 2)
        self.assertEqual(document["result"]["answer"], "Model answer")
        self.assertEqual(document["result"]["tokens"], 30)
        self.assertEqual(document["task"]["maxScore"], 2)

    def test_unfinalized_solution_is_shown_as_under_review(self) -> None:
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
                "max_score": 2,
            },
            column={
                "model_key": "anthropic:test",
                "model_id": "test",
                "short_label": "Test",
                "provider": "anthropic",
                "provider_label": "Anthropic",
            },
            attempt={
                "model_key": "anthropic:test",
                "result_id": "res_under_review",
                "result": {"answer": "Model answer"},
            },
            score=None,
        )
        self.assertEqual(document["result"]["verdict"], "На проверке")

    def test_gpt_draft_feedback_is_not_published_before_review(self) -> None:
        attempt = {
            "model_key": "openai:gpt-test",
            "result_id": "res_draft",
            "result_index": 0,
            "finalization": {
                "score": 1,
                "max_score": 2,
                "feedback": "Draft that still needs review",
                "feedback_review_required": True,
            },
            "result": {"answer": "Model answer"},
        }
        document = solution_document(
            competition={"competition_id": "cup", "competition_title": "Cup", "metadata": {}},
            problem={"problem_id": "task", "problem_title": "Task", "statement": "S", "solution": "O", "max_score": 2},
            column={"model_key": "openai:gpt-test", "model_id": "gpt-test", "short_label": "GPT Test", "provider": "openai"},
            attempt=attempt,
            score=1,
        )
        self.assertEqual(document["review"]["final"]["feedback"], "")
        self.assertNotIn("Draft that still needs review", str(document))

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
