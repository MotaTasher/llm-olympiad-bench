from __future__ import annotations

import unittest

from scripts.deduplicate_evaluations import deduplicate_payload


class DeduplicateEvaluationsTests(unittest.TestCase):
    def test_keeps_latest_named_reviewer_entry_and_refreshes_snapshot(self) -> None:
        payload = {
            "evaluation_pool": {
                "res_a": [
                    {
                        "evaluation_id": "ev_old",
                        "evaluator": "reviewer",
                        "score": 1,
                        "updated_at": "2026-01-01T00:00:00Z",
                    },
                    {
                        "evaluation_id": "ev_new",
                        "evaluator": "reviewer",
                        "score": 2,
                        "updated_at": "2026-01-02T00:00:00Z",
                    },
                    {
                        "evaluation_id": "ev_other",
                        "evaluator": "other",
                        "score": 3,
                        "updated_at": "2026-01-01T00:00:00Z",
                    },
                ]
            },
            "evaluations": {"res_a": {"evaluation_id": "ev_old"}},
        }
        self.assertEqual(deduplicate_payload(payload), 1)
        self.assertEqual(
            [entry["evaluation_id"] for entry in payload["evaluation_pool"]["res_a"]],
            ["ev_other", "ev_new"],
        )
        self.assertEqual(payload["evaluations"]["res_a"]["evaluation_id"], "ev_new")


if __name__ == "__main__":
    unittest.main()
