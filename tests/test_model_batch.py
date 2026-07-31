from __future__ import annotations

import unittest

from scripts import run_model_batch
from scripts import run_new_models_math_cup_2026_final


class ModelBatchTests(unittest.TestCase):
    def test_all_and_new_expand_to_curated_active_sets(self) -> None:
        self.assertEqual(
            run_model_batch.model_specs("all"),
            [
                "anthropic:claude-fable-5",
                "anthropic:claude-opus-5",
                "deepseek:deepseek-v4-pro",
                "google:gemini-3.5-flash",
                "gigachat:GigaChat-3-Ultra",
                "xai:grok-4.5",
                "zai:glm-5.2",
                "openai:gpt-5.6-sol",
                "yandexgpt:aliceai-llm",
            ],
        )
        self.assertEqual(
            run_model_batch.model_specs("new"),
            [
                "anthropic:claude-fable-5",
                "anthropic:claude-opus-5",
                "google:gemini-3.5-flash",
                "gigachat:GigaChat-3-Ultra",
                "xai:grok-4.5",
                "openai:gpt-5.6-sol",
                "yandexgpt:aliceai-llm",
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
