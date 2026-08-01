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
                "google:gemini-3.1-pro-preview",
                "gigachat:GigaChat-3-Ultra",
                "xai:grok-4.5",
                "zai:glm-5.2",
                "openai:gpt-5.6-sol",
                "yandexgpt:aliceai-llm",
                "kimi:kimi-k3",
            ],
        )
        self.assertEqual(
            run_model_batch.model_specs("new"),
            [
                "anthropic:claude-fable-5",
                "anthropic:claude-opus-5",
                "google:gemini-3.1-pro-preview",
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

    def test_active_models_share_budget_except_documented_api_caps(self) -> None:
        expected_caps = {
            "anthropic:claude-fable-5": 128_000,
            "anthropic:claude-opus-5": 128_000,
            "deepseek:deepseek-v4-pro": 128_000,
            "google:gemini-3.1-pro-preview": 128_000,
            "gigachat:GigaChat-3-Ultra": 8_192,
            "xai:grok-4.5": 128_000,
            "zai:glm-5.2": 128_000,
            "openai:gpt-5.6-sol": 128_000,
            "yandexgpt:aliceai-llm": 8_000,
            "kimi:kimi-k3": 256_000,
        }
        for model, cap in expected_caps.items():
            with self.subTest(model=model):
                self.assertEqual(run_model_batch.cap_for(model, None), cap)


if __name__ == "__main__":
    unittest.main()
