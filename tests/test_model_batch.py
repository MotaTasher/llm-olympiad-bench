from __future__ import annotations

import unittest

from scripts import run_model_batch
from scripts import run_new_models_math_cup_2026_final


class ModelBatchTests(unittest.TestCase):
    def test_all_and_new_expand_to_curated_active_sets(self) -> None:
        self.assertEqual(
            run_model_batch.model_specs("all"),
            [
                "anthropic:claude-opus-4-8",
                "anthropic:claude-haiku-4-5-20251001",
                "deepseek:deepseek-v4-pro",
                "google:gemini-3.1-pro-preview",
                "gigachat:GigaChat-2-Max",
                "xai:grok-4.3",
                "zai:glm-5.2",
                "openai:gpt-5.5",
                "yandexgpt:yandexgpt-5.1",
            ],
        )
        self.assertEqual(
            run_model_batch.model_specs("new"),
            [
                "google:gemini-3.1-pro-preview",
                "xai:grok-4.3",
                "zai:glm-5.2",
            ],
        )

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
