from __future__ import annotations

import unittest

from scoring.repository import next_finalization_action


def attempt(result_id: str, **values):
    return {
        "result_id": result_id,
        "successful_answer": True,
        "evaluation_count": 1,
        "finalized": False,
        "review_status": "one_review",
        "comment_required": False,
        "feedback_review_required": False,
        **values,
    }


class FinalizationNavigationTests(unittest.TestCase):
    def test_advances_across_models_before_next_task_and_skips_complete_cells(self) -> None:
        first = attempt("first", finalized=True, review_status="consensus")
        second = attempt("second", feedback_review_required=True, finalized=True)
        complete = attempt("complete", finalized=True, review_status="consensus")
        third = attempt("third", comment_required=True, finalized=True)
        competition = {
            "problem_order": ["task_01", "task_02"],
            "model_columns": [{"model_key": "a"}, {"model_key": "b"}],
            "problems": {
                "task_01": {"model_states": [
                    {"model_key": "a", "attempts": [first]},
                    {"model_key": "b", "attempts": [second]},
                ]},
                "task_02": {"model_states": [
                    {"model_key": "a", "attempts": [complete]},
                    {"model_key": "b", "attempts": [third]},
                ]},
            },
        }

        self.assertEqual(
            next_finalization_action(
                competition,
                current_problem_id="task_01",
                current_result_id="first",
            ),
            ("task_01", second),
        )
        self.assertEqual(
            next_finalization_action(
                competition,
                current_problem_id="task_01",
                current_result_id="second",
            ),
            ("task_02", third),
        )


if __name__ == "__main__":
    unittest.main()
