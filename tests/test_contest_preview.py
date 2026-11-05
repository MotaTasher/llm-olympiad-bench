from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scoring.repository import configured_model_columns
from scripts.export_contest_preview import build_preview

ROOT = Path(__file__).resolve().parents[1]


class ContestPreviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot = json.loads((ROOT / "data/public_results/algo-cup-2026-qualifying.json").read_text())

    def test_official_acm_order_and_scores_are_preserved(self) -> None:
        competition = build_preview(self.snapshot)["competitions"][0]
        teams = [p for p in competition["participants"] if p["type"] == "team"]
        self.assertEqual(competition["contestId"], 103053)
        self.assertEqual([p["name"] for p in teams], ["Чемпионское дерьмо", "Откатили интеллект", "Печень"])
        self.assertEqual([p["penalty"] for p in teams], [99, 130, 141])
        self.assertTrue(all(p["points"] == 4 and p["scores"] == [1, 1, 1, 1] for p in teams))

    def test_every_configured_model_is_empty_without_fabricated_attempts(self) -> None:
        competition = build_preview(self.snapshot)["competitions"][0]
        models = [p for p in competition["participants"] if p["type"] == "model"]
        self.assertEqual(len(models), len(configured_model_columns()))
        for model in models:
            self.assertEqual(model["runStatus"], "not_started")
            self.assertEqual(model["scores"], [None] * 4)
            self.assertEqual(model["solutions"], [None] * 4)
            for key in ("points", "solved", "penalty", "accuracy", "cost", "tokens"):
                self.assertIsNone(model[key], (model["name"], key))

    def test_rejects_scores_or_ranks_that_disagree_with_official_totals(self) -> None:
        invalid = copy.deepcopy(self.snapshot)
        invalid["teams"][0]["scores"][0] = 0
        with self.assertRaises(ValueError):
            build_preview(invalid)
        invalid = copy.deepcopy(self.snapshot)
        invalid["teams"][0]["penalty"] = 200
        with self.assertRaises(ValueError):
            build_preview(invalid)

    def test_checked_in_projection_matches_current_snapshot_and_models(self) -> None:
        content = (ROOT / "public_results/contest-previews.js").read_text()
        published = json.loads(content.removeprefix("window.CONTEST_PREVIEWS = ").strip().removesuffix(";"))
        self.assertEqual(published, build_preview(self.snapshot))


if __name__ == "__main__":
    unittest.main()
