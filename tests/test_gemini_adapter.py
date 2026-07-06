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


class FakeResponse:
    text = "VISIBLE_ANSWER"
    usage_metadata = FakeUsage()

    def model_dump(self) -> dict:
        return {
            "id": "gemini-resp-1",
            "modelVersion": "gemini-resolved",
            "usageMetadata": {
                "promptTokenCount": 11,
                "candidatesTokenCount": 22,
                "totalTokenCount": 40,
                "thoughtsTokenCount": 7,
                "cachedContentTokenCount": 3,
            },
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {"thought": True, "text": "hidden"},
                            {"text": "VISIBLE_ANSWER"},
                        ]
                    },
                }
            ],
            "api_key": "secret",
        }


class FakeModels:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


class FakeClient:
    last_client = None

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.models = FakeModels()
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
            GenerateContentConfig=FakeConfig,
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

        call = FakeClient.last_client.models.calls[0]
        config = call["config"]
        self.assertEqual(call["model"], "gemini-3.1-pro-preview")
        self.assertEqual(call["contents"], "problem")
        self.assertEqual(config.kwargs["system_instruction"], SYSTEM_PROMPT)
        self.assertEqual(config.kwargs["max_output_tokens"], 123)
        self.assertEqual(config.kwargs["temperature"], 0.2)
        self.assertEqual(config.kwargs["thinking_config"].kwargs["thinking_level"], "HIGH")
        self.assertNotIn("tools", json.dumps(result.request).lower())
        self.assertEqual(result.provider, "google")
        self.assertEqual(result.requested_model_id, "gemini-3.1-pro-preview")
        self.assertEqual(result.resolved_model_id, "gemini-resolved")
        self.assertEqual(result.answer, "VISIBLE_ANSWER")
        self.assertEqual(result.usage["reasoning_tokens"], 7)
        self.assertEqual(result.usage["cached_input_tokens"], 3)
        self.assertIn("store", result.request)
        self.assertFalse(result.request["store"])
        json.dumps(result.raw_response)
        self.assertEqual(result.raw_response["api_key"], "[REDACTED]")

    def test_provider_exception_and_missing_key_return_error_result(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            missing = GeminiModel("gemini-3.5-flash").solve("problem")
        self.assertTrue(missing.error)
        self.assertEqual(missing.provider, "google")

        class FailingModels(FakeModels):
            def generate_content(self, **kwargs):
                raise RuntimeError("boom api_key=hidden")

        class FailingClient(FakeClient):
            def __init__(self, **kwargs) -> None:
                super().__init__(**kwargs)
                self.models = FailingModels()
                FakeClient.last_client = self

        fake_types = types.SimpleNamespace(
            GenerateContentConfig=FakeConfig,
            ThinkingConfig=FakeThinkingConfig,
            ThinkingLevel=types.SimpleNamespace(HIGH="HIGH"),
        )
        fake_genai = types.SimpleNamespace(Client=FailingClient, types=fake_types)
        with patch.dict(sys.modules, {"google": types.SimpleNamespace(genai=fake_genai), "google.genai": fake_genai, "google.genai.types": fake_types}), patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}, clear=True):
            result = GeminiModel("gemini-3.5-flash").solve("problem")
        self.assertTrue(result.error)
        self.assertNotIn("hidden", result.error)


if __name__ == "__main__":
    unittest.main()
