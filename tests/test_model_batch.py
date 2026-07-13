from __future__ import annotations

import unittest

from scripts import run_model_batch
from scripts import run_new_models_math_cup_2026_final


class ModelBatchTests(unittest.TestCase):
    def test_explicit_total_budget_can_exceed_batch_default(self) -> None:
        model = "zai:glm-5.2"
        self.assertEqual(run_model_batch.cap_for(model, None), 128_000)
        self.assertEqual(run_model_batch.cap_for(model, 256_000), 256_000)
        self.assertEqual(
            run_new_models_math_cup_2026_final.cap_for(model, 256_000),
            256_000,
        )


if __name__ == "__main__":
    unittest.main()
