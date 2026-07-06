from __future__ import annotations

import json
import sys
import types
import unittest
from unittest.mock import patch

from models.common import SYSTEM_PROMPT
from models.gemini import GeminiModel
from models.gemini.versions import VERSIONS


class FakeUsage:
    prompt_token_count = 11
    candidates_token_count = 22
    total_token_count = 40
    thoughts_token_count = 7
    cached_content_token_count = 3


class FakeInteraction:
    id = "gemini-interaction-1"
    output_text = "VISIBLE_ANSWER"
    usage_metadata = FakeUsage()

    def model_dump(self) -> dict:
        return {
            "id": self.id,
            "modelVersion": "gemini-resolved",
            "usageMetadata": {
                "promptTokenCount": 11,
                "candidatesTokenCount": 22,
                "totalTokenCount": 40,
                "thoughtsTokenCount": 7,
                "cachedContentTokenCount": 3,
            },
            "finishReason": "STOP",
            "outputText": self.output_text,
            "api_key": "secret",
        }


class FakeInteractions:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeInteraction()


class FakeClient:
    last_client = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.interactions = FakeInteractions()
        FakeClient.last_client = self


class FakeConfig:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class FakeThinkingConfig:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class FakeHttpOptions:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs


class GeminiAdapterTests(unittest.TestCase):
    def fake_google_modules(self):
        fake_types = types.SimpleNamespace(
            ThinkingConfig=FakeThinkingConfig,
            ThinkingLevel=types.SimpleNamespace(HIGH="HIGH", MEDIUM="MEDIUM", LOW="LOW"),
            HttpOptions=FakeHttpOptions,
        )
        fake_genai = types.SimpleNamespace(Client=FakeClient, types=fake_types)
        fake_google = types.SimpleNamespace(genai=fake_genai)
        return patch.dict(
            sys.modules,
            {
                "google": fake_google,
                "google.genai": fake_genai,
                "google.genai.types": fake_types,
            },
        )

    def test_default_override_versions_and_text_only_request(self) -> None:
        self.assertEqual(GeminiModel().model_id, VERSIONS[0])
        self.assertEqual(GeminiModel(VERSIONS[1]).model_id, VERSIONS[1])
        with self.fake_google_modules(), patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            result = GeminiModel("gemini-3.1-pro-preview").solve("problem", max_tokens=123)

        call = FakeClient.last_client.interactions.calls[0]
        self.assertEqual(call["model"], "gemini-3.1-pro-preview")
        self.assertEqual(call["input"], "problem")
        self.assertEqual(call["system_instruction"], SYSTEM_PROMPT)
        self.assertEqual(call["generation_config"]["max_output_tokens"], 123)
        self.assertEqual(call["generation_config"]["temperature"], 0.2)
        self.assertEqual(call["generation_config"]["thinking_level"], "high")
        self.assertTrue(call["store"])
        self.assertNotIn("previous_interaction_id", call)
        self.assertNotIn("tools", json.dumps(result.request).lower())
        self.assertEqual(result.provider, "google")
        self.assertEqual(result.requested_model_id, "gemini-3.1-pro-preview")
        self.assertEqual(result.resolved_model_id, "gemini-resolved")
        self.assertEqual(result.answer, "VISIBLE_ANSWER")
        self.assertEqual(result.usage["reasoning_tokens"], 7)
        self.assertEqual(result.usage["cached_input_tokens"], 3)
        self.assertEqual(result.usage["output_tokens"], 22)
        self.assertEqual(result.raw_response["usage"]["billable_output_tokens"], 29)
        self.assertTrue(result.raw_response["multi_request"]["enabled"] is False)
        self.assertIn("store", result.request)
        self.assertTrue(result.request["store"])
        json.dumps(result.raw_response)
        self.assertEqual(result.raw_response["last_response"]["api_key"], "[REDACTED]")

    def test_total_budget_uses_multiple_interactions(self) -> None:
        class FirstUsage:
            prompt_token_count = 10
            candidates_token_count = 0
            total_token_count = 65536
            thoughts_token_count = 65526
            cached_content_token_count = 0

        class SecondUsage:
            prompt_token_count = 12
            candidates_token_count = 20
            total_token_count = 100
            thoughts_token_count = 68
            cached_content_token_count = 0

        class FirstInteraction:
            id = "first-id"
            output_text = ""
            usage_metadata = FirstUsage()

            def model_dump(self):
                return {
                    "id": self.id,
                    "modelVersion": "gemini-resolved",
                    "usageMetadata": {
                        "promptTokenCount": 10,
                        "candidatesTokenCount": 0,
                        "totalTokenCount": 65536,
                        "thoughtsTokenCount": 65526,
                    },
                    "finishReason": "MAX_TOKENS",
                }

        class SecondInteraction:
            id = "second-id"
            output_text = "FINAL"
            usage_metadata = SecondUsage()

            def model_dump(self):
                return {
                    "id": self.id,
                    "modelVersion": "gemini-resolved",
                    "usageMetadata": {
                        "promptTokenCount": 12,
                        "candidatesTokenCount": 20,
                        "totalTokenCount": 100,
                        "thoughtsTokenCount": 68,
                    },
                    "finishReason": "STOP",
                }

        class MultiInteractions(FakeInteractions):
            def create(self, **kwargs):
                self.calls.append(kwargs)
                return FirstInteraction() if len(self.calls) == 1 else SecondInteraction()

        class MultiClient(FakeClient):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.interactions = MultiInteractions()
                FakeClient.last_client = self

        fake_types = types.SimpleNamespace(
            ThinkingLevel=types.SimpleNamespace(HIGH="HIGH"),
            HttpOptions=FakeHttpOptions,
        )
        fake_genai = types.SimpleNamespace(Client=MultiClient, types=fake_types)
        with patch.dict(sys.modules, {"google": types.SimpleNamespace(genai=fake_genai), "google.genai": fake_genai, "google.genai.types": fake_types}), patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            result = GeminiModel("gemini-3.5-flash").solve("problem", max_tokens=70_000)

        calls = FakeClient.last_client.interactions.calls
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["generation_config"]["max_output_tokens"], 65536)
        self.assertEqual(calls[1]["generation_config"]["max_output_tokens"], 4464)
        self.assertEqual(calls[1]["previous_interaction_id"], "first-id")
        self.assertEqual(result.answer, "FINAL")
        self.assertEqual(result.prompt_tokens, 22)
        self.assertEqual(result.completion_tokens, 20)
        self.assertEqual(result.usage["reasoning_tokens"], 65594)
        self.assertTrue(result.raw_response["multi_request"]["enabled"])
        self.assertEqual(result.raw_response["multi_request"]["requests"], 2)

    def test_provider_exception_and_missing_key_return_error_result(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            missing = GeminiModel("gemini-3.5-flash").solve("problem")
        self.assertTrue(missing.error)
        self.assertEqual(missing.provider, "google")

        class FailingInteractions(FakeInteractions):
            def create(self, **kwargs):
                raise RuntimeError("boom api_key=hidden")

        class FailingClient(FakeClient):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.interactions = FailingInteractions()
                FakeClient.last_client = self

        fake_types = types.SimpleNamespace(
            ThinkingLevel=types.SimpleNamespace(HIGH="HIGH"),
        )
        fake_genai = types.SimpleNamespace(Client=FailingClient, types=fake_types)
        with patch.dict(sys.modules, {"google": types.SimpleNamespace(genai=fake_genai), "google.genai": fake_genai, "google.genai.types": fake_types}), patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            result = GeminiModel("gemini-3.5-flash").solve("problem")
        self.assertTrue(result.error)
        self.assertNotIn("hidden", result.error)


if __name__ == "__main__":
    unittest.main()
