from __future__ import annotations

import unittest

from scripts.migrate_score_scale import migrate_sidecar, rounded_rescaled_score


class ScoreScaleMigrationTests(unittest.TestCase):
    def test_rescale_uses_half_up_rounding(self) -> None:
        self.assertEqual(rounded_rescaled_score(0.25, 1, 4), 1)
        self.assertEqual(rounded_rescaled_score(0.26, 1, 4), 1)
        self.assertEqual(rounded_rescaled_score(0.5, 1, 4), 2)
        self.assertEqual(rounded_rescaled_score(1, 1, 4), 4)

    def test_sidecar_pool_and_snapshot_are_kept_in_sync(self) -> None:
        evaluation = {
            "score": 0.5,
            "max_score": 1,
            "score_category": "partial",
        }
        payload = {
            "evaluation_pool": {"result": [{**evaluation}]},
            "evaluations": {"result": {**evaluation}},
        }
        self.assertEqual(migrate_sidecar(payload, 4), 1)
        self.assertEqual(payload["evaluation_pool"]["result"][0]["score"], 2)
        self.assertEqual(payload["evaluation_pool"]["result"][0]["max_score"], 4)
        self.assertEqual(payload["evaluations"]["result"]["score"], 2)
        self.assertEqual(payload["evaluations"]["result"]["max_score"], 4)

    def test_migration_is_idempotent(self) -> None:
        payload = {
            "evaluation_pool": {
                "result": [
                    {"score": 3, "max_score": 4, "score_category": "partial"}
                ]
            }
        }
        self.assertEqual(migrate_sidecar(payload, 4), 0)


if __name__ == "__main__":
    unittest.main()
